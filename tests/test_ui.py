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
