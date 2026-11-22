# Examples 示例

Everything here uses **fictional** brands, so the outputs can be inspected without touching
real brand files. 这里的品牌都是虚构的，只用来展示效果。

- English set: *Calm Habits* (@calmhabits.sample)
- 中文示例：*晨光慢习惯* (@morninglight.sample), in `zh/`

## English examples

| File | What it is | Produced by |
|---|---|---|
| `sample-brand-profile.md` | A finished brand profile (what onboarding should produce) | the assistant, from the onboarding interview |
| `sample-brand-kit.json` | A finished brand kit: colors, handle, timezone, schedule | the assistant, from onboarding |
| `sample-week-plan.json` | A full week (2026-W48): 13 items, all four statuses, one revision | `plan_tool.py new`, the assistant's content patch, `update`, status changes |
| `sample-week-plan.md` | The same week as a production document | `plan_tool.py export --format md` |
| `sample-calendar.html` | The visual Monday-Sunday calendar for that week (open in a browser) | `plan_tool.py render` |
| `sample-transcript.srt` | Captions of a 66 s talking-head video with fillers, pauses and a retake | input example |
| `sample-repurpose-output.md` | Expected answer when repurposing that video into reels, carousel, stories, email, hooks | the assistant, following references/repurposing.md |
| `sample-carousel.json` | The carousel spec from that repurposing | the assistant |
| `assets/sample-carousel-cover.jpg` | Its rendered cover, used as the calendar thumbnail | `carousel.py render` |

## 中文示例（`zh/` 文件夹）

| 文件 | 内容 | 生成方式 |
|---|---|---|
| `zh/sample-brand-profile.zh.md` | 填好的中文品牌档案 | 品牌设定对话后由助手生成 |
| `zh/sample-brand-kit.zh.json` | 中文品牌配置（`"language": "zh-CN"`，日历和清单显示中文） | 品牌设定对话后由助手生成 |
| `zh/sample-week-plan.zh.json` / `.md` | 一周计划（2026-W49，light 频率，7 条内容） | `plan_tool.py new` + 内容补丁 + `update` |
| `zh/sample-calendar.zh.html` | 中文界面的可视化周日历（用浏览器打开） | `plan_tool.py render` |
| `zh/sample-transcript.zh.srt` | 61 秒口播字幕，包含「嗯、呃、那个」、停顿和一次重说 | 输入示例 |
| `zh/sample-carousel.zh.json` | 由这段口播改写成的 8 页轮播图 | 助手生成 |
| `zh/assets/sample-carousel-cover.zh.jpg` | 渲染出的轮播封面（日历缩略图） | `carousel.py render` |
| `zh/sample-one-idea-many-posts.zh.json` / `.md` | 一个选题生成多平台帖子（Reel、轮播、快拍、邮件、TikTok、Shorts、备选钩子） | 助手生成 |

## Example requests 示例指令

**1. Plan a week 规划一周**
- EN: "Plan my content for next week. Theme: calm mornings when it's dark out. I want to push my free guide on Thursday."
- 中文：「帮我规划下周的内容，主题是冬天的早晨也能慢下来，周四推广我的免费指南。」

Expect: the brand profile and library digest read first, then a full plan with Thursday's items
tied to the guide, a summary table, the calendar file and a production document.

**2. Repurpose a video 一稿多用**
- EN: "Here's my latest video transcript (sample-transcript.srt). Turn it into reels, a carousel, stories and a newsletter."
- 中文：「这是我最新视频的字幕（zh/sample-transcript.zh.srt），帮我改成 Reel 选题、轮播图、快拍和邮件。」

**3. Edit a Reel 剪辑视频**
- EN: "Edit this into a reel with subtitles. If you can't render video, give me a cut list for CapCut."
- 中文：「把这个视频剪成带字幕的 Reel。如果没法直接导出视频，就给我剪映（CapCut）的剪辑清单。」

With ffmpeg: a verified 1080x1920 MP4 plus `cutlist.csv`, `cutlist.edl`, `captions.srt`. Without
ffmpeg: no video is claimed; you get the cut list, the captions and step-by-step editing instructions.

## Try the scripts 试运行脚本

```bash
python scripts/transcript.py analyze examples/zh/sample-transcript.zh.srt
python scripts/carousel.py render examples/zh/sample-carousel.zh.json --brand-kit examples/zh/sample-brand-kit.zh.json --out carousel-zh --pptx
python scripts/plan_tool.py summary examples/sample-week-plan.json
python scripts/plan_tool.py render examples/zh/sample-week-plan.zh.json --brand-kit examples/zh/sample-brand-kit.zh.json --out calendar-zh.html
```
