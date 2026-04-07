# -*- coding: utf-8 -*-
"""Main PhoenixPanel dialog - 3-tab system, right-click title to cycle tabs.

Tab assignment logic:
  Tab 0  – General (all workspaces not caught by tabs 1/2)
  Tab 1  – UV Editing workspace (auto-switch when UV Editor layout active)
  Tab 2  – Hypershade (auto-switch when Hypershade panel is the active panel)

Right-clicking the "PhoenixPanel" title label cycles through the 3 tabs.
There is no hover-reveal tab bar; the only UI for tabs is the three thin
indicator segments drawn below the title row.
"""

from __future__ import annotations

import os
import json

import maya.cmds as cmds
import maya.mel as mel

try:
    from PySide6 import QtWidgets, QtCore, QtGui
except ImportError:
    from PySide2 import QtWidgets, QtCore, QtGui

NUM_TABS = 3

# Workspace name fragments that identify the UV Editing layout in Maya.
# Maya's built-in UV Editing workspace is usually called "UV Editing".
_UV_WORKSPACE_HINTS = ("uv editing", "uv editor", "uv edit")

# Lazy imports - only load when needed
_SHELF_PICKER = None
_SETTINGS = None


def _get_shelf_picker():
    global _SHELF_PICKER
    if _SHELF_PICKER is None:
        from .shelf_picker import ShelfPickerDialog
        _SHELF_PICKER = ShelfPickerDialog
    return _SHELF_PICKER


def _get_settings():
    global _SETTINGS
    if _SETTINGS is None:
        from .settings import PhoenixPanelSettings
        _SETTINGS = PhoenixPanelSettings
    return _SETTINGS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_hypershade_active():
    """Return True if the cursor is over a Hypershade window, or Hypershade is active.

    widgetAt() misses OpenGL viewports, so we walk ALL top-level windows and
    check if any Hypershade window's frameGeometry contains the cursor.
    """
    try:
        try:
            from PySide6 import QtWidgets as _QW, QtGui as _QG
        except ImportError:
            from PySide2 import QtWidgets as _QW, QtGui as _QG

        cursor_pos = _QG.QCursor.pos()

        for win in _QW.QApplication.topLevelWidgets():
            if not win.isVisible():
                continue
            title = win.windowTitle().lower()
            if "hypershade" not in title:
                continue
            # Cursor is inside this Hypershade window
            if win.frameGeometry().contains(cursor_pos):
                return True
            # Or it is the active window (keyboard shortcut trigger)
            if win.isActiveWindow():
                return True

        # Fallback: Maya panel focus (docked Hypershade)
        focused = cmds.getPanel(withFocus=True) or ""
        if focused and cmds.getPanel(typeOf=focused) == "hyperShadePanel":
            return True

    except Exception:
        pass
    return False


def _detect_desired_tab():
    """Return the tab index (0/1/2) appropriate for the current Maya state.

    Priority:
      1. If Hypershade is the active window  → tab 2
      2. If the workspace layout is UV Editing → tab 1
      3. Everything else                      → tab 0
    """
    # --- Hypershade check (multi-strategy) ---
    if _is_hypershade_active():
        return 2

    # --- UV workspace check ---
    try:
        workspace_name = (cmds.workspaceLayoutManager(
            query=True, current=True) or "").lower()
        if any(hint in workspace_name for hint in _UV_WORKSPACE_HINTS):
            return 1
    except Exception:
        pass

    return 0


# ---------------------------------------------------------------------------
# PhoenixPanel
# ---------------------------------------------------------------------------

