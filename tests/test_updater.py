"""Tests for the in-app yt-dlp updater (updater.py) and its core.py hooks."""

import hashlib
import io
import json
import os
import stat
import subprocess
import zipfile

import pytest

import core
import updater

PREFIX = updater.DOWNLOAD_PREFIX + "2026.11.10/"


def _release_json(version="2026.11.10", names=("yt-dlp.exe", "yt-dlp_macos.zip")):
    assets = [{"name": n, "browser_download_url": PREFIX + n}
              for n in (*names, updater.SUMS_NAME)]
    return {"tag_name": version, "assets": assets}


@pytest.fixture
def dirs(monkeypatch, tmp_path):
    """Isolated settings folder (per-user target) and bundled-tools folder."""
    settings = tmp_path / "settings" / "ytdl-ui" / "settings.json"
    bundled = tmp_path / "app"
    bundled.mkdir()
    monkeypatch.setattr(core, "cookie_settings_path", lambda: str(settings))
    monkeypatch.setattr(core, "_venv_bin_dir", lambda: str(bundled))
    monkeypatch.setattr(core, "is_frozen", lambda: True)
    monkeypatch.setattr(core.os, "access", lambda *_args: True)
    monkeypatch.setattr(core, "YT_DLP", "yt-dlp")
    return tmp_path, bundled


def _serve(monkeypatch, files):
    """Make updater._open return in-memory bytes for known URLs."""
    def fake_open(url, _timeout):
        if url not in files:
            raise OSError(f"unexpected URL {url}")
        return io.BytesIO(files[url])
    monkeypatch.setattr(updater, "_open", fake_open)


def _fake_version(monkeypatch, version="2026.11.10"):
    calls = []

    def fake_run(cmd, **_kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, version + "\n", "")
    monkeypatch.setattr(updater.subprocess, "run", fake_run)
    return calls


def _sums(**assets):
    return "".join(
        f"{hashlib.sha256(data).hexdigest()}  {name}\n" for name, data in assets.items()
    ).encode()


def _macos_zip():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        exe = zipfile.ZipInfo("yt-dlp_macos")
        exe.external_attr = (stat.S_IFREG | 0o755) << 16
        archive.writestr(exe, b"new-exe")
        archive.writestr("_internal/lib.dylib", b"lib")
    return buf.getvalue()


class TestReleaseParsing:
    def test_picks_platform_asset_and_sums(self):
        release = updater.parse_release(_release_json(), "win32")
        assert release == updater.Release(
            "2026.11.10", "yt-dlp.exe", PREFIX + "yt-dlp.exe",
            PREFIX + updater.SUMS_NAME,
        )
        assert updater.parse_release(_release_json(), "darwin").asset_name == "yt-dlp_macos.zip"

    def test_rejects_download_from_other_host(self):
        data = _release_json()
        data["assets"][0]["browser_download_url"] = "https://evil.example/yt-dlp.exe"
        with pytest.raises(updater.UpdateError):
            updater.parse_release(data, "win32")

    def test_rejects_missing_asset(self):
        with pytest.raises(updater.UpdateError):
            updater.parse_release(_release_json(names=()), "win32")

    def test_rejects_bad_tag(self):
        with pytest.raises(updater.UpdateError):
            updater.parse_release(_release_json(version="latest"), "win32")

    def test_parse_sums(self):
        digest = "a" * 64
        text = f"{digest}  yt-dlp.exe\n{'B' * 64} *yt-dlp_macos.zip\nnot a line\n"
        assert updater.parse_sums(text) == {
            "yt-dlp.exe": digest, "yt-dlp_macos.zip": "b" * 64,
        }

    @pytest.mark.parametrize("latest, current, expected", [
        ("2026.11.10", "2026.10.26", True),
        ("2026.11.10", "2026.11.10", False),
        ("2026.11.10", "2026.11.10.1234", False),
        ("2026.11.10", None, True),
        ("garbage", "2026.10.26", False),
    ])
    def test_is_newer(self, latest, current, expected):
        assert updater.is_newer(latest, current) is expected

    def test_fetch_latest_release_wraps_network_errors(self, monkeypatch):
        _serve(monkeypatch, {})
        with pytest.raises(updater.UpdateError, match="Could not check"):
            updater.fetch_latest_release()


class TestSupport:
    def test_not_supported_from_source(self, monkeypatch):
        monkeypatch.setattr(core, "is_frozen", lambda: False)
        assert updater.is_supported() is False
        assert "pip install -U yt-dlp" in updater.unsupported_reason()

    def test_supported_on_frozen_windows(self, monkeypatch):
        monkeypatch.setattr(core, "is_frozen", lambda: True)
        monkeypatch.setattr(updater.sys, "platform", "win32")
        assert updater.is_supported() is True


