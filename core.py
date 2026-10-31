"""Tk-free application logic and yt-dlp process integration."""

import io
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
from dataclasses import dataclass
import urllib.error
import urllib.parse
import urllib.request

# CalVer (YYYY.MM.DD, plus .N for a further release on the same day).
# Single source of truth: bump this when tagging a release (tag: vYYYY.MM.DD).
APP_VERSION = "2026.10.31"

log = logging.getLogger("ytdl-ui")
log.addHandler(logging.NullHandler())
log.setLevel(logging.INFO)
log.propagate = False
LOG_DIR = os.path.join(tempfile.gettempdir(), "ytdl-ui")
LOG_PATH = os.path.join(LOG_DIR, f"ytdl-ui-{os.getpid()}.log")
COOKIE_BROWSERS = {
    "Chrome": "chrome",
    "Edge": "edge",
    "Firefox": "firefox",
    "Brave": "brave",
}


def cookie_settings_path():
    """Return the per-user path used to remember the cookie preference."""
    if sys.platform == "win32":
        settings_dir = (
            os.environ.get("LOCALAPPDATA")
            or os.environ.get("APPDATA")
            or os.path.expanduser("~")
        )
    elif sys.platform == "darwin":
        settings_dir = os.path.join(os.path.expanduser("~"), "Library", "Application Support")
    else:
        settings_dir = os.environ.get(
            "XDG_CONFIG_HOME", os.path.join(os.path.expanduser("~"), ".config")
        )
    return os.path.join(settings_dir, "ytdl-ui", "settings.json")


def _default_cookie_browser():
    return "firefox" if sys.platform == "win32" else "chrome"


def _read_cookie_settings():
    try:
        with open(cookie_settings_path(), encoding="utf-8") as settings_file:
            settings = json.load(settings_file)
    except FileNotFoundError:
        return {}
    except (OSError, json.JSONDecodeError) as exc:
        log.warning("load_cookie_settings: %s", exc)
        return {}
    return settings if isinstance(settings, dict) else {}


def load_cookie_settings():
    """Load the opt-in and browser name; never persist browser cookie data."""
    settings = _read_cookie_settings()
    browser = settings.get("browser")
    if browser not in COOKIE_BROWSERS.values():
        browser = _default_cookie_browser()
    return settings.get("use_browser_cookies") is True, browser


def load_cookie_file_settings():
    """Load the selected cookie file and whether it is the active source."""
    settings = _read_cookie_settings()
    cookie_file = settings.get("cookie_file")
    if not isinstance(cookie_file, str) or not cookie_file:
        cookie_file = ""
    source = settings.get("cookie_source")
    if source not in ("browser", "file"):
        source = "browser"
    return cookie_file, source


def save_cookie_settings(enabled, browser, cookie_file="", cookie_source="browser"):
    """Persist cookie preferences and a path, never the cookie data itself."""
    if browser not in COOKIE_BROWSERS.values():
        return False
    if cookie_source not in ("browser", "file"):
        return False
    path = cookie_settings_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as settings_file:
            json.dump(
                {
                    "use_browser_cookies": bool(enabled),
                    "browser": browser,
                    "cookie_file": cookie_file or "",
                    "cookie_source": cookie_source,
                },
                settings_file,
            )
    except OSError as exc:
        log.warning("save_cookie_settings: %s", exc)
        return False
    return True


def configure_logging(log_dir=None):
    """Configure app logging, optionally directing it to a specific directory."""
    destination_dir = os.fspath(log_dir) if log_dir is not None else LOG_DIR
    os.makedirs(destination_dir, exist_ok=True)
    log_path = os.path.join(destination_dir, f"ytdl-ui-{os.getpid()}.log")
    log.setLevel(logging.INFO)
    log.propagate = False
    is_configured = any(
        isinstance(handler, logging.FileHandler)
        and os.path.abspath(handler.baseFilename) == os.path.abspath(log_path)
        for handler in log.handlers
    )
    if not is_configured:
        formatter = logging.Formatter(
            "%(asctime)s %(levelname)s [pid=%(process)d thread=%(threadName)s] %(message)s"
        )
        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setFormatter(formatter)
        log.addHandler(file_handler)
        stream_handler = logging.StreamHandler(sys.stderr)
        stream_handler.setFormatter(formatter)
        log.addHandler(stream_handler)
    log.info("ytdl-ui %s", APP_VERSION)
    log.info("Python %s", sys.version.split()[0])
    log.info("yt-dlp resolved to: %s", YT_DLP)
    log.info("JS runtime opts: %s", JS_RUNTIME_OPTS or "(none — yt-dlp will auto-detect)")
    return log_path


