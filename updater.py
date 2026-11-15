"""Tk-free yt-dlp self-updater for the frozen (PyInstaller) builds.

Checks the latest stable yt-dlp GitHub release, downloads the platform's
official build, verifies it against the release's SHA2-256SUMS, smoke-tests it
with `--version`, then swaps it into place with a rollback on failure.
"""

import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass

import core
from core import UPDATE_LOCATION_BUNDLED, UPDATE_LOCATION_USER, log

RELEASES_API = "https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest"
DOWNLOAD_PREFIX = "https://github.com/yt-dlp/yt-dlp/releases/download/"
SUMS_NAME = "SHA2-256SUMS"
# Official release assets that match how each build ships yt-dlp: a onefile
# exe on Windows, a one-dir build (executable + _internal/) on macOS.
ASSETS = {"win32": "yt-dlp.exe", "darwin": "yt-dlp_macos.zip"}
MACOS_EXECUTABLE = "yt-dlp_macos"
API_TIMEOUT = 20
DOWNLOAD_TIMEOUT = 60
VERSION_TIMEOUT = 120
MAX_ASSET_BYTES = 300_000_000
MAX_SUMS_BYTES = 1_000_000
_CHUNK = 1024 * 1024


class UpdateError(Exception):
    """An update step failed; the message is shown to the user."""


@dataclass(frozen=True)
class Release:
    version: str
    asset_name: str
    asset_url: str
    sums_url: str


@dataclass(frozen=True)
class UpdateResult:
    version: str
    executable: str
    restart_required: bool


def asset_name(platform=None):
    return ASSETS.get(platform or sys.platform)


def is_supported():
    """Only frozen Windows/macOS builds manage their own yt-dlp."""
    return core.is_frozen() and asset_name() is not None


def unsupported_reason():
    if not core.is_frozen():
        return (
            "ytdl-ui is running from source, so yt-dlp comes from the venv.\n"
            "Update it with:\n  pip install -U yt-dlp"
        )
    return "The in-app yt-dlp updater supports the Windows and macOS builds only."


parse_version = core.yt_dlp_version_key


def is_newer(latest, current):
    latest_t = parse_version(latest)
    if latest_t is None:
        return False
    current_t = parse_version(current) if current else None
    return current_t is None or latest_t > current_t


def parse_release(data, platform=None):
    """Turn a GitHub release JSON object into a Release for this platform."""
    name = asset_name(platform)
    if not isinstance(data, dict) or not name:
        raise UpdateError("Unexpected response from GitHub.")
    version = data.get("tag_name")
    if parse_version(version) is None:
        raise UpdateError(f"Unrecognized yt-dlp release tag: {version!r}")
    urls = {
        asset.get("name"): asset.get("browser_download_url")
        for asset in data.get("assets") or []
        if isinstance(asset, dict)
    }
    for needed in (name, SUMS_NAME):
        url = urls.get(needed)
        # Only accept assets from the official repo's release downloads.
        if not isinstance(url, str) or not url.startswith(DOWNLOAD_PREFIX):
            raise UpdateError(f"yt-dlp {version} has no {needed} download.")
    return Release(version, name, urls[name], urls[SUMS_NAME])


def _open(url, timeout):
    request = urllib.request.Request(url, headers={"User-Agent": "ytdl-ui"})
    return urllib.request.urlopen(request, timeout=timeout)


def fetch_latest_release():
    try:
        with _open(RELEASES_API, API_TIMEOUT) as resp:
            data = json.loads(resp.read(MAX_SUMS_BYTES))
    except (OSError, ValueError) as exc:
        log.warning("fetch_latest_release: %s", exc)
        raise UpdateError(f"Could not check for yt-dlp updates:\n{exc}") from exc
    return parse_release(data)


def parse_sums(text):
    """Parse `sha256  filename` lines into {filename: lowercase hex digest}."""
    sums = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) == 2 and len(parts[0]) == 64:
            sums[parts[1].lstrip("*")] = parts[0].lower()
    return sums


