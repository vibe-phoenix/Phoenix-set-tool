# -*- coding: utf-8 -*-
"""Settings dialog for PhoenixPanel (rows/cols, quick buttons, etc.)."""

from __future__ import annotations

try:
    from PySide6 import QtWidgets, QtCore
except ImportError:
    from PySide2 import QtWidgets, QtCore


class PhoenixPanelSettings(QtWidgets.QDialog):

    settingsChanged = QtCore.Signal()

    def __init__(self, parent, panel):
        super(PhoenixPanelSettings, self).__init__(parent)

        self.panel = panel

        self.setWindowTitle("PhoenixPanel Settings")
        self.setWindowFlags(
            QtCore.Qt.Tool |
            QtCore.Qt.FramelessWindowHint |
            QtCore.Qt.WindowStaysOnTopHint
        )
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)
        self.setMinimumSize(520, 320)

        # ----------------- OUTER -----------------
        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        bg = QtWidgets.QWidget()
        bg.setObjectName("SettingsBg")
        bg.setStyleSheet("""
        #SettingsBg {
            background-color: #1a1d25;
            border-radius: 10px;
            border: 1px solid #444a57;
        }
        """)
        outer.addWidget(bg)

        layout = QtWidgets.QVBoxLayout(bg)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        # ----------------- TITLE BAR -----------------
        title_row = QtWidgets.QHBoxLayout()
        title = QtWidgets.QLabel("PhoenixPanel Settings")
        title.setStyleSheet("color: #f5f7ff; font-weight: bold; font-size: 13px;")
        title_row.addWidget(title)
        title_row.addStretch(1)

        close_btn = QtWidgets.QPushButton("✕")
        close_btn.setFixedSize(26, 26)
        close_btn.setStyleSheet("""
        QPushButton {
            background-color: #272c3a;
            color: #d0d2e0;
            border-radius: 13px;
        }
        QPushButton:hover {
            background-color: #ff4b6a;
        }
        """)
        close_btn.clicked.connect(self.close)
        title_row.addWidget(close_btn)

        layout.addLayout(title_row)

        # ----------------- GRID FORM (panel layout) -----------------
        grid = QtWidgets.QGridLayout()
        grid.setVerticalSpacing(8)
        grid.setHorizontalSpacing(10)

        self.rows_spin = QtWidgets.QSpinBox()
        self.rows_spin.setRange(1, 20)
        self.rows_spin.setValue(panel.rows)

        self.cols_spin = QtWidgets.QSpinBox()
        self.cols_spin.setRange(1, 20)
        self.cols_spin.setValue(panel.cols)

        self.scale_spin = QtWidgets.QDoubleSpinBox()
        self.scale_spin.setRange(0.4, 3.0)
        self.scale_spin.setSingleStep(0.1)
        self.scale_spin.setValue(panel.button_scale)

        self.pad_spin = QtWidgets.QSpinBox()
        self.pad_spin.setRange(0, 50)
        self.pad_spin.setValue(panel.padding)

        self.width_spin = QtWidgets.QSpinBox()
        self.width_spin.setRange(200, 1600)
        self.width_spin.setValue(panel.panel_width)

        self.height_spin = QtWidgets.QSpinBox()
        self.height_spin.setRange(150, 1200)
        self.height_spin.setValue(panel.panel_height)

        self.align_combo = QtWidgets.QComboBox()
        self.align_combo.addItems(["Left", "Center", "Right"])
        self.align_combo.setCurrentIndex(self.panel.quick_alignment)

        r = 0
        grid.addWidget(QtWidgets.QLabel("Rows"), r, 0)
        grid.addWidget(self.rows_spin, r, 1)
        grid.addWidget(QtWidgets.QLabel("Columns"), r, 2)
        grid.addWidget(self.cols_spin, r, 3)

        r += 1
        grid.addWidget(QtWidgets.QLabel("Button Scale"), r, 0)
        grid.addWidget(self.scale_spin, r, 1)
        grid.addWidget(QtWidgets.QLabel("Padding"), r, 2)
        grid.addWidget(self.pad_spin, r, 3)

        r += 1
        grid.addWidget(QtWidgets.QLabel("Panel Width"), r, 0)
        grid.addWidget(self.width_spin, r, 1)
        grid.addWidget(QtWidgets.QLabel("Panel Height"), r, 2)
        grid.addWidget(self.height_spin, r, 3)

        r += 1
        grid.addWidget(QtWidgets.QLabel("Hot Buttons Align"), r, 0)
        grid.addWidget(self.align_combo, r, 1)

        self.grid_row_align_combo = QtWidgets.QComboBox()
        self.grid_row_align_combo.addItems(["Left", "Center", "Right"])
        self.grid_row_align_combo.setCurrentIndex(getattr(panel, "grid_row_alignment", 1))
        grid.addWidget(QtWidgets.QLabel("Last Row Align"), r, 2)
        grid.addWidget(self.grid_row_align_combo, r, 3)

        r += 1
        self.grid_full_row_align_combo = QtWidgets.QComboBox()
        self.grid_full_row_align_combo.addItems(["Left", "Center", "Right"])
        self.grid_full_row_align_combo.setCurrentIndex(getattr(panel, "grid_full_row_alignment", 1))
        grid.addWidget(QtWidgets.QLabel("Full Rows Align"), r, 0)
        grid.addWidget(self.grid_full_row_align_combo, r, 1)

        layout.addLayout(grid)

        # -------------------------------------------------
        # WORKSPACE TOGGLE PAIR
        # -------------------------------------------------
        ws_label = QtWidgets.QLabel("Right-Click ⚙ Workspace Toggle")
        ws_label.setStyleSheet("color: #f5f7ff; font-weight: bold; margin-top: 4px;")
        layout.addWidget(ws_label)

        ws_hint = QtWidgets.QLabel(
            "Right-clicking ⚙ cycles between these two workspaces."
        )
        ws_hint.setStyleSheet("color: #8899bb; font-size: 10px; font-style: italic;")
        layout.addWidget(ws_hint)

        ws_row = QtWidgets.QHBoxLayout()
        ws_row.setSpacing(8)
        # Fetch available workspaces.
        # <userPrefDir>/workspaces/ contains one .json per workspace (built-in + custom).
        # Filenames use underscores for spaces (e.g. UV_Editing.json -> "UV Editing").
        # We convert underscores back to spaces and deduplicate against the hardcoded
        # built-in list so "UV Editing" and "UV_Editing" don't both appear.
        try:
            import os as _os
            import maya.cmds as _cmds

            _BUILTIN = [
                "General", "UV Editing", "Rigging", "Sculpting",
                "Rendering", "XGen", "Motion Graphics",
            ]
            # Normalise to lowercase-no-space for dedup comparison
            _builtin_keys = {w.replace(" ", "").lower(): w for w in _BUILTIN}

            _ws_dir = _os.path.join(
                (_cmds.internalVar(userPrefDir=True) or "").rstrip("/\\"),
                "workspaces"
            )

            _found = set()
            if _os.path.isdir(_ws_dir):
                for _fname in _os.listdir(_ws_dir):
                    if _fname.endswith(".json"):
                        # Convert underscores to spaces to get display name
                        _name = _fname[:-5].replace("_", " ")
                        _key  = _name.replace(" ", "").lower()
                        # Use the canonical built-in spelling if it matches one
                        _found.add(_builtin_keys.get(_key, _name))

            # Always include built-ins even if the prefs folder is missing
            _available_workspaces = sorted(set(_BUILTIN) | _found)

        except Exception:
            _available_workspaces = ["General", "UV Editing", "Rigging", "Sculpting",
                                     "Rendering", "XGen", "Motion Graphics"]

        _current_cycle = getattr(panel, "workspace_cycle", ["General", "UV Editing"])

        ws_a_label = QtWidgets.QLabel("Workspace A:")
        ws_a_label.setStyleSheet("color: #c8d2ff; font-size: 11px;")
        self.ws_a_combo = QtWidgets.QComboBox()
        self.ws_a_combo.addItems(_available_workspaces)
        _idx_a = self.ws_a_combo.findText(_current_cycle[0])
        if _idx_a >= 0:
            self.ws_a_combo.setCurrentIndex(_idx_a)

        ws_arrow = QtWidgets.QLabel("⇄")
        ws_arrow.setStyleSheet("color: #505878; font-size: 14px;")
        ws_arrow.setAlignment(QtCore.Qt.AlignCenter)

        ws_b_label = QtWidgets.QLabel("Workspace B:")
        ws_b_label.setStyleSheet("color: #c8d2ff; font-size: 11px;")
        self.ws_b_combo = QtWidgets.QComboBox()
        self.ws_b_combo.addItems(_available_workspaces)
        _idx_b = self.ws_b_combo.findText(_current_cycle[1])
        if _idx_b >= 0:
            self.ws_b_combo.setCurrentIndex(_idx_b)

        ws_row.addWidget(ws_a_label)
        ws_row.addWidget(self.ws_a_combo, 1)
        ws_row.addWidget(ws_arrow)
        ws_row.addWidget(ws_b_label)
        ws_row.addWidget(self.ws_b_combo, 1)
        layout.addLayout(ws_row)

        # -------------------------------------------------
        # VISIBILITY TOGGLES ROW (1–5)
        # -------------------------------------------------
        vis_row_label = QtWidgets.QLabel("Hot Buttons Visibility")
        vis_row_label.setStyleSheet("color: #f5f7ff; font-weight: bold; margin-top: 4px;")
        layout.addWidget(vis_row_label)

        self.vis_toggle_layout = QtWidgets.QHBoxLayout()
        self.vis_toggle_layout.setSpacing(6)
        self.vis_toggle_layout.addStretch(1)

        self.vis_toggle_buttons = []

        for i in range(5):
            btn = QtWidgets.QPushButton(str(i + 1))
            btn.setCheckable(True)
            visible = self.panel.custom_buttons[i].get("visible", True)
            btn.setChecked(visible)
            self._style_vis_toggle(btn, visible)
            btn.clicked.connect(lambda checked=False, idx=i, b=btn: self._on_vis_toggle(idx, b.isChecked()))

            btn.setFixedWidth(36)
            self.vis_toggle_buttons.append(btn)
            self.vis_toggle_layout.addWidget(btn)

        self.vis_toggle_layout.addStretch(1)
        layout.addLayout(self.vis_toggle_layout)

        # -------------------------------------------------
        # TITLE MIDDLE-CLICK CODE
        # -------------------------------------------------
        title_click_label = QtWidgets.QLabel("Title Middle-Click Code")
        title_click_label.setStyleSheet("color: #f5f7ff; font-weight: bold; margin-top: 4px;")
        layout.addWidget(title_click_label)

        title_click_row = QtWidgets.QHBoxLayout()
        title_click_row.setSpacing(6)
        tc_type_label = QtWidgets.QLabel("Type:")
        tc_type_label.setStyleSheet("color: #c8d2ff; font-size: 11px;")
        self.title_click_type_box = QtWidgets.QComboBox()
        self.title_click_type_box.addItems(["Python", "MEL"])
        cur_tc_type = (getattr(panel, "title_click_type", "python") or "python").lower()
        self.title_click_type_box.setCurrentIndex(0 if cur_tc_type == "python" else 1)
        title_click_row.addWidget(tc_type_label)
        title_click_row.addWidget(self.title_click_type_box)
        title_click_row.addStretch(1)
        layout.addLayout(title_click_row)

        self.title_click_edit = QtWidgets.QTextEdit()
        self.title_click_edit.setPlainText(getattr(panel, "title_click_code", "") or "")
        self.title_click_edit.setFixedHeight(70)
        self.title_click_edit.setPlaceholderText("Python or MEL code to run on middle-click of the title…")
        self.title_click_edit.setStyleSheet("""
        QTextEdit {
            background: #10131a;
            color: #f5f7ff;
            border-radius: 4px;
            border: 1px solid #303645;
            font-family: Consolas, 'Courier New', monospace;
            font-size: 11px;
        }
        """)
        layout.addWidget(self.title_click_edit)

        # -------------------------------------------------
        # QUICK BUTTON EDITOR (TABS)
        # -------------------------------------------------
        self.tabs = QtWidgets.QTabWidget()
        self.tabs.setStyleSheet("""
        QTabWidget::pane {
            border: 1px solid #333a4a;
            border-radius: 6px;
            top: -4px;
        }
        QTabBar::tab {
            background: #252a39;
            color: #c8d2ff;
            padding: 4px 10px;
            border-top-left-radius: 6px;
            border-top-right-radius: 6px;
            margin-right: 2px;
        }
        QTabBar::tab:selected {
            background: #32384c;
        }
        """)
        layout.addWidget(self.tabs)

        self.quick_name_edits = []
        self.quick_tooltip_edits = []
        self.quick_type_boxes = []
        self.quick_code_edits = []
        self.quick_rc_enabled = []
        self.quick_rc_name_edits = []
        self.quick_rc_type_boxes = []
        self.quick_rc_code_edits = []

        # Ensure we always have 5 slots
        while len(self.panel.custom_buttons) < 5:
            self.panel.custom_buttons.append({
                "name": "BTN{}".format(len(self.panel.custom_buttons) + 1),
                "tooltip": "",
                "type": "mel",
                "code": "",
                "visible": True,
            })

        for i in range(5):
            data = self.panel.custom_buttons[i]
            tab = QtWidgets.QWidget()
            tlay = QtWidgets.QVBoxLayout(tab)
            tlay.setContentsMargins(8, 8, 8, 8)
            tlay.setSpacing(6)

            form = QtWidgets.QFormLayout()
            form.setLabelAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)

            name_edit = QtWidgets.QLineEdit()
            name_edit.setMaxLength(4)
            name_edit.setText((data.get("name", "BTN{}".format(i + 1))[:4]).upper())
            name_edit.setPlaceholderText("4-char label, e.g. ABCD")

            tooltip_edit = QtWidgets.QLineEdit()
            tooltip_edit.setText(data.get("tooltip", ""))
            tooltip_edit.setPlaceholderText("Tooltip for this button")

            type_box = QtWidgets.QComboBox()
            type_box.addItems(["MEL", "Python"])
            cur_type = (data.get("type", "mel") or "mel").lower()
            type_box.setCurrentIndex(1 if cur_type == "python" else 0)

            form.addRow("Button Name", name_edit)
            form.addRow("Tooltip", tooltip_edit)
            form.addRow("Code Type", type_box)

            tlay.addLayout(form)

            code_label = QtWidgets.QLabel("Button Code")
            code_label.setStyleSheet("color: #c8d2ff; font-size: 11px;")
            tlay.addWidget(code_label)

            code_edit = QtWidgets.QTextEdit()
            code_edit.setPlainText(data.get("code", ""))
            code_edit.setMinimumHeight(80)
            code_edit.setStyleSheet("""
            QTextEdit {
                background: #10131a;
                color: #f5f7ff;
                border-radius: 4px;
                border: 1px solid #303645;
                font-family: Consolas, 'Courier New', monospace;
                font-size: 11px;
            }
            """)
            tlay.addWidget(code_edit)

            # ---- Right-click action (global, not tab-specific) ----
            rc_data = panel.quick_button_rc[i] if i < len(panel.quick_button_rc) else {}

            rc_sep = QtWidgets.QFrame()
            rc_sep.setFrameShape(QtWidgets.QFrame.HLine)
            rc_sep.setStyleSheet("color: #303645;")
            tlay.addWidget(rc_sep)

            rc_header_row = QtWidgets.QHBoxLayout()
            rc_label = QtWidgets.QLabel("Right-Click Action  (shared across all tabs)")
            rc_label.setStyleSheet("color: #8899bb; font-size: 10px; font-style: italic;")
            rc_header_row.addWidget(rc_label)
            rc_header_row.addStretch(1)
            rc_enabled_chk = QtWidgets.QCheckBox("Enable")
            rc_enabled_chk.setChecked(bool(rc_data.get("enabled", False)))
            rc_header_row.addWidget(rc_enabled_chk)
            tlay.addLayout(rc_header_row)

            rc_form = QtWidgets.QFormLayout()
            rc_form.setLabelAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
            rc_name_edit = QtWidgets.QLineEdit()
            rc_name_edit.setMaxLength(20)
            rc_name_edit.setText(rc_data.get("name", ""))
            rc_name_edit.setPlaceholderText("Label shown in menu / as button text")
            rc_type_box = QtWidgets.QComboBox()
            rc_type_box.addItems(["Python", "MEL"])
            rc_cur_type = (rc_data.get("type", "python") or "python").lower()
            rc_type_box.setCurrentIndex(0 if rc_cur_type == "python" else 1)
            rc_form.addRow("Action Name", rc_name_edit)
            rc_form.addRow("Code Type", rc_type_box)
            tlay.addLayout(rc_form)

            rc_code_label = QtWidgets.QLabel("Right-Click Code")
            rc_code_label.setStyleSheet("color: #8899bb; font-size: 10px;")
            tlay.addWidget(rc_code_label)

            rc_code_edit = QtWidgets.QTextEdit()
            rc_code_edit.setPlainText(rc_data.get("code", ""))
            rc_code_edit.setMinimumHeight(60)
            rc_code_edit.setStyleSheet("""
            QTextEdit {
                background: #10131a;
                color: #f5f7ff;
                border-radius: 4px;
                border: 1px solid #2a3050;
                font-family: Consolas, 'Courier New', monospace;
                font-size: 11px;
            }
            """)
            tlay.addWidget(rc_code_edit)

            tlay.addStretch(1)

            self.tabs.addTab(tab, "Button {}".format(i + 1))

            self.quick_name_edits.append(name_edit)
            self.quick_tooltip_edits.append(tooltip_edit)
            self.quick_type_boxes.append(type_box)
            self.quick_code_edits.append(code_edit)
            self.quick_rc_enabled.append(rc_enabled_chk)
            self.quick_rc_name_edits.append(rc_name_edit)
            self.quick_rc_type_boxes.append(rc_type_box)
            self.quick_rc_code_edits.append(rc_code_edit)




        # ----------------- IMPORT / EXPORT -----------------
        impex_row = QtWidgets.QHBoxLayout()

        self.import_btn = QtWidgets.QPushButton("Import")
        self.export_btn = QtWidgets.QPushButton("Export")

        for b in (self.import_btn, self.export_btn):
            b.setFixedHeight(26)
            b.setStyleSheet("""
            QPushButton {
                background: #2c3348;
                color: #d6daf5;
                border-radius: 6px;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover { background: #3a4057; }
            """)

        impex_row.addWidget(self.import_btn)
        impex_row.addWidget(self.export_btn)
        layout.addLayout(impex_row)


        # ----------------- DELETE ALL BUTTON -----------------
        self.delete_all_btn = QtWidgets.QPushButton("Delete All Buttons")
        self.delete_all_btn.setFixedHeight(26)
        self.delete_all_btn.setStyleSheet("""
        QPushButton {
            background: #612a3d;
            color: #ffb1c8;
            border-radius: 6px;
            font-size: 11px;
            font-weight: bold;
        }
        QPushButton:hover { background: #8b3d54; }
        """)
        layout.addWidget(self.delete_all_btn)



        # ----------------- APPLY BUTTON -----------------
        apply_btn = QtWidgets.QPushButton("Apply")
        apply_btn.setFixedHeight(30)
        apply_btn.setStyleSheet("""
        QPushButton {
            background-color: #2a3142;
            color: #ffffff;
            border-radius: 6px;
        }
        QPushButton:hover {
            background-color: #435072;
        }
        """)
        layout.addWidget(apply_btn)

        apply_btn.clicked.connect(self.apply_changes)
        self.import_btn.clicked.connect(self._import_config)
        self.export_btn.clicked.connect(self._export_config)
        self.delete_all_btn.clicked.connect(self._delete_all_confirm)


    # -----------------------------------------------------
    # VIS TOGGLE STYLE
    # -----------------------------------------------------
    def _style_vis_toggle(self, btn, state):
        """Green = visible, Grey = hidden."""
        if state:
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #4caf50;
                    color: white;
                    border-radius: 4px;
                    font-weight: bold;
                }
            """)
        else:
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #2c3348;
                    color: #a0a7c2;
                    border-radius: 4px;
                    font-weight: bold;
                }
            """)

    # -----------------------------------------------------
    # VIS TOGGLE HANDLER
    # -----------------------------------------------------
    def _on_vis_toggle(self, idx, checked):
        # Update underlying data
        self.panel.custom_buttons[idx]["visible"] = checked
        # Restyle this toggle button
        self._style_vis_toggle(self.vis_toggle_buttons[idx], checked)
        # Refresh hot buttons in main panel
        self.panel.update_quick_buttons()
        self.panel.save_config()

    # -----------------------------------------------------
    # APPLY SETTINGS (Auto-close after apply)
    # -----------------------------------------------------
    def apply_changes(self):
        # Panel geometry
        self.panel.rows = self.rows_spin.value()
        self.panel.cols = self.cols_spin.value()
        self.panel.button_scale = self.scale_spin.value()
        self.panel.padding = self.pad_spin.value()
        self.panel.panel_width = max(self.width_spin.value(), 460)
        self.panel.panel_height = max(self.height_spin.value(), 200)
        self.panel.quick_alignment    = self.align_combo.currentIndex()
        self.panel.grid_full_row_alignment = self.grid_full_row_align_combo.currentIndex()
        self.panel.grid_row_alignment       = self.grid_row_align_combo.currentIndex()
        self.panel.title_click_code   = self.title_click_edit.toPlainText()
        self.panel.title_click_type   = "python" if self.title_click_type_box.currentIndex() == 0 else "mel"

        # Workspace cycle pair
        ws_a = self.ws_a_combo.currentText().strip()
        ws_b = self.ws_b_combo.currentText().strip()
        if ws_a and ws_b:
            self.panel.workspace_cycle = [ws_a, ws_b]

        # Quick buttons (name, tooltip, type, code, visible)
        # Also save global right-click actions
        for i in range(5):
            data = self.panel.custom_buttons[i]

            name = (self.quick_name_edits[i].text() or "BTN{}".format(i + 1)).upper()[:4]
            tooltip = self.quick_tooltip_edits[i].text() or ""
            btn_type = "python" if self.quick_type_boxes[i].currentIndex() == 1 else "mel"
            code = self.quick_code_edits[i].toPlainText() or ""

            # Right-click action
            self.panel.quick_button_rc[i] = {
                "name":    self.quick_rc_name_edits[i].text().strip(),
                "code":    self.quick_rc_code_edits[i].toPlainText(),
                "type":    "python" if self.quick_rc_type_boxes[i].currentIndex() == 0 else "mel",
                "enabled": self.quick_rc_enabled[i].isChecked(),
            }
            visible = self.vis_toggle_buttons[i].isChecked()

            data["name"] = name
            data["tooltip"] = tooltip
            data["type"] = btn_type
            data["code"] = code
            data["visible"] = visible

        # Apply on panel
        self.panel.rebuild_grid()
        self.panel.update_quick_buttons()
        self.panel.save_config()
        self.panel.save_global_state()  # persist shared rc actions
        self.panel.resize(self.panel.panel_width, self.panel.panel_height)

        self.settingsChanged.emit()
        self.accept()



    def _import_config(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Import PhoenixPanel Preset",
            "",
            "PhoenixPanel Preset (*.json)"
        )
        if not path:
            return

        try:
            import json
            with open(path, "r") as f:
                config = json.load(f)

            self.panel.custom_buttons = config.get("quick_buttons", self.panel.custom_buttons)
            self.panel.buttons_data = config.get("buttons", self.panel.buttons_data)

            self.panel.save_config()
            self.panel.rebuild_grid()
            self.panel.update_quick_buttons()
            self.settingsChanged.emit()

        except Exception as e:
            cmds.warning("Import failed: {}".format(e))


    def _export_config(self):
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Export PhoenixPanel Preset",
            "phoenix_panel_preset.json",
            "PhoenixPanel Preset (*.json)"
        )
        if not path:
            return

        try:
            import json
            data = {
                "quick_buttons": self.panel.custom_buttons,
                "buttons": self.panel.buttons_data,
            }
            with open(path, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            cmds.warning("Export failed: {}".format(e))


    def _delete_all_confirm(self):
        reply = QtWidgets.QMessageBox.question(
            self,
            "Confirm Delete",
            "Are you sure you want to delete **all panel buttons**?\n"
            "This cannot be undone.",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.Cancel,
            QtWidgets.QMessageBox.Cancel
        )
        if reply != QtWidgets.QMessageBox.Yes:
            return

        self.panel.buttons_data = []
        self.panel.save_config()
        self.panel.rebuild_grid()
        self.settingsChanged.emit()