class ProcessController:
    """Track and cancel the current yt-dlp subprocess."""

    def __init__(self):
        self._lock = threading.Lock()
        self._proc = None
        self._cancelled = False

    def register(self, proc):
        with self._lock:
            self._proc = proc
            self._cancelled = False

    def clear(self):
        with self._lock:
            self._proc = None

    def stop(self, grace_seconds=3):
        with self._lock:
            proc = self._proc
            if proc is None:
                return False
            self._cancelled = True
        log.info("stop_active_proc: terminating pid=%s", proc.pid)
        proc.terminate()
        try:
            proc.wait(timeout=grace_seconds)
        except subprocess.TimeoutExpired:
            log.warning("stop_active_proc: grace expired, killing pid=%s", proc.pid)
            proc.kill()
        return True

    def was_cancelled(self):
        with self._lock:
            return self._cancelled


process_controller = ProcessController()


def _venv_bin_dir():
    return os.path.dirname(os.path.abspath(sys.executable))


def _find_executable(name):
    """Prefer executables installed beside the active Python interpreter."""
    bin_dir = _venv_bin_dir()
    for candidate in (name, name + ".exe"):
        local = os.path.join(bin_dir, candidate)
        if os.path.isfile(local) and os.access(local, os.X_OK):
            return local
    return shutil.which(name)


YT_DLP = _find_executable("yt-dlp") or "yt-dlp"


def _js_runtime_opts():
    """Pass the venv Deno path and enable yt-dlp's EJS challenge component."""
    bin_dir = _venv_bin_dir()
    opts = []
    for candidate in ("deno", "deno.exe"):
        deno = os.path.join(bin_dir, candidate)
        if os.path.isfile(deno) and os.access(deno, os.X_OK):
            opts.extend(["--js-runtimes", f"deno:{deno}"])
            break
    opts.extend(["--remote-components", "ejs:github"])
    return opts


JS_RUNTIME_OPTS = _js_runtime_opts()

YT_DLP_NOT_FOUND = (
    "Error: yt-dlp not found. Install it with:\n"
    "  pip install -r requirements.txt\n"
    "or visit https://github.com/yt-dlp/yt-dlp#installation"
)

RATE_LIMITED_MSG = (
    "Rate limited by the server (HTTP 429: Too Many Requests).\n"
    "\n"
    "Try the following:\n"
    "  - Wait a few minutes before retrying.\n"
    "  - Update yt-dlp; a bundled build must be rebuilt or have yt-dlp.exe replaced.\n"
    "  - Avoid checking many URLs in quick succession.\n"
    "\n"
    "Cookies (when YouTube requires sign-in or a CAPTCHA):\n"
    "  - On Windows, Firefox is the recommended browser-cookie option. Install it and retry.\n"
    "  - For Chrome or Edge, browser cookie decryption may fail on Windows.\n"
    "    1. Install a 'Get cookies.txt' extension such as "
    "https://chromewebstore.google.com/detail/get-cookiestxt-locally/"
    "cclelndahbckbenkjhflpdbgdldlbecc?pli=1 in order to download the file.\n"
    "    2. Sign in to YouTube, then use the extension to export its cookies.\n"
    "    3. Enable Use browser cookies and choose Browse... to select the file.\n"
    "  - The selected cookie file is remembered between sessions.\n"
    "  - More details: https://github.com/yt-dlp/yt-dlp/issues/10927"
)

