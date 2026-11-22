# Platform specs and defaults

Platforms change limits often. These values were correct as best known in 2026. If a
limit matters for a decision (length, slide count, hashtags), mention that the user should
confirm it in the app.

## Instagram

| Format | Size | Length / count | Notes |
|---|---|---|---|
| Reel | 1080x1920 (9:16), 30 fps | up to 3 min; most educational Reels work at 15-45 s | cover shows as a 3:4 crop on the profile grid: keep the title in the center 1080x1440 |
| Story | 1080x1920 (9:16) | up to 60 s per video frame | one interactive sticker per set; link sticker for URLs |
| Carousel / post | 1080x1350 (4:5) default; 1080x1440 (3:4) also supported; 1080x1080 | up to 20 slides; 5-10 recommended | first slide is the cover in the feed; grid shows a 3:4 crop |
| Caption | up to 2,200 characters | about 125 characters visible before "more" | keyword early; 3-5 specific hashtags |

**Reel and Story safe zone (1080x1920):** keep text and faces out of roughly the top 250 px
(profile and audio), the bottom 450 px (caption, buttons) and the right 150 px (like and comment icons).
Burned captions default to sitting about 620 px above the bottom edge.

## TikTok

- 1080x1920, 9:16. Videos can be long, but 15-60 s is typical for this kind of content.
- Caption up to 4,000 characters; front-load search keywords; 3-5 hashtags.
- Safe zone similar to Reels, with more UI on the right and bottom.
- Post natively: upload the clean render, not an Instagram download with a watermark. Use TikTok's own sounds or text if wanted.

## YouTube Shorts

- 1080x1920, 9:16, up to 3 minutes.
- Title up to 100 characters (keyword-rich), description optional, `#Shorts` not required.
- The bottom area holds title and channel UI; keep captions above it.

## Email

- Subject 30-50 characters; preview text 40-90 characters.
- Single column; most readers are on mobile; one primary button.

## Audio and video export

- H.264 video, AAC audio 48 kHz, about 8-12 Mbps for 1080x1920, `faststart` for quick playback.
- Loudness around -14 LUFS integrated (`render --loudnorm`).
- Voice clearly above music (music at about -20 dB under the voice).

## Default posting times (starting points only)

Defaults in the brand kit, in the audience's timezone:

| Format | Weekdays | Weekends |
|---|---|---|
| Reel | 18:00 (second slot 12:00) | 11:00 (17:00) |
| Carousel | 12:00 (19:00) | 10:00 (16:00) |
| Story | 08:30 and 20:00 | 10:00 and 19:30 |
| Email | 08:00 | 09:00 |
| TikTok cross-post | 19:00 | 19:00 |
| Shorts cross-post | 17:00 | 17:00 |

These are generic. Once the user shares Instagram Insights' "most active times" or post
results, update `schedule.default_times` in the brand kit and say why.
