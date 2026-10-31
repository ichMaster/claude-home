#!/usr/bin/env python
"""Resolve a voice profile into environment assignments for `voice/el_say.sh`.

    eval-free use:  while IFS= read -r l; do export "$l"; done < <(voice_profile.py mood)

A profile (`voice.profiles.<name>` in config) names a voice from `voice.voices` and the
settings that voice needs; a role (`voice.roles.<kind>`) names a profile. Both are looked
up here so no shell script has to know the shape of the config.

Audio tags only work on the v3/v4 models — `eleven_multilingual_v2` reads them out as
words (measured, `docs/voice-emotion.md`), so a profile that wants tags must pin a model.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from noosconf import conf

name = sys.argv[1] if len(sys.argv) > 1 else ""
# a role name resolves to a profile; a profile name is used as it is
profile = conf(f"voice.roles.{name}") or name
p = conf(f"voice.profiles.{profile}") or {}
if not p:
    sys.exit(0)                                   # unknown profile: leave the default voice alone

voice_id = conf(f"voice.voices.{p.get('voice', '')}") or p.get("voice_id", "")
out = {}
if voice_id:
    out["ELEVENLABS_VOICE_ID"] = voice_id
if p.get("model"):
    out["ELEVENLABS_MODEL"] = p["model"]
if p.get("stability") is not None:
    out["ELEVENLABS_STABILITY"] = p["stability"]
if p.get("speed") is not None:
    out["ELEVENLABS_SPEED"] = p["speed"]
if p.get("style") is not None:
    out["ELEVENLABS_STYLE"] = p["style"]
if p.get("tempo") is not None:
    # not an ElevenLabs setting: applied after synthesis, because v3/v4 ignore `speed`
    out["NOOS_TEMPO"] = p["tempo"]
for k, v in out.items():
    print(f"{k}={v}")
