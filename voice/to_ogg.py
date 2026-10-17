#!/usr/bin/env python
"""mp3 -> ogg/opus (формат голосових Telegram): voice/to_ogg.py <вхід> <вихід.ogg>"""
import sys, av

src, dst = sys.argv[1], sys.argv[2]
inp = av.open(src)
out = av.open(dst, "w", format="ogg")
ostream = out.add_stream("libopus", rate=48000, layout="mono")
resampler = av.AudioResampler(format="s16", layout="mono", rate=48000)
for frame in inp.decode(audio=0):
    for rf in resampler.resample(frame):
        for p in ostream.encode(rf):
            out.mux(p)
for rf in resampler.resample(None) or []:
    for p in ostream.encode(rf):
        out.mux(p)
for p in ostream.encode(None):
    out.mux(p)
out.close(); inp.close()
print(dst)
