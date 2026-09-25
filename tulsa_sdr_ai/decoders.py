from __future__ import annotations

import re
import subprocess
import threading
from pathlib import Path
from typing import Callable, Optional


TalkgroupCallback = Callable[[int, str], None]


class OP25Adapter:
    """Launch OP25 and emit talkgroup IDs parsed from decoder metadata.

    OP25 owns the RTL-SDR while this adapter is active. The Python RTL reader
    must not open the same dongle concurrently.
    """

    patterns = [
        re.compile(r"(?:tgid|talkgroup|grpaddr)[^0-9]{0,8}(\d+)", re.I),
        re.compile(r"\bTG(?:ID)?[=: ]+(\d+)\b", re.I),
    ]

    def __init__(self, rx_path: str, python_exe: str = "python3") -> None:
        self.rx_path = Path(rx_path)
        self.python_exe = python_exe

    def start(
        self,
        serial: str,
        frequency_hz: float,
        trunk_tsv: str,
        on_talkgroup: TalkgroupCallback,
        sample_rate: int = 2_048_000,
        log_dir: str = "runtime/decoder",
    ) -> subprocess.Popen:
        if not self.rx_path.exists():
            raise FileNotFoundError(f"OP25 rx.py not found: {self.rx_path}")

        Path(log_dir).mkdir(parents=True, exist_ok=True)
        log_path = Path(log_dir) / f"op25-{serial}.log"

        cmd = [
            self.python_exe,
            str(self.rx_path),
            "--args",
            f"rtl={serial}",
            "-S",
            str(sample_rate),
            "-f",
            str(int(frequency_hz)),
            "-T",
            str(Path(trunk_tsv).resolve()),
            "-V",
            "-2",
        ]

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

        def parse_stream(stream, prefix: str) -> None:
            if stream is None:
                return
            with log_path.open("a", encoding="utf-8") as fh:
                for line in stream:
                    fh.write(f"[{prefix}] {line}")
                    fh.flush()
                    for pat in self.patterns:
                        match = pat.search(line)
                        if match:
                            on_talkgroup(int(match.group(1)), line.strip())
                            break

        threading.Thread(target=parse_stream, args=(proc.stderr, "stderr"), daemon=True).start()
        threading.Thread(target=parse_stream, args=(proc.stdout, "stdout"), daemon=True).start()
        return proc


class DMRAdapter:
    """Generic DMR decoder subprocess wrapper.

    The command comes from config.json. Metadata is parsed from stdout/stderr,
    so dsdcc, dsd-fme, or another compatible decoder can be used without
    coupling the application to a single distribution.
    """

    patterns = [
        re.compile(r"(?:tgid|talkgroup|group|target)[^0-9]{0,8}(\d+)", re.I),
        re.compile(r"\bTG(?:ID)?[=: ]+(\d+)\b", re.I),
    ]

    def __init__(self, command_template: list[str]) -> None:
        self.command_template = command_template

    def build_command(
        self,
        *,
        serial: str,
        frequency_hz: float,
        input_path: str = "",
        output_path: str = "",
    ) -> list[str]:
        values = {
            "serial": serial,
            "frequency": int(frequency_hz),
            "input": input_path,
            "output": output_path,
        }
        return [part.format(**values) for part in self.command_template]

    def parse_line(self, line: str) -> Optional[int]:
        for pat in self.patterns:
            match = pat.search(line)
            if match:
                return int(match.group(1))
        return None

    def start(
        self,
        *,
        serial: str,
        frequency_hz: float,
        on_talkgroup: TalkgroupCallback,
        input_path: str = "",
        output_path: str = "",
        log_dir: str = "runtime/decoder",
    ) -> subprocess.Popen:
        if not self.command_template:
            raise ValueError("DMR command template is empty")

        Path(log_dir).mkdir(parents=True, exist_ok=True)
        log_path = Path(log_dir) / f"dmr-{serial}.log"
        cmd = self.build_command(
            serial=serial,
            frequency_hz=frequency_hz,
            input_path=input_path,
            output_path=output_path,
        )

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

        def parse_stream(stream, prefix: str) -> None:
            if stream is None:
                return
            with log_path.open("a", encoding="utf-8") as fh:
                for line in stream:
                    fh.write(f"[{prefix}] {line}")
                    fh.flush()
                    tgid = self.parse_line(line)
                    if tgid is not None:
                        on_talkgroup(tgid, line.strip())

        threading.Thread(target=parse_stream, args=(proc.stdout, "stdout"), daemon=True).start()
        threading.Thread(target=parse_stream, args=(proc.stderr, "stderr"), daemon=True).start()
        return proc
