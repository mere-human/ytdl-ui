"""UI smoke tests for widget state behavior in ui.py.

These build the real widgets via ui.build_ui() on a headless Tk root (no
mainloop) and assert the busy/idle enable-disable logic, per the AGENTS.md
preference for tests over ad-hoc verification. Skipped automatically when Tk
cannot initialize (e.g. a headless CI with no display).
"""

import tkinter
from tkinter import ttk

import pytest

import ui


@pytest.fixture
def app_root(monkeypatch):
    """A headless Tk root with the app's widgets built, torn down after use."""
    monkeypatch.setattr(ui.core, "load_cookie_settings", lambda: (False, "chrome"))
    monkeypatch.setattr(ui.core, "load_cookie_file_settings", lambda: ("", "browser"))
    try:
        root = tkinter.Tk()
    except tkinter.TclError as exc:  # no display available
        pytest.skip(f"Tk unavailable: {exc}")
    root.withdraw()  # don't pop a window during tests
    ui.build_ui(root)
    ui.state.phase = "init"
    ui.state.busy = False
    ui.set_busy(False)
    try:
        yield root
    finally:
        root.destroy()


def _state(widget):
    """Return the widget's Tk 'state' option as a plain string."""
    return str(widget.cget("state"))


class TestSetBusyWidgetStates:
    def test_combobox_disabled_while_busy(self, app_root):
        # Regression: the format picker must not stay interactive during work.
        ui.url_var.set("https://youtu.be/dQw4w9WgXcQ")
        ui.set_busy(True)
        assert _state(ui.format_combo) == "disabled"

    def test_combobox_returns_to_readonly_when_idle(self, app_root):
        # Not 'normal' — that would let the user type into the picker.
        ui.url_var.set("https://youtu.be/dQw4w9WgXcQ")
        ui.set_busy(True)
        ui.set_busy(False)
        assert _state(ui.format_combo) == "readonly"

    def test_combobox_disabled_when_url_empty(self, app_root):
        # Regression: clearing the URL (e.g. after a check) must also disable
        # the format picker, not just the run button.
        ui.url_var.set("https://youtu.be/dQw4w9WgXcQ")
        assert _state(ui.format_combo) == "readonly"
        ui.url_var.set("")
        assert _state(ui.format_combo) == "disabled"

    def test_combobox_disabled_for_invalid_url(self, app_root):
        ui.url_var.set("not a url")
        assert _state(ui.format_combo) == "disabled"

    def test_url_entry_and_browse_disabled_while_busy(self, app_root):
        ui.set_busy(True)
        assert _state(ui.url_entry) == "disabled"
        assert _state(ui.browse_btn) == "disabled"

    def test_url_entry_and_browse_reenabled_when_idle(self, app_root):
        ui.set_busy(True)
        ui.set_busy(False)
        assert _state(ui.url_entry) == "normal"
        assert _state(ui.browse_btn) == "normal"


class TestRunButtonState:
    def test_disabled_when_url_empty(self, app_root):
        ui.url_var.set("")
        assert _state(ui.run_btn) == "disabled"

    def test_disabled_for_invalid_url(self, app_root):
        ui.url_var.set("not a url")
        assert _state(ui.run_btn) == "disabled"

    def test_enabled_for_valid_url_when_idle(self, app_root):
        ui.url_var.set("https://youtu.be/dQw4w9WgXcQ")
        assert _state(ui.run_btn) == "normal"

    def test_disabled_while_busy_even_with_valid_url(self, app_root):
        ui.url_var.set("https://youtu.be/dQw4w9WgXcQ")
        ui.set_busy(True)
        assert _state(ui.run_btn) == "disabled"


class TestBrowserCookies:
    def test_starts_opted_out_with_browser_disabled(self, app_root):
        assert ui.use_browser_cookies_var.get() is False
        assert ui.cookie_browser_var.get() == "Chrome"
        assert _state(ui.cookie_browser_combo) == "disabled"

    def test_selection_is_persisted_and_enables_browser_choice(
        self, app_root, monkeypatch,
    ):
        saved = []
        monkeypatch.setattr(
            ui.core,
            "save_cookie_settings",
            lambda enabled, browser, cookie_file="", cookie_source="browser":
                saved.append((enabled, browser, cookie_file, cookie_source)),
        )

        ui.use_browser_cookies_var.set(True)
        ui.on_cookie_settings_changed()
        assert _state(ui.cookie_browser_combo) == "readonly"
        assert saved[-1] == (True, "chrome", "", "browser")

        ui.cookie_browser_var.set("Edge")
        ui.on_cookie_settings_changed()
        assert saved[-1] == (True, "edge", "", "browser")

    def test_browse_is_the_last_combo_option(self, app_root):
        assert ui.cookie_browser_combo.cget("values")[-1] == "Browse..."

    def test_browse_selects_and_persists_cookie_file(self, app_root, monkeypatch):
        saved = []
        cookie_file = r"C:\Users\me\Downloads\cookies.txt"
        monkeypatch.setattr(
            ui.filedialog, "askopenfilename", lambda **_kwargs: cookie_file,
        )
        monkeypatch.setattr(
            ui.core,
            "save_cookie_settings",
            lambda enabled, browser, path="", source="browser":
                saved.append((enabled, browser, path, source)),
        )

        ui.cookie_browser_var.set("Browse...")
        ui.on_cookie_browser_selected()

        assert ui.cookie_browser_var.get() == "Browse..."
        assert ui.selected_cookie_browser() is None
        assert ui.selected_cookie_file() == cookie_file
        assert ui.cookie_file_label.cget("text") == f"Cookie file: {cookie_file}"
        assert saved[-1] == (False, "chrome", cookie_file, "file")

    def test_cancelled_picker_restores_browser_choice(self, app_root, monkeypatch):
        monkeypatch.setattr(ui.filedialog, "askopenfilename", lambda **_kwargs: "")
        ui.cookie_browser_var.set("Browse...")

        ui.on_cookie_browser_selected()

        assert ui.cookie_browser_var.get() == "Chrome"
        assert ui.selected_cookie_browser() == "chrome"

    def test_cookie_controls_disabled_while_busy(self, app_root):
        ui.use_browser_cookies_var.set(True)
        ui.update_cookie_controls()
        ui.set_busy(True)
        assert _state(ui.cookie_browser_check) == "disabled"
        assert _state(ui.cookie_browser_combo) == "disabled"


