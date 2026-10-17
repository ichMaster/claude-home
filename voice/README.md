# Голосовий стек claude-home

Готовий до перевикористання — саме його варто взяти агентам matrix-agora.
Ключі: `~/claude-home/.env.voice` (права 600) — ElevenLabs + Deepgram.
Venv: `~/claude-home/.venv-voice`.

## Синтез (текст → голос)

```bash
./voice/reply.sh "текст" out.ogg          # один крок: ElevenLabs → ogg/opus
./voice/el_say.sh out.mp3 "текст"         # лише синтез
.venv-voice/bin/python voice/to_ogg.py in.mp3 out.ogg
```

Налаштування через env: `ELEVENLABS_VOICE_ID`, `ELEVENLABS_SPEED` (0.7-1.2),
`ELEVENLABS_STABILITY`, `NOOS_MUFFLE` (light|medium|heavy).
Голос Нооса — **HAL-UA**, id у `.env.voice` (`ELEVENLABS_VOICE_ID`). Приглушення (`voice/muffle.py`)
за замовчуванням **вимкнене**: чистий голос звучить краще.

## Розпізнавання (голос → текст)

```bash
./voice/dg_stt.sh file.oga uk             # Deepgram nova-3, ~1 с на 15 с аудіо
./voice/el_stt.sh file.oga ukr            # запасний шлях, ElevenLabs Scribe
```

`nova-2` на українській плутає власні назви — не брати.

## Що знати, роблячи голос агентам у Matrix

1. **Кожному агенту свій `voice_id`**, інакше Kit, Bruno й Ada звучать однаково.
   Голоси задавати в конфігу агента, не в коді.
2. **Matrix-подія**: `m.audio` з `org.matrix.msc3245.voice: {}` і `waveform`
   в `org.matrix.msc1767.audio`. Без цих полів Element показує вкладений файл,
   а не голосову бульбашку.
3. **Формат**: ogg/opus, моно. `to_ogg.py` уже дає потрібне.
4. **Текст теж надсилати.** Правило, перевірене на практиці: голос без дубля
   текстом незручний — не можна ні процитувати, ні виправити розпізнане.
5. **Що не озвучувати**: посилання, емодзі, маркери списків, латиницю та
   скорочення. Готова чистка — у `notify.sh` (regex перед синтезом) і в
   `status/uk_num.py` (числа словами українською).
6. **Довжина**: ElevenLabs бере великий текст, але голосове понад ~2 хв ніхто
   не слухає. Різати на абзаци або давати стислу версію.

## Де це вже працює

- `notify.sh --голос` — надсилання в Telegram текстом і голосом через Bot API
- `status/digest-headless.sh` — дайджест о 08:03 і 20:03, голос через sendVoice
- основна сесія Нооса — відповіді в Telegram голосом + текстом
