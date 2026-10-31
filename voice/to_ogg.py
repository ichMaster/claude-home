#!/usr/bin/env python
"""mp3 -> ogg/opus (the Telegram voice format): voice/to_ogg.py <in> <out.ogg> [tempo]

`tempo` speeds the result up without changing pitch (libavfilter `atempo`). It exists
because **the `speed` voice setting is ignored by the tag-performing models**: measured on
2026-10-27, `eleven_multilingual_v2` goes 5.34 s → 3.81 s between speed 1.0 and 1.2, while
`eleven_v3` and `eleven_v4_turbo` return the same 5.28 s at every speed from 1.0 to 1.5. So
the emotional voice is sped up here instead, after synthesis.

`atempo` itself only accepts 0.5–2.0 per stage; larger factors are chained.
"""
import sys

import av
import av.filter

src, dst = sys.argv[1], sys.argv[2]
tempo = float(sys.argv[3]) if len(sys.argv) > 3 else 1.0

inp = av.open(src)
istream = inp.streams.audio[0]
out = av.open(dst, "w", format="ogg")
ostream = out.add_stream("libopus", rate=48000, layout="mono")
resampler = av.AudioResampler(format="s16", layout="mono", rate=48000)

graph = None
if abs(tempo - 1.0) > 0.01:
    graph = av.filter.Graph()
    nodes = [graph.add_abuffer(template=istream)]
    rest = tempo
    while abs(rest - 1.0) > 0.01:                 # atempo takes 0.5–2.0, so chain if needed
        step = max(0.5, min(2.0, rest))
        nodes.append(graph.add("atempo", f"{step:.4f}"))
        rest /= step
    nodes.append(graph.add("abuffersink"))
    for a, b in zip(nodes, nodes[1:]):
        a.link_to(b)
    graph.configure()


def emit(frame):
    for rf in resampler.resample(frame):
        for p in ostream.encode(rf):
            out.mux(p)


def through_graph(frame):
    """Push one frame through atempo and yield whatever comes out; the filter buffers, so a
    frame in is not a frame out."""
    if frame is not None:
        graph.push(frame)
    else:
        graph.push(None)
    while True:
        try:
            yield graph.pull()
        except (av.BlockingIOError, av.EOFError):
            return


for frame in inp.decode(audio=0):
    if graph is None:
        emit(frame)
    else:
        for f in through_graph(frame):
            emit(f)

if graph is not None:
    for f in through_graph(None):
        emit(f)

for rf in resampler.resample(None) or []:
    for p in ostream.encode(rf):
        out.mux(p)
for p in ostream.encode(None):
    out.mux(p)
out.close(); inp.close()
print(dst)