class TestInstallTarget:
    def test_windows_targets(self, dirs):
        tmp_path, bundled = dirs
        assert updater.install_target("bundled", "win32") == os.path.realpath(
            bundled / "yt-dlp.exe")
        assert updater.install_target("user", "win32") == os.path.realpath(
            os.path.join(core.user_runtime_dir(), "yt-dlp.exe"))

    def test_macos_targets_are_folders(self, dirs):
        _tmp, bundled = dirs
        assert updater.install_target("bundled", "darwin") == os.path.realpath(
            bundled / "yt-dlp-runtime")
        assert updater.install_target("user", "darwin") == os.path.realpath(
            core.user_runtime_dir())

    def test_resolves_symlinked_bundle_folder(self, dirs, tmp_path):
        _tmp, bundled = dirs
        real = tmp_path / "Resources" / "yt-dlp-runtime"
        real.mkdir(parents=True)
        os.symlink(real, bundled / "yt-dlp-runtime")
        assert updater.install_target("bundled", "darwin") == os.path.realpath(real)


class TestExtractZip:
    def test_keeps_exec_bit_and_symlinks(self, tmp_path):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as archive:
            exe = zipfile.ZipInfo("yt-dlp_macos")
            exe.external_attr = (stat.S_IFREG | 0o755) << 16
            archive.writestr(exe, b"exe")
            archive.writestr("_internal/real.dylib", b"lib")
            link = zipfile.ZipInfo("_internal/link.dylib")
            link.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(link, "real.dylib")
        zip_path = tmp_path / "a.zip"
        zip_path.write_bytes(buf.getvalue())
        out = tmp_path / "out"
        out.mkdir()

        updater.extract_zip(zip_path, out)

        assert os.access(out / "yt-dlp_macos", os.X_OK)
        assert os.readlink(out / "_internal" / "link.dylib") == "real.dylib"

    @pytest.mark.parametrize("name, link", [("../evil", None), ("x", "../../evil")])
    def test_rejects_escaping_paths(self, tmp_path, name, link):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as archive:
            info = zipfile.ZipInfo(name)
            if link:
                info.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(info, link or "data")
        zip_path = tmp_path / "a.zip"
        zip_path.write_bytes(buf.getvalue())
        out = tmp_path / "out"
        out.mkdir()
        with pytest.raises(updater.UpdateError, match="Unsafe"):
            updater.extract_zip(zip_path, out)


class TestSwapIntoPlace:
    def test_replaces_and_removes_backup(self, tmp_path):
        target, staged = tmp_path / "yt-dlp.exe", tmp_path / "new.exe"
        target.write_text("old")
        staged.write_text("new")
        updater.swap_into_place(str(staged), str(target))
        assert target.read_text() == "new"
        assert not (tmp_path / "yt-dlp.exe.old").exists()

    def test_restores_old_copy_when_move_fails(self, tmp_path, monkeypatch):
        target = tmp_path / "yt-dlp.exe"
        target.write_text("old")
        real_replace = os.replace

        def flaky_replace(src, dst):
            if str(src).endswith("missing"):
                raise OSError("locked")
            real_replace(src, dst)
        monkeypatch.setattr(updater.os, "replace", flaky_replace)
        with pytest.raises(OSError):
            updater.swap_into_place(str(tmp_path / "missing"), str(target))
        assert target.read_text() == "old"