def fetch_expected_sha256(release):
    try:
        with _open(release.sums_url, API_TIMEOUT) as resp:
            text = resp.read(MAX_SUMS_BYTES).decode("utf-8", "replace")
    except OSError as exc:
        raise UpdateError(f"Could not download {SUMS_NAME}:\n{exc}") from exc
    digest = parse_sums(text).get(release.asset_name)
    if not digest:
        raise UpdateError(f"{SUMS_NAME} has no entry for {release.asset_name}.")
    return digest


def download(url, dest, max_bytes=MAX_ASSET_BYTES):
    """Stream url to dest and return its SHA-256 hex digest."""
    digest = hashlib.sha256()
    total = 0
    try:
        with _open(url, DOWNLOAD_TIMEOUT) as resp, open(dest, "wb") as out:
            while chunk := resp.read(_CHUNK):
                total += len(chunk)
                if total > max_bytes:
                    raise UpdateError("The yt-dlp download is unexpectedly large.")
                digest.update(chunk)
                out.write(chunk)
    except OSError as exc:
        raise UpdateError(f"Could not download yt-dlp:\n{exc}") from exc
    return digest.hexdigest()


def extract_zip(zip_path, dest_dir):
    """Extract a zip, keeping exec bits and symlinks; refuse paths that escape."""
    root = os.path.realpath(dest_dir)

    def inside(path):
        return os.path.commonpath([root, os.path.realpath(path)]) == root

    with zipfile.ZipFile(zip_path) as archive:
        for info in archive.infolist():
            target = os.path.join(root, info.filename)
            if os.path.isabs(info.filename) or not inside(target):
                raise UpdateError(f"Unsafe path in yt-dlp archive: {info.filename}")
            mode = info.external_attr >> 16
            if info.is_dir():
                os.makedirs(target, exist_ok=True)
                continue
            os.makedirs(os.path.dirname(target), exist_ok=True)
            if stat.S_ISLNK(mode):
                link = archive.read(info).decode("utf-8")
                resolved = os.path.join(os.path.dirname(target), link)
                if os.path.isabs(link) or not inside(resolved):
                    raise UpdateError(f"Unsafe link in yt-dlp archive: {info.filename}")
                os.symlink(link, target)
                continue
            with archive.open(info) as src, open(target, "wb") as out:
                shutil.copyfileobj(src, out)
            if mode & 0o111:
                os.chmod(target, 0o755)


def install_target(location, platform=None):
    """The file (Windows) or folder (macOS) the update replaces."""
    platform = platform or sys.platform
    if location == UPDATE_LOCATION_BUNDLED:
        base = core._venv_bin_dir()
        target = (os.path.join(base, "yt-dlp.exe") if platform == "win32"
                  else os.path.join(base, "yt-dlp-runtime"))
    else:
        base = core.user_runtime_dir()
        target = os.path.join(base, "yt-dlp.exe") if platform == "win32" else base
    # In a macOS .app the bundled folder may be a symlink into Resources;
    # swap the real folder so the link keeps pointing at the new copy.
    return os.path.realpath(target)


def executable_in(target, platform=None):
    if (platform or sys.platform) == "win32":
        return target
    return os.path.join(target, "yt-dlp")


def stage(release, staging_dir, expected_sha256, platform=None):
    """Download and verify the asset; return the staged file/folder to install."""
    platform = platform or sys.platform
    asset_path = os.path.join(staging_dir, release.asset_name)
    actual = download(release.asset_url, asset_path)
    if actual != expected_sha256:
        raise UpdateError(
            f"Checksum mismatch for {release.asset_name}; the download was discarded.\n"
            f"expected {expected_sha256}\nactual   {actual}"
        )
    if platform == "win32":
        return asset_path
    unpacked = os.path.join(staging_dir, "unpacked")
    os.makedirs(unpacked)
    try:
        extract_zip(asset_path, unpacked)
    except (zipfile.BadZipFile, OSError) as exc:
        raise UpdateError(f"Could not unpack {release.asset_name}:\n{exc}") from exc
    for folder in (unpacked, *(os.path.join(unpacked, d) for d in os.listdir(unpacked))):
        exe = os.path.join(folder, MACOS_EXECUTABLE)
        if os.path.isfile(exe):
            # The app looks for `yt-dlp`; a one-dir build doesn't care about its name.
            os.replace(exe, os.path.join(folder, "yt-dlp"))
            return folder
    raise UpdateError(f"{release.asset_name} does not contain {MACOS_EXECUTABLE}.")


