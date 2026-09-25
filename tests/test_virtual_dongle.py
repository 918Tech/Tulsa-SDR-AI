import numpy as np
from tulsa_sdr_ai.virtual_dongle import VirtualDongle
from tulsa_sdr_ai.audio import fm_demodulate

def test_virtual_iq():
    d=VirtualDongle(0,"VRTL-000",856112500,sample_rate=256000,seed=918); iq=d.read_samples(4096)
    assert iq.shape==(4096,) and np.iscomplexobj(iq) and np.isfinite(iq).all()

def test_demod():
    d=VirtualDongle(0,"VRTL-000",856112500,sample_rate=256000,seed=918); a=fm_demodulate(d.read_samples(256000),256000,16000)
    assert a.size>0 and np.isfinite(a).all()
