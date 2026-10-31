# Emotion in voice — findings and proposed changes

Written 2026-10-21, after an empirical session on ElevenLabs audio tags. Everything
below was measured on this machine with the real account, not taken from the docs; where
the docs and the measurement disagree, the measurement is recorded as the truth.

## 1. What was measured

**Audio tags are square-bracket directions inside the text** (`[laughs]`, `[whispers]`,
`[surprised]`). Whether they are rendered or read out loud depends entirely on the model.

| model | tags | evidence |
|---|---|---|
| `eleven_multilingual_v2` | **read aloud as words** | input `[смішок] Ага, звісно. [laughs] Я так і думав` → heard back «Смішок. Ага, звісно, лавс. Я так і думав» |
| `eleven_v3` | rendered | same input → «Ха-ха, ага, звісно» |
| `eleven_v3_conversational` | rendered | «Ха-ха-ха, а, звісно» |
| `eleven_v4` | rendered | «Ха-ха-ха, звісно» |
| `eleven_v4_turbo` | rendered | «Ха-ха-ха, звісно» |

Method: synthesize, then recognize with Deepgram `nova-3` and look for the tag as a word.
A tag that survives into the transcript was spoken; a tag that disappears was performed.

Three more facts from the same session:

- **Ukrainian tags work like English ones.** `[смішок]`, `[зітхає]`, `[шепоче]`,
  `[радісно]` all disappeared from the transcript and changed the delivery.
- **Undocumented tags are swallowed, not spoken.** `[deep belly laugh]` and `[hesitant]`
  are not in the documented vocabulary; neither was read aloud, and both altered pacing.
  So inventing a tag is safe — the worst case is that it does nothing.
- **The documentation contradicts itself.** The model table claims tags work only in
  `v4_turbo` and `v3_conversational`; the v4 prompting guide documents tags for
  `eleven_v4`. In practice all four rendered them. Trust the test.

## 2. Tags do change the delivery — measured, not assumed

Deepgram does not transcribe laughter reliably, so two numbers were used instead.

**Duration per 100 characters of speech** (tags stripped before counting), Kira's voice:
plain speech sits at ~11 s; a laughter ladder (`[starts laughing] … [laughs] …
[laughs harder] … [wheezing]`) comes out at 15.8 s, and `[deep belly laugh]` at 15.4 s.
Those extra ~4 seconds are breath, wheeze and laughter the recognizer cannot spell.

**Loudness envelope** (RMS over 5-second windows, the 63-second story): 0.16 through the
surprised and laughing part, 0.05 through `[thoughtful]` → `[sighs]`, 0.008 in the final
`[whispers]` — a threefold drop and then near-silence. The recognizer dropped the
whispered tail entirely, which is itself the proof that it was whispered.

## 3. The recipe that the owner picked by ear

Seven laughter variants were generated on one voice and judged by listening. The winner:

```
model_id: eleven_v4_turbo
voice_settings: stability 0.3, similarity_boost 0.75, speed 1.0
```

1. **A ladder, not a single tag.** `[starts laughing] …` → `[laughs] …` →
   `[laughs harder] …` → `[wheezing] …`, spread over three or four short clauses.
   Laughter needs a run-up; a lone `[laughs]` only puts a smile in the voice.
2. **The tag goes before the clause it governs**, so long sentences must be chopped:
   «Я стояла з термосом… / З термосом, розумієш! / Як пані на екскурсії.»
3. **For a sustained emotion, repeat the same tag**: `[chuckles] … [chuckles] …`.
4. **Do not spell laughter out** («ха-ха-ха») when a ladder is present. Spelled-out
   laughter is the only thing the recognizer hears for certain, but by ear it sounds
   clownish next to the ladder.
5. **Quiet endings work:** `[thoughtful]` → `[sighs]` → `[whispers]`.

## 4. Proposed changes

### 4.1 Applied already

- **`voice/el_say.sh`: `ELEVENLABS_MODEL` is now overridable from the environment.**
  The script sourced `.env.voice` *after* saving the overrides and kept only voice, speed
  and stability, so the file's `eleven_multilingual_v2` always won and the model could
  not be changed from outside at all. This cost one spoiled take, where the tags were
  read out loud. The environment now wins, consistently with the other three variables.
  Rollback: drop the `om=` line and the `[ -n "$om" ]` line.

### 4.2 For this repository (Noos)

- **Switching the default model — declined by the owner, 2026-10-21.** The proposal was
  `ELEVENLABS_MODEL=eleven_v4_turbo` in `.env.voice`; the answer was that the current
  HAL-UA voice on `eleven_multilingual_v2` fits and stays as it is. Consequence to hold
  on to: tags remain unavailable to Noos, so any bracketed text in his replies would be
  read out loud. If the render layer of section 6 ever reaches this repository, it must
  strip tags for Noos unconditionally rather than pass them through.