def staged_version(executable):
    try:
        ret = subprocess.run(
            [executable, "--version"], capture_output=True, encoding="utf-8",
            errors="replace", timeout=VERSION_TIMEOUT, **core.SUBPROCESS_FLAGS,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise UpdateError(f"The downloaded yt-dlp does not run:\n{exc}") from exc
    if ret.returncode != 0:
        raise UpdateError(f"The downloaded yt-dlp does not run:\n{ret.stderr.strip()}")
    return ret.stdout.strip()


def _remove(path):
    if os.path.isdir(path) and not os.path.islink(path):
        shutil.rmtree(path)
    elif os.path.lexists(path):
        os.remove(path)


def swap_into_place(staged, target):
    """Replace target with staged; restore the old copy if the move fails."""
    backup = target + ".old"
    try:
        _remove(backup)
    except OSError:
        # A previous old copy may still be locked (e.g. a running exe on Windows).
        backup = f"{target}.old-{os.getpid()}"
    had_old = os.path.lexists(target)
    if had_old:
        os.replace(target, backup)
    try:
        os.replace(staged, target)
    except OSError:
        if had_old:
            os.replace(backup, target)
        raise
    if had_old:
        try:
            _remove(backup)
        except OSError as exc:
            log.warning("swap_into_place: could not remove %s: %s", backup, exc)


def install_update(release, location, platform=None):
    """Download, verify and install release; return where it went."""
    platform = platform or sys.platform
    target = install_target(location, platform)
    parent = os.path.dirname(target)
    try:
        os.makedirs(parent, exist_ok=True)
        # Stage beside the target so the final swap is a same-volume rename.
        staging = tempfile.mkdtemp(prefix=".yt-dlp-update-", dir=parent)
    except OSError as exc:
        hint = ""
        if location == UPDATE_LOCATION_BUNDLED:
            hint = "\n\nEnable Help > Install yt-dlp updates per user and try again."
        raise UpdateError(f"Cannot write to {parent}:\n{exc}{hint}") from exc
    log.info("install_update: yt-dlp %s -> %s", release.version, target)
    try:
        expected = fetch_expected_sha256(release)
        staged = stage(release, staging, expected, platform)
        version = staged_version(executable_in(staged, platform))
        if parse_version(version) != parse_version(release.version):
            raise UpdateError(
                f"The downloaded yt-dlp reports version {version!r}, "
                f"expected {release.version}."
            )
        try:
            swap_into_place(staged, target)
        except OSError as exc:
            raise UpdateError(f"Could not replace {target}:\n{exc}") from exc
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    if location == UPDATE_LOCATION_USER:
        core.write_user_runtime_marker()
    else:
        # Drop a stale per-user copy so it can't shadow the bundled update later.
        shutil.rmtree(core.user_runtime_dir(), ignore_errors=True)
    executable = executable_in(target, platform)
    in_use = core.refresh_yt_dlp()
    # yt-dlp runs as a fresh process per check/download, so the new copy is
    # picked up immediately unless the app still resolves a different one.
    restart = os.path.realpath(in_use) != os.path.realpath(executable)
    return UpdateResult(release.version, executable, restart)


def result_message(result):
    text = f"yt-dlp {result.version} installed to:\n{result.executable}\n\n"
    if result.restart_required:
        return text + "Restart ytdl-ui to start using it."
    return text + "No restart needed; the next check or download uses it."
