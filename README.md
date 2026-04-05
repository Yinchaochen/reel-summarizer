# Reel Summarizer

Summarize any Instagram Reel using Google Gemini for full video analysis. Supports any output language.

## How it works

1. Downloads the Reel via `yt-dlp` (uses your Instagram browser session)
2. Uploads the video directly to Gemini 2.5 Flash for complete analysis
3. Returns a detailed summary — visuals, subtitles, humor/meme structure, overall impression
4. Caches results for 24 hours (same URL won't re-download)

If Gemini is unavailable, falls back to frame extraction + OCR + a local agent.

## Requirements

**System dependencies:**

```bash
sudo apt install ffmpeg tesseract-ocr yt-dlp
```

**Python dependencies:**

```bash
pip install -r requirements.txt
```

**API key:**

Get a free Gemini API key at [aistudio.google.com](https://aistudio.google.com) and add it to your shell:

```bash
echo 'export GOOGLE_API_KEY=your_key_here' >> ~/.bashrc
source ~/.bashrc
```

**Instagram session:**

`yt-dlp` reads cookies from a Chromium browser profile. Make sure you're logged in to Instagram in your browser. For auto re-login, set:

```bash
export INSTAGRAM_USERNAME=your_username
export INSTAGRAM_PASSWORD=your_password
```

## Usage

```bash
# Install as a global command
sudo install -m 755 reel_summary.py /usr/local/bin/reel-summary

# Summarize a Reel (default: English)
reel-summary 'https://www.instagram.com/reel/...'

# Summarize in a specific language (any language, any phrasing)
reel-summary 'https://www.instagram.com/reel/...' "请用中文总结"
reel-summary 'https://www.instagram.com/reel/...' "Türkçe özetle"
reel-summary 'https://www.instagram.com/reel/...' "résume en français"
```

## OpenClaw / Telegram integration

This script is designed to work as an [OpenClaw](https://openclaw.ai) skill. When deployed, your Telegram or WhatsApp bot will automatically summarize any Instagram Reel link you send it.
