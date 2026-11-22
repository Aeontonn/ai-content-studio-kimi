# Example: repurposing one video (expected output)

**Input:** `examples/sample-transcript.srt`, a 66-second talking-head video for the
fictional brand Calm Habits (`examples/sample-brand-profile.md`).
**Request:** "Turn this video into reels, a carousel, stories and a newsletter."
This is the shape and quality bar of a repurposing answer.

---

## Source summary

**Core idea:** Morning routines fail by design, not because of laziness: they're copied,
too long, and they start too late.

**Key points**
1. You copied someone else's routine: start with one habit that fits your actual morning.
2. You made it too long: keep a 10-minute version for bad days.
3. It starts the night before: pick a phone-down time and protect it.

**Best lines (timestamps)**
- "It's probably not because you're lazy." (00:04)
- "If your routine needs ninety minutes, it will die the first time you oversleep." (00:31)
- "Pick a phone-down time and protect it like a meeting." (00:54)
- "Make it yours, make it short, and start the night before." (00:59)

**Clip candidates:** 00:27.7-00:39.8 (reason two, stands alone) · 00:41.6-00:57.4
(reason three) · 00:04.2-00:22.4 (setup and reason one, needs the retake at 00:11 removed).

**Fixes before reuse:** cut the "Um, so" before the hook (00:01.4), the false start
"Reason one is, uh, you copied" (00:11.2-00:13.5) and 6 pauses over 1 s.

---

## Reels (3)

### Reel 1: "It will die the first time you oversleep"
- **Clip:** 00:27.7-00:39.8 (12 s), cut the "Basically" and "Um" (review by ear)
- **Hook (spoken):** "If your routine needs ninety minutes, it will die the first time you oversleep."
  Reorder: open on 00:31.3, then 00:27.7 "Reason two: you made it way too long."
- **On-screen:** "your routine is too long"
- **Beats:** 0-3 s hook line · 3-6 s "you made it way too long" (punch-in) · 6-12 s "keep a ten-minute version for bad days" + text "the 10-min version"
- **Caption:** If your routine needs 90 minutes, it will die the first time you oversleep.
  Keep a 10-minute version for bad days: the non-negotiable one. What's in yours?
- **CTA:** Comment your 10-minute version
- **TikTok:** "if your morning routine needs 90 minutes it's not a routine, it's a wish #morningroutine #habits"
- **Shorts title:** "Why long morning routines always fail"

### Reel 2: "Your routine starts the night before"
- **Clip:** 00:41.6-00:57.4 (16 s), cut "So you know," (00:53.7)
- **Hook (spoken):** "And reason three, which nobody talks about: your routine starts the night before."
  Trim to "Nobody talks about this: your routine starts the night before." if re-recording is possible.
- **On-screen:** "it starts the night before"
- **Caption:** Your morning routine doesn't start when the alarm goes off. It starts when you put your phone down.
  Pick a phone-down time and protect it like a meeting. What time is yours?
- **CTA:** Send this to your scrolling-until-1-a.m. friend
- **Shorts title:** "The morning routine tip nobody talks about"

### Reel 3: re-film, POV format
- **Concept:** "POV: you copied a CEO's 5 a.m. routine" (day 1 energetic, day 3 snoozing, day 5 back to chaos), then the creator to camera: "Start with one thing that already fits *your* morning."
- **Hook:** visual: alarm at 05:00 and a groan. On-screen "POV: you copied someone's 5 a.m. routine"
- **Beats:** 0-3 s alarm · 3-8 s day 1 montage · 8-12 s day 3 snooze · 12-15 s day 5 chaos · 15-25 s the fix to camera
- **CTA:** Follow for routines that survive real life

---

## Carousel (8 slides), rendered

Spec: `examples/sample-carousel.json`. Rendered with `carousel.py render ... --pptx`
to `slide-01.png` ... `slide-08.png`, `carousel.pptx`, `overview.png`.

1. **Cover:** Your routine isn't failing because you're **lazy** / 3 reasons it keeps falling apart, and the fix for each
2. The 5 a.m. alarm. The cold plunge. The journal. / And by Thursday it's gone. Again.
3. 1. You copied **someone else's** routine / Start with one habit that already fits the morning you actually have.
4. 2. You made it **way too long** / A 90-minute routine dies the first time you oversleep.
5. 3. It starts **the night before** / Pick a phone-down time and protect it like a meeting.
6. **Recap:** Make it yours · Make it short · Start the night before
7. **Quote:** "A routine you can do on your worst day beats a perfect one you skip."
8. **CTA:** Save this for tomorrow morning / Which ONE habit would you keep? / Follow for calm habits

**Alt text:** Eight-slide carousel on three reasons morning routines fail and the fix for each.

---

## Story sequence (5 frames)
1. Kitchen, dark window. "Quick one: did your routine survive this week?" · poll: Yes / Barely / What routine
2. "Most routines die for 3 reasons. None of them is laziness."
3. "1. copied · 2. too long · 3. starts at the alarm, not the night before"
4. Reshare of Reel 1 · sticker: "watch the full thing"
5. "What's your phone-down time?" · question box

---

## Email newsletter

**Subject options:** "It's not laziness" · "Why your routine dies on day 3"
**Preview text:** Three design flaws, and the 10-minute fix I use on bad days.

> Hi,
>
> On day three of my "perfect" morning routine, I overslept by 40 minutes. The whole thing (journal, stretching, the cold shower I hated) was gone before 8 a.m. I almost decided I'm just not a morning person.
>
> But it wasn't me. It was the design. Most routines fail for three reasons:
>
> **They're copied.** Someone else's 5 a.m. doesn't fit your kids, your commute or your body clock. Start with one thing that already fits your real morning.
>
> **They're too long.** If it needs 90 minutes, it dies the first time you oversleep. Keep a 10-minute version for bad days: that's the one that counts.
>
> **They start too late.** Your morning starts the night before. Pick a phone-down time and protect it like a meeting.
>
> This week, try just one: write your 10-minute version on a sticky note and put it by the kettle.
>
> **[Get the free 10-minute morning guide]**
>
> P.S. Hit reply and tell me your phone-down time. I read every reply.

---

## Alternative hooks (for testing)
| Type | Hook |
|---|---|
| Contrarian | "Stop blaming yourself for your failed morning routine." |
| Question | "Why does every routine you start die by Thursday?" |
| Specific | "A 90-minute routine dies the first time you oversleep." |
| Curiosity | "The part of your morning routine nobody talks about happens at night." |
| Identity | "If you're 'not a morning person', this is for you." |
| Story | "On day three of my perfect routine, I overslept by 40 minutes." |
| List | "3 reasons your morning routine keeps failing" |
| Myth | "You don't need more discipline. You need a shorter routine." |

## Alternative captions
- **Short:** Your morning routine isn't failing because you're lazy. It's failing because it's too long. Save this.
- **Medium (value list):** It's not laziness. It's design: 1) it's copied, 2) it's too long, 3) it starts at the alarm instead of the night before. Fix one this week. Which one is yours?
- **Long (story):** Day 3 of my "perfect" routine I overslept by 40 minutes and almost quit... (opens like the email, ends with "Make it yours, make it short, start the night before. Save this for tomorrow.")

## Suggested schedule (week 2026-W48 plan)
Tue 18:00 original reel · Wed 08:30 Story sequence · Wed 12:00 carousel · Thu 08:00 email ·
next week: Reel 1 (Tue) and Reel 2 (Sat) as clips · Reel 3 when there's filming time.
