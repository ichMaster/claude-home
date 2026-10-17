#!/usr/bin/env python
"""Pad silence at both ends: voice/pad.py <in> <out.ogg> [seconds]

Deepgram eats the first word when speech starts at second zero, and Telegram often
delivers exactly such clipped recordings.
"""
import sys, numpy as np, av
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from noosconf import conf, path

src, dst = sys.argv[1], sys.argv[2]
sec = float(sys.argv[3]) if len(sys.argv) > 3 else 0.6
SR = conf("voice.sample_rate", 48000)

c = av.open(src)
rs = av.AudioResampler(format="fltp", layout="mono", rate=SR)
ch = []
for fr in c.decode(audio=0):
    for r in rs.resample(fr):
        ch.append(r.to_ndarray().reshape(-1))
c.close()
x = np.concatenate(ch) if ch else np.zeros(0, dtype="float32")
pad = np.zeros(int(SR * sec), dtype="float32")
y = np.concatenate([pad, x, pad]).astype("float32")

out = av.open(dst, "w", format="ogg")
st = out.add_stream("libopus", rate=SR, layout="mono")
rs2 = av.AudioResampler(format="s16", layout="mono", rate=SR)
for i in range(0, len(y), 960):
    fr = av.AudioFrame.from_ndarray(y[i:i + 960].reshape(1, -1), format="fltp", layout="mono")
    fr.sample_rate = SR
    for r in rs2.resample(fr):
        for p in st.encode(r):
            out.mux(p)
for p in st.encode(None):
    out.mux(p)
out.close()
print(dst)