- **Transliterate foreign words before synthesis.** Latin script mangles: `literally`
  came out as «лitterрal й», `anyway` was dropped outright, and `Ich` became «їх». Write
  «літерально», «енівей», «Іх». This belongs next to the existing rule about avoiding
  Latin script in text meant for voice.

### 4.3 For Agora

- **Pin the model per agent.** No model is set anywhere in `matrix-agora` — not in
  `.env`, not in `docker-compose.yml`, not in code (`api.elevenlabs.io` does not appear
  in the repository at all; each agent synthesizes on its own). Until `eleven_v4_turbo`
  is set explicitly, tags in agent lines will be read aloud. Cheapest form: add
  `ELEVENLABS_MODEL=eleven_v4_turbo` to `server/voice.env`, which every speaking agent
  already loads.
- **Calibrate each voice with a shot test.** All nine agent voices are
  `category: generated` (Voice Design), not clones of a living person, so a tag only
  lands if that delivery exists in the voice's data. Procedure: one short line per voice
  with a laughter ladder and a sigh, then listen and keep the tags that work per voice.
  Kira's ladder is confirmed; the other eight are untested.

### 4.4 The emotion layer itself (the part that matters more than tags)

Tags are the output format. The model of emotion should sit behind them:

- **Do not let the model pick a tag or an emoji directly.** It overacts, and the emotion
  resets every turn.
- **Keep a small state** that persists between turns and decays towards a baseline —
  two or three numbers are enough: valence, arousal, fatigue.
- **Split generation from rendering.** The agent writes only text; a separate render
  layer turns the state into tags plus `voice_settings` (stability, speed, style).
- **Budget one or two tags per reply**, placed before the clause they affect. Punctuation
  and sentence length carry more emotion than tag count does.

### 4.5 Character-driven voice

A canon file is a voice specification, not only a personality. Kira's canon
(`agents/canon/kira.md`) yields concrete speech features: a loud laugh audible two rooms
away (so the ladder fits her, and the ladder is exactly what won by ear), unnoticed
russisms («на протязі», «вірно», «якби»), Edinburgh anglicisms, cosmic scale in every
other sentence, kintsugi as her way of seeing broken things. Hesitancy is rendered with
`[hesitant]`, `[thoughtful]`, ellipses and self-interruptions — not with a tag alone.

Proposal: when a persona gets a voice, derive its tag palette and its verbal tics from
the canon in the same pass, and store them next to the voice id.

## 5. Costs and limits

- All models cost 1x per character except Flash v2.5 (0.5x). Switching to v4_turbo does
  not change the bill.
- The ElevenLabs account is shared with the other agents, so quota is read from the
  provider (`status/tools/voice_api.py`), not from the local log.
- This session's experiments consumed a few thousand characters — negligible against the
  200k monthly budget per Agora speaker.

## 6. Concept: the emotion channel, end to end

This section is the implementable part — written for whoever builds it in Agora, not for
this repository. It assumes section 3's recipe and section 1's model table as given.

### 6.1 One pass, not two

**The agent writes the tags itself, inline, in its own reply.** No second LLM pass to
"add emotion".

Why: tags are ordinary text, so a model needs nothing but a palette in its system
prompt; and whoever places a tag must know the intent behind the sentence. A second pass
sees only words and cannot tell irony from sincerity. The author of the line is the best
director of the line.

Cost argument: one pass adds zero latency and zero tokens. A director pass adds roughly a
second and a few hundred tokens to **every** reply, and Agora has nine speakers in one
room.

A second pass is justified in exactly two cases:

- **Foreign text with no author present** — a digest, a news item, a book chapter read
  aloud. There is no intent to preserve, so a director can invent one.
- **An agent that systematically overacts.** Then the second pass is a censor, not a
  director: it removes surplus tags and never adds new ones.

### 6.2 The contract: one reply, three outputs

**One generation, one string, three renderings.** The model is called once and returns
a single text with tags inside it. Nothing is generated twice: the room text is derived
from that same string by code — a regular expression, no LLM — and the synthesis text is
that string unchanged. "Three outputs" means three views of one reply, not three replies.

The reply leaves the agent once and is rendered three ways:

```
reply (with tags)
   ├─ room text      tags removed, emotion re-rendered for the eye (6.3)
   ├─ synthesis text tags left exactly as written
   └─ voice_settings derived from the emotional state, never from the model (6.5)
```

The reader must never see a bracket; the listener must never hear one. In Agora the same
line goes out as both text and audio, so this split is not optional.

