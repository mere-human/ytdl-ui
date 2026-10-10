"""Unit tests for the Tk-free logic in core.py."""

import os
import subprocess
import sys

import core


# A realistic `yt-dlp -F` capture: preamble lines, a header row, a dashed
# separator, then one row per format. Includes a storyboard (non-numeric id),
# audio-only, video-only, and a combined (progressive) row.
SAMPLE_F_OUTPUT = """\
[youtube] Extracting URL: https://youtu.be/dQw4w9WgXcQ
[youtube] dQw4w9WgXcQ: Downloading webpage
[info] Available formats for dQw4w9WgXcQ:
ID  EXT   RESOLUTION FPS CH |   FILESIZE   TBR PROTO | VCODEC       MORE INFO
------------------------------------------------------------------------------
sb0 mhtml 48x27        0    |                  mhtml | images       storyboard
139 m4a   audio only      2 |    1.31MiB   49k https | audio only   low, m4a_dash
140 m4a   audio only      2 |    3.50MiB  130k https | audio only   medium
137 mp4   1920x1080   30    |   45.00MiB 1200k https | avc1.640028  video only
18  mp4   640x360     30  2 |   10.00MiB  200k https | avc1.42001E  360p
"""


class TestParseFormats:
    def test_parses_all_format_rows(self):
        formats = core.parse_formats(SAMPLE_F_OUTPUT)
        ids = [fid for fid, _label in formats]
        assert ids == ["sb0", "139", "140", "137", "18"]

    def test_skips_preamble_and_header(self):
        formats = core.parse_formats(SAMPLE_F_OUTPUT)
        # No preamble/header tokens leak in as format ids.
        ids = [fid for fid, _label in formats]
        assert "[youtube]" not in ids
        assert "[info]" not in ids
        assert "ID" not in ids

    def test_label_starts_with_id_and_keeps_details(self):
        formats = dict(core.parse_formats(SAMPLE_F_OUTPUT))
        assert formats["137"].startswith("137")
        assert "1920x1080" in formats["137"]
        assert "video only" in formats["137"]

    def test_non_numeric_id_preserved(self):
        # Storyboard rows use ids like "sb0"; we must not assume digits.
        ids = [fid for fid, _label in core.parse_formats(SAMPLE_F_OUTPUT)]
        assert "sb0" in ids

    def test_empty_input_returns_empty_list(self):
        assert core.parse_formats("") == []
        assert core.parse_formats(None) == []

    def test_output_without_separator_returns_empty(self):
        # Without the dashed separator there are no format rows to parse.
        text = "[youtube] Extracting URL: ...\n[info] Available formats:\n"
        assert core.parse_formats(text) == []

    def test_blank_lines_are_ignored(self):
        text = (
            "ID EXT\n"
            "----------\n"
            "\n"
            "137 mp4 1080p\n"
            "\n"
            "140 m4a audio only\n"
        )
        ids = [fid for fid, _label in core.parse_formats(text)]
        assert ids == ["137", "140"]

    def test_skips_thumb_print_line(self):
        text = (
            SAMPLE_F_OUTPUT
            + "\nTHUMB:https://i.ytimg.com/vi/dQw4w9WgXcQ/maxresdefault.jpg\n"
        )
        ids = [fid for fid, _label in core.parse_formats(text)]
        assert ids == ["sb0", "139", "140", "137", "18"]


class TestFormatIdFromLabel:
    def test_default_label_returns_none(self):
        assert core.format_id_from_label(core.DEFAULT_FORMAT_LABEL) is None

    def test_empty_or_none_returns_none(self):
        assert core.format_id_from_label("") is None
        assert core.format_id_from_label(None) is None

    def test_picked_label_returns_leading_id(self):
        assert core.format_id_from_label("137  mp4 1920x1080 video only") == "137"

    def test_non_numeric_id(self):
        assert core.format_id_from_label("sb0  mhtml 48x27 storyboard") == "sb0"

    def test_roundtrip_with_parse_formats(self):
        # Every label produced by parse_formats maps back to its own id.
        for fid, label in core.parse_formats(SAMPLE_F_OUTPUT):
            assert core.format_id_from_label(label) == fid


