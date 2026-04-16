---
name: reel-summarizer
description: Summarize any short video (Instagram Reels, TikTok, YouTube Shorts) using Gemini AI. Trigger when the user shares a short video URL and asks to summarize, describe, translate, or explain it. Also triggers on phrases like "what's in this video", "tell me about this reel", or "summarize this TikTok". Supports any output language.
trigger: /reel
---

# Reel Summarizer

Summarize Instagram Reels, TikTok videos, and YouTube Shorts using Gemini AI full-video analysis. Results are cached for 24 hours — the same URL won't re-download.

Falls back to frame extraction + OCR + local agent if Gemini is unavailable.

## Trigger Conditions

Use this skill when the user:
- Pastes an Instagram, TikTok, or YouTube Shorts URL and asks for a summary
- Says things like "what does this video show?", "summarize this reel", "explain this TikTok", "这个视频讲的是什么"
- Explicitly runs `/reel <url>` or `/reel <url> <language instruction>`

Do **not** trigger for regular YouTube videos (non-Shorts), Vimeo, or other platforms not in the list above.

## First-Time Setup

Run this once before first use. Skip steps already done.

### 1. Check system dependencies

```bash
which yt-dlp ffmpeg tesseract || echo "MISSING — install below"
```

If any are missing:
```bash
# Debian / Ubuntu
sudo apt install -y ffmpeg tesseract-ocr

# yt-dlp (always install via pip to get latest)
pip install -U yt-dlp
```

### 2. Install the script globally

```bash
# Clone or update the skill repo
SKILL_DIR="$HOME/.openclaw/skills/reel-summarizer"
if [ -d "$SKILL_DIR/.git" ]; then
  git -C "$SKILL_DIR" pull -q
else
  git clone https://github.com/Yinchaochen/reel-summarizer.git "$SKILL_DIR"
fi

# Install as a global command
sudo install -m 755 "$SKILL_DIR/reel_summary.py" /usr/local/bin/reel-summary
```

### 3. Install Python dependencies

```bash
pip install -r "$HOME/.openclaw/skills/reel-summarizer/requirements.txt"
```

### 4. Set the Gemini API key

Get a free key at https://aistudio.google.com and add it once:

```bash
echo 'export GOOGLE_API_KEY=your_key_here' >> ~/.bashrc && source ~/.bashrc
```

### 5. (Optional) Instagram auto re-login

If the session expires, the script can re-login automatically:

```bash
echo 'export INSTAGRAM_USERNAME=your_username' >> ~/.bashrc
echo 'export INSTAGRAM_PASSWORD=your_password' >> ~/.bashrc
source ~/.bashrc
```

If these are not set, the script will print a clear error and stop on session expiry instead of crashing silently.

---

## Workflow

### Step 1 — Extract the URL and language

From the user's message, extract:
- `VIDEO_URL`: the full short video URL
- `LANG_REQUEST` (optional): any language instruction the user gave, e.g. "用中文", "in French", "Türkçe özetle"

If no URL is found, ask the user: "Please paste the video URL."

### Step 2 — Check that the script is installed

```bash
which reel-summary || echo "NOT_INSTALLED"
```

If it prints `NOT_INSTALLED`, run the **First-Time Setup** section above before continuing.

### Step 3 — Run the summarizer

```bash
# Without language instruction (defaults to English)
reel-summary 'VIDEO_URL'

# With language instruction
reel-summary 'VIDEO_URL' 'LANG_REQUEST'
```

Substitute `VIDEO_URL` and `LANG_REQUEST` with actual values. Always quote the URL — it may contain special characters (`&`, `?`, `=`).

Wait for the script to finish. It will print:
- Progress lines (`Downloading reel...`, `Uploading to Gemini...`, `Processing...`)
- A separator line (`========================================`)
- The summary

If it prints `(cached)`, the result is from the 24-hour cache — this is expected and fast.

### Step 4 — Present the summary

Show the user everything below the `===` separator line verbatim. Do not rephrase, truncate, or add your own interpretation unless the user asks for it.

If the user asked for the summary in a specific language, confirm: "Summary in [language] as requested."

---

## Error Handling

| Error message | What to do |
|---|---|
| `Download failed` | The URL may be private, expired, or geo-restricted. Ask the user to check if the video is publicly accessible. |
| `Instagram session expired` and no credentials set | Tell the user to set `INSTAGRAM_USERNAME` and `INSTAGRAM_PASSWORD` in `~/.bashrc` and re-run. |
| `GOOGLE_API_KEY not set` | Tell the user to follow Setup Step 4. |
| `google-genai not installed` | Run `pip install google-genai` and retry. |
| Gemini fails, falls back to frame analysis | This is normal — the script handles it automatically. The summary may be shorter or less detailed. |
| `yt-dlp: command not found` | Run `pip install -U yt-dlp` and retry. |

---

## Supported URL Formats

```
https://www.instagram.com/reel/ABC123/
https://www.instagram.com/p/ABC123/
https://www.tiktok.com/@user/video/1234567890
https://vm.tiktok.com/XXXXXXX/
https://www.youtube.com/shorts/dQw4w9WgXcQ
```

---

## Notes

- **Cache location:** `~/.cache/reel-summary/` — delete to force re-download
- **Cookie source:** OpenClaw's Chromium profile at `~/.openclaw/browser/openclaw/user-data`
- **Gemini models tried in order:** `gemini-2.5-flash` → `gemini-3-flash-preview` → `gemini-flash-latest`
- **Fallback** uses `faster-whisper` (audio transcription) + `tesseract` (OCR) + OpenClaw agent vision
