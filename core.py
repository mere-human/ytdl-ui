"""Tk-free application logic and yt-dlp process integration."""

import io
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import urllib.error
import urllib.parse
import urllib.request

log = logging.getLogger("ytdl-ui")
log.addHandler(logging.NullHandler())
log.setLevel(logging.INFO)
log.propagate = False
LOG_DIR = os.path.join(tempfile.gettempdir(), "ytdl-ui")
LOG_PATH = os.path.join(LOG_DIR, f"ytdl-ui-{os.getpid()}.log")


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


def _runtime_bin_dirs():
    directories = []
    bundle_dir = getattr(sys, "_MEIPASS", None)
    if getattr(sys, "frozen", False) and bundle_dir:
        directories.append(bundle_dir)
    executable_dir = os.path.dirname(os.path.abspath(sys.executable))
    if executable_dir not in directories:
        directories.append(executable_dir)
    return directories


def _find_executable(name):
    """Prefer bundled or venv executables before searching PATH."""
    for bin_dir in _runtime_bin_dirs():
        for candidate in (name, name + ".exe"):
            local = os.path.join(bin_dir, candidate)
            if os.path.isfile(local) and os.access(local, os.X_OK):
                return local
    return shutil.which(name)


YT_DLP = _find_executable("yt-dlp") or "yt-dlp"


def _js_runtime_opts():
    """Pass the bundled or venv Deno path explicitly when available."""
    for bin_dir in _runtime_bin_dirs():
        for candidate in ("deno", "deno.exe"):
            deno = os.path.join(bin_dir, candidate)
            if os.path.isfile(deno) and os.access(deno, os.X_OK):
                return ["--js-runtimes", f"deno:{deno}"]
    return []


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
    "  - Update yt-dlp: pip install -U yt-dlp\n"
    "  - Avoid checking many URLs in quick succession."
)

RATE_LIMIT_OPTS = [
    "--retries", "10",
    "--retry-sleep", "exp=1:120",
    "--sleep-requests", "1",
]
DEFAULT_FORMAT_LABEL = "best (default)"
THUMB_PRINT_PREFIX = "THUMB:"
THUMB_PRINT_TEMPLATE = THUMB_PRINT_PREFIX + "%(thumbnail)s"
THUMB_MAX_WIDTH = 320
THUMB_MAX_HEIGHT = 180
THUMB_FETCH_TIMEOUT = 15
THUMB_MAX_BYTES = 5_000_000


def is_rate_limited(text):
    if not text:
        return False
    lowered = text.lower()
    return "429" in text or "too many requests" in lowered


def parse_formats(output):
    """Parse yt-dlp -F output into (format id, label) tuples."""
    if not output:
        return []
    formats = []
    seen_separator = False
    for line in output.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(THUMB_PRINT_PREFIX):
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


def run_download(*args):
    """Run yt-dlp and return the CompletedProcess, or None if not found."""
    cmd = [YT_DLP, *JS_RUNTIME_OPTS, *RATE_LIMIT_OPTS, *args]
    log.info("run_download: starting: %s", " ".join(cmd))
    try:
        ret = subprocess.run(
            cmd, capture_output=True, encoding="utf-8", errors="replace",
        )
        log.info(
            "run_download: finished rc=%s (stdout %d chars, stderr %d chars)",
            ret.returncode, len(ret.stdout or ""), len(ret.stderr or ""),
        )
        if ret.returncode != 0:
            log.error("run_download: yt-dlp failed rc=%s stderr=%r", ret.returncode, ret.stderr)
        return ret
    except FileNotFoundError:
        log.error("run_download: yt-dlp not found at %s", YT_DLP)
        return None


def run_download_live(*args, on_line=None):
    """Run yt-dlp with live line-by-line output via on_line callback."""
    cmd = [YT_DLP, *JS_RUNTIME_OPTS, *RATE_LIMIT_OPTS, *args]
    log.info("run_download_live: starting: %s", " ".join(cmd))
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError:
        log.error("run_download_live: yt-dlp not found at %s", YT_DLP)
        return None

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
    return proc.returncode, stderr
