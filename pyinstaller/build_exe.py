"""Build a standalone ytdl-ui executable with PyInstaller.

The script validates the environment first so the common failures are caught
early: missing PyInstaller, missing project files, and missing venv runtime.
"""

import argparse
import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SPEC_DIR = REPO_ROOT / "pyinstaller"
SPEC = SPEC_DIR / "ytdl_ui.spec"
MAIN = REPO_ROOT / "main.py"


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
    """Ensure the project files and PyInstaller package are present."""
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


def build_command(python: Path, onefile: bool, clean: bool, windowed: bool) -> list[str]:
    """Create the PyInstaller command for one-file or one-dir builds."""
    cmd = [str(python), "-m", "PyInstaller"]
    if clean:
        cmd.append("--clean")
    if windowed:
        cmd.append("--windowed")
    if onefile:
        cmd.extend(["--onefile", "--noconfirm", "--specpath", str(SPEC_DIR), "--name", "ytdl-ui"])
        cmd.append(str(MAIN))
        return cmd

    cmd.extend(["--specpath", str(SPEC_DIR), str(SPEC)])
    return cmd


def main():
    parser = argparse.ArgumentParser(description="Build the ytdl-ui PyInstaller bundle.")
    parser.add_argument("--onefile", action="store_true", help="Create a single-file executable")
    parser.add_argument("--windowed", action="store_true", help="Hide the console window for the Tk GUI build")
    parser.add_argument("--clean", action="store_true", help="Remove cached PyInstaller build data")
    args = parser.parse_args()

    python = preferred_python()
    try:
        ensure_tools(python)
    except (FileNotFoundError, RuntimeError) as exc:
        print(f"Build pre-check failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    if args.onefile:
        print(f"Using Python: {python}")
    else:
        print(f"Using Python: {python}")

    cmd = build_command(python, args.onefile, args.clean, args.windowed)
    print("Running:", " ".join(cmd))
    subprocess.check_call(cmd)


if __name__ == "__main__":
    main()
