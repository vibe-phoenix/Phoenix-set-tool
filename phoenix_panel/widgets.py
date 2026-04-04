# -*- coding: utf-8 -*-
"""Button widget for PhoenixPanel.

Reposition mode is owned by the PANEL (core.py), not the button.
Buttons just report mouse events upward via signals and accept style commands.
"""

from __future__ import annotations

try:
    from PySide6 import QtWidgets, QtCore, QtGui
except ImportError:
    from PySide2 import QtWidgets, QtCore, QtGui


class _GhostLabel(QtWidgets.QLabel):
    """Semi-transparent floating pixmap that follows the cursor."""

    def __init__(self, pixmap, parent=None):
        super(_GhostLabel, self).__init__(parent)
        self.setWindowFlags(
            QtCore.Qt.ToolTip |
            QtCore.Qt.FramelessWindowHint |
            QtCore.Qt.WindowStaysOnTopHint
        )
        # NOTE: do NOT set WindowTransparentForInput — we need widgetAt() to
        # skip it, which we handle in the panel by temporarily hiding it.
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)
        self.setAttribute(QtCore.Qt.WA_ShowWithoutActivating, True)

        faded = QtGui.QPixmap(pixmap.size())
        faded.fill(QtCore.Qt.transparent)
        p = QtGui.QPainter(faded)
        p.setOpacity(0.72)
        p.drawPixmap(0, 0, pixmap)
        p.end()

        self.setPixmap(faded)
        self.resize(faded.size())

    def move_center_to(self, global_pos):
        self.move(global_pos - QtCore.QPoint(self.width() // 2, self.height() // 2))


class PhoenixButtonWidget(QtWidgets.QWidget):
    """Single grid button. Reposition drag logic lives in the panel."""

    # Emitted on left-click (execute)
    triggeredWithIndex = QtCore.Signal(int)
    # Context-menu actions
    requestDelete      = QtCore.Signal(int)
    requestReposition  = QtCore.Signal(int)   # panel sets reposition mode

    def __init__(self, index, overlay_label, icon, tooltip, parent=None):
        super(PhoenixButtonWidget, self).__init__(parent)
        self.index = index
        self._is_destroyed = False

        self.tool_btn = QtWidgets.QToolButton(self)
        self.tool_btn.setToolButtonStyle(QtCore.Qt.ToolButtonIconOnly)
        self.tool_btn.setIcon(icon)
        self.tool_btn.setToolTip(tooltip or "")

        self.overlay = QtWidgets.QLabel(overlay_label, self.tool_btn)
        self.overlay.setAlignment(QtCore.Qt.AlignCenter)
        self.overlay.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)
        self.has_label = bool(overlay_label and overlay_label.strip())
        if self.has_label:
            self.overlay.setStyleSheet("""
            QLabel {
                background-color: rgba(0,0,0,170);
                color: #f5f7ff;
                font-size: 9px;
                padding: 2px 3px;
                border-bottom-left-radius: 8px;
                border-bottom-right-radius: 8px;
            }
            """)
        else:
            self.overlay.setStyleSheet("background: transparent; color: transparent;")
            self.overlay.hide()

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.tool_btn)

        self.tool_btn.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.tool_btn.customContextMenuRequested.connect(self._show_menu)
        self.tool_btn.clicked.connect(
            lambda checked=False: self.triggeredWithIndex.emit(self.index)
        )

        self._normal_style()

    # ---------------------------------------------------------------- sizing
    def set_sizes(self, side, icon_size):
        total = side + 12
        self.setFixedSize(total, total)
        self.tool_btn.setFixedSize(total, total)
        self.tool_btn.setIconSize(QtCore.QSize(icon_size, icon_size))

    def resizeEvent(self, event):
        super(PhoenixButtonWidget, self).resizeEvent(event)
        if self.has_label and not self._is_destroyed:
            w = self.tool_btn.width()
            h = self.tool_btn.height()
            lh = max(16, int(h * 0.32))
            self.overlay.setGeometry(0, h - lh, w, lh)

    # --------------------------------------------------------------- styles
    def _normal_style(self):
        if self._is_destroyed:
            return
        self.tool_btn.setStyleSheet("""
        QToolButton {
            background-color: #202432;
            border-radius: 14px;
            padding: 6px;
        }
        QToolButton:hover { background-color: #2a3042; }
        QToolButton:pressed { background-color: #161a24; }
        QToolTip {
            background-color: #ffffdc;
            color: #000000;
            border: 1px solid #888888;
            padding: 1px 4px;
        }
        """)

    def _reposition_idle_style(self):
        """All buttons get this when reposition mode is active but nothing dragging."""
        if self._is_destroyed:
            return
        self.tool_btn.setStyleSheet("""
        QToolButton {
            background-color: #1c2030;
            border-radius: 14px;
            padding: 6px;
            border: 1px dashed #404a6a;
        }
        """)

    def _dragging_source_style(self):
        """The button being dragged shows an empty slot."""
        if self._is_destroyed:
            return
        self.tool_btn.setStyleSheet("""
        QToolButton {
            background-color: #10131a;
            border-radius: 14px;
            border: 2px dashed #2a3350;
        }
        """)

    def _drop_target_style(self):
        """Button lit up as the current drop destination."""
        if self._is_destroyed:
            return
        self.tool_btn.setStyleSheet("""
        QToolButton {
            background-color: #1e3050;
            border-radius: 14px;
            border: 2px solid #5a90d0;
        }
        """)

    # -------------------------------------------------------------- context menu
    def _show_menu(self, pos):
        if self._is_destroyed:
            return

        menu = QtWidgets.QMenu(self)
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
        QMenu::separator {
            height: 1px;
            background: #3a3a3a;
            margin: 3px 8px;
        }
        """)

        act_repos = menu.addAction("Reposition")
        menu.addSeparator()
        act_del = menu.addAction("Delete")

        gpos   = self.tool_btn.mapToGlobal(pos)
        chosen = menu.exec_(gpos) if hasattr(menu, "exec_") else menu.exec(gpos)

        if not chosen:
            return
        if chosen == act_repos:
            self.requestReposition.emit(self.index)
        elif chosen == act_del:
            self.requestDelete.emit(self.index)

    # ---------------------------------------------------------------- cleanup
    def cleanup(self):
        if self._is_destroyed:
            return
        self._is_destroyed = True
        try:
            if hasattr(self, "tool_btn") and self.tool_btn:
                self.tool_btn.clicked.disconnect()
                self.tool_btn.customContextMenuRequested.disconnect()
        except Exception:
            pass
        try:
            self.triggeredWithIndex.disconnect()
            self.requestDelete.disconnect()
            self.requestReposition.disconnect()
        except Exception:
            pass

    def __del__(self):
        self.cleanup()