# Brand memory and content library

The studio remembers who the brand is and what has already been made. Two layers:

| Layer | Files | Changes | Purpose |
|---|---|---|---|
| Identity | `brand/brand-profile.md`, `brand/brand-kit.json`, `brand/fonts/`, `brand/assets/` | Rarely | Voice, audience, pillars, colors, fonts, logo |
| Library | `library.json`, `weeks/*.json`, `media/` | Every week | Items planned and published, idea backlog, footage index, results, learnings |

Both live in the **workspace** folder (default `./content-studio`, or `$CONTENT_STUDIO_DIR`).

## Contents
1. Onboarding interview (English and Chinese)
2. Writing the profile and brand kit
3. Keeping memory between sessions in Kimi
4. Library operations
5. Results and learnings

---

## 1. Onboarding interview

Run it when `library.py status` says the profile is not configured, or when the user asks to
set up or change their brand. Goal: a specific, usable profile in about five minutes. Ask in
**three short rounds**, in the user's language, not as one long form. Offer examples so
answering is easy, and accept "skip" / "跳过" for anything.

**Round 1: who and for whom**
1. What's your name or brand name, and your Instagram handle?
2. In one sentence: who do you help (or entertain), and with what?
3. Describe your ideal follower: age range, situation, what they struggle with, what they want.
4. Which language for captions, and for on-screen text? Which timezone is your audience in?

**Round 2: goals and voice**
5. What should content achieve in the next 3 months (followers, newsletter sign-ups, sales, bookings, brand deals)? Any offers, links or launches coming up?
6. Pick 3 words for how you want to sound. Anything you never want to sound like?
7. Paste one or two captions you're proud of (or describe a creator whose *tone* you like).
8. What 3-5 topics could you talk about forever? (These become content pillars.)

