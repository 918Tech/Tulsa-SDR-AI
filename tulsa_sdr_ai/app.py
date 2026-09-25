from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from queue import Full, Queue

import numpy as np
import soundfile as sf
from flask import Flask, jsonify, render_template
from flask_socketio import SocketIO
from faster_whisper import WhisperModel

from .audio import fm_demodulate
from .decoders import DMRAdapter, OP25Adapter
from .devices import build_device_plan

try:
    from rtlsdr import RtlSdr
except Exception:
    RtlSdr = None


AUDIO_QUEUE: Queue = Queue(maxsize=32)


def create_app(config_path: str = "config.json"):
    cfg = json.loads(Path(config_path).read_text(encoding="utf-8"))
    rf = cfg["rf"]

    app = Flask(__name__, template_folder="../templates")
    socketio = SocketIO(app, async_mode="threading", cors_allowed_origins="*")

    model = WhisperModel(
        cfg["whisper"]["model"],
        device=cfg["whisper"].get("device", "cpu"),
        compute_type=cfg["whisper"].get("compute_type", "int8"),
    )

    runtime = Path("runtime")
    audio_root = runtime / "audio"
    decoder_root = runtime / "decoder"
    audio_root.mkdir(parents=True, exist_ok=True)
    decoder_root.mkdir(parents=True, exist_ok=True)
    events_path = runtime / "events.jsonl"

    state = {"devices": [], "events": [], "markers": {}, "decoder_metadata": {}}
    lock = threading.RLock()

    @app.get("/")
    def root():
        return render_template("index.html")

    @app.get("/api/state")
    def api_state():
        with lock:
            return jsonify(state)

    @socketio.on("connect")
    def on_connect():
        with lock:
            socketio.emit("state", state)

    def publish_event(item: dict, text: str = "", event_type: str = "audio") -> None:
        tgid = item.get("talkgroup")
        tg = cfg.get("talkgroups", {}).get(str(tgid), {}) if tgid is not None else {}
        event = {
            "time": time.time(),
            "type": event_type,
            "source": item.get("source"),
            "mode": item.get("mode"),
            "frequency_hz": item.get("frequency"),
            "talkgroup": tgid,
            "tag": tg.get("tag", ""),
            "text": text,
            "encrypted": bool(item.get("encrypted", False)),
        }

        with events_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, ensure_ascii=False) + "\n")

        with lock:
            state["events"] = (state["events"] + [event])[-200:]
            if tgid is not None and "location" in tg:
                # This is a configured service-area/label point, not caller GPS.
                state["markers"][str(tgid)] = {
                    "location": tg["location"],
                    "tag": tg.get("tag", ""),
                    "last_seen": event["time"],
                }

        socketio.emit("radio_event", event)
        socketio.emit("state", state)

    def decoder_metadata(source: str, frequency: float, mode: str, tgid: int, raw: str) -> None:
        now = time.time()
        with lock:
            state["decoder_metadata"][source] = {
                "talkgroup": tgid,
                "frequency": frequency,
                "mode": mode,
                "time": now,
                "raw": raw[-500:],
            }
        publish_event(
            {
                "source": source,
                "frequency": frequency,
                "mode": mode,
                "talkgroup": tgid,
            },
            raw,
            "decoder_metadata",
        )

    def active_tgid(source: str):
        hold = float(cfg["decoder"].get("metadata_hold_seconds", 4.0))
        with lock:
            meta = state["decoder_metadata"].get(source)
            if meta and time.time() - meta["time"] <= hold:
                return meta["talkgroup"]
        return None

    def enqueue_audio(item: dict) -> None:
        try:
            AUDIO_QUEUE.put(item, timeout=0.1)
        except Full:
            # Preserve real-time behavior: stale audio is less useful than blocking RF capture.
            pass

    def transcriber() -> None:
        while True:
            item = AUDIO_QUEUE.get()
            try:
                if item.get("encrypted"):
                    continue
                audio = np.asarray(item["audio"], dtype=np.float32)
                if not audio.size or float(np.max(np.abs(audio))) < 1e-6:
                    continue

                tgid = item.get("talkgroup")
                if tgid is None:
                    tgid = active_tgid(item["source"])
                    item["talkgroup"] = tgid

                segments, _ = model.transcribe(
                    audio,
                    beam_size=3,
                    vad_filter=True,
                    language="en",
                )
                text = " ".join(s.text.strip() for s in segments).strip()
                if not text:
                    continue

                if tgid is not None:
                    folder = audio_root / str(tgid)
                    folder.mkdir(parents=True, exist_ok=True)
                    stamp = str(int(time.time() * 1000))
                    sf.write(folder / f"{stamp}.wav", audio, int(rf["audio_rate"]))

                publish_event(item, text, "transcript")
            finally:
                AUDIO_QUEUE.task_done()

    def analog_or_virtual_worker(item: dict) -> None:
        frequency = float(item["frequency"])
        serial = item["serial"]
        block = int(rf["sample_rate"] * cfg["virtual_dongles"].get("seconds_per_block", 1.0))

        if item["kind"] == "virtual":
            device = item["device"]
            while True:
                audio = fm_demodulate(
                    device.read_samples(block),
                    rf["sample_rate"],
                    rf["audio_rate"],
                )
                enqueue_audio({
                    "audio": audio,
                    "source": serial,
                    "frequency": frequency,
                    "mode": "virtual",
                    "talkgroup": active_tgid(serial),
                })
                time.sleep(cfg["virtual_dongles"].get("seconds_per_block", 1.0))
            return

        if RtlSdr is None:
            return

        device = RtlSdr(item["index"])
        try:
            device.sample_rate = rf["sample_rate"]
            device.center_freq = frequency
            device.gain = rf["gain_db"]
            device.freq_correction = rf.get("ppm", 0)
            while True:
                audio = fm_demodulate(
                    device.read_samples(block),
                    rf["sample_rate"],
                    rf["audio_rate"],
                )
                enqueue_audio({
                    "audio": audio,
                    "source": serial,
                    "frequency": frequency,
                    "mode": "analog",
                    "talkgroup": active_tgid(serial),
                })
        finally:
            device.close()

    def digital_worker(item: dict, mode: str) -> None:
        serial = item["serial"]
        frequency = float(item["frequency"])

        callback = lambda tg, raw: decoder_metadata(serial, frequency, mode, tg, raw)

        if mode == "p25":
            adapter = OP25Adapter(
                cfg["decoder"]["op25_rx_path"],
                cfg["decoder"].get("op25_python", "python3"),
            )
            proc = adapter.start(
                serial,
                frequency,
                "trunk.tsv",
                callback,
                sample_rate=int(rf["sample_rate"]),
            )
        elif mode == "dmr":
            adapter = DMRAdapter(cfg["decoder"].get("dmr_command", []))
            proc = adapter.start(
                serial=serial,
                frequency_hz=frequency,
                on_talkgroup=callback,
            )
        else:
            analog_or_virtual_worker(item)
            return

        proc.wait()

    def start() -> None:
        entries = [
            x for x in cfg["frequencies"]
            if rf["min_hz"] <= float(x["hz"]) <= rf["max_hz"]
        ]
        plan = build_device_plan(
            [float(x["hz"]) for x in entries],
            cfg["virtual_dongles"].get("enabled", True),
            cfg["virtual_dongles"].get("seed", 918),
        )

        for item, entry in zip(plan, entries):
            item["configured_mode"] = entry.get("mode", cfg["decoder"].get("mode", "auto"))

        with lock:
            state["devices"] = [
                {k: v for k, v in item.items() if k != "device"}
                for item in plan
            ]

        threading.Thread(target=transcriber, daemon=True).start()

        for item in plan:
            if item["kind"] == "unassigned":
                continue
            mode = item.get("configured_mode", "auto")
            # Synthetic sources always exercise the local pipeline. Real P25/DMR
            # sources are handed exclusively to the corresponding native decoder.
            if item["kind"] == "virtual":
                target = analog_or_virtual_worker
                args = (item,)
            elif mode in {"p25", "dmr"}:
                target = digital_worker
                args = (item, mode)
            else:
                target = analog_or_virtual_worker
                args = (item,)
            threading.Thread(target=target, args=args, daemon=True).start()

    return app, socketio, start