RATE_LIMIT_OPTS = [
    "--retries", "10",
    "--retry-sleep", "exp=1:120",
    "--sleep-requests", "1",
]
DEFAULT_FORMAT_LABEL = "best (default)"
THUMB_PRINT_PREFIX = "THUMB:"
THUMB_PRINT_TEMPLATE = THUMB_PRINT_PREFIX + "%(thumbnail)s"
SUBS_PRINT_PREFIX = "SUBS:"
SUBS_PRINT_TEMPLATE = SUBS_PRINT_PREFIX + "%(subtitles)j"
AUTO_SUBS_PRINT_PREFIX = "AUTOSUBS:"
AUTO_SUBS_PRINT_TEMPLATE = AUTO_SUBS_PRINT_PREFIX + "%(automatic_captions)j"
PRINT_PREFIXES = (THUMB_PRINT_PREFIX, SUBS_PRINT_PREFIX, AUTO_SUBS_PRINT_PREFIX)

TYPE_VIDEO_AUDIO = "Video + Audio"
TYPE_VIDEO_ONLY = "Video only"
TYPE_AUDIO_ONLY = "Audio only"
FORMAT_TYPES = (TYPE_VIDEO_AUDIO, TYPE_VIDEO_ONLY, TYPE_AUDIO_ONLY)
QUALITY_BEST = "Best"
QUALITY_LOWEST = "Lowest"
AUDIO_QUALITIES = (QUALITY_BEST, "Medium", "Low")
VIDEO_CONTAINERS = ("Auto", "MP4", "MKV")
AUDIO_CONTAINERS = ("Original", "MP3", "M4A", "Opus")
THUMB_MAX_WIDTH = 320
THUMB_MAX_HEIGHT = 180
THUMB_FETCH_TIMEOUT = 15
THUMB_MAX_BYTES = 5_000_000


def is_rate_limited(text):
    if not text:
        return False
    lowered = text.lower()
    return "429" in text or "too many requests" in lowered


def is_cookie_read_error(text):
    """Identify yt-dlp errors that indicate browser cookies could not be read."""
    if not text:
        return False
    lowered = text.lower()
    if "dpapi" in lowered and "decrypt" in lowered:
        return True
    return "cookie" in lowered and any(
        phrase in lowered
        for phrase in (
            "could not copy",
            "could not find",
            "failed to decrypt",
            "could not decrypt",
            "failed to load",
            "no cookies",
        )
    )


def cookie_args(browser):
    """Return yt-dlp cookie flags for a recognized browser, if selected."""
    if browser not in COOKIE_BROWSERS.values():
        return []
    return ["--cookies-from-browser", browser]


def cookie_file_args(cookie_file):
    """Return yt-dlp cookie-file flags when a file is selected."""
    if not cookie_file:
        return []
    return ["--cookies", os.fspath(cookie_file)]


def parse_formats(output):
    """Parse yt-dlp -F output into (format id, label) tuples."""
    if not output:
        return []
    formats = []
    seen_separator = False
    for line in output.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(PRINT_PREFIXES):
            continue
        if not seen_separator:
            if set(stripped) <= set("-\u2500 "):
                seen_separator = True
            continue
        parts = stripped.split(None, 1)
        if len(parts) < 2 or parts[0].upper() == "ID":
            continue
        fmt_id, rest = parts
        formats.append((fmt_id, f"{fmt_id}  {rest}".rstrip()))
    return formats


def format_id_from_label(label):
    if not label or label == DEFAULT_FORMAT_LABEL:
        return None
    return label.split(None, 1)[0]


def strip_print_lines(output):
    """Drop the machine-readable --print lines from check output."""
    if not output:
        return output
    return "\n".join(
        line for line in output.splitlines()
        if not line.strip().startswith(PRINT_PREFIXES)
    )


@dataclass(frozen=True)
class FormatInfo:
    """One selectable yt-dlp format parsed from a `-F` table row."""

    id: str
    ext: str
    resolution: str
    height: int | None
    kind: str  # "video+audio", "video" or "audio"
    size: int | None  # bytes, when yt-dlp reports one
    detail: str


_SIZE_UNITS = {"KiB": 1024, "MiB": 1024**2, "GiB": 1024**3, "TiB": 1024**4}
_SIZE_RE = re.compile(r"([\d.]+)\s*(KiB|MiB|GiB|TiB)")
_RES_RE = re.compile(r"\b\d+x(\d+)\b")


