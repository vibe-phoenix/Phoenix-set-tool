"""
Phoenix UV Transfer Tool
========================
Transfer UVs from one source object to multiple targets using Maya's
transferAttributes node, with full control over sample space,
search method, UV sets, flip and mirror options.

Usage:
    Run this script in Maya's Script Editor (Python tab).
    Or drag-drop into shelf.
"""

import maya.cmds as cmds
from maya import OpenMayaUI as omui

try:
    from PySide6.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
        QLabel, QComboBox, QCheckBox, QFrame, QSizePolicy
    )
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QFont, QColor
    from shiboken6 import wrapInstance
except ImportError:
    from PySide2.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
        QLabel, QComboBox, QCheckBox, QFrame, QSizePolicy
    )
    from PySide2.QtCore import Qt
    from PySide2.QtGui import QFont, QColor
    from shiboken2 import wrapInstance

import sys

# ── Helpers ──────────────────────────────────────────────────────────────────

def maya_main_window():
    ptr = omui.MQtUtil.mainWindow()
    return wrapInstance(int(ptr), QWidget)


def toast(msg, pos="topCenter"):
    """Viewport-style feedback via in-view message."""
    cmds.inViewMessage(amg=f"<hl>{msg}</hl>", pos=pos, fade=True, fst=700, fad=400)


# ── Constants ─────────────────────────────────────────────────────────────────

WINDOW_TITLE  = "Phoenix UV Transfer"
WINDOW_OBJECT = "PhoenixUVTransferWin"

# sampleSpace flag values for transferAttributes
SAMPLE_SPACE_MAP = {
    "World":     0,
    "Local":     1,
    "UV":        3,
    "Component": 4,
    "Topology":  5,
}

# searchMethod flag values
SEARCH_METHOD_MAP = {
    "Closest Along Normal": 0,
    "Closest Point":        3,
}

# ── Stylesheet ────────────────────────────────────────────────────────────────

STYLE = """
QWidget#PhoenixUVTransfer {
    background: #1e1e24;
    color: #d4d4dc;
    font-family: "Segoe UI", "SF Pro Text", sans-serif;
    font-size: 12px;
}

/* ── Section label ── */
QLabel#section_label {
    color: #6c6c80;
    font-size: 10px;
    letter-spacing: 1.5px;
    text-transform: uppercase;
    padding: 0px;
    margin: 0px;
}

/* ── Source info label ── */
QLabel#source_label {
    background: #2a2a34;
    border: 1px solid #3a3a48;
    border-radius: 4px;
    padding: 5px 8px;
    color: #a0a0b8;
    font-size: 11px;
}

/* ── Copy / Paste buttons ── */
QPushButton#btn_copy {
    background: #2d3a4f;
    border: 1px solid #3d5a8a;
    border-radius: 5px;
    color: #7ab8f5;
    font-size: 12px;
    font-weight: 600;
    padding: 8px 0px;
    letter-spacing: 0.5px;
}
QPushButton#btn_copy:hover {
    background: #3a4f6e;
    border-color: #5a8ad4;
    color: #a8d0ff;
}
QPushButton#btn_copy:pressed {
    background: #1e2d42;
}

QPushButton#btn_paste {
    background: #2a3f2a;
    border: 1px solid #3a7a3a;
    border-radius: 5px;
    color: #7ada7a;
    font-size: 12px;
    font-weight: 600;
    padding: 8px 0px;
    letter-spacing: 0.5px;
}
QPushButton#btn_paste:hover {
    background: #3a5a3a;
    border-color: #5aba5a;
    color: #a8f0a8;
}
QPushButton#btn_paste:pressed {
    background: #1e2e1e;
}
QPushButton#btn_paste:disabled {
    background: #222228;
    border-color: #333340;
    color: #444458;
}

/* ── Divider ── */
QFrame#divider {
    background: #2e2e3c;
    max-height: 1px;
    margin: 4px 0px;
}

/* ── ComboBox ── */
QComboBox {
    background: #26262e;
    border: 1px solid #3a3a4e;
    border-radius: 4px;
    color: #c8c8d8;
    padding: 4px 8px;
    font-size: 11px;
}
QComboBox:hover       { border-color: #5a5a7a; }
QComboBox::drop-down  { border: none; width: 20px; }
QComboBox::down-arrow { image: none; }
QComboBox QAbstractItemView {
    background: #22222e;
    border: 1px solid #3a3a4e;
    color: #c8c8d8;
    selection-background-color: #3a3a5a;
}

/* ── Row labels ── */
QLabel#row_label {
    color: #9090a8;
    font-size: 11px;
    min-width: 100px;
}

/* ── CheckBox ── */
QCheckBox {
    color: #9090a8;
    font-size: 11px;
    spacing: 6px;
}
QCheckBox::indicator {
    width: 14px; height: 14px;
    border: 1px solid #4a4a6a;
    border-radius: 3px;
    background: #26262e;
}
QCheckBox::indicator:checked {
    background: #4a6aaa;
    border-color: #6a8adf;
}
QCheckBox:hover { color: #c0c0d8; }

/* ── Active source badge ── */
QLabel#badge_active {
    background: #1e3a2a;
    border: 1px solid #2a6a3a;
    border-radius: 10px;
    color: #5ada8a;
    font-size: 10px;
    padding: 1px 8px;
    font-weight: 600;
}
QLabel#badge_none {
    background: #2e2a1e;
    border: 1px solid #5a4a1a;
    border-radius: 10px;
    color: #b89040;
    font-size: 10px;
    padding: 1px 8px;
    font-weight: 600;
}
"""

