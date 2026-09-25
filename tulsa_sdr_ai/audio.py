import numpy as np
from scipy.signal import butter, decimate, sosfilt

def fm_demodulate(iq,sample_rate,output_rate=16000):
    if len(iq)<2:return np.zeros(0,dtype=np.float32)
    phase=np.angle(iq[1:]*np.conj(iq[:-1])); factor=max(1,int(round(sample_rate/output_rate)))
    audio=decimate(phase,factor,ftype="fir",zero_phase=True)
    sos=butter(4,[250,min(3900,output_rate*.45)],btype="bandpass",fs=output_rate,output="sos")
    audio=sosfilt(sos,audio).astype(np.float32); peak=float(np.max(np.abs(audio))) if audio.size else 0
    return (audio/peak*.9 if peak>1e-8 else audio).astype(np.float32)
