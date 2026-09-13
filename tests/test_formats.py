"""Unit tests for the pure (Tk-free) logic in main.py.

main.py guards its Tk construction under `if __name__ == "__main__"`, so it can
be imported here without launching a UI. These tests cover format parsing,
format-id extraction, and rate-limit detection.
"""

import main


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
        formats = main.parse_formats(SAMPLE_F_OUTPUT)
        ids = [fid for fid, _label in formats]
        assert ids == ["sb0", "139", "140", "137", "18"]

    def test_skips_preamble_and_header(self):
        formats = main.parse_formats(SAMPLE_F_OUTPUT)
        # No preamble/header tokens leak in as format ids.
        ids = [fid for fid, _label in formats]
        assert "[youtube]" not in ids
        assert "[info]" not in ids
        assert "ID" not in ids

    def test_label_starts_with_id_and_keeps_details(self):
        formats = dict(main.parse_formats(SAMPLE_F_OUTPUT))
        assert formats["137"].startswith("137")
        assert "1920x1080" in formats["137"]
        assert "video only" in formats["137"]

    def test_non_numeric_id_preserved(self):
        # Storyboard rows use ids like "sb0"; we must not assume digits.
        ids = [fid for fid, _label in main.parse_formats(SAMPLE_F_OUTPUT)]
        assert "sb0" in ids

    def test_empty_input_returns_empty_list(self):
        assert main.parse_formats("") == []
        assert main.parse_formats(None) == []

    def test_output_without_separator_returns_empty(self):
        # Without the dashed separator there are no format rows to parse.
        text = "[youtube] Extracting URL: ...\n[info] Available formats:\n"
        assert main.parse_formats(text) == []

    def test_blank_lines_are_ignored(self):
        text = (
            "ID EXT\n"
            "----------\n"
            "\n"
            "137 mp4 1080p\n"
            "\n"
            "140 m4a audio only\n"
        )
        ids = [fid for fid, _label in main.parse_formats(text)]
        assert ids == ["137", "140"]


class TestFormatIdFromLabel:
    def test_default_label_returns_none(self):
        assert main.format_id_from_label(main.DEFAULT_FORMAT_LABEL) is None

    def test_empty_or_none_returns_none(self):
        assert main.format_id_from_label("") is None
        assert main.format_id_from_label(None) is None

    def test_picked_label_returns_leading_id(self):
        assert main.format_id_from_label("137  mp4 1920x1080 video only") == "137"

    def test_non_numeric_id(self):
        assert main.format_id_from_label("sb0  mhtml 48x27 storyboard") == "sb0"

    def test_roundtrip_with_parse_formats(self):
        # Every label produced by parse_formats maps back to its own id.
        for fid, label in main.parse_formats(SAMPLE_F_OUTPUT):
            assert main.format_id_from_label(label) == fid


class TestIsRateLimited:
    def test_detects_429_code(self):
        assert main.is_rate_limited("ERROR: HTTP Error 429: blah") is True

    def test_detects_too_many_requests_phrase(self):
        assert main.is_rate_limited("Server said: Too Many Requests") is True

    def test_case_insensitive_phrase(self):
        assert main.is_rate_limited("too many requests") is True

    def test_normal_output_not_flagged(self):
        assert main.is_rate_limited("Downloading webpage") is False

    def test_empty_or_none_not_flagged(self):
        assert main.is_rate_limited("") is False
        assert main.is_rate_limited(None) is False
