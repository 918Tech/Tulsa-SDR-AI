try:
    from rtlsdr import RtlSdr
except Exception:
    RtlSdr=None
from .virtual_dongle import VirtualDongle

def detect_physical_sdrs(limit=16):
    out=[]
    if RtlSdr is None:return out
    for i in range(limit):
        s=None
        try:
            s=RtlSdr(i); out.append({"index":i,"serial":str(s.get_serial()),"kind":"physical"})
        except Exception: break
        finally:
            if s:
                try:s.close()
                except Exception:pass
    return out

def build_device_plan(freqs,virtual_enabled=True,seed=918):
    physical=detect_physical_sdrs(); plan=[]
    for i,f in enumerate(freqs):
        if i<len(physical): plan.append({**physical[i],"frequency":f})
        elif virtual_enabled:
            v=VirtualDongle(i-len(physical),f"VRTL-{i-len(physical):03d}",f,seed=seed+i)
            plan.append({"index":v.index,"serial":v.serial,"kind":"virtual","frequency":f,"device":v})
        else: plan.append({"index":-1,"serial":"","kind":"unassigned","frequency":f})
    return plan