### 6.3 Rendering the text channel

Two devices, each for a different kind of tag.

**Inside the reply — italics, describing what is happening to the speaker.** Not an
emoji: an emote. It reads as a person in a chat rather than a bot with stickers, and
Matrix renders italics natively.

```
[starts laughing] А я з термосом... [laughs] з термосом стою!
→  *починає сміятися* А я з термосом... з термосом стою!
```

**At the end of the reply — at most one emoji**, placed after the final sentence. An
emoji at the start reads as a label for the whole line; at the end it reads as the tone
it was left in.

**Collapse by family.** A ladder of four laughter tags is one mark, not four. First match
in a family wins, the rest are dropped.

| family | tags | inline emote | end-of-reply emoji |
|---|---|---|---|
| laughter | `[laughs]` `[laughs harder]` `[starts laughing]` `[wheezing]` | *сміється* | 😂 |
| amusement | `[chuckles]` `[snorts]` | *усміхається* | 🙂 |
| sadness | `[sighs]` `[exhales]` `[crying]` | *зітхає* | 😔 |
| surprise | `[surprised]` | *здивовано* | 😮 |
| thought | `[curious]` `[thoughtful]` | *задумливо* | 🤔 |
| delivery | `[whispers]` `[shouts]` | *шепоче* | — |
| hesitation | `[hesitant]` | — | — |

Two rules behind the table:

- **Delivery is typography, not pictures.** A whisper is better served by italics or a
  quieter line than by an emoji of a finger at the lips.
- **Hesitation needs no mark at all.** The ellipses and self-interruptions are already in
  the words; adding a sign to them is redundant.

### 6.4 Parsing

```python
import re

TAG = re.compile(r"\[([^\]\n]{1,40})\]")
# the documented vocabulary that carries no emote of its own, plus anything in FAMILY
EXTRA = {"happy", "sad", "excited", "angry", "annoyed", "appalled", "sarcastic",
         "mischievously", "applause", "clapping", "gunshot", "explosion", "sings",
         "swallows", "gulps", "clears throat"}
WORDS = re.compile(r"^[a-zа-яїєґ][a-zа-яїєґ \-']+$")    # multi-word bodies: an invented tag

FAMILY = {                      # tag → family
    "laughs": "laughter", "laughs harder": "laughter",
    "starts laughing": "laughter", "wheezing": "laughter",
    "chuckles": "amusement", "snorts": "amusement",
    "sighs": "sadness", "exhales": "sadness", "crying": "sadness",
    "surprised": "surprise",
    "curious": "thought", "thoughtful": "thought",
    "whispers": "delivery", "shouts": "delivery",
    "hesitant": "hesitation",
}

EMOTE = {"laughter": "сміється", "amusement": "усміхається",
         "sadness": "зітхає", "surprise": "здивовано",
         "thought": "задумливо", "delivery": "шепоче"}

EMOJI = {"laughter": "\U0001F602", "amusement": "\U0001F642",
         "sadness": "\U0001F614", "surprise": "\U0001F62E",
         "thought": "\U0001F914"}        # delivery and hesitation get no emoji


def render(reply: str) -> tuple[str, str]:
    """(room text, synthesis text) from one tagged reply."""
    seen, out, tail, pos = set(), [], None, 0
    for m in TAG.finditer(reply):
        body = m.group(1).strip().lower()
        out.append(reply[pos:m.start()])
        pos = m.end()
        fam = FAMILY.get(body)
        if fam is None:
            invented = " " in body and WORDS.match(body)
            if body not in EXTRA and not invented:
                out.append(m.group(0))       # "[1]", "arr[i]", "[ОСТРІВ 3]" — keep it
            continue                         # a tag with no emote: strip, the voice still performs it
        if fam in seen:
            continue                         # collapse: one mark per family
        seen.add(fam)
        if EMOTE.get(fam):
            out.append(f"*{EMOTE[fam]}* ")
        tail = EMOJI.get(fam, tail)          # the last emotional family wins the tail
    out.append(reply[pos:])
    room = re.sub(r"[ \t]{2,}", " ", "".join(out))
    room = "\n".join(line.strip() for line in room.splitlines()).strip()
    if tail:
        room = f"{room} {tail}"
    return room, reply                       # synthesis gets the original, untouched
```

Edge cases worth handling explicitly:

- **An unknown tag** (`[deep belly laugh]`, `[hesitant]` before it was added to the map)
  must be stripped from the room text and left in the synthesis text. Measured fact:
  undocumented tags are performed, not read aloud, so passing them through is safe.