class TestIsRateLimited:
    def test_detects_429_code(self):
        assert core.is_rate_limited("ERROR: HTTP Error 429: blah") is True

    def test_detects_too_many_requests_phrase(self):
        assert core.is_rate_limited("Server said: Too Many Requests") is True

    def test_case_insensitive_phrase(self):
        assert core.is_rate_limited("too many requests") is True

    def test_normal_output_not_flagged(self):
        assert core.is_rate_limited("Downloading webpage") is False

    def test_empty_or_none_not_flagged(self):
        assert core.is_rate_limited("") is False
        assert core.is_rate_limited(None) is False


class TestOutputTemplate:
    def test_none_or_empty_returns_none(self):
        assert core.output_template(None) is None
        assert core.output_template("") is None

    def test_joins_dir_with_default_pattern(self):
        template = core.output_template(os.path.join("home", "user", "Downloads"))
        assert template == os.path.join(
            "home", "user", "Downloads", "%(title)s [%(id)s].%(ext)s"
        )


class TestOutputArgs:
    def test_none_or_empty_returns_empty_list(self):
        assert core.output_args(None) == []
        assert core.output_args("") == []

    def test_builds_dash_o_args(self):
        args = core.output_args("/tmp/dl")
        assert args[0] == "-o"
        assert args[1] == core.output_template("/tmp/dl")


class TestDefaultOutputDir:
    def test_returns_existing_directory(self):
        # Whatever it picks (Downloads or cwd), it must be a real directory.
        assert os.path.isdir(core.default_output_dir())

    def test_falls_back_to_cwd_without_downloads(self, monkeypatch, tmp_path):
        # Point HOME at a dir with no Downloads folder -> fall back to cwd.
        monkeypatch.setenv("HOME", str(tmp_path))
        # expanduser on some platforms also consults USERPROFILE; align it.
        monkeypatch.setenv("USERPROFILE", str(tmp_path))
        monkeypatch.chdir(tmp_path)
        assert core.default_output_dir() == os.getcwd()

    def test_prefers_downloads_when_present(self, monkeypatch, tmp_path):
        (tmp_path / "Downloads").mkdir()
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("USERPROFILE", str(tmp_path))
        assert core.default_output_dir() == str(tmp_path / "Downloads")


class TestIsValidUrl:
    def test_empty_or_none_is_invalid(self):
        assert core.is_valid_url("") is False
        assert core.is_valid_url(None) is False
        assert core.is_valid_url("   ") is False

    def test_plain_text_is_invalid(self):
        assert core.is_valid_url("not a url") is False

    def test_missing_scheme_is_invalid(self):
        assert core.is_valid_url("youtube.com/watch?v=x") is False

    def test_scheme_without_host_is_invalid(self):
        assert core.is_valid_url("http://") is False

    def test_non_http_scheme_is_invalid(self):
        assert core.is_valid_url("ftp://host/file") is False

    def test_http_and_https_with_host_are_valid(self):
        assert core.is_valid_url("http://youtu.be/dQw4w9WgXcQ") is True
        assert core.is_valid_url("https://www.youtube.com/watch?v=x") is True

    def test_surrounding_whitespace_is_tolerated(self):
        assert core.is_valid_url("  https://www.youtube.com/watch?v=x  ") is True


class TestParseThumbnailUrl:
    def test_extracts_prefixed_https_url(self):
        output = (
            SAMPLE_F_OUTPUT
            + "\nTHUMB:https://i.ytimg.com/vi/dQw4w9WgXcQ/maxresdefault.jpg\n"
        )
        assert (
            core.parse_thumbnail_url(output)
            == "https://i.ytimg.com/vi/dQw4w9WgXcQ/maxresdefault.jpg"
        )

    def test_ignores_na_and_empty(self):
        assert core.parse_thumbnail_url("THUMB:NA") is None
        assert core.parse_thumbnail_url("THUMB:") is None
        assert core.parse_thumbnail_url("") is None
        assert core.parse_thumbnail_url(None) is None

    def test_ignores_unrelated_output(self):
        assert core.parse_thumbnail_url(SAMPLE_F_OUTPUT) is None


class TestFitThumbnailSize:
    def test_scales_down_to_fit(self):
        # 800x600 -> limited by height 180 -> 240x180
        assert core.fit_thumbnail_size(800, 600) == (240, 180)

    def test_does_not_upscale(self):
        assert core.fit_thumbnail_size(80, 45) == (80, 45)

    def test_invalid_dimensions_fall_back_to_max(self):
        assert core.fit_thumbnail_size(0, 10) == (
            core.THUMB_MAX_WIDTH, core.THUMB_MAX_HEIGHT
        )


