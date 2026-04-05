#!/usr/bin/env python3
# Setup: add to ~/.bashrc
#   export INSTAGRAM_USERNAME=your_username
#   export INSTAGRAM_PASSWORD=your_password
#   export GOOGLE_API_KEY=your_gemini_api_key
import sys, os, glob, shutil, subprocess, time, re, hashlib

COOKIES_BROWSER = "chromium:~/.openclaw/browser/openclaw/user-data"
YT_DLP = os.path.expanduser("~/.local/bin/yt-dlp")
OPENCLAW = shutil.which("openclaw") or os.path.expanduser("~/.npm-global/bin/openclaw")
CACHE_DIR = os.path.expanduser("~/.cache/reel-summary")
CACHE_TTL = 86400  # 24 hours

# --- Cache ---

def cache_key(url):
    return hashlib.md5(url.encode()).hexdigest()

def load_cache(url):
    path = os.path.join(CACHE_DIR, cache_key(url) + ".txt")
    if os.path.exists(path) and time.time() - os.path.getmtime(path) < CACHE_TTL:
        with open(path) as f:
            return f.read()
    return None

def save_cache(url, result):
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(os.path.join(CACHE_DIR, cache_key(url) + ".txt"), "w") as f:
        f.write(result)

# --- Download ---

def run_yt_dlp(url):
    return subprocess.run(
        [YT_DLP, "--cookies-from-browser", COOKIES_BROWSER,
         url, "-o", "/tmp/reel_input.mp4", "-q"],
        capture_output=True, text=True
    )

def is_login_error(result):
    combined = result.stdout + result.stderr
    return any(k in combined.lower() for k in ["login required", "login page", "not available"])

def browser_cmd(*args):
    return subprocess.run([OPENCLAW, "browser"] + list(args),
                         capture_output=True, text=True, timeout=15)

def instagram_relogin():
    print("Session expired. Attempting re-login...")
    username = os.environ.get("INSTAGRAM_USERNAME", "")
    password = os.environ.get("INSTAGRAM_PASSWORD", "")
    if not username or not password:
        raise Exception(
            "Instagram session expired.\n"
            "Set INSTAGRAM_USERNAME and INSTAGRAM_PASSWORD in ~/.bashrc and retry."
        )
    browser_cmd("navigate", "https://www.instagram.com/accounts/login/")
    time.sleep(3)
    browser_cmd("evaluate", "--fn", '() => { const b = [...document.querySelectorAll("button")].find(x => x.textContent.includes("Allow all")); if(b) b.click(); }')
    time.sleep(1)
    browser_cmd("evaluate", "--fn",
        f'() => {{ document.querySelector("input[name=\'username\']").value = "{username}"; }}')
    browser_cmd("evaluate", "--fn",
        f'() => {{ document.querySelector("input[name=\'password\']").value = "{password}"; }}')
    browser_cmd("evaluate", "--fn",
        '() => { document.querySelector("button[type=\'submit\']").click(); }')
    time.sleep(4)
    browser_cmd("evaluate", "--fn",
        '() => { const b = [...document.querySelectorAll("button")].find(x => x.textContent.includes("Save info")); if(b) b.click(); }')
    time.sleep(2)
    print("Re-login complete.")

def download(url):
    for f in glob.glob("/tmp/reel_*"):
        if os.path.isfile(f): os.remove(f)
    shutil.rmtree("/tmp/reel_frames", ignore_errors=True)
    os.makedirs("/tmp/reel_frames", exist_ok=True)

    result = run_yt_dlp(url)
    if result.returncode == 0:
        return True

    if is_login_error(result):
        instagram_relogin()
        print("Retrying download after re-login...")
        result = run_yt_dlp(url)
        return result.returncode == 0

    print(f"Download error: {result.stderr[:200]}")
    return False

# --- Gemini video analysis (primary) ---

GEMINI_MODELS = [
    "models/gemini-2.5-flash",
    "models/gemini-3-flash-preview",
    "models/gemini-flash-latest",
]

