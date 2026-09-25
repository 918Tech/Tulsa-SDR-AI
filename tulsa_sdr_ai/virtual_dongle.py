from dataclasses import dataclass
import numpy as np

@dataclass
class VirtualDongle:
    index: int
    serial: str
    center_freq: float
    sample_rate: float = 2048000.0
    seed: int = 918
    def __post_init__(self): self.rng=np.random.default_rng(self.seed+self.index)
    def read_samples(self,count):
        n=np.arange(count,dtype=np.float64); audio=np.sin(2*np.pi*1000*n/self.sample_rate)
        phase=np.cumsum(2*np.pi*2500*audio/self.sample_rate)
        noise=.02*(self.rng.standard_normal(count)+1j*self.rng.standard_normal(count))
        return (np.exp(1j*phase)+noise).astype(np.complex64)
    def close(self): pass

def seed_virtual_dongles(count,frequencies,seed=918):
    return [VirtualDongle(i,f"VRTL-{i:03d}",frequencies[i%len(frequencies)] if frequencies else 0,seed=seed) for i in range(count)]
