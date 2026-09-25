import json,threading,time
from pathlib import Path
from queue import Queue
import numpy as np
from flask import Flask,jsonify
from flask_socketio import SocketIO
from faster_whisper import WhisperModel
from .audio import fm_demodulate
from .devices import build_device_plan

try:
    from rtlsdr import RtlSdr
except Exception:
    RtlSdr=None

AUDIO_QUEUE=Queue(maxsize=32)

def create_app(config_path="config.json"):
    cfg=json.loads(Path(config_path).read_text()); rf=cfg["rf"]
    app=Flask(__name__); socketio=SocketIO(app,async_mode="threading",cors_allowed_origins="*")
    model=WhisperModel(cfg["whisper"]["model"],device=cfg["whisper"].get("device","cpu"),compute_type=cfg["whisper"].get("compute_type","int8"))
    runtime=Path("runtime");runtime.mkdir(exist_ok=True);events_path=runtime/"events.jsonl"
    state={"devices":[],"events":[]};lock=threading.Lock()

    @app.get("/")
    def root():return jsonify({"service":"Tulsa SDR AI","devices":state["devices"],"events":state["events"][-20:]})
    @app.get("/api/state")
    def api_state():return jsonify(state)

    def publish(item,text):
        tgid=item.get("talkgroup"); tag=cfg.get("talkgroups",{}).get(str(tgid),{}).get("tag","") if tgid else ""
        ev={"time":time.time(),"source":item["source"],"frequency_hz":item["frequency"],"talkgroup":tgid,"tag":tag,"text":text}
        with events_path.open("a") as f:f.write(json.dumps(ev)+"\n")
        with lock:state["events"]=(state["events"]+[ev])[-100:]
        socketio.emit("radio_event",ev)

    def transcriber():
        while True:
            item=AUDIO_QUEUE.get()
            try:
                audio=np.asarray(item["audio"],dtype=np.float32)
                if not audio.size or float(np.max(np.abs(audio)))<1e-6:continue
                segments,_=model.transcribe(audio,beam_size=3,vad_filter=True,language="en")
                text=" ".join(s.text.strip() for s in segments).strip()
                if text:publish(item,text)
            finally:AUDIO_QUEUE.task_done()

    def source_worker(item):
        f=float(item["frequency"]); serial=item["serial"]; block=int(rf["sample_rate"]*cfg["virtual_dongles"].get("seconds_per_block",1))
        if item["kind"]=="virtual":
            d=item["device"]
            while True:
                audio=fm_demodulate(d.read_samples(block),rf["sample_rate"],rf["audio_rate"])
                AUDIO_QUEUE.put({"audio":audio,"source":serial,"frequency":f,"talkgroup":None});time.sleep(cfg["virtual_dongles"].get("seconds_per_block",1))
        elif item["kind"]=="physical" and RtlSdr:
            d=RtlSdr(item["index"])
            try:
                d.sample_rate=rf["sample_rate"];d.center_freq=f;d.gain=rf["gain_db"];d.freq_correction=rf.get("ppm",0)
                while True:AUDIO_QUEUE.put({"audio":fm_demodulate(d.read_samples(block),rf["sample_rate"],rf["audio_rate"]),"source":serial,"frequency":f,"talkgroup":None})
            finally:d.close()

    def start():
        freqs=[float(x["hz"]) for x in cfg["frequencies"] if rf["min_hz"]<=float(x["hz"])<=rf["max_hz"]]
        plan=build_device_plan(freqs,cfg["virtual_dongles"].get("enabled",True),cfg["virtual_dongles"].get("seed",918))
        state["devices"]=[{k:v for k,v in x.items() if k!="device"} for x in plan]
        threading.Thread(target=transcriber,daemon=True).start()
        for item in plan:
            if item["kind"]!="unassigned":threading.Thread(target=source_worker,args=(item,),daemon=True).start()
    return app,socketio,start
