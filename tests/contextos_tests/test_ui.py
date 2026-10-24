"""Tests for contextos/ui.py — 3 tests."""

from __future__ import annotations


def test_import_succeeds_without_display():
    """ui.py must importable in headless environments (no DISPLAY)."""
    import contextos.ui as ui
    assert hasattr(ui, "ContextOSTab")
    assert hasattr(ui, "is_qt_available")
    assert callable(ui.is_qt_available)


def test_headless_fallback_is_noop():
    """When Qt is not available, ContextOSTab is the headless stub."""
    import contextos.ui as ui
    tab = ui.ContextOSTab()
    assert tab.is_headless() is True
    tab.refresh()   # must not raise


def test_is_qt_available_returns_bool():
    import contextos.ui as ui
    result = ui.is_qt_available()
    assert isinstance(result, bool)