**Round 3: look and practicalities** (needed before carousels and calendar colors)
9. Brand colors as hex codes (or describe them and I'll propose a palette). Fonts, if any.
10. What footage can you realistically make each week? Talking to camera, voice-over B-roll, tutorials? Where, and how much time?
11. Anything off-limits: topics, showing family or home, claims you can't make?

**中文版问题（用户用中文交流时使用）**

第一轮：你是谁，为谁创作
1. 你的名字或品牌名是什么？Instagram 账号是？
2. 用一句话说：你帮助（或娱乐）什么人，内容是关于什么的？
3. 描述你的理想粉丝：年龄段、生活状态、他们的困扰和想要的结果。
4. 文案用什么语言？画面上的文字用什么语言？你的受众在哪个时区？

第二轮：目标和语气
5. 接下来三个月，内容最想达成什么（涨粉、邮件订阅、卖产品、预约咨询、品牌合作）？有没有即将推出的产品、链接或活动？
6. 用三个词形容你想要的说话风格。有没有绝对不想变成的风格？
7. 贴一两条你满意的文案（或者描述一位你喜欢其*语气*的创作者）。
8. 哪 3-5 个话题你可以一直聊下去？（它们会成为你的内容支柱。）

第三轮：视觉和实际情况（做轮播图和日历配色前需要）
9. 品牌颜色的色号（如 #2E3A33），或者描述一下，我来推荐配色。有固定字体吗？
10. 你每周实际能拍多少内容？对镜头说话、配音加空镜、教程？在哪里拍，有多少时间？
11. 有哪些禁区：话题、家人或住址是否出镜、不能做的承诺？

If the user wants to go fast, ask only questions 1-3 and 6, write a provisional profile, and
mark open items as "(not set)" / "（未填写）".

**Proposing a palette** when the user has none: offer 2 options as hex sets (primary,
secondary, accent, background, text, muted). Check that text on background has at least
4.5:1 contrast. Let the user choose; never silently pick one.

**Fonts:** carousel rendering needs `.ttf`/`.otf`/`.ttc` font files. Latin fonts can come from
fonts.google.com ("Download family"); put the files in `brand/fonts/` and set
`fonts.heading.file` / `fonts.body.file`, e.g. `fonts/Inter-Bold.ttf`. **Chinese slides need a
Chinese font**: Windows (Microsoft YaHei) and macOS (PingFang) have one built in and it is found
automatically; elsewhere, or for a specific brand font, put a file such as
`NotoSansSC-Regular.otf` (free, from fonts.google.com, "Noto Sans SC") in `brand/fonts/` and
set `fonts.cjk.file`.

## 2. Writing the profile and brand kit

- Fill `brand/brand-profile.md` using the template's headings (they are bilingual; write the
  answers in the user's language). Delete the first line (`<!-- ACS:TEMPLATE ... -->`); its
  presence means "not configured".
- Prefer concrete examples over adjectives: "says 'okay' not 'OK!!'", "never says '干货满满'".
- Content pillars get a share (%), used to balance each week.
- Fill `brand/brand-kit.json`: `brand_name`, `handle`, `language` (e.g. `zh-CN`, `en`, `sv`),
  `timezone` (IANA name, e.g. `Asia/Shanghai`, `Europe/Stockholm`), `colors`, `fonts`, `logo`
  (path under `brand/`), and remove `"_placeholder": true`. Optional: `schedule.frequency_preset`
  (`light`, `balanced`, `heavy`, `custom` plus `custom_mix`), preferred days and posting times.
  With `language` set to `zh-CN` the calendar page, checklists and Markdown export are in Chinese.
- Show the user a short summary of the profile and ask for corrections before saving.

## 3. Keeping memory between sessions in Kimi

**Kimi Code and Kimi Work (files on the user's computer):** the workspace folder stays on disk
between sessions. Keep working in the same folder and nothing else is needed.

**kimi.com website, or any chat where files are not kept between conversations:**
1. Work in a `content-studio` folder wherever the environment lets you save files, so every
   file can be downloaded.
2. At the end of a session where the library or brand changed, zip the workspace:
   `python -c "import shutil; shutil.make_archive('content-studio', 'zip', '.', 'content-studio')"`
   and ask the user to keep `content-studio.zip`. Next time they attach it, unzip it before
   running `library.py status`.
3. In chat-only mode, give the updated `brand-profile.md` and `library.json` back as code
   blocks to save, and ask the user to attach them next time.

**Baking the brand into the skill** (so it is known without attachments): once the profile is
final, run
`python "<skill>/scripts/library.py" bake --workspace <ws> --out ai-content-studio-kimi.zip`.
The user uploads that ZIP in Kimi Work as a local skill (replacing the old one), or unzips it
over the skill folder in Kimi Code. `init` then starts new workspaces from the baked brand.

Explain this once, briefly, the first time memory matters. Do not pretend the library was
saved permanently when the session will be reset.

## 4. Library operations

All commands: `python "<skill>/scripts/library.py" <command> --workspace <ws>`.

| Task | Command |
|---|---|
| Memory digest before planning | `recent --weeks 8` |
| Register / sync a week plan | `add-week weeks/2026-W48.json` (after planning and after status changes) |
| Check ideas for repeats | `check --plan weeks/2026-W48.json` / `check --text "hook or title"` / `check --ideas ideas.json` |
| Save an idea for later | `add-idea --title "..." --hook "..." --pillar "..."` |
| See the backlog | `ideas --unused` |
| Register footage / assets | `add-media media/clip.mp4 --kind footage --description "..." --tags "kitchen,morning"` |
| Unused footage | `media --unused` |
| Save a learning | `add-learning "Carousels with a numbered recap get 2x saves" --source "W46-W48"` |

`check` compares title + hook + first sentence of the concept (English words, or two-character
pieces of Chinese text), and flags anything at or above the duplicate threshold. A flag means:
**change the angle, the format, or the example**, not just the wording. Reusing a *proven
pattern* is good; reusing the same idea within about 8 weeks is not, unless it is a deliberate
series or re-run of a top performer (say so in `notes`, or set `repurposed_from`).

## 5. Results and learnings

Ask for numbers after a post has been live 3-7 days. From Instagram Insights per post: views,
reach, likes, comments, saves, shares, follows (and average watch time / 3-second retention
for Reels if shown). Email: open rate, click rate. Log them:

`library.py log-performance --id 2026W48-tue-reel1 --views 12400 --reach 9800 --likes 640 --comments 41 --saves 310 --shares 95 --follows 22 --notes "hook tested a question"`

Or import a CSV with an `id` column plus metric columns via `--csv`. Engagement rate is
(likes + comments + saves + shares) / reach (or views).

`top --metric saves` and `recent` show best performers. When a pattern repeats across 2-3
posts, record it with `add-learning` and update section 11 of the profile. One viral post is a
hint, not a rule.
