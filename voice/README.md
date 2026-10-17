# The claude-home voice stack

Ready to reuse — this is what the matrix-agora agents should take.
Keys: `~/claude-home/.env.voice` (mode 600) — ElevenLabs + Deepgram.
Virtualenv: `~/claude-home/.venv-voice`.

## Synthesis (text to speech)

```bash
./voice/reply.sh "text" out.ogg           # one step: ElevenLabs -> ogg/opus
./voice/el_say.sh out.mp3 "text"          # synthesis only
.venv-voice/bin/python voice/to_ogg.py in.mp3 out.ogg
```

Tunable through env: `ELEVENLABS_VOICE_ID`, `ELEVENLABS_SPEED` (0.7-1.2),
`ELEVENLABS_STABILITY`, `NOOS_MUFFLE` (light|medium|heavy).
Noos's voice is **HAL-UA**; its id lives in `.env.voice` (`ELEVENLABS_VOICE_ID`).
Muffling (`voice/muffle.py`) is **off** by default: the clean voice sounds better.

## Recognition (speech to text)

```bash
./voice/dg_stt.sh file.oga uk             # Deepgram nova-3, ~1 s per 15 s of audio
./voice/el_stt.sh file.oga ukr            # fallback, ElevenLabs Scribe
```

`nova-2` mangles Ukrainian proper nouns — do not use it.

## What to know when giving agents a voice in Matrix

1. **A separate `voice_id` per agent**, otherwise Kit, Bruno and Ada all sound the same.
   Set voices in the agent config, not in code.
2. **The Matrix event**: `m.audio` with `org.matrix.msc3245.voice: {}` and a `waveform`
   in `org.matrix.msc1767.audio`. Without those fields Element shows an attached file
   rather than a voice bubble.
3. **Format**: ogg/opus, mono. `to_ogg.py` already produces it.
4. **Send the text too.** A rule proven in practice: voice without a text duplicate is
   awkward — you can neither quote it nor correct what was misheard.
5. **What not to speak**: links, emoji, list markers, Latin script and abbreviations.
   Ready-made cleanup lives in `notify.sh` (a regex before synthesis) and
   `status/uk_num.py` (numbers spelled out in Ukrainian).
6. **Length**: ElevenLabs accepts long text, but nobody listens to a voice message over
   ~2 minutes. Split by paragraph or send a short version.

## Where this already runs

- `notify.sh --voice` — sends text and voice to Telegram through the Bot API
- `status/digest-headless.sh` — the 08:03 and 20:03 digest, voice via sendVoice
- the main Noos session — Telegram replies as voice plus text
