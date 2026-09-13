"""UI smoke tests for widget state behavior in main.py.

These build the real widgets via main.build_ui() on a headless Tk root (no
mainloop) and assert the busy/idle enable-disable logic, per the AGENTS.md
preference for tests over ad-hoc verification. Skipped automatically when Tk
cannot initialize (e.g. a headless CI with no display).
"""

import tkinter

import pytest

import main


@pytest.fixture
def app_root():
    """A headless Tk root with the app's widgets built, torn down after use."""
    try:
        root = tkinter.Tk()
    except tkinter.TclError as exc:  # no display available
        pytest.skip(f"Tk unavailable: {exc}")
    root.withdraw()  # don't pop a window during tests
    main.build_ui(root)
    # Reset the module-level busy flag so tests start from a known state.
    main._busy = False
    main.set_busy(False)
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
        main.url_var.set("https://youtu.be/dQw4w9WgXcQ")
        main.set_busy(True)
        assert _state(main.format_combo) == "disabled"

    def test_combobox_returns_to_readonly_when_idle(self, app_root):
        # Not 'normal' — that would let the user type into the picker.
        main.url_var.set("https://youtu.be/dQw4w9WgXcQ")
        main.set_busy(True)
        main.set_busy(False)
        assert _state(main.format_combo) == "readonly"

    def test_combobox_disabled_when_url_empty(self, app_root):
        # Regression: clearing the URL (e.g. after a check) must also disable
        # the format picker, not just the run button.
        main.url_var.set("https://youtu.be/dQw4w9WgXcQ")
        assert _state(main.format_combo) == "readonly"
        main.url_var.set("")
        assert _state(main.format_combo) == "disabled"

    def test_combobox_disabled_for_invalid_url(self, app_root):
        main.url_var.set("not a url")
        assert _state(main.format_combo) == "disabled"

    def test_url_entry_and_browse_disabled_while_busy(self, app_root):
        main.set_busy(True)
        assert _state(main.url_entry) == "disabled"
        assert _state(main.browse_btn) == "disabled"

    def test_url_entry_and_browse_reenabled_when_idle(self, app_root):
        main.set_busy(True)
        main.set_busy(False)
        assert _state(main.url_entry) == "normal"
        assert _state(main.browse_btn) == "normal"


class TestRunButtonState:
    def test_disabled_when_url_empty(self, app_root):
        main.url_var.set("")
        assert _state(main.run_btn) == "disabled"

    def test_disabled_for_invalid_url(self, app_root):
        main.url_var.set("not a url")
        assert _state(main.run_btn) == "disabled"

    def test_enabled_for_valid_url_when_idle(self, app_root):
        main.url_var.set("https://youtu.be/dQw4w9WgXcQ")
        assert _state(main.run_btn) == "normal"

    def test_disabled_while_busy_even_with_valid_url(self, app_root):
        main.url_var.set("https://youtu.be/dQw4w9WgXcQ")
        main.set_busy(True)
        assert _state(main.run_btn) == "disabled"


def _is_gridded(widget):
    """True if the widget is currently placed by grid (not grid_remove()d).

    winfo_manager() returns 'grid' while mapped and '' after grid_remove(),
    without needing the event loop to run.
    """
    return widget.winfo_manager() == "grid"


class TestStopButton:
    def test_hidden_initially(self, app_root):
        assert _is_gridded(main.stop_btn) is False

    def test_shown_by_show_stop(self, app_root):
        main.show_stop()
        assert _is_gridded(main.stop_btn) is True
        assert _state(main.stop_btn) == "normal"

    def test_hidden_by_hide_stop(self, app_root):
        main.show_stop()
        main.hide_stop()
        assert _is_gridded(main.stop_btn) is False

    def test_stays_visible_while_busy(self, app_root):
        # Stop must remain usable during a download, unlike the other inputs.
        main.show_stop()
        main.set_busy(True)
        assert _is_gridded(main.stop_btn) is True

    def test_press_disables_button(self, app_root):
        # With no live process, stop_active_proc() returns False quickly; the
        # button should still be disabled to prevent double-clicks.
        main.show_stop()
        main.stop_btn_press()
        assert _state(main.stop_btn) == "disabled"


class TestCancelledCompletion:
    def test_returns_to_info_state_and_hides_stop(self, app_root):
        main.show_stop()
        main.on_download_complete(returncode=-15, stderr="", cancelled=True,
                                  target=None)
        assert main.current_state == "info"
        assert main.run_btn_var.get() == "download"
        assert _is_gridded(main.stop_btn) is False
        assert "stopped" in main.info_var.get().lower()

    def test_shows_partial_file_note_when_target_known(self, app_root, tmp_path):
        target = str(tmp_path / "video [x].mp4")
        main.show_stop()
        main.on_download_complete(returncode=-15, stderr="", cancelled=True,
                                  target=target)
        assert target in main.info_var.get()
