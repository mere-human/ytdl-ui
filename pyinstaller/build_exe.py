"""Build a standalone ytdl-ui directory distribution with PyInstaller.

The script validates the environment first so the common failures are caught
early: missing PyInstaller, yt-dlp, Deno, or project files.
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SPEC_DIR = REPO_ROOT / "pyinstaller"
SPEC = SPEC_DIR / "ytdl_ui.spec"
MAIN = REPO_ROOT / "main.py"
BUILD_DIR = REPO_ROOT / "build"
YTDLP_DIST_DIR = BUILD_DIR / "yt-dlp-runtime"


def preferred_python() -> Path:
    """Prefer the project .venv interpreter when available."""
    candidates = [
        REPO_ROOT / ".venv" / "Scripts" / "python.exe",
        REPO_ROOT / ".venv" / "bin" / "python",
        Path(sys.executable),
    ]
    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate
    return Path(sys.executable)


def ensure_tools(python: Path):
    """Ensure the build dependencies are present."""
    if sys.platform != "win32":
        raise RuntimeError("This build helper currently targets Windows only.")
    if not MAIN.exists():
        raise FileNotFoundError(f"Project entry point not found: {MAIN}")
    if not SPEC.exists():
        raise FileNotFoundError(f"PyInstaller spec not found: {SPEC}")

    result = subprocess.run(
        [str(python), "-c", "import PyInstaller; print(PyInstaller.__version__)"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "PyInstaller is not installed in the selected Python environment. "
            "Install it with: python -m pip install pyinstaller"
        )

    result = subprocess.run(
        [
            str(python), "-c",
            "import pathlib, yt_dlp; "
            "print(pathlib.Path(yt_dlp.__file__).with_name('__main__.py'))",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "yt-dlp is not installed in the selected Python environment. "
            "Install it with: python -m pip install -r requirements.txt"
        )
    if not result.stdout.strip() or not Path(result.stdout.strip()).is_file():
        raise RuntimeError("Could not locate yt-dlp's Python module entry point.")

    deno_candidates = [Path(python).resolve().parent / "deno.exe"]
    deno_from_path = shutil.which("deno.exe") or shutil.which("deno")
    if deno_from_path:
        deno_candidates.append(Path(deno_from_path))
    if not any(candidate.is_file() for candidate in deno_candidates):
        raise RuntimeError(
            "Deno is not installed in the selected environment. "
            "Install it with: python -m pip install -r requirements.txt"
        )


def build_yt_dlp(python: Path, clean: bool):
    """Freeze yt-dlp into a standalone Windows executable for the app bundle."""
    result = subprocess.run(
        [
            str(python), "-c",
            "import pathlib, yt_dlp; "
            "print(pathlib.Path(yt_dlp.__file__).with_name('__main__.py'))",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    entrypoint = Path(result.stdout.strip())
    cmd = [str(python), "-m", "PyInstaller"]
    if clean:
        cmd.append("--clean")
    cmd.extend([
        "--onefile", "--noconfirm", "--name", "yt-dlp",
        "--distpath", str(YTDLP_DIST_DIR),
        "--workpath", str(BUILD_DIR / "yt-dlp-work"),
        "--specpath", str(BUILD_DIR / "yt-dlp-spec"),
        "--collect-all", "yt_dlp", str(entrypoint),
    ])
    print("Building standalone yt-dlp runtime:", " ".join(cmd))
    subprocess.check_call(cmd, cwd=REPO_ROOT)


def build_command(python: Path, clean: bool) -> list[str]:
    """Create the PyInstaller command for the Windows directory bundle."""
    cmd = [str(python), "-m", "PyInstaller"]
    if clean:
        cmd.append("--clean")
    cmd.extend([
        "--noconfirm",
        "--distpath", str(REPO_ROOT / "dist"),
        "--workpath", str(BUILD_DIR / "ytdl-ui-work"),
        str(SPEC),
    ])
    return cmd


def main():
    parser = argparse.ArgumentParser(description="Build the Windows ytdl-ui directory bundle.")
    parser.add_argument("--clean", action="store_true", help="Remove cached PyInstaller build data")
    args = parser.parse_args()

    python = preferred_python()
    try:
        ensure_tools(python)
    except (FileNotFoundError, RuntimeError) as exc:
        print(f"Build pre-check failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    print(f"Using Python: {python}")
    build_yt_dlp(python, args.clean)
    cmd = build_command(python, args.clean)
    print("Running:", " ".join(cmd))
    subprocess.check_call(cmd, cwd=REPO_ROOT)


if __name__ == "__main__":
    main()