# ── UI ────────────────────────────────────────────────────────────────────────

class PhoenixUVTransfer(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent, Qt.Window)
        self.setObjectName("PhoenixUVTransfer")
        self.setWindowTitle(WINDOW_TITLE)
        self.setStyleSheet(STYLE)
        self.setMinimumWidth(310)
        self.setMaximumWidth(380)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Minimum)

        self._source_object = None
        self._build_ui()

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 14)
        root.setSpacing(10)

        # ── Title ──
        title = QLabel("UV TRANSFER")
        title.setObjectName("section_label")
        title.setAlignment(Qt.AlignCenter)
        f = title.font(); f.setPointSize(9); f.setLetterSpacing(QFont.AbsoluteSpacing, 2.5)
        title.setFont(f)
        root.addWidget(title)

        # ── Source row ──
        src_row = QHBoxLayout(); src_row.setSpacing(6)
        src_lbl = QLabel("Source:")
        src_lbl.setObjectName("row_label")
        src_row.addWidget(src_lbl)
        self.lbl_source = QLabel("None selected")
        self.lbl_source.setObjectName("source_label")
        self.lbl_source.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        src_row.addWidget(self.lbl_source)
        self.badge = QLabel("NONE")
        self.badge.setObjectName("badge_none")
        self.badge.setAlignment(Qt.AlignCenter)
        src_row.addWidget(self.badge)
        root.addLayout(src_row)

        # ── Copy / Paste buttons ──
        btn_row = QHBoxLayout(); btn_row.setSpacing(6)
        self.btn_copy  = QPushButton("⬆  COPY SOURCE")
        self.btn_copy.setObjectName("btn_copy")
        self.btn_copy.setToolTip("Select one object, then click to set as UV source")
        self.btn_copy.clicked.connect(self._on_copy)

        self.btn_paste = QPushButton("⬇  PASTE UVs")
        self.btn_paste.setObjectName("btn_paste")
        self.btn_paste.setToolTip("Select one or more targets, then click to transfer UVs")
        self.btn_paste.setEnabled(False)
        self.btn_paste.clicked.connect(self._on_paste)

        btn_row.addWidget(self.btn_copy)
        btn_row.addWidget(self.btn_paste)
        root.addLayout(btn_row)

        # ── Divider ──
        root.addWidget(self._divider())

        # ── Options label ──
        opt_lbl = QLabel("TRANSFER OPTIONS")
        opt_lbl.setObjectName("section_label")
        f2 = opt_lbl.font(); f2.setPointSize(8); f2.setLetterSpacing(QFont.AbsoluteSpacing, 1.8)
        opt_lbl.setFont(f2)
        root.addWidget(opt_lbl)

        # ── Sample Space ──
        root.addLayout(self._combo_row(
            "Sample Space:",
            ["Topology", "World", "Local", "UV", "Component"],
            attr="_cmb_sample_space"
        ))

        # ── Search Method ──
        root.addLayout(self._combo_row(
            "Search Method:",
            ["Closest Point", "Closest Along Normal"],
            attr="_cmb_search"
        ))

        # ── UV Sets ──
        root.addLayout(self._combo_row(
            "UV Sets:",
            ["Current", "All"],
            attr="_cmb_uvsets"
        ))

        # ── Divider ──
        root.addWidget(self._divider())

        # ── Flip / Mirror ──
        toggle_row = QHBoxLayout(); toggle_row.setSpacing(16)
        self.chk_flip   = QCheckBox("Flip UVs")
        self.chk_mirror = QCheckBox("Mirror UVs")
        toggle_row.addWidget(self.chk_flip)
        toggle_row.addWidget(self.chk_mirror)
        toggle_row.addStretch()
        root.addLayout(toggle_row)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _divider(self):
        d = QFrame(); d.setObjectName("divider")
        d.setFrameShape(QFrame.HLine)
        return d

    def _combo_row(self, label_text, items, attr=None, default=0):
        row = QHBoxLayout(); row.setSpacing(8)
        lbl = QLabel(label_text); lbl.setObjectName("row_label")
        row.addWidget(lbl)
        cmb = QComboBox()
        cmb.addItems(items)
        cmb.setCurrentIndex(default)
        cmb.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        row.addWidget(cmb)
        if attr:
            setattr(self, attr, cmb)
        return row

    # ── Logic ─────────────────────────────────────────────────────────────────

    def _on_copy(self):
        sel = cmds.ls(selection=True, long=True)
        if not sel:
            toast("⚠  Select a mesh first", "topCenter")
            return
        if len(sel) > 1:
            toast("⚠  Select only ONE source object", "topCenter")
            return

        # Validate it's a mesh
        shapes = cmds.listRelatives(sel[0], shapes=True, fullPath=True) or []
        if not any(cmds.nodeType(s) == "mesh" for s in shapes):
            toast("⚠  Selected object has no mesh shape", "topCenter")
            return

        self._source_object = sel[0]
        short = sel[0].split("|")[-1]
        self.lbl_source.setText(short)
        self.badge.setText("SET")
        self.badge.setObjectName("badge_active")
        self.badge.setStyleSheet("")   # force re-eval
        self.badge.setStyleSheet(STYLE)
        self.btn_paste.setEnabled(True)
        toast(f"✔  Source locked → {short}", "topCenter")

    def _on_paste(self):
        if not self._source_object:
            toast("⚠  No source set — use Copy Source first", "topCenter")
            return

        sel = cmds.ls(selection=True, long=True)
        if not sel:
            toast("⚠  Select one or more target meshes", "topCenter")
            return

        # Filter out the source itself
        targets = [o for o in sel if o != self._source_object]
        if not targets:
            toast("⚠  No valid targets (source == selection?)", "topCenter")
            return

        # ── Read options ──────────────────────────────────────────────────────
        ss_text  = self._cmb_sample_space.currentText()
        sm_text  = self._cmb_search.currentText()
        uvs_text = self._cmb_uvsets.currentText()
        flip     = self.chk_flip.isChecked()
        mirror   = self.chk_mirror.isChecked()

        sample_space  = SAMPLE_SPACE_MAP.get(ss_text, 5)
        search_method = SEARCH_METHOD_MAP.get(sm_text, 3)
        uv_flag       = 2 if uvs_text == "All" else 1  # 1=current, 2=all

        # ── Transfer ──────────────────────────────────────────────────────────
        success_count = 0
        fail_count    = 0

        for target in targets:
            try:
                cmds.transferAttributes(
                    self._source_object,
                    target,
                    transferPositions=0,
                    transferNormals=0,
                    transferUVs=uv_flag,
                    transferColors=0,
                    sampleSpace=sample_space,
                    searchMethod=search_method,
                    flipUVs=1 if flip else 0,
                )
                # Auto-delete history after bake so the node doesn't persist
                cmds.bakePartialHistory(target, prePostDeformers=True)

                # Mirror UVs post-transfer via polyEditUV (scale U by -1 around 0.5)
                if mirror:
                    all_uvs = cmds.polyListComponentConversion(target, toUV=True)
                    all_uvs = cmds.filterExpand(all_uvs, selectionMask=35, expand=True)
                    if all_uvs:
                        cmds.polyEditUV(
                            all_uvs,
                            pivotU=0.5, pivotV=0.5,
                            scaleU=-1.0, scaleV=1.0,
                            relative=False
                        )

                success_count += 1
            except Exception as e:
                fail_count += 1
                print(f"[PhoenixUVTransfer] Failed on {target}: {e}")

        # ── Feedback ──────────────────────────────────────────────────────────
        if fail_count == 0:
            toast(f"✔  UVs transferred to {success_count} object(s)", "topCenter")
        else:
            toast(
                f"⚠  {success_count} ok / {fail_count} failed — check Script Editor",
                "topCenter"
            )

# ── Launch ────────────────────────────────────────────────────────────────────

def launch():
    # Close existing window if open
    for widget in (maya_main_window().findChildren(QWidget, WINDOW_OBJECT) or []):
        widget.close()
        widget.deleteLater()

    win = PhoenixUVTransfer(parent=maya_main_window())
    win.setObjectName(WINDOW_OBJECT)
    win.show()
    win.raise_()


launch()