def analyze_with_gemini(video_path, lang_request=None):
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        return None, "google-genai not installed"

    api_key = os.environ.get("GOOGLE_API_KEY", "")
    if not api_key:
        return None, "GOOGLE_API_KEY not set"

    client = genai.Client(api_key=api_key)

    print("Uploading video to Gemini...")
    with open(video_path, "rb") as f:
        video_file = client.files.upload(
            file=f,
            config=types.UploadFileConfig(mime_type="video/mp4")
        )

    print("Processing...", end="", flush=True)
    while video_file.state.name == "PROCESSING":
        time.sleep(2)
        print(".", end="", flush=True)
        video_file = client.files.get(name=video_file.name)
    print()

    if video_file.state.name != "ACTIVE":
        return None, f"Video processing failed: {video_file.state.name}"

    lang_instruction = (
        f'The user said: "{lang_request}". '
        f"Detect which language they want and reply in that language."
        if lang_request else
        "Reply in English."
    )
    prompt = (
        f"Watch this Instagram Reel completely. {lang_instruction}\n"
        f"Describe in detail:\n"
        f"1) All visuals and actions (including fast cuts)\n"
        f"2) All visible text and subtitles\n"
        f"3) Core theme (if humorous/meme, explain the joke)\n"
        f"4) Overall impression\n"
        f"Output the analysis directly — no opening remarks."
    )

    last_err = None
    for model_name in GEMINI_MODELS:
        try:
            print(f"Trying {model_name}...")
            response = client.models.generate_content(
                model=model_name,
                contents=[video_file, prompt]
            )
            try:
                client.files.delete(name=video_file.name)
            except Exception:
                pass
            return response.text, None
        except Exception as e:
            last_err = str(e)[:200]
            print(f"  {model_name} failed: {last_err[:80]}")

    try:
        client.files.delete(name=video_file.name)
    except Exception:
        pass
    return None, last_err

# --- Fallback: frame-based analysis via OpenClaw agent ---

def extract_audio():
    os.system("ffmpeg -i /tmp/reel_input.mp4 -vn -q:a 0 /tmp/reel_audio.mp3 -y -loglevel quiet 2>/dev/null")
    exists = os.path.exists("/tmp/reel_audio.mp3")
    if exists:
        size = os.path.getsize("/tmp/reel_audio.mp3")
        if size < 1024:
            return False
    return exists

def get_video_duration():
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", "/tmp/reel_input.mp4"],
        capture_output=True, text=True
    )
    try:
        return float(result.stdout.strip())
    except Exception:
        return 60.0

def extract_frames():
    duration = get_video_duration()
    timestamps = set()
    fps = 4.0 if duration <= 15 else 1.0
    t = 0.3
    while t < duration - 0.1:
        timestamps.add(round(t, 2))
        t = round(t + 1.0 / fps, 2)
    scene_result = subprocess.run(
        ["ffmpeg", "-i", "/tmp/reel_input.mp4",
         "-vf", "select=gt(scene\\,0.1),showinfo",
         "-vsync", "vfr", "-f", "null", "-"],
        capture_output=True, text=True
    )
    for line in scene_result.stderr.split('\n'):
        m = re.search(r'pts_time:([\d.]+)', line)
        if m:
            ts = round(float(m.group(1)), 2)
            if 0 < ts < duration:
                timestamps.add(ts)
    sorted_ts = sorted(timestamps)
    deduped = []
    for ts in sorted_ts:
        if not deduped or ts - deduped[-1] >= 0.15:
            deduped.append(ts)
    if len(deduped) > 15:
        indices = [int(i * (len(deduped) - 1) / 14) for i in range(15)]
        deduped = [deduped[i] for i in indices]
    frames = []
    for i, ts in enumerate(deduped):
        out = f"/tmp/reel_frames/f{i+1:03d}.jpg"
        os.system(f"ffmpeg -ss {ts:.2f} -i /tmp/reel_input.mp4 -vframes 1 {out} -y -loglevel quiet 2>/dev/null")
        if os.path.exists(out):
            frames.append(out)
    print(f"Frames ({len(frames)}): {[f'{ts}s' for ts in deduped]}")
    return frames

def extract_ocr_text(frames):
    try:
        import pytesseract
        from PIL import Image, ImageEnhance
    except ImportError:
        return ''
    seen = set()
    for f in frames:
        try:
            img = Image.open(f)
            img = ImageEnhance.Contrast(img).enhance(2.0)
            for psm in ('11', '6'):
                raw = pytesseract.image_to_string(img, config=f'--psm {psm} --oem 3').strip()
                for line in raw.split('\n'):
                    line = line.strip()
                    if len(line) > 3:
                        seen.add(line)
        except Exception:
            pass
    return '\n'.join(sorted(seen))