class TestFetchThumbnailBytes:
    def test_invalid_url_returns_none(self):
        assert core.fetch_thumbnail_bytes("not a url") is None

    def test_reads_body_from_urlopen(self, monkeypatch):
        body = b"fake-image-bytes"

        class _Resp:
            def read(self, n=-1):
                return body[:n] if n >= 0 else body

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        monkeypatch.setattr(core.urllib.request, "urlopen", lambda *a, **k: _Resp())
        assert core.fetch_thumbnail_bytes("https://example.com/t.jpg") == body

    def test_oversized_body_returns_none(self, monkeypatch):
        class _Resp:
            def read(self, n=-1):
                return b"x" * n

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        monkeypatch.setattr(core.urllib.request, "urlopen", lambda *a, **k: _Resp())
        assert core.fetch_thumbnail_bytes(
            "https://example.com/t.jpg", max_bytes=8
        ) is None

    def test_network_error_returns_none(self, monkeypatch):
        def _boom(*_a, **_k):
            raise core.urllib.error.URLError("nope")

        monkeypatch.setattr(core.urllib.request, "urlopen", _boom)
        assert core.fetch_thumbnail_bytes("https://example.com/t.jpg") is None


class TestDecodeThumbnail:
    def _png_bytes(self, w, h):
        from PIL import Image
        img = Image.new("RGB", (w, h), (255, 0, 0))
        buf = core.io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    def test_resizes_large_image(self):
        data = self._png_bytes(800, 600)
        img = core.decode_thumbnail(data)
        assert img is not None
        assert img.size == (240, 180)

    def test_garbage_bytes_return_none(self):
        assert core.decode_thumbnail(b"not-an-image") is None

    def test_empty_returns_none(self):
        assert core.decode_thumbnail(b"") is None
        assert core.decode_thumbnail(None) is None


class TestParseDownloadTarget:
    def test_extracts_destination_path(self):
        line = "[download] Destination: /tmp/My Video [abc123].mp4"
        assert core.parse_download_target(line) == "/tmp/My Video [abc123].mp4"

    def test_tolerates_surrounding_whitespace(self):
        line = "  [download] Destination: /tmp/v.mp4  \n"
        assert core.parse_download_target(line) == "/tmp/v.mp4"

    def test_progress_line_returns_none(self):
        assert core.parse_download_target("[download]  50.0% of 5.00MiB") is None

    def test_empty_or_none_returns_none(self):
        assert core.parse_download_target("") is None
        assert core.parse_download_target(None) is None


class TestPartialFileNote:
    def test_none_target_returns_none(self):
        assert core.partial_file_note(None) is None
        assert core.partial_file_note("") is None

    def test_points_at_target_when_no_part_file(self, tmp_path):
        target = str(tmp_path / "video [x].mp4")
        note = core.partial_file_note(target)
        assert target in note
        assert "Partial file left on disk" in note

    def test_prefers_dot_part_file_when_present(self, tmp_path):
        target = str(tmp_path / "video [x].mp4")
        part = target + ".part"
        # Create the .part file so the note should point at it.
        with open(part, "w") as fh:
            fh.write("partial")
        note = core.partial_file_note(target)
        assert part in note



class TestProcessController:
    """Exercise process cancellation with a short-lived stand-in process."""

    def _spawn_sleeper(self):
        return subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(30)"],
        )

    def test_no_active_proc_returns_false(self):
        controller = core.ProcessController()
        assert controller.stop() is False

    def test_terminates_registered_process(self):
        proc = self._spawn_sleeper()
        controller = core.ProcessController()
        controller.register(proc)
        try:
            assert controller.stop() is True
            # After stop returns, the process must be dead.
            assert proc.poll() is not None
            assert controller.was_cancelled() is True
        finally:
            if proc.poll() is None:
                proc.kill()
            controller.clear()

    def test_register_resets_cancelled_flag(self):
        proc = self._spawn_sleeper()
        controller = core.ProcessController()
        controller.register(proc)
        try:
            # A freshly registered process is not (yet) cancelled.
            assert controller.was_cancelled() is False
        finally:
            proc.kill()
            proc.wait()
            controller.clear()
