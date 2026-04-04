# -*- coding: utf-8 -*-
"""Entry point for PhoenixPanel. Singleton per tab — recreated on tab switch."""

from __future__ import annotations

_WINDOW_INSTANCE = None


def open_phoenix_panel():
    global _WINDOW_INSTANCE

    # ── Step 1: hide any visible panel IMMEDIATELY, before anything else.
    # This removes it from the screen before we do any Qt work, so the
    # compositor never shows the old tab during tab switching.
    if _WINDOW_INSTANCE is not None:
        try:
            if _WINDOW_INSTANCE.isVisible():
                _WINDOW_INSTANCE.hide()
        except RuntimeError:
            _WINDOW_INSTANCE = None

    # ── Step 2: detect desired tab (Hypershade/UV/General)
    from .core import _detect_desired_tab
    desired_tab = _detect_desired_tab()

    from .utils import get_maya_main_window
    from .core import PhoenixPanel

    # ── Step 3: liveness check
    if _WINDOW_INSTANCE is not None:
        try:
            _WINDOW_INSTANCE.isVisible()
        except RuntimeError:
            _WINDOW_INSTANCE = None

    # ── Step 4: destroy instance if tab changed
    if _WINDOW_INSTANCE is not None and _WINDOW_INSTANCE.current_tab != desired_tab:
        try:
            _WINDOW_INSTANCE.close()
            _WINDOW_INSTANCE.deleteLater()
        except Exception:
            pass
        _WINDOW_INSTANCE = None

    # ── Step 5: create if needed, pre-load correct tab
    if _WINDOW_INSTANCE is None:
        parent = get_maya_main_window()
        _WINDOW_INSTANCE = PhoenixPanel(parent=parent)
        _WINDOW_INSTANCE.current_tab = desired_tab
        _WINDOW_INSTANCE.load_tab_config(desired_tab)

    # ── Step 6: show at cursor on correct tab
    _WINDOW_INSTANCE.show_at_cursor(desired_tab=desired_tab)


if __name__ == "__main__":
    open_phoenix_panel()