class PhoenixPanel(QtWidgets.QDialog):
    """Floating popup grid of custom shelf buttons with 3-tab system."""

    MARGIN = 16  # minimum screen padding

    def __init__(self, parent=None):
        super(PhoenixPanel, self).__init__(parent)

        from .utils import get_config_path, resolve_maya_icon
        from .widgets import PhoenixButtonWidget

        self._resolve_maya_icon    = resolve_maya_icon
        self._PhoenixButtonWidget  = PhoenixButtonWidget
        self._get_config_path      = get_config_path

        self.setObjectName("PhoenixPanel")
        self.setWindowTitle("PhoenixPanel")

        flags = (
            QtCore.Qt.Tool |
            QtCore.Qt.FramelessWindowHint |
            QtCore.Qt.Popup
        )
        self.setWindowFlags(flags)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)
        self.setMinimumSize(50, 50)

        # ---- Tab state ----
        self.current_tab = 0                 # 0, 1 or 2
        self.config_base_path = get_config_path().replace(".json", "")

        # ---- Per-tab UI state (loaded from disk) ----
        self._reset_tab_state()

        self.button_widgets   = []
        self.quick_buttons    = []

        # Right-click actions for quick buttons — shared across all tabs
        # Loaded/saved in global config, not per-tab
        self.quick_button_rc = [
            {"name": "", "code": "", "type": "python", "enabled": False}
            for _ in range(5)
        ]

        # Workspace pair cycled by right-clicking the ⚙ Settings button.
        # Stored as [workspace_a, workspace_b] — toggling flips between them.
        self.workspace_cycle = ["General", "UV Editing"]

        # Reposition mode (panel-owned drag state)
        self._reposition_mode  = False   # True while mode is active
        self._drag_src_index   = None    # index of button being dragged
        self._drag_dst_index   = None    # current drop target index
        self._drag_ghost       = None    # _GhostLabel instance
        self._drag_timer       = None    # QTimer for mouse tracking
        self._ignore_close    = False
        self._event_filters_installed = []

        # ---- Workspace monitoring ----
        self._workspace_poll_timer = None   # QTimer for lightweight polling

        # Load last-used tab then load that tab's config.
        self.load_global_state()
        self.load_tab_config(self.current_tab)

        self._ui_built      = False
        self._grid_dirty    = True   # True = grid needs rebuild before next show

    # ------------------------------------------------------------------
    # Default state values (one tab's worth)
    # ------------------------------------------------------------------
    def _reset_tab_state(self):
        self.buttons_data    = []
        self.rows            = 3
        self.cols            = 4
        self.button_scale    = 1.0
        self.padding         = 8
        self.panel_width     = 420
        self.panel_height    = 360
        self.quick_alignment   = 2
        self.grid_full_row_alignment = 1  # 0=Left 1=Center 2=Right  (full rows)
        self.grid_row_alignment      = 1  # 0=Left 1=Center 2=Right  (partial last row)
        self.title_click_code = ""
        self.title_click_type = "python"
        self.custom_buttons  = [
            {"name": "ABCD", "tooltip": "", "type": "mel", "code": "", "visible": False},
            {"name": "EFGH", "tooltip": "", "type": "mel", "code": "", "visible": False},
            {"name": "IJKL", "tooltip": "", "type": "mel", "code": "", "visible": False},
            {"name": "MNOP", "tooltip": "", "type": "mel", "code": "", "visible": False},
            {"name": "QRST", "tooltip": "", "type": "mel", "code": "", "visible": False},
        ]

    # ------------------------------------------------------------------
    # Lazy UI build
    # ------------------------------------------------------------------
    def _ensure_ui_built(self):
        if self._ui_built:
            return
        self._ui_built = True
        self._build_ui()
        self.rebuild_grid()
        self._grid_dirty = False  # just built, clean
        self.update_quick_buttons()

        from .utils import get_maya_main_window
        main_win = get_maya_main_window()
        if main_win:
            main_win.installEventFilter(self)
            self._event_filters_installed.append(main_win)

        self.installEventFilter(self)

        app = QtWidgets.QApplication.instance()
        if app:
            app.installEventFilter(self)
            self._event_filters_installed.append(app)

    # ------------------------------------------------------------------
    # Event filter  (outside-click to close + right-click title)
    # ------------------------------------------------------------------
    def eventFilter(self, obj, event):
        # Reposition mode intercepts ALL mouse events app-wide (both idle and drag)
        if self._reposition_mode:
            if self._reposition_event_filter(event):
                return True

        # Right-click / middle-click on the title label
        if hasattr(self, "_title_label") and obj is self._title_label:
            if event.type() == QtCore.QEvent.MouseButtonPress:
                if event.button() == QtCore.Qt.RightButton:
                    self._cycle_tab()
                    return True
                if event.button() == QtCore.Qt.MiddleButton:
                    self._run_title_click_code()
                    return True

        # Right-click on + Shelf → toggle default material
        if hasattr(self, "add_btn") and obj is self.add_btn:
            if event.type() == QtCore.QEvent.MouseButtonPress:
                if event.button() == QtCore.Qt.RightButton:
                    self._toggle_default_material()
                    return True

        # Right-click on ⚙ Settings → toggle UV / General workspace
        if hasattr(self, "settings_btn") and obj is self.settings_btn:
            if event.type() == QtCore.QEvent.MouseButtonPress:
                if event.button() == QtCore.Qt.RightButton:
                    self._toggle_workspace()
                    return True

        # Outside-click dismiss — catches MouseButtonPress from app filter.
        # Also works when a button-launched floating window is active.
        if event.type() == QtCore.QEvent.MouseButtonPress:
            if not self.isVisible():
                return False
            if self._ignore_close:
                return False
            if self._reposition_mode:
                return False

            try:
                gp = event.globalPos()
            except Exception:
                try:
                    gp = obj.mapToGlobal(event.pos())
                except Exception:
                    return False

            # Click inside our window → pass through
            if self.frameGeometry().contains(gp):
                return False

            widget_at = QtWidgets.QApplication.widgetAt(gp)
            if widget_at and (widget_at is self or self.isAncestorOf(widget_at)):
                return False

            # Click outside → hide
            self.hide()
            return False

        return False

    # ------------------------------------------------------------------
    # Right-click button actions
    # ------------------------------------------------------------------
    def _toggle_default_material(self):
        """Right-click +Shelf: toggle Use Default Material on the active viewport."""
        try:
            panel = cmds.getPanel(withFocus=True)
            if not panel or cmds.getPanel(typeOf=panel) != "modelPanel":
                panels = cmds.getPanel(type="modelPanel")
                if not panels:
                    cmds.warning("No model panel found.")
                    return
                panel = panels[0]
            current = cmds.modelEditor(panel, q=True, useDefaultMaterial=True)
            cmds.modelEditor(panel, e=True, useDefaultMaterial=not current)
            state = "ON" if not current else "OFF"
            cmds.inViewMessage(
                amg='<span style="color:#F0A500;">Use Default Material:</span> <b>{}</b>'.format(state),
                pos="botCenter", fade=True, fst=500, fad=200
            )
        except Exception as e:
            cmds.warning("PhoenixPanel: toggle default material error: {}".format(e))

    def _toggle_workspace(self):
        """Right-click Settings: cycle between the two workspaces configured in Settings."""
        try:
            ws_a, ws_b = self.workspace_cycle[0], self.workspace_cycle[1]
            current = cmds.workspaceLayoutManager(q=True, current=True)
            # If we're on ws_a switch to ws_b, otherwise switch to ws_a.
            target = ws_b if current == ws_a else ws_a
            cmds.workspaceLayoutManager(setCurrent=target)
            cmds.inViewMessage(
                amg="<hl>{}</hl> Workspace".format(target),
                pos="topCenter", fade=True
            )
        except Exception as e:
            cmds.warning("PhoenixPanel: toggle workspace error: {}".format(e))

    # ------------------------------------------------------------------
    # Title middle-click action
    # ------------------------------------------------------------------
    def _run_title_click_code(self):
        """Execute the user-defined title middle-click code."""
        code = (self.title_click_code or "").strip()
        if not code:
            return
        code_type = (self.title_click_type or "python").lower()
        try:
            if code_type == "python":
                import __main__
                exec(code, __main__.__dict__)
            else:
                mel.eval(code)
        except Exception as e:
            cmds.warning("PhoenixPanel title click error: {}".format(e))

    # ------------------------------------------------------------------
    # Tab cycling (right-click on title)
    # ------------------------------------------------------------------
    def _cycle_tab(self):
        """Advance to the next tab (wraps 0→1→2→0)."""
        next_tab = (self.current_tab + 1) % NUM_TABS
        self.switch_tab(next_tab)

    # ------------------------------------------------------------------
    # UI build
    # ------------------------------------------------------------------
    def _build_ui(self):
        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self.bg = QtWidgets.QWidget()
        self.bg.setObjectName("PanelBg")
        self.bg.setStyleSheet("""
        #PanelBg {
            background-color: #151820;
            border-radius: 12px;
            border: 1px solid #303645;
        }
        """)
        outer.addWidget(self.bg)

        main = QtWidgets.QVBoxLayout(self.bg)
        main.setContentsMargins(10, 10, 10, 10)
        main.setSpacing(8)

        # ---- Title row ----
        title_row = QtWidgets.QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)

        self._title_label = QtWidgets.QLabel("PhoenixPanel")
        self._title_label.setStyleSheet(
            "color: #f5f7ff; font-weight: bold; font-size: 12px;"
        )
        self._title_label.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
        self._title_label.installEventFilter(self)
        title_row.addWidget(self._title_label)

        # Quick buttons frame
        self.quick_buttons_frame = QtWidgets.QFrame()
        self.quick_buttons_frame.setObjectName("QuickButtonsFrame")
        self.quick_buttons_frame.setFixedHeight(26)
        self.quick_buttons_frame.setStyleSheet("""
        #QuickButtonsFrame {
            border-radius: 4px;
            padding: 2px;
            background-color: transparent;
        }
        """)
        self.quick_buttons_layout = QtWidgets.QHBoxLayout(self.quick_buttons_frame)
        self.quick_buttons_layout.setContentsMargins(4, 0, 4, 0)
        self.quick_buttons_layout.setSpacing(self.quick_button_gap if hasattr(self, "quick_button_gap") else 6)
        self.quick_buttons_layout.setAlignment(QtCore.Qt.AlignTop)

        self.quick_buttons = []
        for i in range(5):
            data  = self.custom_buttons[i]
            label = (data.get("name") or "BTN{}".format(i + 1))[:4].upper()
            btn   = QtWidgets.QPushButton(label, parent=self.quick_buttons_frame)
            btn.setFixedHeight(22)
            btn.setFixedWidth(44)
            btn.setStyleSheet("""
                QPushButton {
                    background: #2c3348;
                    color: #d6daf5;
                    border-radius: 4px;
                    font-weight: bold;
                }
                QPushButton:hover { background: #3a4057; }
            """)
            btn.setVisible(data.get("visible", True))
            btn.setToolTip(data.get("tooltip", ""))
            btn.clicked.connect(lambda checked=False, idx=i: self._on_quick_button(idx))
            btn.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
            btn.customContextMenuRequested.connect(
                lambda pos, idx=i, b=btn: self._on_quick_button_rc(idx, b, pos)
            )
            self.quick_buttons.append(btn)

        title_row.addWidget(self.quick_buttons_frame, 1)

        # +Shelf button
        self.add_btn = QtWidgets.QPushButton("+ Shelf")
        self.add_btn.setFixedHeight(24)
        self.add_btn.setStyleSheet("""
        QPushButton {
            background: #252a39;
            color: #c8d2ff;
            border-radius: 6px;
            padding: 2px 8px;
            font-size: 11px;
        }
        QPushButton:hover { background: #2f3547; }
        """)
        self.add_btn.setToolTip("Left: Add shelf buttons  |  Right-click: Toggle default material")
        self.add_btn.installEventFilter(self)
        title_row.addWidget(self.add_btn)

        # Settings button
        self.settings_btn = QtWidgets.QPushButton("\u2699")
        self.settings_btn.setFixedSize(26, 26)
        self.settings_btn.setStyleSheet("""
            QPushButton {
                background: #252a39;
                color: #c8d2ff;
                border-radius: 6px;
                font-size: 14px;
            }
            QPushButton:hover { background: #32384c; }
        """)
        self.settings_btn.setToolTip("Left: Settings  |  Right-click: Toggle workspace (configurable in Settings)")
        self.settings_btn.installEventFilter(self)
        title_row.addWidget(self.settings_btn)

        main.addLayout(title_row)

        # ---- Tab indicator bar (3 thin segments, always visible) ----
        tab_bar = QtWidgets.QHBoxLayout()
        tab_bar.setSpacing(3)
        tab_bar.setContentsMargins(0, 0, 0, 0)

        self._tab_indicators = []
        _NAMES = ["General", "UV Editing", "Hypershade"]
        for i in range(NUM_TABS):
            seg = QtWidgets.QFrame()
            seg.setFixedHeight(3)
            seg.setToolTip(_NAMES[i])
            # Click on a segment also switches directly
            seg.mousePressEvent = lambda _evt, idx=i: self.switch_tab(idx)
            seg.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
            tab_bar.addWidget(seg, 1)
            self._tab_indicators.append(seg)

        main.addLayout(tab_bar)
        self._update_tab_indicators()

        # ---- Scroll + grid ----
        self.scroll_wrapper = QtWidgets.QWidget()
        self.scroll_wrapper.setObjectName("ScrollWrapper")
        self.scroll_wrapper.setStyleSheet("""
        #ScrollWrapper {
            background-color: #373737;
            border-radius: 10px;
        }
        """)
        scroll_wrapper_layout = QtWidgets.QVBoxLayout(self.scroll_wrapper)
        scroll_wrapper_layout.setContentsMargins(0, 0, 0, 0)

        self.scroll = QtWidgets.QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.scroll.setStyleSheet("""
        QScrollArea {
            background: transparent;
            border-radius: 10px;
        }
        QScrollArea > QWidget > QWidget {
            background: transparent;
        }
        QScrollBar:vertical {
            background: #373737;
            width: 6px;
            border-radius: 3px;
        }
        QScrollBar::handle:vertical {
            background: #3a4055;
            border-radius: 3px;
            min-height: 20px;
        }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
            height: 0px;
        }
        QScrollBar:horizontal {
            background: #373737;
            height: 6px;
            border-radius: 3px;
        }
        QScrollBar::handle:horizontal {
            background: #3a4055;
            border-radius: 3px;
            min-width: 20px;
        }
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
            width: 0px;
        }
        """)
        scroll_wrapper_layout.addWidget(self.scroll)
        main.addWidget(self.scroll_wrapper, 1)

        # grid_container uses a VBoxLayout of HBox rows for per-row alignment
        self.grid_container = QtWidgets.QWidget()
        self.grid_container.setStyleSheet("background: transparent;")
        self.grid_layout = QtWidgets.QVBoxLayout(self.grid_container)
        self.grid_layout.setContentsMargins(8, 8, 8, 8)
        self.grid_layout.setSpacing(0)
        self.grid_layout.setAlignment(QtCore.Qt.AlignTop)

        self.scroll.setWidget(self.grid_container)

        # Signals
        self.add_btn.clicked.connect(self.open_shelf_picker)
        self.settings_btn.clicked.connect(self.open_settings_window)

        self._rebuild_quick_buttons_layout()

    # ------------------------------------------------------------------
    # Tab indicator styles
    # ------------------------------------------------------------------
    # Colour palette per tab: (active_colour, inactive_colour)
    _TAB_COLOURS = [
        ("#4a7bb8", "#303645"),   # 0 – General  – blue
        ("#3aaa6e", "#303645"),   # 1 – UV       – green
        ("#b86a2a", "#303645"),   # 2 – Hyper    – orange
    ]

    def _update_tab_indicators(self):
        if not hasattr(self, "_tab_indicators"):
            return
        for i, seg in enumerate(self._tab_indicators):
            active, inactive = self._TAB_COLOURS[i]
            colour = active if i == self.current_tab else inactive
            seg.setStyleSheet(
                "QFrame {{ background: {}; border-radius: 1px; }}".format(colour)
            )

    # ------------------------------------------------------------------
    # Tab switching
    # ------------------------------------------------------------------
    def switch_tab(self, tab_index):
        if tab_index == self.current_tab:
            return
        if tab_index < 0 or tab_index >= NUM_TABS:
            return

        self.save_tab_config(self.current_tab)
        self.current_tab = tab_index
        self.load_tab_config(tab_index)
        self._grid_dirty = True

        if self._ui_built:
            self.rebuild_grid()
            self.update_quick_buttons()
            self._update_tab_indicators()
            self._update_title_tab_hint()

        self.save_global_state()

    def _update_title_tab_hint(self):
        """Keep title as plain PhoenixPanel — no suffix."""
        pass

    # ------------------------------------------------------------------
    # Config paths
    # ------------------------------------------------------------------
    def get_tab_config_path(self, tab_index):
        return "{}_tab{}.json".format(self.config_base_path, tab_index)

    def get_global_config_path(self):
        return "{}_global.json".format(self.config_base_path)

    # ------------------------------------------------------------------
    # Global state (last used tab)
    # ------------------------------------------------------------------
    def load_global_state(self):
        path = self.get_global_config_path()
        if not os.path.exists(path):
            self.current_tab = 0
            return
        try:
            with open(path, "r") as f:
                data = json.load(f)
            self.current_tab = int(data.get("last_tab", 0))
            if not (0 <= self.current_tab < NUM_TABS):
                self.current_tab = 0
            # Load shared right-click actions
            rc_list = data.get("quick_button_rc", [])
            for i in range(5):
                if i < len(rc_list) and isinstance(rc_list[i], dict):
                    self.quick_button_rc[i] = {
                        "name":    rc_list[i].get("name", ""),
                        "code":    rc_list[i].get("code", ""),
                        "type":    rc_list[i].get("type", "python"),
                        "enabled": bool(rc_list[i].get("enabled", False)),
                    }
            # Load workspace cycle pair
            wc = data.get("workspace_cycle")
            if isinstance(wc, list) and len(wc) == 2 and all(isinstance(s, str) for s in wc):
                self.workspace_cycle = wc
        except Exception:
            self.current_tab = 0

    def save_global_state(self):
        path = self.get_global_config_path()
        try:
            with open(path, "w") as f:
                json.dump({
                    "last_tab": self.current_tab,
                    "quick_button_rc": self.quick_button_rc,
                    "workspace_cycle": self.workspace_cycle,
                }, f, indent=2)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Per-tab config  load / save
    # ------------------------------------------------------------------
    def load_tab_config(self, tab_index):
        self._reset_tab_state()
        path = self.get_tab_config_path(tab_index)
        if not os.path.exists(path):
            return

        try:
            with open(path, "r") as f:
                data = json.load(f)
        except Exception:
            return

        panel = data.get("panel", {})
        self.rows            = int(panel.get("rows",         self.rows))
        self.cols            = int(panel.get("cols",         self.cols))
        self.button_scale    = float(panel.get("button_scale", self.button_scale))
        self.padding         = int(panel.get("padding",      self.padding))
        self.panel_width     = max(int(panel.get("panel_width",  self.panel_width)),  50)
        self.panel_height    = max(int(panel.get("panel_height", self.panel_height)), 50)
        self.quick_alignment    = int(panel.get("quick_alignment", self.quick_alignment))
        self.grid_full_row_alignment = int(panel.get("grid_full_row_alignment", self.grid_full_row_alignment))
        self.grid_row_alignment      = int(panel.get("grid_row_alignment",      self.grid_row_alignment))
        self.title_click_code  = panel.get("title_click_code", "")
        self.title_click_type  = panel.get("title_click_type", "python")

        self.buttons_data = data.get("buttons", []) or []

        quicks = data.get("quick_buttons")
        if isinstance(quicks, list) and quicks:
            normalized = []
            for i, q in enumerate(quicks):
                if not isinstance(q, dict):
                    continue
                normalized.append({
                    "name":    (q.get("name") or "BTN{}".format(i + 1))[:4].upper(),
                    "tooltip": q.get("tooltip", ""),
                    "type":    (q.get("type", "mel") or "mel").lower(),
                    "code":    q.get("code", ""),
                    "visible": bool(q.get("visible", True)),
                })
            while len(normalized) < 5:
                normalized.append({
                    "name": "BTN{}".format(len(normalized) + 1),
                    "tooltip": "", "type": "mel", "code": "", "visible": False,
                })
            self.custom_buttons = normalized

    def save_tab_config(self, tab_index):
        path = self.get_tab_config_path(tab_index)
        data = {
            "panel": {
                "rows":          self.rows,
                "cols":          self.cols,
                "button_scale":  self.button_scale,
                "padding":       self.padding,
                "panel_width":   max(self.panel_width,  50),
                "panel_height":  max(self.panel_height, 50),
                "quick_alignment":  self.quick_alignment,
                "grid_full_row_alignment": self.grid_full_row_alignment,
                "grid_row_alignment":      self.grid_row_alignment,
                "title_click_code": self.title_click_code,
                "title_click_type": self.title_click_type,
            },
            "buttons":      self.buttons_data,
            "quick_buttons": self.custom_buttons,
        }
        try:
            with open(path, "w") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass

    # Alias used by settings dialog
    def save_config(self):
        self.save_tab_config(self.current_tab)

    # ------------------------------------------------------------------
    # Workspace-aware auto tab-switch (lightweight polling)
    # ------------------------------------------------------------------
    def _start_workspace_polling(self):
        pass  # Polling removed — tab detection happens on open only (much faster)

    def _poll_workspace(self):
        pass

    def _stop_workspace_polling(self):
        if self._workspace_poll_timer is not None:
            try:
                self._workspace_poll_timer.stop()
            except Exception:
                pass
            self._workspace_poll_timer = None

    # ------------------------------------------------------------------
    # Quick buttons helpers
    # ------------------------------------------------------------------
    def _rebuild_quick_buttons_layout(self):
        while self.quick_buttons_layout.count():
            self.quick_buttons_layout.takeAt(0)

        visible_buttons = []
        for i, btn in enumerate(self.quick_buttons):
            if i < len(self.custom_buttons):
                if bool(self.custom_buttons[i].get("visible", True)):
                    visible_buttons.append(btn)
            else:
                visible_buttons.append(btn)

        if self.quick_alignment == 0:   # LEFT
            for b in visible_buttons:
                self.quick_buttons_layout.addWidget(b)
            self.quick_buttons_layout.addStretch(1)
        elif self.quick_alignment == 1: # CENTER
            self.quick_buttons_layout.addStretch(1)
            for b in visible_buttons:
                self.quick_buttons_layout.addWidget(b)
            self.quick_buttons_layout.addStretch(1)
        else:                           # RIGHT
            self.quick_buttons_layout.addStretch(1)
            for b in visible_buttons:
                self.quick_buttons_layout.addWidget(b)

    def update_quick_buttons(self):
        if not self.quick_buttons:
            return
        while len(self.custom_buttons) < 5:
            self.custom_buttons.append({
                "name": "BTN{}".format(len(self.custom_buttons) + 1),
                "tooltip": "", "type": "mel", "code": "", "visible": False,
            })
        for i, btn in enumerate(self.quick_buttons):
            data    = self.custom_buttons[i]
            name    = (data.get("name") or "BTN{}".format(i + 1))[:4].upper()
            tooltip = data.get("tooltip", "")
            visible = bool(data.get("visible", True))

            rc = self.quick_button_rc[i] if i < len(self.quick_button_rc) else {}
            rc_enabled = bool(rc.get("enabled", False))
            rc_name    = (rc.get("name") or "")[:4].upper()

            # If no left-click code but right-click is enabled: show rc name, left-click runs rc
            has_left_code = bool((data.get("code") or "").strip())
            if rc_enabled and not has_left_code and rc_name:
                display_name = rc_name
            else:
                display_name = name

            # Show button if left visible OR right-click enabled with a name
            show = visible or (rc_enabled and bool(rc_name))

            btn.setText(display_name)
            btn.setToolTip(tooltip)
            btn.setVisible(show)
        self._rebuild_quick_buttons_layout()

    def _on_quick_button(self, index):
        if index < 0 or index >= len(self.custom_buttons):
            return
        data      = self.custom_buttons[index]
        code_type = (data.get("type", "mel") or "mel").lower()
        code      = data.get("code", "") or ""
        # If no left-click code but rc is enabled, run the rc code on left click
        if not code.strip():
            rc = self.quick_button_rc[index] if index < len(self.quick_button_rc) else {}
            if rc.get("enabled") and (rc.get("code") or "").strip():
                self._run_quick_rc(index)
            return
        try:
            if code_type == "python":
                import __main__
                exec(code, __main__.__dict__)
            else:
                mel.eval(code)
        except Exception as e:
            cmds.warning("PhoenixPanel quick button {} error: {}".format(index + 1, e))

    def _on_quick_button_rc(self, index, btn_widget, pos):
        """Right-click on a quick button.
        If rc is enabled: show context menu with rc action name.
        If left-click has no code and rc enabled: left-click already runs rc, so no menu needed.
        """
        if index < 0 or index >= len(self.quick_button_rc):
            return
        rc = self.quick_button_rc[index]
        if not rc.get("enabled") or not (rc.get("code") or "").strip():
            return

        data = self.custom_buttons[index] if index < len(self.custom_buttons) else {}
        has_left_code = bool((data.get("code") or "").strip())

        # If no left click code, rc already runs on left click — no menu needed
        if not has_left_code:
            return

        # Show a tiny context menu with just the rc action
        rc_name = rc.get("name") or "Run"

        menu = QtWidgets.QMenu(btn_widget)
        menu.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)
        menu.setWindowFlags(
            menu.windowFlags() |
            QtCore.Qt.FramelessWindowHint |
            QtCore.Qt.NoDropShadowWindowHint
        )
        menu.setStyleSheet("""
        QMenu {
            background-color: #212121;
            border: 1px solid #3a3a3a;
            border-radius: 8px;
            padding: 4px;
        }
        QMenu::item {
            color: #d6daf5;
            padding: 6px 16px;
            border-radius: 5px;
            font-size: 11px;
        }
        QMenu::item:selected {
            background-color: #2e2e2e;
            color: #ffffff;
        }
        """)
        act = menu.addAction(rc_name)
        gpos   = btn_widget.mapToGlobal(pos)
        chosen = menu.exec_(gpos) if hasattr(menu, "exec_") else menu.exec(gpos)
        if chosen == act:
            self._run_quick_rc(index)

    def _run_quick_rc(self, index):
        """Execute the right-click code for quick button at index."""
        if index < 0 or index >= len(self.quick_button_rc):
            return
        rc        = self.quick_button_rc[index]
        code      = (rc.get("code") or "").strip()
        code_type = (rc.get("type") or "python").lower()
        if not code:
            return
        try:
            if code_type == "python":
                import __main__
                exec(code, __main__.__dict__)
            else:
                mel.eval(code)
        except Exception as e:
            cmds.warning("PhoenixPanel quick button {} RC error: {}".format(index + 1, e))

    # ------------------------------------------------------------------
    # Grid
    # ------------------------------------------------------------------
    def clear_grid(self):
        for btn in self.button_widgets:
            try:
                btn.cleanup()
            except Exception:
                pass
        # Remove all row widgets (and spacer items) from the VBox
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self.button_widgets.clear()

    def rebuild_grid(self):
        self.clear_grid()
        if not self.buttons_data:
            return

        base      = 64
        side      = int(base * self.button_scale)
        icon_size = int(side * 0.82)
        pad       = self.padding
        total     = len(self.buttons_data)
        cols      = self.cols

        # Build buttons first
        all_btns = []
        for i, info in enumerate(self.buttons_data):
            overlay = info.get("label", "") or ""
            ann     = info.get("annotation", "") or ""
            icon    = self._resolve_maya_icon(info.get("icon", ""))
            btn = self._PhoenixButtonWidget(i, overlay, icon, ann, parent=self.grid_container)
            btn.set_sizes(side, icon_size)
            btn.triggeredWithIndex.connect(self._on_button_triggered)
            btn.requestReposition.connect(self._enter_reposition_mode)
            btn.requestDelete.connect(self._on_button_delete)
            all_btns.append(btn)
            self.button_widgets.append(btn)

        # Lay out row-by-row so partial last row can be aligned independently
        # grid_row_alignment: 0=Left, 1=Center, 2=Right
        align = self.grid_row_alignment
        num_rows = (total + cols - 1) // cols

        for r in range(num_rows):
            row_btns = all_btns[r * cols : (r + 1) * cols]
            is_last  = (r == num_rows - 1)
            partial  = is_last and (total % cols != 0)

            row_widget = QtWidgets.QWidget()
            row_widget.setStyleSheet("background: transparent;")
            row_layout = QtWidgets.QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(pad)

            if partial:
                # Partial last row: apply last-row alignment
                self._apply_row_align(row_layout, row_btns, align)
            else:
                # Full row: apply full-row alignment
                self._apply_row_align(row_layout, row_btns, self.grid_full_row_alignment)

            # Add vertical spacing above rows after the first
            if r > 0:
                self.grid_layout.addSpacing(pad)
            self.grid_layout.addWidget(row_widget)

    @staticmethod
    def _apply_row_align(layout, widgets, alignment):
        """Add widgets to an HBoxLayout with the given alignment (0=L,1=C,2=R)."""
        if alignment == 0:    # Left
            for w in widgets:
                layout.addWidget(w)
            layout.addStretch(1)
        elif alignment == 2:  # Right
            layout.addStretch(1)
            for w in widgets:
                layout.addWidget(w)
        else:                 # Center
            layout.addStretch(1)
            for w in widgets:
                layout.addWidget(w)
            layout.addStretch(1)

    # ------------------------------------------------------------------
    # Button operations
    # ------------------------------------------------------------------
    def _on_button_delete(self, index):
        if 0 <= index < len(self.buttons_data):
            self.buttons_data.pop(index)
            self._grid_dirty = True
            self.rebuild_grid()
            self.save_tab_config(self.current_tab)

    # ------------------------------------------------------------------
    # REPOSITION MODE  (panel owns all drag state)
    # ------------------------------------------------------------------
    def _enter_reposition_mode(self, src_index):
        """Activate reposition mode. Style all buttons, install app filter.
        Drag does not start until the user clicks a button (handled in
        _reposition_event_filter idle state).
        """
        if self._reposition_mode:
            return  # already active

        self._reposition_mode = True
        self._drag_src_index  = None   # idle — no button picked up yet
        self._drag_dst_index  = None

        # Style all buttons as reposition-idle (dashed border)
        for btn in self.button_widgets:
            btn._reposition_idle_style()

        # Immediately start dragging the button that was right-clicked
        src_btn = self.button_widgets[src_index] if 0 <= src_index < len(self.button_widgets) else None
        if src_btn:
            centre = src_btn.mapToGlobal(src_btn.rect().center())
            self._start_drag_on(src_index, centre)

        # Install app-level filter to track ALL mouse events
        app = QtWidgets.QApplication.instance()
        if app:
            app.installEventFilter(self)

    def _reposition_event_filter(self, evt):
        """Full state-machine for reposition mode mouse events.

        States:
          _drag_src_index is None  → idle (waiting for a click on a button)
          _drag_src_index is set   → actively dragging that button

        Returns True to consume the event, False to pass through.
        """
        t = evt.type()

        # ── IDLE: waiting for user to click a button to drag ──────────
        if self._drag_src_index is None:

            if t == QtCore.QEvent.MouseButtonPress:
                try:
                    gpos = evt.globalPos()
                except AttributeError:
                    gpos = evt.globalPosition().toPoint()

                # Outside the panel → exit reposition mode, close panel
                # Use frameGeometry() — it's in screen coords for a top-level window
                if not self.frameGeometry().contains(gpos):
                    self._cancel_reposition()
                    self.hide()
                    return True

                # Find which button was clicked
                from .widgets import PhoenixButtonWidget as _PBW
                widget_under = QtWidgets.QApplication.widgetAt(gpos)
                clicked_index = None
                w = widget_under
                for _ in range(8):
                    if w is None:
                        break
                    if isinstance(w, _PBW):
                        clicked_index = w.index
                        break
                    w = w.parent() if hasattr(w, "parent") else None

                if clicked_index is not None:
                    # Start dragging this button
                    self._start_drag_on(clicked_index, gpos)
                    return True

                # Clicked inside panel but not on a button — ignore
                return True

            elif t == QtCore.QEvent.MouseButtonRelease:
                # Always consume releases in idle state so tool_btn.clicked never fires
                return True

            elif t == QtCore.QEvent.KeyPress:
                if evt.key() == QtCore.Qt.Key_Escape:
                    self._cancel_reposition()
                    return True

            return False  # pass through non-mouse events

        # ── DRAGGING: button picked up, tracking mouse ─────────────────
        if t == QtCore.QEvent.MouseMove:
            try:
                gpos = evt.globalPos()
            except AttributeError:
                gpos = evt.globalPosition().toPoint()
            self._reposition_mouse_move(gpos)
            return True

        elif t == QtCore.QEvent.MouseButtonRelease:
            if evt.button() == QtCore.Qt.LeftButton:
                self._commit_reposition()
                return True

        elif t == QtCore.QEvent.KeyPress:
            if evt.key() == QtCore.Qt.Key_Escape:
                self._cancel_reposition()
                return True

        return False

    def _start_drag_on(self, src_index, global_pos):
        """Pick up the button at src_index and start dragging it."""
        from .widgets import _GhostLabel

        if not (0 <= src_index < len(self.button_widgets)):
            return

        self._drag_src_index = src_index
        self._drag_dst_index = src_index

        # Build ghost
        src_btn = self.button_widgets[src_index]
        pm = src_btn.grab()
        if self._drag_ghost:
            self._drag_ghost.hide()
            self._drag_ghost.deleteLater()
        self._drag_ghost = _GhostLabel(pm)
        self._drag_ghost.move_center_to(global_pos)
        self._drag_ghost.show()

        src_btn._dragging_source_style()

    def _reposition_mouse_move(self, global_pos):
        """Move ghost and update live order preview."""
        if self._drag_ghost:
            self._drag_ghost.move_center_to(global_pos)

        # Hit-test: hide ghost temporarily so widgetAt sees through it
        if self._drag_ghost:
            self._drag_ghost.hide()
        widget_under = QtWidgets.QApplication.widgetAt(global_pos)
        if self._drag_ghost:
            self._drag_ghost.show()

        # Walk up to find a PhoenixButtonWidget
        from .widgets import PhoenixButtonWidget as _PBW
        target_index = None
        w = widget_under
        for _ in range(8):
            if w is None:
                break
            if isinstance(w, _PBW):
                target_index = w.index
                break
            w = w.parent() if hasattr(w, "parent") else None

        if target_index is None or target_index == self._drag_src_index:
            # Not over a valid target — clear previous highlight
            if self._drag_dst_index != self._drag_src_index:
                if 0 <= self._drag_dst_index < len(self.button_widgets):
                    self.button_widgets[self._drag_dst_index]._reposition_idle_style()
            self._drag_dst_index = self._drag_src_index
            return

        if target_index == self._drag_dst_index:
            return  # same slot, nothing to do

        # Clear old target highlight
        if (self._drag_dst_index != self._drag_src_index and
                0 <= self._drag_dst_index < len(self.button_widgets)):
            self.button_widgets[self._drag_dst_index]._reposition_idle_style()

        self._drag_dst_index = target_index

        # Live-shuffle data + widgets
        self._live_swap(self._drag_src_index, target_index)
        self._drag_src_index = target_index  # source follows the data

        # Highlight new slot
        if 0 <= target_index < len(self.button_widgets):
            self.button_widgets[target_index]._drop_target_style()

    def _live_swap(self, src, dst):
        """Move data and widgets from src to dst without destroying anything."""
        if src == dst:
            return
        if not (0 <= src < len(self.buttons_data) and 0 <= dst < len(self.buttons_data)):
            return

        # Move data
        item = self.buttons_data.pop(src)
        self.buttons_data.insert(dst, item)

        # Move widget reference
        widget = self.button_widgets.pop(src)
        self.button_widgets.insert(dst, widget)

        # Update .index on all widgets
        for i, btn in enumerate(self.button_widgets):
            btn.index = i

        # Reflow: rebuild row widgets in the VBox
        self._reflow_grid_widgets()

        # Keep source slot showing empty style, rest idle
        for i, btn in enumerate(self.button_widgets):
            if i == dst:
                btn._dragging_source_style()
            else:
                btn._reposition_idle_style()

    def _reflow_grid_widgets(self):
        """Rebuild VBox row layout from current button_widgets order (no widget recreation)."""
        # Remove existing row containers
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        pad   = self.padding
        cols  = self.cols
        total = len(self.button_widgets)
        align = self.grid_row_alignment
        num_rows = (total + cols - 1) // cols if total else 0

        for r in range(num_rows):
            row_btns = self.button_widgets[r * cols : (r + 1) * cols]
            is_last  = (r == num_rows - 1)
            partial  = is_last and (total % cols != 0)

            row_widget = QtWidgets.QWidget()
            row_widget.setStyleSheet("background: transparent;")
            row_layout = QtWidgets.QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(pad)

            if partial:
                self._apply_row_align(row_layout, row_btns, align)
            else:
                self._apply_row_align(row_layout, row_btns, self.grid_full_row_alignment)

            if r > 0:
                self.grid_layout.addSpacing(pad)
            self.grid_layout.addWidget(row_widget)

    def _commit_reposition(self):
        """Mouse released — save order, reset to idle, stay in reposition mode.
        User can now click any other button to drag it.
        """
        self._grid_dirty = False  # reflow already kept grid in sync
        self.save_tab_config(self.current_tab)

        if self._drag_ghost:
            self._drag_ghost.hide()
            self._drag_ghost.deleteLater()
            self._drag_ghost = None

        self._drag_src_index = None   # back to idle state
        self._drag_dst_index = None

        # All buttons return to reposition-idle style (dashed border)
        for btn in self.button_widgets:
            btn._reposition_idle_style()

    def _cancel_reposition(self):
        """Escape or panel close — exit reposition mode entirely."""
        self._reposition_mode = False
        self._drag_src_index  = None
        self._drag_dst_index  = None

        if self._drag_ghost:
            self._drag_ghost.hide()
            self._drag_ghost.deleteLater()
            self._drag_ghost = None

        app = QtWidgets.QApplication.instance()
        if app:
            try:
                app.removeEventFilter(self)
            except Exception:
                pass

        for btn in self.button_widgets:
            btn._normal_style()

    def _exit_reposition_mode(self):
        """Alias used on panel close."""
        if self._reposition_mode:
            self._cancel_reposition()

    def _on_button_triggered(self, index):
        if index < 0 or index >= len(self.buttons_data):
            return
        info = self.buttons_data[index]
        cmd  = info.get("command", "")
        src  = (info.get("sourceType", "mel") or "mel").lower()
        if not cmd:
            return
        # Keep panel open even if the command opens a floating window
        self._ignore_close = True
        try:
            if src == "python":
                import __main__
                exec(cmd, __main__.__dict__)
            else:
                mel.eval(cmd)
        except Exception as e:
            cmds.warning("PhoenixPanel: Error executing button: {}".format(e))
        finally:
            # Small delay before re-arming dismiss so the opened window
            # has time to appear without being mistaken for an outside click
            QtCore.QTimer.singleShot(300, self._rearm_dismiss)

    def _rearm_dismiss(self):
        self._ignore_close = False

    # ------------------------------------------------------------------
    # Settings / Shelf picker
    # ------------------------------------------------------------------
    def open_settings_window(self):
        self._ignore_close = True
        SettingsClass = _get_settings()
        self.settings_win = SettingsClass(parent=self, panel=self)
        self.settings_win.settingsChanged.connect(self._settings_updated)
        self.settings_win.finished.connect(lambda *_: setattr(self, "_ignore_close", False))
        self.settings_win.show()

    def _settings_updated(self):
        self._grid_dirty = True
        self.rebuild_grid()
        self.update_quick_buttons()
        self.save_tab_config(self.current_tab)

    def open_shelf_picker(self):
        ShelfPickerClass = _get_shelf_picker()
        dlg = ShelfPickerClass(parent=self)
        self._ignore_close = True
        result = dlg.exec_() if hasattr(dlg, "exec_") else dlg.exec()
        self._ignore_close = False
        if result != QtWidgets.QDialog.Accepted:
            return
        items = dlg.selected_buttons()
        if not items:
            return
        self.buttons_data.extend(items)
        self._grid_dirty = True
        self.rebuild_grid()
        self.save_tab_config(self.current_tab)

    # ------------------------------------------------------------------
    # Show at cursor
    # ------------------------------------------------------------------
    def show_at_cursor(self, desired_tab=None):
        if desired_tab is None:
            desired_tab = _detect_desired_tab()

        # Tab switch handled by launcher (destroys+recreates instance).
        # If somehow we still need to switch, do it silently before any paint.
        if desired_tab != self.current_tab:
            self.save_tab_config(self.current_tab)
            self.current_tab = desired_tab
            self.load_tab_config(desired_tab)
            self._grid_dirty = True

        self.setUpdatesEnabled(False)
        self._ensure_ui_built()

        if self._grid_dirty:
            self.rebuild_grid()
            self._grid_dirty = False

        self.update_quick_buttons()
        self._rebuild_quick_buttons_layout()
        self._update_tab_indicators()
        self._update_title_tab_hint()

        # Calculate position first
        pos  = QtGui.QCursor.pos()
        app  = QtWidgets.QApplication.instance()
        if hasattr(app, "screenAt"):
            screen = app.screenAt(pos)
        else:
            screen = app.primaryScreen()

        rect = screen.availableGeometry()
        w, h = self.panel_width, self.panel_height
        x, y = pos.x(), pos.y()
        m    = self.MARGIN

        if x + w + m > rect.right():  x = rect.right()  - w - m
        if y + h + m > rect.bottom(): y = rect.bottom() - h - m
        if x < rect.left()  + m:      x = rect.left()   + m
        if y < rect.top()   + m:      y = rect.top()    + m

        # Place window at correct position BEFORE re-enabling updates
        # so no intermediate paint happens at 0,0
        self.setGeometry(x, y, w, h)
        self.setUpdatesEnabled(True)
        # Re-apply window flags before every show() — this re-arms the OS-level
        # Popup mouse grab so outside clicks dismiss the panel even when
        # Hypershade or UV Editor was the previously active window.
        self.setWindowFlags(
            QtCore.Qt.Tool |
            QtCore.Qt.FramelessWindowHint |
            QtCore.Qt.Popup
        )
        self.show()
        self.raise_()
        self.activateWindow()

    # ------------------------------------------------------------------
    # Close / cleanup
    # ------------------------------------------------------------------
    def closeEvent(self, event):
        self._exit_reposition_mode()
        self.save_tab_config(self.current_tab)
        self.save_global_state()
        self._stop_workspace_polling()

        for obj in self._event_filters_installed:
            try:
                obj.removeEventFilter(self)
            except Exception:
                pass
        self._event_filters_installed.clear()

        for btn in self.button_widgets:
            try:
                btn.cleanup()
            except Exception:
                pass

        for btn in self.quick_buttons:
            try:
                btn.clicked.disconnect()
            except Exception:
                pass

        super(PhoenixPanel, self).closeEvent(event)