# -*- coding: utf-8 -*-
"""Dialog for picking existing shelf buttons to add into PhoenixPanel."""

from __future__ import annotations

import maya.cmds as cmds

try:
    from PySide6 import QtWidgets, QtCore
except ImportError:
    from PySide2 import QtWidgets, QtCore

from .utils import resolve_maya_icon


class ShelfPickerDialog(QtWidgets.QDialog):

    def __init__(self, parent=None):
        super(ShelfPickerDialog, self).__init__(parent)

        self.setWindowTitle("Select Shelf Buttons")
        self.resize(420, 520)

        self._data = []
        self._process_queue = []
        self._process_index = 0
        self._current_shelf = ""
        self._icon_load_index = 0
        self._is_closed = False  # Track if dialog was closed

        layout = QtWidgets.QVBoxLayout(self)

        # Shelf selector row
        row = QtWidgets.QHBoxLayout()
        self.shelf_combo = QtWidgets.QComboBox()
        self.refresh_btn = QtWidgets.QPushButton("Refresh")

        row.addWidget(QtWidgets.QLabel("Shelf:"))
        row.addWidget(self.shelf_combo, 1)
        row.addWidget(self.refresh_btn)
        layout.addLayout(row)

        # List of shelf buttons
        self.list_widget = QtWidgets.QListWidget()
        self.list_widget.setSelectionMode(QtWidgets.QAbstractItemView.MultiSelection)
        layout.addWidget(self.list_widget)

        # Footer buttons
        row2 = QtWidgets.QHBoxLayout()
        self.select_all_btn = QtWidgets.QPushButton("Select All")
        self.ok_btn = QtWidgets.QPushButton("OK")
        self.cancel_btn = QtWidgets.QPushButton("Cancel")

        row2.addWidget(self.select_all_btn)
        row2.addStretch(1)
        row2.addWidget(self.ok_btn)
        row2.addWidget(self.cancel_btn)
        layout.addLayout(row2)

        # Signals
        self.refresh_btn.clicked.connect(self.populate_shelves)
        self.shelf_combo.currentIndexChanged.connect(self.populate_buttons)
        self.select_all_btn.clicked.connect(self.list_widget.selectAll)
        self.ok_btn.clicked.connect(self.accept)
        self.cancel_btn.clicked.connect(self.reject)

        # Start
        self.populate_shelves()

    # ---------------------------------------------------------
    # GET SHELVES
    # ---------------------------------------------------------
    def get_shelves(self):
        if cmds.shelfTabLayout("ShelfLayout", exists=True):
            try:
                return cmds.shelfTabLayout("ShelfLayout", q=True, childArray=True) or []
            except Exception:
                return []
        return []

    # ---------------------------------------------------------
    # POPULATE SHELF LIST
    # ---------------------------------------------------------
    def populate_shelves(self):
        self.shelf_combo.blockSignals(True)
        self.shelf_combo.clear()

        shelves = self.get_shelves()
        for s in shelves:
            self.shelf_combo.addItem(s)

        self.shelf_combo.blockSignals(False)

        if shelves:
            self.populate_buttons()

    # ---------------------------------------------------------
    # POPULATE BUTTONS (ASYNC)
    # ---------------------------------------------------------
    def populate_buttons(self):
        self.list_widget.clear()
        self._data = []
        self._icon_load_index = 0

        shelf = self.shelf_combo.currentText()
        if not shelf:
            return

        self._current_shelf = shelf

        try:
            children = cmds.shelfLayout(shelf, q=True, childArray=True) or []
        except Exception:
            children = []

        # Start async processing
        self._process_queue = list(children)
        self._process_index = 0
        
        if self._process_queue:
            QtCore.QTimer.singleShot(0, self._process_next_batch)

    # ---------------------------------------------------------
    # PROCESS BUTTONS IN BATCHES
    # ---------------------------------------------------------
    def _process_next_batch(self):
        # Safety check - stop if dialog was closed
        if self._is_closed:
            return
        
        BATCH_SIZE = 20  # Process 20 buttons at a time
        
        shelf = self._current_shelf
        
        for _ in range(BATCH_SIZE):
            if self._process_index >= len(self._process_queue):
                # Done processing, start loading icons
                QtCore.QTimer.singleShot(0, self._load_icons_batch)
                return
            
            btn = self._process_queue[self._process_index]
            self._process_index += 1
            
            # Build full path
            full = f"{shelf}|{btn}"
            if not cmds.shelfButton(full, exists=True):
                if not cmds.shelfButton(btn, exists=True):
                    continue
                full = btn

            # Extract fields
            try:
                label       = cmds.shelfButton(full, q=True, label=True) or ""
                ann         = cmds.shelfButton(full, q=True, annotation=True) or ""
                icon_label  = cmds.shelfButton(full, q=True, imageOverlayLabel=True) or ""
                icon        = cmds.shelfButton(full, q=True, image=True) or ""
                cmd         = cmds.shelfButton(full, q=True, command=True) or ""
                src         = cmds.shelfButton(full, q=True, sourceType=True) or "mel"
            except Exception:
                continue

            # STRICT RULE: overlay ONLY from imageOverlayLabel
            if icon_label and icon_label.strip():
                overlay = icon_label.strip()
            else:
                overlay = ""

            # Safety cleanup
            if overlay.lower() in {"-imageoverlaylabel", "imageoverlaylabel"}:
                overlay = ""

            info = {
                "full_path": full,
                "label": overlay,
                "annotation": ann,
                "icon_label": icon_label,
                "icon": icon,
                "command": cmd,
                "sourceType": src,
            }
            self._data.append(info)

            # Determine display name ONLY from the shelf's label
            if label and label.strip():
                display = label.strip()
            else:
                display = "The button has no name"

            item = QtWidgets.QListWidgetItem(display)
            
            # Store icon name for later loading
            item.setData(QtCore.Qt.UserRole, icon)
            
            if ann:
                item.setToolTip(ann)

            self.list_widget.addItem(item)
        
        # Schedule next batch if there are more items
        if self._process_index < len(self._process_queue):
            QtCore.QTimer.singleShot(0, self._process_next_batch)

    # ---------------------------------------------------------
    # LOAD ICONS IN BATCHES (ASYNC)
    # ---------------------------------------------------------
    def _load_icons_batch(self):
        # Safety check - stop if dialog was closed
        if self._is_closed:
            return
        
        BATCH_SIZE = 10  # Load 10 icons at a time
        
        count = self.list_widget.count()
        
        for _ in range(BATCH_SIZE):
            if self._icon_load_index >= count:
                return  # Done loading icons
            
            item = self.list_widget.item(self._icon_load_index)
            if item is None:  # Safety check
                self._icon_load_index += 1
                continue
            
            icon_name = item.data(QtCore.Qt.UserRole)
            
            if icon_name:
                try:
                    item.setIcon(resolve_maya_icon(icon_name))
                except Exception:
                    pass
            
            self._icon_load_index += 1
        
        # Schedule next batch if there are more icons to load
        if self._icon_load_index < count:
            QtCore.QTimer.singleShot(0, self._load_icons_batch)

    # ---------------------------------------------------------
    # CLEANUP
    # ---------------------------------------------------------
    def closeEvent(self, event):
        """Clean up when dialog closes."""
        self._is_closed = True
        self._process_queue.clear()
        self._data.clear()
        super(ShelfPickerDialog, self).closeEvent(event)

    def reject(self):
        """Override reject to ensure cleanup."""
        self._is_closed = True
        super(ShelfPickerDialog, self).reject()

    def accept(self):
        """Override accept to ensure cleanup."""
        self._is_closed = True
        super(ShelfPickerDialog, self).accept()

    # ---------------------------------------------------------
    # GET SELECTED BUTTONS
    # ---------------------------------------------------------
    def selected_buttons(self):
        out = []
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item and item.isSelected():
                if i < len(self._data):
                    out.append(self._data[i])
        return out