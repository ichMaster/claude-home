# Bot avatars — Zirka and Bruno (Nano Banana 2)

Two Telegram bots carry the automatic broadcasts: **Zirka** speaks the morning horoscope
in Зоря's voice, **Bruno** reads the digest's news and the YouTube picks in his own.
Both avatars share the ink language of `noos-icon-prompt.md` — solid black masses, bare
white paper, highlights carved out as angular white slashes — so the three chats read as
one set in the chat list. Each bot gets exactly **one accent colour** and nothing else:
amber for Zirka, cyan for Bruno. That single spot of colour is what separates them at
64 pixels, where a face does not resolve at all.

Telegram crops avatars to a circle, so everything that matters stays inside the middle
square and nothing important touches a corner.

## Zirka — the horoscope

A high-contrast black-and-white ink illustration in the style of 1980s manga ink art: no
greys, no gradients, no halftone — only solid black masses and bare white paper, with
highlights carved out of the black as sharp angular white slashes. Subject: a young
woman of about thirty seen close up in three-quarter view, head tilted slightly back as
if reading the sky, filling most of the square frame. Her expression is awake and amused
— a half-smile, one eyebrow a touch higher than the other, eyes bright with two white
catchlights each. Short wavy hair rendered as one bold black shape, its ends breaking
apart into small five-pointed stars that scatter up and out of the frame. Behind her
head, filling the background, is a flat black disc of night sky with a thin white
ecliptic line crossing it and a sparse scatter of white points; a single large eight-ray
star sits just off-centre behind her temple, its rays cutting white channels through the
black. One accent colour only, warm amber (#E8A33D), used for that one large star and
for a thin line along the ecliptic — everything else stays pure black and white.
Composition bold and symmetrical enough to read as an icon at small size: heavy black
silhouette, generous white space, clean sticker-like edge, nothing important in the
corners. No text, no shading, ink only.

## Bruno — the news and the videos

A high-contrast black-and-white ink illustration in the style of 1980s manga ink art: no
greys, no gradients, no halftone — only solid black masses and bare white paper, with
highlights carved out of the black as sharp angular white slashes. Subject: a man of
about thirty-five seen close up in three-quarter view, chin level, looking straight out
of the frame with the steady attention of someone about to speak on air. Short dark hair
and a few days of stubble as flat black shapes; a slight asymmetric set to the mouth,
the look of someone who finds the news interesting rather than grave. Large studio
headphones around his neck, drawn as two bold black cups with white rim highlights, the
coiled cable running down out of frame. Behind his head, filling the background, is the
face of a mixing desk flattened into pattern: a row of vertical faders, a horizontal
ventilation grille, and one circular VU meter whose needle sits just past centre, all in
the same flat ink language. Thin white lines run across the black panel like scratches
in the paint. One accent colour only, cold cyan (#3DC8E8), used for the VU meter's arc
and a single lit fader cap — everything else stays pure black and white. Composition
bold and symmetrical enough to read as an icon at small size: heavy black silhouette,
generous white space, clean sticker-like edge, nothing important in the corners. No
text, no shading, ink only.

## Alternative: no colour at all

Both prompts with the accent-colour sentence removed — pure black and white, matching
`noos-icon-prompt.md` exactly. A stricter set, and the two bots then differ only by
subject: stars against a mixing desk. Worth it if the three avatars sitting next to each
other matter more than telling Zirka from Bruno at a glance.

## Alternative: pixel art

A 64×64 pixel-art portrait, hard pixel edges, no anti-aliasing, a palette of six colours
at most. Zirka: amber and cream on deep indigo, a star in the upper left. Bruno: cyan and
grey on near-black, headphone cups as two solid blocks. Reads cleanly at any size by
construction, and closer to the retro-computing side of the house — but it drops the ink
language the rest of the set is built on.

## Notes for generation

- Ask for a square 1:1 image and crop nothing: Telegram does the circle itself.
- Check each result at 64 pixels before accepting it. If the face turns to mush and only
  the accent colour survives, that is the version to keep — in a chat list that colour
  is the whole signal.
- Avoid putting a star or a needle exactly in a corner; the circular crop eats it.