def transcribe():
    from faster_whisper import WhisperModel
    m = WhisperModel("medium", device="cpu", compute_type="int8")
    segs, info = m.transcribe(
        "/tmp/reel_audio.mp3",
        vad_filter=False,
        condition_on_previous_text=False
    )
    text = "".join(s.text for s in segs).strip()
    return text, info.language

def analyze_with_openclaw(transcript, lang, frames, ocr_text):
    frame_urls = " ".join(f"file:///tmp/reel_frames/{os.path.basename(f)}" for f in frames)
    ocr_part = f" On-screen text extracted via OCR: {ocr_text}." if ocr_text else ""
    if transcript:
        msg = (
            f"Analyze this Instagram Reel and reply in Chinese only. "
            f"Spoken language: {lang}. Transcript: {transcript}.{ocr_part} "
            f"Use the browser tool to view each video frame: {frame_urls}. "
            f"For each URL: call browser navigate, then immediately call browser screenshot to see the image. "
            f"After viewing all frames, write a concise Chinese summary covering: "
            f"visual content (describe ALL visible actions, humor, and meme structure), "
            f"main message, key speech points, overall impression. "
            f"IMPORTANT: Output ONLY the summary. Do NOT write any opening sentence about what you are about to do. "
            f"Do NOT offer numbered options or ask clarifying questions."
        )
    else:
        msg = (
            f"Analyze this Instagram Reel and reply in Chinese only. No speech detected.{ocr_part} "
            f"Use the browser tool to view each video frame: {frame_urls}. "
            f"For each URL: call browser navigate, then immediately call browser screenshot to see the image. "
            f"After viewing all frames, write a concise Chinese summary covering: "
            f"visual content (describe ALL visible actions, humor, and meme structure), "
            f"apparent topic, overall impression. "
            f"IMPORTANT: Output ONLY the summary. Do NOT write any opening sentence about what you are about to do. "
            f"Do NOT offer numbered options or ask clarifying questions."
        )
    result = subprocess.run(
        [OPENCLAW, "agent", "--agent", "main", "--message", msg],
        capture_output=True, text=True, timeout=180
    )
    lines = result.stdout.split("\n")
    resp = "\n".join(
        l for l in lines if l.strip() and not any(
            c in l for c in ["🦞", "◇", "│", "─", "OpenClaw", "Gateway", "Restarted"]
        )
    )
    return resp.strip() or result.stdout

# --- Cleanup ---

def cleanup():
    for f in glob.glob("/tmp/reel_*"):
        if os.path.isfile(f): os.remove(f)
    shutil.rmtree("/tmp/reel_frames", ignore_errors=True)

# --- Main ---

if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else input("Instagram URL: ").strip()
    lang_request = sys.argv[2] if len(sys.argv) > 2 else None

    cached = load_cache(url)
    if cached:
        print("(cached)")
        print("\n" + "="*40)
        print(cached)
        sys.exit(0)

    try:
        print("Downloading reel...")
        if not download(url): sys.exit("Download failed")

        # Primary: Gemini full video analysis
        summary, err = analyze_with_gemini("/tmp/reel_input.mp4", lang_request)

        if summary:
            save_cache(url, summary)
            print("\n" + "="*40)
            print(summary)
        else:
            # Fallback: frame-based analysis via OpenClaw agent
            print(f"Gemini unavailable ({err}), falling back to frame analysis...")
            print("Extracting audio and frames...")
            has_audio = extract_audio()
            frames = extract_frames()
            transcript, lang = "", "unknown"
            if has_audio:
                print("Transcribing audio...")
                transcript, lang = transcribe()
                print(f"Language: {lang} | Speech: {'yes' if transcript else 'none detected'}")
            print("Running OCR on frames...")
            ocr_text = extract_ocr_text(frames)
            print("Analyzing with OpenClaw agent...")
            summary = analyze_with_openclaw(transcript, lang, frames, ocr_text)
            save_cache(url, summary)
            print("\n" + "="*40)
            print(summary)
    finally:
        print("Cleaning up temporary files...")
        cleanup()