- **A bracket that is not a tag** — a citation, a code sample, `[1]` — must survive into
  the room text. The length bound in the regex and the family lookup handle the common
  cases; anything unmatched should be left alone rather than deleted.
- **A line that goes out as text only** (no voice that turn) should still be stripped,
  never published raw.
- **The emoji budget is one per reply.** If several emotional families fire, the last one
  wins the tail: it is the tone the line was left in.

The sketch above was run against these inputs; this is its actual output, not an
intention:

| in | out (room text) |
|---|---|
| `Дивись [1] і [deep belly laugh] ось так. [laughs] Ха.` | `Дивись [1] і ось так. *сміється* Ха. 😂` |
| `Код: arr[i] = 3 і [ОСТРІВ 3]` | `Код: arr[i] = 3 і [ОСТРІВ 3]` |
| `[excited] Є! [applause] Вітаю. [sighs] Хоча...` | `Є! Вітаю. *зітхає* Хоча... 😔` |
| `[whispers] тихо. [laughs] [laughs harder] ха!` | `*шепоче* тихо. *сміється* ха! 😂` |

Note the asymmetry in row three: `[excited]` and `[applause]` are performed by the voice
but carry no emote, so they vanish from the text while `[sighs]` leaves a mark. That is
deliberate — the text channel shows what the reader would otherwise lose, not everything
the listener gets.

### 6.5 Voice settings come from state, not from the model

The model chooses tags. It does not choose `stability`, `speed`, or the model id — those
are a deterministic function of the emotional state, which persists between turns and
decays towards a baseline:

```
arousal > 0.7                → stability 0.2, speed 1.05
baseline                     → stability 0.3, speed 1.00
fatigue > 0.6 or low valence → stability 0.5, speed 0.95
```

Keep the state small — valence, arousal, fatigue is enough — and keep it in code. An LLM
asked to pick its own stability will drift; a decaying state gives a character a mood that
outlives a single reply, which is the thing emoji in a text channel can never do.

### 6.6 What the agent's system prompt needs

Three short blocks, no more:

1. **A palette of five to seven tags already verified on that agent's voice** — not the
   full vocabulary. Kira's verified set: `[starts laughing]`, `[laughs]`,
   `[laughs harder]`, `[wheezing]`, `[chuckles]`, `[surprised]`, `[thoughtful]`,
   `[hesitant]`, `[whispers]`.
2. **The budget and placement rule:** one or two tags per reply; a tag goes before the
   clause it governs; laughter uses the ladder and needs short clauses to climb.
3. **A warning about Latin script:** foreign words must be written in Cyrillic
   («літерально», «енівей», «Іх»), because the synthesizer mangles or drops Latin —
   measured in section 4.2.

Everything else — collapsing, emoji, italics, voice settings — belongs to the render
layer, where it can be changed without touching nine prompts.


## 7. Addendum, 2026-10-27 — speed, pauses and the Ада profile

Measured on this machine, Ада's voice, same method as section 1 (synthesize, measure the
duration, recognize and look for the tag as a word).

**`speed` is ignored by the tag-performing models.** On `eleven_multilingual_v2` the same
line runs 5.34 s at speed 1.0 and 3.81 s at 1.2 — the setting works. On `eleven_v3` and
`eleven_v4_turbo` it returns 5.28–5.52 s at every speed from 1.0 to 1.5: no error, no
effect. So a voice that performs tags cannot be sped up through the API at all.

The fix is post-synthesis: `voice/to_ogg.py` takes a third argument, a tempo factor, and
applies libavfilter's `atempo` (pitch preserved, factors above 2.0 chained). 5.47 s → 4.21 s
at 1.3, exactly the ratio asked for. Profiles carry it as `tempo`; `voice_profile.py`
exports it as `NOOS_TEMPO`, and both `notify.sh` and `voice/reply.sh` pass it through.

**Pauses are tags, not markup.** `[довга пауза]` and `[пауза]` give real silence — a line
with two of them ran 9.04 s against 6.08 s plain — and neither reaches the transcript.
`<break time="1.5s" />`, the documented v2 syntax, does nothing on v4_turbo: 6.16 s against
6.08 s. Section headings are therefore separated by a pause tag plus `[без емоцій]` on the
heading itself, which is what makes the structure audible.

**Intonation comes from the settings, not from more tags.** `style` was hardcoded to 0.0 in
`voice/el_say.sh`, so every voice read flat no matter what the tags said; it is now
`ELEVENLABS_STYLE`, and the forecast profile runs style 0.45 with stability 0.2 — low
stability widens the swing between sentences.

The Ада profile as it stands: `eleven_v4_turbo`, stability 0.2, style 0.45, speed 1.0
(inert), tempo 1.3, tags on.