def parse_format_details(output):
    """Parse `-F` output into FormatInfo rows, skipping storyboards."""
    infos = []
    for fmt_id, label in parse_formats(output):
        rest = label[len(fmt_id):].strip()
        ext = rest.split(None, 1)[0] if rest else ""
        if ext == "mhtml" or "storyboard" in rest:
            continue
        res = _RES_RE.search(rest)
        height = int(res.group(1)) if res else None
        if "audio only" in rest:
            kind, resolution = "audio", "audio only"
        elif height is None:
            continue
        else:
            kind = "video" if "video only" in rest else "video+audio"
            resolution = res.group(0)
        size = None
        size_match = _SIZE_RE.search(rest)
        if size_match:
            size = int(float(size_match.group(1)) * _SIZE_UNITS[size_match.group(2)])
        parts = rest.split("|", 2)
        detail = " ".join(parts[2].split()) if len(parts) > 2 else ""
        infos.append(FormatInfo(fmt_id, ext, resolution, height, kind, size, detail))
    return infos


def sort_formats_for_display(formats):
    """Order formats video+audio, then video-only, then audio; best first."""
    order = {"video+audio": 0, "video": 1, "audio": 2}
    return sorted(
        formats,
        key=lambda f: (order[f.kind], -(f.height or 0), -(f.size or 0)),
    )


def available_heights(formats):
    """Distinct video heights, highest first."""
    return sorted({f.height for f in formats if f.kind != "audio" and f.height},
                  reverse=True)


def quality_choices(fmt_type, formats):
    """Quality dropdown values for the chosen download type."""
    if fmt_type == TYPE_AUDIO_ONLY:
        return list(AUDIO_QUALITIES)
    return [QUALITY_BEST] + [f"{h}p" for h in available_heights(formats)] + [QUALITY_LOWEST]


def container_choices(fmt_type):
    """Container dropdown values for the chosen download type."""
    return list(AUDIO_CONTAINERS if fmt_type == TYPE_AUDIO_ONLY else VIDEO_CONTAINERS)


def _quality_height(quality):
    if quality and quality.endswith("p") and quality[:-1].isdigit():
        return int(quality[:-1])
    return None


def format_selector(fmt_type, quality):
    """Build the yt-dlp `-f` expression for a type + quality choice."""
    height = _quality_height(quality)
    if fmt_type == TYPE_AUDIO_ONLY:
        return {
            "Medium": "ba[abr<=160]/ba/b",
            "Low": "wa/w",
        }.get(quality, "ba/b")
    cap = f"[height<={height}]" if height else ""
    if quality == QUALITY_LOWEST:
        return "wv*" if fmt_type == TYPE_VIDEO_ONLY else "wv*+wa/w"
    if fmt_type == TYPE_VIDEO_ONLY:
        return f"bv*{cap}"
    return f"bv*{cap}+ba/b{cap}"


def format_selection_args(fmt_type, quality, container):
    """yt-dlp args (format, container, audio extraction) for the UI choices."""
    args = ["-f", format_selector(fmt_type, quality)]
    if fmt_type == TYPE_AUDIO_ONLY:
        if container in ("MP3", "M4A", "Opus"):
            args += ["-x", "--audio-format", container.lower()]
    elif container in ("MP4", "MKV"):
        flag = "--remux-video" if fmt_type == TYPE_VIDEO_ONLY else "--merge-output-format"
        args += [flag, container.lower()]
    return args


def custom_format_args(fmt_id, formats):
    """`-f` args for a raw format pick; video-only picks get audio merged in."""
    info = next((f for f in formats if f.id == fmt_id), None)
    if info is not None and info.kind == "video":
        return ["-f", f"{fmt_id}+ba/{fmt_id}"]
    return ["-f", fmt_id]