def _is_gridded(widget):
    """True if the widget is currently placed by grid (not grid_remove()d).

    winfo_manager() returns 'grid' while mapped and '' after grid_remove(),
    without needing the event loop to run.
    """
    return widget.winfo_manager() == "grid"


class TestStopButton:
    def test_hidden_initially(self, app_root):
        assert _is_gridded(ui.stop_btn) is False

    def test_shown_by_show_stop(self, app_root):
        ui.show_stop()
        assert _is_gridded(ui.stop_btn) is True
        assert _state(ui.stop_btn) == "normal"

    def test_hidden_by_hide_stop(self, app_root):
        ui.show_stop()
        ui.hide_stop()
        assert _is_gridded(ui.stop_btn) is False

    def test_stays_visible_while_busy(self, app_root):
        # Stop must remain usable during a download, unlike the other inputs.
        ui.show_stop()
        ui.set_busy(True)
        assert _is_gridded(ui.stop_btn) is True

    def test_press_disables_button(self, app_root):
        # With no live process, the stop controller returns False quickly; the
        # button should still be disabled to prevent double-clicks.
        ui.show_stop()
        ui.stop_btn_press()
        assert _state(ui.stop_btn) == "disabled"


class TestCancelledCompletion:
    def test_returns_to_info_state_and_hides_stop(self, app_root):
        ui.show_stop()
        ui.on_download_complete(returncode=-15, stderr="", cancelled=True,
                                  target=None)
        assert ui.state.phase == "info"
        assert ui.run_btn_var.get() == "download"
        assert _is_gridded(ui.stop_btn) is False
        assert "stopped" in ui.info_var.get().lower()

    def test_shows_partial_file_note_when_target_known(self, app_root, tmp_path):
        target = str(tmp_path / "video [x].mp4")
        ui.show_stop()
        ui.on_download_complete(returncode=-15, stderr="", cancelled=True,
                                  target=target)
        assert target in ui.info_var.get()


class TestInfoPanelScroll:
    """P3 Scroll: the info panel is a read-only, scrollable Text widget kept
    in sync with info_var so existing set()/get() call sites still work."""

    def _text(self, root):
        # Full text content of the info widget, minus Tk's trailing newline.
        return ui.info_text.get("1.0", "end-1c")

    def test_is_text_widget_with_scrollbar(self, app_root):
        assert isinstance(ui.info_text, tkinter.Text)
        assert isinstance(ui.info_scroll, ttk.Scrollbar)

    def test_text_is_readonly(self, app_root):
        # Read-only so users can select/copy/scroll but not type into it.
        assert _state(ui.info_text) == "disabled"

    def test_info_var_set_updates_text_widget(self, app_root):
        ui.info_var.set("hello world")
        assert self._text(app_root) == "hello world"

    def test_info_var_set_replaces_previous_content(self, app_root):
        ui.info_var.set("first")
        ui.info_var.set("second")
        assert self._text(app_root) == "second"

    def test_multiline_output_preserved(self, app_root):
        payload = "line1\nline2\nline3"
        ui.info_var.set(payload)
        assert self._text(app_root) == payload

    def test_scrollbar_wired_to_text_yview(self, app_root):
        # Scrollbar drives the Text's vertical view.
        assert str(ui.info_text.cget("yscrollcommand")) != ""


def _png_bytes(w=64, h=36):
    from PIL import Image
    import io
    img = Image.new("RGB", (w, h), (20, 80, 160))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class TestThumbnailPreview:
    def test_hidden_initially(self, app_root):
        assert _is_gridded(ui.thumb_label) is False

    def test_shown_after_successful_check(self, app_root):
        class _Ret:
            returncode = 0
            stdout = "ok"
            stderr = ""

        ui.on_check_complete(_Ret(), _png_bytes())
        assert _is_gridded(ui.thumb_label) is True
        assert ui._thumb_photo is not None

    def test_hidden_when_bytes_missing(self, app_root):
        class _Ret:
            returncode = 0
            stdout = "ok"
            stderr = ""

        ui.on_check_complete(_Ret(), None)
        assert _is_gridded(ui.thumb_label) is False

    def test_hidden_on_check_error(self, app_root):
        ui.show_thumbnail(_png_bytes())
        class _Ret:
            returncode = 1
            stdout = ""
            stderr = "boom"

        ui.on_check_complete(_Ret())
        assert _is_gridded(ui.thumb_label) is False

    def test_hidden_after_successful_download(self, app_root):
        ui.show_thumbnail(_png_bytes())
        ui.on_download_complete(returncode=0, stderr="")
        assert _is_gridded(ui.thumb_label) is False

    def test_kept_when_download_stopped(self, app_root):
        ui.show_thumbnail(_png_bytes())
        ui.show_stop()
        ui.on_download_complete(returncode=-15, stderr="", cancelled=True,
                                  target=None)
        assert _is_gridded(ui.thumb_label) is True
