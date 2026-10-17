#!/usr/bin/env python
"""Muffle the voice as if it came through a ventilation grille.

  voice/muffle.py <in.mp3> <out.ogg> [light|medium|heavy]

Three things: roll off the top end (voice behind a panel), add a short boxy room
echo, and mix in a steady fan hum.
"""
import sys, numpy as np, av
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from noosconf import conf, path

PRESETS = {           # зріз, порядок фільтра, рівень шуму (dBFS), гул
    "light":  (4500, 2, -36, 0.5),
    "medium": (3200, 3, -30, 1.0),
    "heavy":  (2200, 4, -25, 1.6),
}
SR = conf("voice.sample_rate", 48000)

def decode(path):
    c = av.open(path)
    rs = av.AudioResampler(format="fltp", layout="mono", rate=SR)
    chunks = []
    for fr in c.decode(audio=0):
        for r in rs.resample(fr):
            chunks.append(r.to_ndarray().reshape(-1))
    c.close()
    return np.concatenate(chunks).astype(np.float64)

def spectral(x, fc, order, kind="low"):
    """Frequency-domain filter: 1/(1+(f/fc)^2)^(order/2).

    The length is padded to a power of two: numpy computes that transform an order
    of magnitude faster than an arbitrary length, and circular convolution wrap-around
    disappears as a side effect.
    """
    n = len(x)
    N = 1 << int(np.ceil(np.log2(n + 1)))
    f = np.fft.rfftfreq(N, 1 / SR)
    r = (f / fc) ** 2
    h = (1 / (1 + r)) ** (order / 2) if kind == "low" else (r / (1 + r)) ** (order / 2)
    return np.fft.irfft(np.fft.rfft(x.astype(np.float32), N) * h, N)[:n]

def encode(x, path):
    x = np.clip(x / max(1e-9, np.abs(x).max()) * 0.9, -1, 1).astype(np.float32)
    out = av.open(path, "w", format="ogg")
    st = out.add_stream("libopus", rate=SR, layout="mono")
    rs = av.AudioResampler(format="s16", layout="mono", rate=SR)
    step = 960
    for i in range(0, len(x), step):
        fr = av.AudioFrame.from_ndarray(x[i:i + step].reshape(1, -1), format="fltp", layout="mono")
        fr.sample_rate = SR
        for r in rs.resample(fr):
            for p in st.encode(r):
                out.mux(p)
    for p in st.encode(None):
        out.mux(p)
    out.close()

src, dst = sys.argv[1], sys.argv[2]
fc, order, noise_db, hum = PRESETS[sys.argv[3] if len(sys.argv) > 3 else "medium"]

v = decode(src)
v = spectral(v, 120, 2, "high")      # прибрати низ, як у дрібного динаміка
v = spectral(v, fc, order, "low")    # власне приглушення

# short boxy echo of a ventilation shaft
wet = np.zeros_like(v)
for delay_ms, gain in ((11, 0.28), (23, 0.16), (37, 0.08)):
    d = int(SR * delay_ms / 1000)
    wet[d:] += v[:-d] * gain
v = v + spectral(wet, fc * 0.8, 2, "low")

# fan hum: broad low-frequency noise plus a 100 Hz tone
rng = np.random.default_rng(7)
bed = spectral(rng.standard_normal(len(v)), 450, 3, "low")
bed /= max(1e-9, np.abs(bed).max())
t = np.arange(len(v)) / SR
bed += hum * 0.35 * (np.sin(2 * np.pi * 100 * t) + 0.4 * np.sin(2 * np.pi * 200 * t))
bed *= 10 ** (noise_db / 20) / max(1e-9, np.abs(bed).max()) * 1.0

mix = np.tanh((v / max(1e-9, np.abs(v).max()) * 0.85) + bed)
encode(mix, dst)
print(dst)
