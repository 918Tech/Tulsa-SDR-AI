import re, subprocess, threading
from pathlib import Path

class OP25Adapter:
    patterns=[re.compile(r"(?:tgid|talkgroup|grpaddr)[^0-9]{0,8}(\\d+)",re.I),re.compile(r"\\bTG(?:ID)?[=: ]+(\\d+)\\b",re.I)]
    def __init__(self,rx_path,python_exe="python3"): self.rx_path=Path(rx_path); self.python_exe=python_exe
    def start(self,serial,frequency_hz,trunk_tsv,on_talkgroup,log_dir="runtime/decoder"):
        if not self.rx_path.exists(): raise FileNotFoundError(f"OP25 rx.py not found: {self.rx_path}")
        Path(log_dir).mkdir(parents=True,exist_ok=True); log=Path(log_dir)/f"op25-{serial}.log"
        cmd=[self.python_exe,str(self.rx_path),"--args",f"rtl={serial}","-S","2048000","-f",str(int(frequency_hz)),"-T",str(Path(trunk_tsv).resolve()),"-V","-2"]
        p=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,bufsize=1)
        def parse():
            with log.open("a") as fh:
                for line in p.stderr:
                    fh.write(line); fh.flush()
                    for pat in self.patterns:
                        m=pat.search(line)
                        if m:on_talkgroup(int(m.group(1)),line.strip());break
        threading.Thread(target=parse,daemon=True).start(); return p

class DMRAdapter:
    pattern=re.compile(r"(?:tg|talkgroup|group)[^0-9]{0,8}(\\d+)",re.I)
    def __init__(self,command_template):self.command_template=command_template
    def build_command(self,input_path,output_path):return [x.format(input=input_path,output=output_path) for x in self.command_template]
    def parse_line(self,line):
        m=self.pattern.search(line); return int(m.group(1)) if m else None