class TestInstallUpdate:
    def test_windows_per_user_install(self, dirs, monkeypatch):
        _tmp, bundled = dirs
        (bundled / "yt-dlp.exe").write_bytes(b"bundled")
        exe = b"new-exe"
        _serve(monkeypatch, {
            PREFIX + "yt-dlp.exe": exe,
            PREFIX + updater.SUMS_NAME: _sums(**{"yt-dlp.exe": exe}),
        })
        calls = _fake_version(monkeypatch)
        release = updater.parse_release(_release_json(), "win32")

        result = updater.install_update(release, "user", "win32")

        installed = os.path.join(core.user_runtime_dir(), "yt-dlp.exe")
        assert result == updater.UpdateResult("2026.11.10", installed, False)
        assert open(installed, "rb").read() == exe
        assert (bundled / "yt-dlp.exe").read_bytes() == b"bundled"
        assert core.YT_DLP == installed
        # The smoke test ran the staged copy, not the installed one.
        assert calls[0][0] != installed and calls[0][1] == "--version"
        assert sorted(os.listdir(core.user_runtime_dir())) == [
            "installed-by.json", "yt-dlp.exe"]
        assert "No restart needed" in updater.result_message(result)

    def test_macos_bundled_install_replaces_folder(self, dirs, monkeypatch):
        _tmp, bundled = dirs
        runtime = bundled / "yt-dlp-runtime"
        (runtime / "_internal").mkdir(parents=True)
        (runtime / "yt-dlp").write_bytes(b"old")
        (runtime / "_internal" / "stale.so").write_bytes(b"stale")
        archive = _macos_zip()
        _serve(monkeypatch, {
            PREFIX + "yt-dlp_macos.zip": archive,
            PREFIX + updater.SUMS_NAME: _sums(**{"yt-dlp_macos.zip": archive}),
        })
        _fake_version(monkeypatch)
        core.save_update_location("bundled")
        release = updater.parse_release(_release_json(), "darwin")

        result = updater.install_update(release, "bundled", "darwin")

        assert result.executable == os.path.join(os.path.realpath(runtime), "yt-dlp")
        assert result.restart_required is False
        assert (runtime / "yt-dlp").read_bytes() == b"new-exe"
        assert sorted(os.listdir(runtime / "_internal")) == ["lib.dylib"]
        assert sorted(os.listdir(bundled)) == ["yt-dlp-runtime"]

    def test_checksum_mismatch_leaves_target_untouched(self, dirs, monkeypatch):
        _tmp, bundled = dirs
        (bundled / "yt-dlp.exe").write_bytes(b"bundled")
        _serve(monkeypatch, {
            PREFIX + "yt-dlp.exe": b"tampered",
            PREFIX + updater.SUMS_NAME: _sums(**{"yt-dlp.exe": b"genuine"}),
        })
        calls = _fake_version(monkeypatch)
        release = updater.parse_release(_release_json(), "win32")

        with pytest.raises(updater.UpdateError, match="Checksum mismatch"):
            updater.install_update(release, "bundled", "win32")

        assert (bundled / "yt-dlp.exe").read_bytes() == b"bundled"
        assert os.listdir(bundled) == ["yt-dlp.exe"]  # staging cleaned up
        assert calls == []  # never ran the unverified download

    def test_version_mismatch_leaves_target_untouched(self, dirs, monkeypatch):
        _tmp, bundled = dirs
        (bundled / "yt-dlp.exe").write_bytes(b"bundled")
        exe = b"new-exe"
        _serve(monkeypatch, {
            PREFIX + "yt-dlp.exe": exe,
            PREFIX + updater.SUMS_NAME: _sums(**{"yt-dlp.exe": exe}),
        })
        _fake_version(monkeypatch, version="2020.01.01")
        release = updater.parse_release(_release_json(), "win32")

        with pytest.raises(updater.UpdateError, match="reports version"):
            updater.install_update(release, "bundled", "win32")
        assert (bundled / "yt-dlp.exe").read_bytes() == b"bundled"

    def test_unwritable_bundle_suggests_per_user(self, dirs, monkeypatch):
        def deny(*_args, **_kwargs):
            raise PermissionError("denied")
        monkeypatch.setattr(updater.tempfile, "mkdtemp", deny)
        release = updater.parse_release(_release_json(), "win32")
        with pytest.raises(updater.UpdateError, match="per user"):
            updater.install_update(release, "bundled", "win32")


class TestCoreUpdateHooks:
    def test_saving_settings_keeps_other_keys(self, dirs):
        assert core.save_update_location("bundled") is True
        assert core.save_cookie_settings(True, "edge") is True
        assert core.load_update_location() == "bundled"
        assert core.load_cookie_settings() == (True, "edge")

    def test_update_location_defaults_to_user(self, dirs):
        assert core.load_update_location() == "user"
        assert core.save_update_location("elsewhere") is False

    def _install_user_copy(self, app_version=core.APP_VERSION):
        folder = core.user_runtime_dir()
        os.makedirs(folder)
        open(os.path.join(folder, "yt-dlp"), "w").close()
        with open(os.path.join(folder, "installed-by.json"), "w") as marker:
            json.dump({"app_version": app_version}, marker)
        return os.path.join(folder, "yt-dlp")

    def test_frozen_build_prefers_user_copy(self, dirs):
        _tmp, bundled = dirs
        (bundled / "yt-dlp").touch()
        user_copy = self._install_user_copy()
        assert core.resolve_yt_dlp() == user_copy
        core.save_update_location("bundled")
        assert core.resolve_yt_dlp() == str(bundled / "yt-dlp")

    def test_source_run_ignores_user_copy(self, dirs, monkeypatch):
        _tmp, bundled = dirs
        (bundled / "yt-dlp").touch()
        self._install_user_copy()
        monkeypatch.setattr(core, "is_frozen", lambda: False)
        assert core.resolve_yt_dlp() == str(bundled / "yt-dlp")

    def test_copy_from_other_app_version_waits_for_reconcile(self, dirs):
        _tmp, bundled = dirs
        (bundled / "yt-dlp").touch()
        self._install_user_copy(app_version="2000.01.01")
        assert core.resolve_yt_dlp() == str(bundled / "yt-dlp")

    @pytest.mark.parametrize("user_version, keeps", [
        ("2026.11.10", True), ("2026.01.01", False),
    ])
    def test_reconcile_keeps_only_newer_user_copy(
        self, dirs, monkeypatch, user_version, keeps,
    ):
        _tmp, bundled = dirs
        (bundled / "yt-dlp").touch()
        user_copy = self._install_user_copy(app_version="2000.01.01")
        versions = {user_copy: user_version, str(bundled / "yt-dlp"): "2026.10.26"}
        monkeypatch.setattr(
            core, "get_yt_dlp_version",
            lambda timeout=90, executable=None: versions[executable],
        )

        core.reconcile_user_yt_dlp()

        assert os.path.exists(user_copy) is keeps
        assert core.YT_DLP == (user_copy if keeps else str(bundled / "yt-dlp"))

    def test_status_text_mentions_available_update(self):
        assert core.version_status_text("2026.10.26", "2026.11.10").endswith(
            "yt-dlp 2026.10.26 · yt-dlp 2026.11.10 available (Help > Update yt-dlp...)"
        )