def estimate_size(formats, fmt_type, quality):
    """Rough download size in bytes for the choice, or None when unknown."""
    sized_audio = sorted(f.size for f in formats if f.kind == "audio" and f.size)
    audio_size = None
    if sized_audio:
        if quality == "Low":
            audio_size = sized_audio[0]
        elif quality == "Medium":
            audio_size = sized_audio[len(sized_audio) // 2]
        else:
            audio_size = sized_audio[-1]
    if fmt_type == TYPE_AUDIO_ONLY:
        return audio_size
    videos = [f for f in formats if f.kind != "audio" and f.height]
    if not videos:
        return None
    heights = sorted({f.height for f in videos})
    cap = _quality_height(quality)
    if quality == QUALITY_LOWEST:
        target = heights[0]
    elif cap:
        target = max((h for h in heights if h <= cap), default=heights[0])
    else:
        target = heights[-1]
    sizes = [f.size for f in videos if f.height == target and f.size]
    if not sizes:
        return None
    video_size = max(sizes)
    if fmt_type == TYPE_VIDEO_ONLY:
        return video_size
    return video_size + (audio_size or 0)


def format_size(num_bytes):
    """Human-readable size such as '~52.4 MiB'."""
    if not num_bytes:
        return "size unknown"
    value = float(num_bytes)
    for unit in ("B", "KiB", "MiB", "GiB"):
        if value < 1024 or unit == "GiB":
            return f"~{value:.1f} {unit}" if unit != "B" else f"~{int(value)} B"
        value /= 1024


def _json_object(payload):
    try:
        data = json.loads(payload)
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _subtitle_name(entries, code):
    if isinstance(entries, list):
        for entry in entries:
            if isinstance(entry, dict) and entry.get("name"):
                return entry["name"]
    return code


def parse_subtitle_languages(output):
    """Return dropdown labels for manual then auto-generated subtitle tracks.

    Labels look like "en - English" or "en - English (auto)"; English leads
    each group. Use `subtitle_args` to turn a label back into yt-dlp flags.
    """
    manual, auto = {}, {}
    for line in (output or "").splitlines():
        if line.startswith(SUBS_PRINT_PREFIX):
            manual = _json_object(line[len(SUBS_PRINT_PREFIX):])
        elif line.startswith(AUTO_SUBS_PRINT_PREFIX):
            auto = _json_object(line[len(AUTO_SUBS_PRINT_PREFIX):])

    def labels(tracks, suffix):
        codes = sorted(tracks, key=lambda c: (not c.startswith("en"), c))
        return [f"{c} - {_subtitle_name(tracks[c], c)}{suffix}" for c in codes
                if not c.startswith("live_chat")]

    return labels(manual, "") + labels(auto, " (auto)")


def subtitle_args(label):
    """yt-dlp flags for a subtitle dropdown label (empty when none chosen)."""
    if not label:
        return []
    code = label.split(None, 1)[0]
    flag = "--write-auto-subs" if label.endswith("(auto)") else "--write-subs"
    return [flag, "--sub-langs", code]


def default_output_dir():
    downloads = os.path.join(os.path.expanduser("~"), "Downloads")
    return downloads if os.path.isdir(downloads) else os.getcwd()


def output_template(out_dir):
    if not out_dir:
        return None
    return os.path.join(out_dir, "%(title)s [%(id)s].%(ext)s")


def output_args(out_dir):
    template = output_template(out_dir)
    return ["-o", template] if template else []


def is_valid_url(url):
    if not url:
        return False
    parsed = urllib.parse.urlparse(url.strip())
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def parse_thumbnail_url(output):
    if not output:
        return None
    for line in output.splitlines():
        stripped = line.strip()
        if stripped.startswith(THUMB_PRINT_PREFIX):
            url = stripped[len(THUMB_PRINT_PREFIX):].strip()
            if is_valid_url(url):
                return url
    return None


def fit_thumbnail_size(width, height, max_w=THUMB_MAX_WIDTH, max_h=THUMB_MAX_HEIGHT):
    if width <= 0 or height <= 0:
        return max(1, max_w), max(1, max_h)
    scale = min(max_w / width, max_h / height, 1.0)
    return max(1, int(width * scale)), max(1, int(height * scale))


def fetch_thumbnail_bytes(url, timeout=THUMB_FETCH_TIMEOUT, max_bytes=THUMB_MAX_BYTES):
    if not is_valid_url(url):
        return None
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "ytdl-ui"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read(max_bytes + 1)
    except (OSError, urllib.error.URLError, ValueError) as exc:
        log.warning("fetch_thumbnail_bytes: %s", exc)
        return None
    if not data or len(data) > max_bytes:
        return None
    return data


def decode_thumbnail(data, max_w=THUMB_MAX_WIDTH, max_h=THUMB_MAX_HEIGHT):
    if not data:
        return None
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(data))
        img.load()
        size = fit_thumbnail_size(img.size[0], img.size[1], max_w, max_h)
        if size != img.size:
            img = img.resize(size, Image.Resampling.LANCZOS)
        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGBA" if "A" in img.getbands() else "RGB")
        return img
    except Exception as exc:
        log.warning("decode_thumbnail: %s", exc)
        return None


