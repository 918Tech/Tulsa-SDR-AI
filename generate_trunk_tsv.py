import csv,json
from pathlib import Path

def generate_trunk_tsv(config_path="config.json",output_path="trunk.tsv"):
    cfg=json.loads(Path(config_path).read_text()); controls=[int(x["hz"]) for x in cfg["frequencies"] if x.get("role")=="control"]
    if not controls:raise ValueError("No control frequencies configured")
    with Path(output_path).open("w",newline="") as f:
        w=csv.writer(f,delimiter="\t"); w.writerow(["Sysname","Control Channel List","Offset","NAC","Modulation","TGID Tags File","Whitelist","Blacklist","Center Frequency"])
        w.writerow(["Tulsa",",".join(map(str,controls)),"0","0","CQPSK","","","",str(controls[0])])
if __name__=="__main__":generate_trunk_tsv();print("Wrote trunk.tsv")