def parse_download_target(line):
    if not line:
        return None
    text = line.strip()
    marker = "[download] Destination: "
    if text.startswith(marker):
        return text[len(marker):].strip() or None
    return None


def partial_file_note(target):
    if not target:
        return None
    part = target + ".part"
    which = part if os.path.exists(part) else target
    return f"Partial file left on disk:\n  {which}"


# Keep the frozen (windowed) exe from flashing a console for each yt-dlp child.
SUBPROCESS_FLAGS = (
    {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}
)


def get_yt_dlp_version(timeout=15):
    """Return the yt-dlp version string, or None if it cannot be determined."""
    try:
        ret = subprocess.run(
            [YT_DLP, "--version"], capture_output=True, encoding="utf-8",
            errors="replace", timeout=timeout, **SUBPROCESS_FLAGS,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        log.warning("get_yt_dlp_version: %s", exc)
        return None
    version = (ret.stdout or "").strip()
    return version if ret.returncode == 0 and version else None


def version_status_text(yt_dlp_version=None):
    """Footer text showing the app version and, once known, the yt-dlp version."""
    text = f"ytdl-ui {APP_VERSION}"
    if yt_dlp_version:
        text += f" · yt-dlp {yt_dlp_version}"
    return text


def run_download(*args, cookie_browser=None, cookie_file=None):
    """Run yt-dlp and return the CompletedProcess, or None if not found."""
    cmd = [YT_DLP, *JS_RUNTIME_OPTS, *RATE_LIMIT_OPTS,
           *cookie_args(cookie_browser), *cookie_file_args(cookie_file), *args]
    log.info("run_download: starting: %s", " ".join(cmd))
    try:
        ret = subprocess.run(
            cmd, capture_output=True, encoding="utf-8", errors="replace",
            **SUBPROCESS_FLAGS,
        )
        log.info(
            "run_download: finished rc=%s (stdout %d chars, stderr %d chars)",
            ret.returncode, len(ret.stdout or ""), len(ret.stderr or ""),
        )
        if ret.returncode != 0:
            log.error("run_download: yt-dlp failed rc=%s stderr=%r", ret.returncode, ret.stderr)
            if (cookie_browser or cookie_file) and is_cookie_read_error(ret.stderr):
                log.warning("run_download: cookies could not be read; retrying without cookies")
                return run_download(*args)
        return ret
    except FileNotFoundError:
        log.error("run_download: yt-dlp not found at %s", YT_DLP)
        return None


def run_download_live(*args, on_line=None, cookie_browser=None, cookie_file=None):
    """Run yt-dlp with live line-by-line output via on_line callback."""
    cmd = [YT_DLP, *JS_RUNTIME_OPTS, *RATE_LIMIT_OPTS,
           *cookie_args(cookie_browser), *cookie_file_args(cookie_file), *args]
    log.info("run_download_live: starting: %s", " ".join(cmd))
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding="utf-8",
            errors="replace",
            **SUBPROCESS_FLAGS,
        )
    except FileNotFoundError:
        log.error("run_download_live: yt-dlp not found at %s", YT_DLP)
        return None

    assert proc.stdout is not None and proc.stderr is not None
    process_controller.register(proc)
    try:
        for line in proc.stdout:
            if on_line:
                on_line(line)
        proc.wait()
        stderr = proc.stderr.read()
        proc.stderr.close()
        proc.stdout.close()
    finally:
        process_controller.clear()
    log.info(
        "run_download_live: finished rc=%s (stderr %d chars)",
        proc.returncode, len(stderr or ""),
    )
    if proc.returncode != 0:
        log.error("run_download_live: yt-dlp failed rc=%s stderr=%r", proc.returncode, stderr)
        if (cookie_browser or cookie_file) and is_cookie_read_error(stderr):
            log.warning("run_download_live: cookies could not be read; retrying without cookies")
            return run_download_live(*args, on_line=on_line)
    return proc.returncode, stderr
