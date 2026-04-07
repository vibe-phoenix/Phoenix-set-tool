# =============================================================================
# Phoenix UV Toolbox
# Compatible with Maya 2024+
# PySide2 / PySide6 compatible
# Dockable via Maya's workspaceControl
# =============================================================================

try:
    from PySide6 import QtWidgets, QtCore, QtGui
    from PySide6.QtCore import Qt
    PYSIDE_VERSION = 6
except ImportError:
    from PySide2 import QtWidgets, QtCore, QtGui
    from PySide2.QtCore import Qt
    PYSIDE_VERSION = 2

from functools import partial
import maya.cmds as cmds
import maya.mel as mel
import maya.OpenMayaUI as omui

try:
    from shiboken6 import wrapInstance
except ImportError:
    from shiboken2 import wrapInstance


# =============================================================================
# CONSTANTS
# =============================================================================
TOOL_NAME        = "PhoenixUVToolbox"
WORKSPACE_CTRL   = TOOL_NAME + "WorkspaceControl"
TOOL_VERSION     = "Phoenix UV Toolbox v1.1"

# Colour palette  (R, G, B  0-255)
C_RED        = "#B34244"
C_GREEN      = "#48AC48"
C_BLUE       = "#2576BC"
C_GREY       = "#828282"
C_ORANGE     = "#C5854D"
C_YELLOW     = "#B8AE63"
C_TEAL       = "#6DA4A4"
C_PURPLE     = "#9887C4"
C_PURPLE2    = "#7387C7"
C_GREEN2     = "#569778"
C_GREENYEL   = "#80AB5E"
C_DARK       = "#2b2b2b"
C_SECTION    = "#3a3a3a"
C_HEADER     = "#1e1e1e"


# =============================================================================
# STYLE HELPERS
# =============================================================================
def btn_style(color, text_color="#ffffff", radius=4, height=22):
    return (
        f"QPushButton{{"
        f"background:{color};color:{text_color};"
        f"border-radius:{radius}px;"
        f"font-size:11px;font-weight:600;"
        f"padding:0 4px;"
        f"min-height:{height}px;max-height:{height}px;"
        f"}}"
        f"QPushButton:hover{{background:{color}cc;}}"
        f"QPushButton:pressed{{background:{color}88;}}"
    )


def section_label(text):
    lbl = QtWidgets.QLabel(text)
    lbl.setAlignment(Qt.AlignCenter)
    lbl.setStyleSheet(
        f"color:#cccccc;font-size:10px;font-weight:700;"
        f"background:{C_SECTION};border-radius:3px;"
        f"padding:2px 0;"
    )
    lbl.setFixedHeight(18)
    return lbl


def make_btn(label, color, callback, height=22, tooltip=""):
    b = QtWidgets.QPushButton(label)
    b.setStyleSheet(btn_style(color, height=height))
    b.clicked.connect(callback)
    if tooltip:
        b.setToolTip(tooltip)
    return b


def make_check(label, default=True):
    cb = QtWidgets.QCheckBox(label)
    cb.setChecked(default)
    cb.setStyleSheet("color:#cccccc;font-size:11px;")
    return cb


def hline():
    f = QtWidgets.QFrame()
    f.setFrameShape(QtWidgets.QFrame.HLine)
    f.setStyleSheet("color:#444;")
    f.setFixedHeight(1)
    return f


def row(*widgets, spacing=3):
    w = QtWidgets.QWidget()
    l = QtWidgets.QHBoxLayout(w)
    l.setContentsMargins(0, 0, 0, 0)
    l.setSpacing(spacing)
    for ww in widgets:
        if ww == "stretch":
            l.addStretch()
        else:
            l.addWidget(ww)
    return w


def col(*widgets, spacing=3):
    w = QtWidgets.QWidget()
    l = QtWidgets.QVBoxLayout(w)
    l.setContentsMargins(0, 0, 0, 0)
    l.setSpacing(spacing)
    for ww in widgets:
        if ww == "stretch":
            l.addStretch()
        else:
            l.addWidget(ww)
    return w


# Shared spinbox stylesheet – up button muted blue (+), down muted red (-)
_SPINBOX_SS = (
    "QSpinBox, QDoubleSpinBox {"
    "  background: #1e1e1e; color: #ddd;"
    "  border: 1px solid #555; border-radius: 3px;"
    "  font-size: 11px;"
    "  padding-left: 4px; padding-right: 18px;"
    "}"
    "QSpinBox::up-button, QDoubleSpinBox::up-button {"
    "  subcontrol-origin: border;"
    "  subcontrol-position: top right;"
    "  width: 16px; height: 10px;"
    "  border-left: 1px solid #555;"
    "  border-bottom: 1px solid #444;"
    "  border-top-right-radius: 3px;"
    "  background: #2a2a2a;"
    "}"
    "QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover {"
    "  background: #333;"
    "}"
    "QSpinBox::down-button, QDoubleSpinBox::down-button {"
    "  subcontrol-origin: border;"
    "  subcontrol-position: bottom right;"
    "  width: 16px; height: 10px;"
    "  border-left: 1px solid #555;"
    "  border-bottom-right-radius: 3px;"
    "  background: #2a2a2a;"
    "}"
    "QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {"
    "  background: #333;"
    "}"
    "QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {"
    "  width: 8px; height: 8px;"
    "}"
    "QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {"
    "  width: 8px; height: 8px;"
    "}"
)

class _SpinArrowStyle(QtWidgets.QProxyStyle):
    """Draws ▲ (blue) for up and ▼ (red) for down on all spinboxes."""
    def drawPrimitive(self, element, option, painter, widget=None):
        PE = QtWidgets.QStyle.PrimitiveElement
        if element in (PE.PE_IndicatorSpinUp, PE.PE_IndicatorSpinDown):
            painter.save()
            painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
            r  = option.rect
            cx = r.center().x()
            cy = r.center().y()
            w, h = 5, 3
            # ▲ blue, ▼ red
            if element == PE.PE_IndicatorSpinUp:
                color = QtGui.QColor("#5ab4f0")
                poly  = QtGui.QPolygon()
                poly.setPoints(6,
                    cx - w, cy + h,
                    cx + w, cy + h,
                    cx,     cy - h)
            else:
                color = QtGui.QColor("#e06060")
                poly  = QtGui.QPolygon()
                poly.setPoints(6,
                    cx - w, cy - h,
                    cx + w, cy - h,
                    cx,     cy + h)
            painter.setPen(QtCore.Qt.NoPen)
            painter.setBrush(color)
            painter.drawPolygon(poly)
            painter.restore()
        else:
            super().drawPrimitive(element, option, painter, widget)


_spin_arrow_style = None   # created once, shared across all spinboxes

def _get_spin_style():
    global _spin_arrow_style
    if _spin_arrow_style is None:
        _spin_arrow_style = _SpinArrowStyle()
    return _spin_arrow_style


def spin_box(value, mn, mx, decimals=0, width=None):
    if decimals:
        sb = QtWidgets.QDoubleSpinBox()
        sb.setDecimals(decimals)
    else:
        sb = QtWidgets.QSpinBox()
    sb.setMinimum(mn)
    sb.setMaximum(mx)
    sb.setValue(value)
    if width is not None:
        sb.setFixedWidth(width)
    else:
        sb.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed
        )
    sb.setFixedHeight(22)
    sb.setStyleSheet(_SPINBOX_SS)
    sb.setStyle(_get_spin_style())
    return sb


def combo_box(items, width=90):
    cb = QtWidgets.QComboBox()
    cb.addItems(items)
    cb.setFixedWidth(width)
    cb.setFixedHeight(22)
    cb.setStyleSheet(
        "QComboBox{background:#1e1e1e;color:#ddd;"
        "border:1px solid #555;border-radius:3px;"
        "font-size:11px;padding:0 4px;}"
        "QComboBox::drop-down{border:none;}"
        "QComboBox QAbstractItemView{background:#2b2b2b;color:#ddd;"
        "selection-background-color:#444;}"
    )
    return cb


# =============================================================================
# MAYA MEL / CMD HELPERS
# =============================================================================
def mel_run(cmd):
    try:
        mel.eval(cmd)
    except Exception as e:
        cmds.warning(f"[PhoenixUV] MEL error: {e}")


def run(fn):
    """Decorator – wraps a method so exceptions print as warnings."""
    def wrapper(*a, **kw):
        try:
            return fn(*a, **kw)
        except Exception as e:
            cmds.warning(f"[PhoenixUV] {fn.__name__}: {e}")
    return wrapper



# =============================================================================
# UTILITY – split a flat UV list into per-shell sublists
# =============================================================================
def _mel_get_shells():
    """Port of MEL texGetShells().
    Returns a list of UV-string lists, one sublist per active UV shell.
    Uses ConvertSelectionToUVShell iteratively via MEL to get each shell,
    matching what MEL tokenize(texGetShells()[i]) produces.
    """
    # Get all selected UVs first
    all_uvs = cmds.ls(sl=True, fl=True) or []
    if not all_uvs:
        return []

    # Get the shape node from the first UV string e.g. "pSphereShape1.map[0]"
    shape = all_uvs[0].split(".")[0]

    # Use polyEvaluate -aus/-uis on the shape directly
    try:
        active_shells = cmds.polyEvaluate(shape, aus=True) or []
    except Exception:
        return []

    result = []
    for s in active_shells:
        try:
            uv_indices = cmds.polyEvaluate(shape, uis=s) or []
            if uv_indices:
                result.append([f"{shape}.map[{idx}]" for idx in uv_indices])
        except Exception:
            pass
    return result


# =============================================================================
# UV TOOLBOX  – MAIN WIDGET
# =============================================================================
# UV TOOLBOX  – MAIN WIDGET
# =============================================================================
class PhoenixUVToolbox(QtWidgets.QWidget):

    # ------------------------------------------------------------------ init
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName(TOOL_NAME)
        self.setMinimumWidth(230)
        self.setStyleSheet(
            f"QWidget{{background:{C_DARK};color:#cccccc;font-size:11px;}}"
            f"QScrollArea{{border:none;}}"
            f"QScrollBar:vertical{{background:#222;width:6px;border-radius:3px;}}"
            f"QScrollBar::handle:vertical{{background:#555;border-radius:3px;}}"
        )
        # load saved font size from Maya optionVar (persists across restarts)
        _OV = "phoenixUVToolbox_fontSize"
        if cmds.optionVar(exists=_OV):
            self._font_size = cmds.optionVar(q=_OV)
        else:
            self._font_size = 11
        self._build_ui()
        # apply saved scale after UI is built
        if self._font_size != 11:
            self._apply_font_size(self._font_size)

    def mousePressEvent(self, event):
        btn = event.button()
        if btn in (QtCore.Qt.ExtraButton1, QtCore.Qt.ExtraButton2):
            self._stack.setCurrentIndex(1)
            UVGrouperPage.instance = self._grouper_page
        else:
            super().mousePressEvent(event)

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        root_layout = QtWidgets.QVBoxLayout(self)
        root_layout.setContentsMargins(4, 4, 4, 4)
        root_layout.setSpacing(4)

        # title
        title = QtWidgets.QLabel(TOOL_VERSION)
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(
            f"background:{C_HEADER};color:#aaa;"
            f"font-size:10px;padding:3px;border-radius:3px;"
        )
        root_layout.addWidget(title)

        # stacked widget: page 0 = main tool, page 1 = grouper
        self._stack = QtWidgets.QStackedWidget()
        root_layout.addWidget(self._stack)

        # ── page 0: main tool ──────────────────────────────────────────
        main_page = QtWidgets.QWidget()
        main_page_layout = QtWidgets.QVBoxLayout(main_page)
        main_page_layout.setContentsMargins(0, 0, 0, 0)
        main_page_layout.setSpacing(0)

        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        content = QtWidgets.QWidget()
        self.main_layout = QtWidgets.QVBoxLayout(content)
        self.main_layout.setContentsMargins(2, 2, 2, 2)
        self.main_layout.setSpacing(5)
        scroll.setWidget(content)
        main_page_layout.addWidget(scroll)
        self._stack.addWidget(main_page)   # index 0

        # ── page 1: grouper (built after main sections below) ──────────
        # created in _build_grouper_page(), called at end of _build_ui

        self._build_projection()
        self.main_layout.addWidget(hline())
        self._build_gridify()
        self.main_layout.addWidget(hline())
        self._build_move_shells()
        self.main_layout.addWidget(hline())
        self._build_unfold()
        self.main_layout.addWidget(hline())
        self._build_straighten()
        self.main_layout.addWidget(hline())
        self._build_orient()
        self.main_layout.addWidget(hline())
        self._build_find_shells()
        self.main_layout.addWidget(hline())
        self._build_layout_local()
        self.main_layout.addWidget(hline())
        self._build_layout_global()
        self.main_layout.addWidget(hline())
        self._build_texel_density()
        self.main_layout.addWidget(hline())
        self._build_group_shells_btn()

        # ── page 1: grouper ────────────────────────────────────────────
        self._grouper_page = UVGrouperPage(parent=self)
        self._stack.addWidget(self._grouper_page)   # index 1
        # make grouper instance point to the embedded page
        UVGrouperPage.instance = self._grouper_page
        self.main_layout.addStretch()

        # ── font scale bar (below stack, always visible) ───────────────
        root_layout.addWidget(hline())
        scale_row = QtWidgets.QHBoxLayout()
        scale_row.setSpacing(4)

        lbl = QtWidgets.QLabel("UI Scale:")
        lbl.setStyleSheet("color:#888;font-size:10px;")
        lbl.setFixedWidth(52)
        scale_row.addWidget(lbl)

        self._font_slider = QtWidgets.QSlider(Qt.Horizontal)
        self._font_slider.setRange(8, 20)
        self._font_slider.setValue(self._font_size)
        self._font_slider.setFixedHeight(16)
        self._font_slider.setStyleSheet(
            "QSlider::groove:horizontal{"
            "  height:4px;background:#333;border-radius:2px;}"
            "QSlider::handle:horizontal{"
            "  width:12px;height:12px;margin:-4px 0;"
            "  background:#2176ae;border-radius:6px;}"
            "QSlider::handle:horizontal:hover{background:#3aa0e8;}"
            "QSlider::sub-page:horizontal{background:#1a3a52;border-radius:2px;}"
        )
        self._font_slider.valueChanged.connect(self._on_font_scale)
        scale_row.addWidget(self._font_slider, 1)

        root_layout.addLayout(scale_row)

    # ==================================================================
    #  SECTION BUILDERS
    # ==================================================================

    # -------------------------------------------------------- PROJECTION
    def _build_projection(self):
        self.main_layout.addWidget(section_label("PROJECTION / MAPPING"))

        # keep w/h  &  proj w/h – single row, spinbox fills remaining width
        self.chk_keep_wh  = make_check("Keep W/H Ratio", True)
        self.chk_proj_wh  = make_check("Proj W/H", False)
        self.proj_wh_val  = spin_box(400, 1, 99999, decimals=2)
        self.proj_wh_val.setToolTip("World-space projection size (e.g. 400 units)")

        self.main_layout.addWidget(row(self.chk_keep_wh, self.chk_proj_wh, self.proj_wh_val))

        # cut & sew tool
        bcs = make_btn("Cut and Sew", C_TEAL, self.cut_and_sew, height=26,
                       tooltip="Activate Cut/Sew UV Tool")
        bcs.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        self.main_layout.addWidget(bcs)

        # planar X Y Z
        bx = make_btn("Map X", C_RED,   self.planar_x, tooltip="Planar map along X")
        by = make_btn("Map Y", C_GREEN,  self.planar_y, tooltip="Planar map along Y")
        bz = make_btn("Map Z", C_BLUE,   self.planar_z, tooltip="Planar map along Z")
        self.main_layout.addWidget(row(bx, by, bz))

        # cam / auto / best
        bc = make_btn("Cam",       C_GREY,   self.planar_cam,   tooltip="Camera planar map")
        ba = make_btn("Automatic", C_ORANGE, self.planar_auto,  tooltip="Automatic map")
        bb = make_btn("Best",      C_GREY,   self.planar_best,  tooltip="Best-plane map")
        self.main_layout.addWidget(row(bc, ba, bb))

    # -------------------------------------------------------- GRIDIFY
    def _build_gridify(self):
        self.main_layout.addWidget(section_label("GRIDIFY / RECTANGULARIZE  [For Pipes]"))
        bg = make_btn("Grid UVs",  C_PURPLE,  self.grid_uvs,  tooltip="Gridify selected faces into uniform squares")
        br = make_btn("Rec UVs",   C_PURPLE,  self.rec_uvs,   tooltip="Rectangularize UVs with correct aspect ratio")
        self.main_layout.addWidget(row(bg, br))

    # -------------------------------------------------------- MOVE SHELLS
    def _build_move_shells(self):
        self.main_layout.addWidget(section_label("MOVE SHELLS"))

        self.chk_align = make_check("Align Mode", False)
        self.main_layout.addWidget(row(self.chk_align, "stretch"))

        # spin row
        bsl = make_btn("◄ Spin",  C_GREY, self.spin_left,  height=20)
        bsr = make_btn("Spin ►",  C_GREY, self.spin_right, height=20)
        self.main_layout.addWidget(row(bsl, bsr))

        # up
        bu = make_btn("▲  Up",    C_PURPLE2, self.move_up,    height=20)
        self.main_layout.addWidget(bu)

        # left / down / right
        bleft  = make_btn("◄ Left",  C_PURPLE2, self.move_left,  height=20)
        bdown  = make_btn("▼ Down",  C_PURPLE2, self.move_down,  height=20)
        bright = make_btn("Right ►", C_PURPLE2, self.move_right, height=20)
        self.main_layout.addWidget(row(bleft, bdown, bright))

        # stack / flip
        bst  = make_btn("Stack",  C_BLUE, self.stack_shells, height=20)
        bfu  = make_btn("Flip U", C_BLUE, self.flip_u,       height=20)
        bfv  = make_btn("Flip V", C_BLUE, self.flip_v,       height=20)
        self.main_layout.addWidget(row(bst, bfu, bfv))

    # -------------------------------------------------------- UNFOLD
    def _build_unfold(self):
        self.main_layout.addWidget(section_label("UNFOLD"))

        self.chk_orient_unfold = make_check("Orient to Longest Edge", False)
        self.main_layout.addWidget(row(self.chk_orient_unfold, "stretch"))

        buv = make_btn("Unfold UV", C_GREEN2, self.unfold_uv, tooltip="Full unfold U+V")
        bu  = make_btn("Unfold U",  C_GREEN2, self.unfold_u,  tooltip="Unfold along U only")
        bv  = make_btn("Unfold V",  C_GREEN2, self.unfold_v,  tooltip="Unfold along V only")
        self.main_layout.addWidget(row(buv, bu, bv))

        bopt = make_btn("Optimize", C_GREEN2, self.optimize, height=20,
                        tooltip="Optimize UVs – 10 iterations, default settings")
        self.main_layout.addWidget(bopt)

    # -------------------------------------------------------- STRAIGHTEN
    def _build_straighten(self):
        self.main_layout.addWidget(section_label("STRAIGHTEN UVs"))

        buv    = make_btn("UV",    C_GREY, self.straighten_uv,    height=22)
        bshell = make_btn("Shell", C_GREY, self.straighten_shell, height=22)
        bsu    = make_btn("U",     C_GREY, self.straighten_u,     height=22)
        bsv    = make_btn("V",     C_GREY, self.straighten_v,     height=22)
        self.main_layout.addWidget(row(buv, bshell, bsu, bsv))

    # -------------------------------------------------------- ORIENT
    def _build_orient(self):
        self.main_layout.addWidget(section_label("ORIENT SHELLS"))

        # world axes
        bx = make_btn("X",    C_RED,   self.orient_x, height=22)
        by = make_btn("Y",    C_GREEN, self.orient_y, height=22)
        bz = make_btn("Z",    C_BLUE,  self.orient_z, height=22)
        be = make_btn("Edge/UVs", C_GREY, self.orient_edge, height=22)
        self.main_layout.addWidget(row(bx, by, bz, be))

        bh = make_btn("Horizontal", C_GREY, self.orient_h, height=20)
        bv = make_btn("Vertical",   C_GREY, self.orient_v, height=20)
        self.main_layout.addWidget(row(bh, bv))

    # -------------------------------------------------------- FIND SHELLS
    def _build_find_shells(self):
        self.main_layout.addWidget(section_label("FIND SHELLS < %"))

        self.find_shells_val = QtWidgets.QDoubleSpinBox()
        self.find_shells_val.setDecimals(3)
        self.find_shells_val.setMinimum(0.001)
        self.find_shells_val.setMaximum(1000.0)
        self.find_shells_val.setValue(5.0)
        self.find_shells_val.setToolTip("Bounding-box area % threshold (0-1 UV space)")
        self.find_shells_val.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        self.find_shells_val.setFixedHeight(22)
        self.find_shells_val.setStyleSheet(_SPINBOX_SS)
        self.find_shells_val.setStyle(_get_spin_style())
        bf = make_btn("Find", C_GREY, self.find_shells, height=22)
        bf.setFixedWidth(52)
        self.main_layout.addWidget(row(self.find_shells_val, bf))

    # -------------------------------------------------------- LAYOUT LOCAL
    def _build_layout_local(self):
        self.main_layout.addWidget(section_label("LAYOUT UVs  (Local)"))

        # padding + map size
        self.local_padding  = spin_box(8.0,  1,  512,  decimals=2)
        self.local_map_size = combo_box(["4096","2048","1024","512","256","128","64","32"], width=72)
        self.local_map_size.setCurrentIndex(1)  # default 2048

        self.main_layout.addWidget(row(
            QtWidgets.QLabel("Padding:"), self.local_padding,
            QtWidgets.QLabel("Map:"),     self.local_map_size,
        ))

        bp = make_btn("Pack to Pivot",  C_GREENYEL, self.pack_to_pivot,  height=22,
                      tooltip="Layout selected shells to current UV pivot")
        self.main_layout.addWidget(bp)

        blu = make_btn("Layout Up",    C_GREENYEL, self.layout_up,    height=20)
        blr = make_btn("Layout Right", C_GREENYEL, self.layout_right, height=20)
        self.main_layout.addWidget(row(blu, blr))

    # -------------------------------------------------------- LAYOUT GLOBAL
    def _build_layout_global(self):
        self.main_layout.addWidget(section_label("LAYOUT UVs  (Global)"))

        # checkboxes row 1
        self.chk_flip  = make_check("Flip",  True)
        self.chk_spin  = make_check("Spin",  True)
        self.chk_scale = make_check("Scale", True)
        self.main_layout.addWidget(row(self.chk_flip, self.chk_spin, self.chk_scale))

        # checkboxes row 2
        self.chk_move     = make_check("Move",       True)
        self.chk_lay_all  = make_check("Layout All", False)
        self.chk_keep_td  = make_check("Keep TD",    False)
        self.main_layout.addWidget(row(self.chk_move, self.chk_lay_all, self.chk_keep_td))

        # checkboxes row 3
        self.chk_stack = make_check("Stack Similar", False)
        self.main_layout.addWidget(row(self.chk_stack, "stretch"))

        # map size + padding (global)
        self.global_map_size = combo_box(["4096","2048","1024","512","256","128","64","32"], width=72)
        self.global_map_size.setCurrentIndex(1)
        self.global_padding  = spin_box(8.0, 1, 512, decimals=2)
        self.main_layout.addWidget(row(
            QtWidgets.QLabel("Map:"),     self.global_map_size,
            QtWidgets.QLabel("Padding:"), self.global_padding,
        ))

        bl = make_btn("Layout UVs", C_YELLOW, self.layout_uvs, height=26,
                      tooltip="Layout all/selected UV shells with current settings")
        self.main_layout.addWidget(bl)

    # -------------------------------------------------------- TEXEL DENSITY
    def _build_texel_density(self):
        self.main_layout.addWidget(section_label("TEXEL DENSITY"))

        self.td_map_size = spin_box(2048, 1, 32768)
        self.td_map_size.setToolTip("Texture resolution for TD calculation")

        self.td_pix_per_unit = spin_box(5.12, 0.0001, 99999.0, decimals=4)
        self.td_pix_per_unit.setToolTip("Pixels per Maya unit (texel density)")

        self.main_layout.addWidget(row(
            QtWidgets.QLabel("Map:"), self.td_map_size,
            QtWidgets.QLabel("Pix:"), self.td_pix_per_unit,
        ))

        bcp = make_btn("Copy TD",  C_RED, self.copy_td,  height=22, tooltip="Read TD from selected face")
        bpt = make_btn("Paste TD", C_RED, self.paste_td, height=22, tooltip="Apply stored TD to selection")
        self.main_layout.addWidget(row(bcp, bpt))

    # -------------------------------------------------------- GROUP SHELLS BTN
    def _build_group_shells_btn(self):
        self.main_layout.addWidget(section_label("UV GROUPER"))
        bg = make_btn("Open UV Grouper", C_PURPLE, self.open_uv_grouper, height=26)
        self.main_layout.addWidget(bg)

    def open_uv_grouper(self, _=None):
        """Switch to grouper page."""
        self._stack.setCurrentIndex(1)
        # ensure instance always points to our embedded page
        UVGrouperPage.instance = self._grouper_page


    # ==================================================================
    #  FONT SCALE
    # ==================================================================
    def _on_font_scale(self, val: int):
        """Slider moved – apply and save."""
        self._apply_font_size(val)

    def _apply_font_size(self, pt: int):
        """Rescale the whole panel: font size drives button/row height."""
        import re as _re
        self._font_size = pt
        btn_h = max(18, pt * 2)   # pt=11→22, pt=14→28, pt=20→40
        # persist across restarts
        cmds.optionVar(iv=("phoenixUVToolbox_fontSize", pt))

        # root stylesheet – text font size
        self.setStyleSheet(
            f"QWidget{{background:{C_DARK};color:#cccccc;font-size:{pt}px;}}"
            f"QScrollArea{{border:none;}}"
            f"QScrollBar:vertical{{background:#222;width:6px;border-radius:3px;}}"
            f"QScrollBar::handle:vertical{{background:#555;border-radius:3px;}}"
        )

        # patch every QPushButton stylesheet:
        # replace min-height, max-height and font-size values
        for btn in self.findChildren(QtWidgets.QPushButton):
            ss = btn.styleSheet()
            if not ss:
                continue
            ss = _re.sub(r'min-height:\s*\d+px', f'min-height:{btn_h}px', ss)
            ss = _re.sub(r'max-height:\s*\d+px', f'max-height:{btn_h}px', ss)
            ss = _re.sub(r'font-size:\s*\d+px',  f'font-size:{pt}px',     ss)
            btn.setStyleSheet(ss)
            btn.setFixedHeight(btn_h)

        # patch spinboxes
        for sb in (self.findChildren(QtWidgets.QSpinBox) + self.findChildren(QtWidgets.QDoubleSpinBox)):
            sb.setFixedHeight(btn_h)

    # ==================================================================
    #  HELPER: compute shell-spacing and tile-margin from padding + map
    # ==================================================================
    def _spacing(self, padding_val, map_combo):
        res = int(map_combo.currentText())
        spc = padding_val / res
        return spc, spc / 2.0

    def _proj_wh(self):
        return self.proj_wh_val.value() if self.chk_proj_wh.isChecked() else None

    def _keep_wh(self):
        return self.chk_keep_wh.isChecked()


    # ==================================================================
    #  CALLBACKS – PROJECTION
    # ==================================================================
    @run
    def _do_planar(self, axis):
        pw = self._proj_wh()
        kir = self._keep_wh()
        mel_run("ConvertSelectionToFaces;")
        if pw is not None:
            nodes = cmds.polyProjection(ch=1, type="Planar", ibd=True, kir=True, md=axis) or []
            for n in nodes:
                cmds.setAttr(f"{n}.projectionHeight", pw)
                cmds.setAttr(f"{n}.projectionWidth",  pw)
        elif kir:
            cmds.polyProjection(ch=1, type="Planar", ibd=True, kir=True, md=axis)
        else:
            cmds.polyProjection(ch=1, type="Planar", ibd=True, md=axis)
        mel_run("SelectFacetMask;")

    @run
    def cut_and_sew(self):
        mel_run("SetCutSewUVTool;")

    def planar_x(self):    self._do_planar("x")
    def planar_y(self):    self._do_planar("y")
    def planar_z(self):    self._do_planar("z")
    def planar_cam(self):  self._do_planar("c")
    def planar_best(self): self._do_planar("b")

    @run
    def planar_auto(self):
        pw = self._proj_wh()
        mel_run("ConvertSelectionToFaces;")
        mel_run("UVAutomaticProjection;")
        mel_run("toggleSelMode; toggleSelMode; selectMode -object;")
        objs = cmds.ls(sl=True) or []
        for obj in objs:
            hist = cmds.listHistory(obj) or []
            if len(hist) > 1:
                n = hist[1]
                cmds.setAttr(f"{n}.planes",         3)
                cmds.setAttr(f"{n}.optimize",        1)
                cmds.setAttr(f"{n}.layoutMethod",    0)
                cmds.setAttr(f"{n}.layout",          3)
                cmds.setAttr(f"{n}.percentageSpace", 0)
                cmds.setAttr(f"{n}.scaleMode",       0)
                if pw is not None:
                    cmds.setAttr(f"{n}.scaleX", pw)
                    cmds.setAttr(f"{n}.scaleY", pw)
                    cmds.setAttr(f"{n}.scaleZ", pw)
                cmds.setAttr(f"{n}.rotateY", 90)
        mel_run("SelectFacetMask;")

    # ==================================================================
    #  CALLBACKS – GRIDIFY
    # ==================================================================
    @run
    def grid_uvs(self):
        mel_run("m341_gridUVs;")

    @run
    def rec_uvs(self):
        mel_run("m341_rectangularizeUVs;")

    # ==================================================================
    #  CALLBACKS – MOVE SHELLS
    # ==================================================================
    def _align_mode(self):
        return self.chk_align.isChecked()

    @run
    def spin_left(self):
        mel_run("m341_uvMapper_spinLeft;")

    @run
    def spin_right(self):
        mel_run("m341_uvMapper_spinRight;")

    @run
    def move_left(self):
        if self._align_mode():
            mel_run("alignUV minU;")
        else:
            mel_run("ConvertSelectionToUVShell; polyEditUV -u -1 -v 0;")

    @run
    def move_right(self):
        if self._align_mode():
            mel_run("alignUV maxU;")
        else:
            mel_run("ConvertSelectionToUVShell; polyEditUV -u 1 -v 0;")

    @run
    def move_up(self):
        if self._align_mode():
            mel_run("alignUV maxV;")
        else:
            mel_run("ConvertSelectionToUVShell; polyEditUV -u 0 -v 1;")

    @run
    def move_down(self):
        if self._align_mode():
            mel_run("alignUV minV;")
        else:
            mel_run("ConvertSelectionToUVShell; polyEditUV -u 0 -v -1;")

    @run
    def stack_shells(self):
        mel_run("texStackShells({});")

    @run
    def flip_u(self):
        mel_run("m341_uvMapper_flipU;")

    @run
    def flip_v(self):
        mel_run("m341_uvMapper_flipV;")

    # ==================================================================
    #  CALLBACKS – UNFOLD
    # ==================================================================
    @run
    def unfold_uv(self):
        if self.chk_orient_unfold.isChecked():
            mel_run("m341_uvMapper_unfoldUVs;")   # calls orient variant if checkbox on in MEL
        else:
            mel_run("u3dUnfold -ite 1 -p 0 -bi 1 -tf 1 -ms 2048 -rs 8;")
            mel_run("toggleSelMode; toggleSelMode; selectMode -object;")
            mel_run("DeleteHistory; ConvertSelectionToUVs; SelectUVMask;")

    @run
    def unfold_u(self):
        mel_run("ConvertSelectionToUVs;")
        mel_run("unfold -i 5000 -ss 0.001 -gb 0 -gmb 0.5 -pub 0 -ps 0 -oa 2 -us off;")
        mel_run("toggleSelMode; toggleSelMode; selectMode -object;")
        mel_run("DeleteHistory; ConvertSelectionToUVs; SelectUVMask;")

    @run
    def unfold_v(self):
        mel_run("ConvertSelectionToUVs;")
        mel_run("unfold -i 5000 -ss 0.001 -gb 0 -gmb 0.5 -pub 0 -ps 0 -oa 1 -us off;")
        mel_run("toggleSelMode; toggleSelMode; selectMode -object;")
        mel_run("DeleteHistory; ConvertSelectionToUVs; SelectUVMask;")

    @run
    def optimize(self):
        mel_run("u3dOptimize -ite 10 -pow 1 -sa 0.0 -bi 1 -tf 1 -ms 2048 -rs 0;")
        print("[PhoenixUV] Optimize UVs complete.")

    # ==================================================================
    #  CALLBACKS – STRAIGHTEN
    # ==================================================================
    @run
    def straighten_uv(self):
        mel_run("texStraightenUVs \"UV\" 30;")
        mel_run("toggleSelMode; toggleSelMode; selectMode -object;")
        mel_run("DeleteHistory; ConvertSelectionToUVs; SelectUVMask;")

    @run
    def straighten_shell(self):
        mel_run("texStraightenShell;")
        mel_run("toggleSelMode; toggleSelMode; selectMode -object;")
        mel_run("DeleteHistory; SelectEdgeMask;")

    @run
    def straighten_u(self):
        mel_run("texStraightenUVs \"U\" 30;")
        mel_run("toggleSelMode; toggleSelMode; selectMode -object;")
        mel_run("DeleteHistory; ConvertSelectionToUVs; SelectUVMask;")

    @run
    def straighten_v(self):
        mel_run("texStraightenUVs \"V\" 30;")
        mel_run("toggleSelMode; toggleSelMode; selectMode -object;")
        mel_run("DeleteHistory; ConvertSelectionToUVs; SelectUVMask;")

    # ==================================================================
    #  CALLBACKS – ORIENT
    # ==================================================================
    _orient_toggle = {"x": False, "y": False, "z": False, "h": False, "v": False}

    def _orient_axis(self, key, rot_flag):
        mel_run("ConvertSelectionToUVShell;")
        mel_run("performResetPivot;")
        shapes = cmds.ls(sl=True, objectsOnly=True) or []
        if not shapes:
            return
        piv1 = cmds.getAttr(f"{shapes[0]}.uvPivot")[0]
        mel_run(f"u3dLayout -res 64 -rot {rot_flag} -trs 1 -spc 0.0078125 -mar 0.00390625 -box 0 1 0 1 -ls 1;")
        mel_run("performResetPivot;")
        piv2 = cmds.getAttr(f"{shapes[0]}.uvPivot")[0]
        du = piv1[0] - piv2[0]
        dv = piv1[1] - piv2[1]
        mel_run(f"polyEditUV -u {du} -v {dv};")
        mel_run("performResetPivot;")
        if self._orient_toggle[key]:
            mel_run("m341_uvMapper_flipU; m341_uvMapper_flipV;")
        self._orient_toggle[key] = not self._orient_toggle[key]

    @run
    def orient_x(self):    self._orient_axis("x", 3)
    @run
    def orient_y(self):    self._orient_axis("y", 4)
    @run
    def orient_z(self):    self._orient_axis("z", 5)
    @run
    def orient_h(self):    self._orient_axis("h", 1)
    @run
    def orient_v(self):    self._orient_axis("v", 2)

    @run
    def orient_edge(self):
        mel_run("texOrientEdge;")
        mel_run("toggleSelMode; toggleSelMode; selectMode -object;")
        mel_run("DeleteHistory; SelectEdgeMask;")

    # ==================================================================
    #  CALLBACKS – FIND SHELLS
    # ==================================================================
    @run
    def find_shells(self):
        threshold = self.find_shells_val.value()
        mel_run("toggleSelMode; toggleSelMode; selectMode -object;")
        mel_run("ConvertSelectionToUVs;")
        shapes = cmds.ls(sl=True, objectsOnly=True) or []
        if not shapes:
            cmds.warning("[PhoenixUV] Nothing selected.")
            return
        result_uvs = []
        for shape in shapes:
            active_shells = cmds.polyEvaluate(shape, aus=True) or []
            for s in active_shells:
                uvs_in = cmds.polyEvaluate(shape, uis=s) or []
                if not uvs_in:
                    continue
                bb = cmds.polyEvaluate(uvs_in, boundingBoxComponent2d=True)
                if bb:
                    w = bb[1] - bb[0]
                    h = bb[3] - bb[2]
                    area_pct = w * h * 100.0
                    if area_pct < threshold:
                        result_uvs.extend(uvs_in)
        if result_uvs:
            cmds.select(result_uvs)
            mel_run("SelectUVMask;")
            print(f"[PhoenixUV] Found {len(result_uvs)} UVs in shells < {threshold}%")
        else:
            cmds.select(cl=True)
            print(f"[PhoenixUV] No shells found smaller than {threshold}%")

    # ==================================================================
    #  CALLBACKS – LAYOUT LOCAL
    # ==================================================================
    @run
    def pack_to_pivot(self):
        spc, mar = self._spacing(self.local_padding.value(), self.local_map_size)
        mel_run("MoveTool; DeleteHistory;")
        shapes = cmds.ls(sl=True, objectsOnly=True) or []
        if not shapes:
            return
        mel_run("ConvertSelectionToFaces;")
        sel = cmds.ls(sl=True, fl=True)
        piv1 = cmds.getAttr(f"{shapes[0]}.uvPivot")[0]
        if self.chk_spin.isChecked():
            mel_run("texOrientShells;")
        mel_run(f"u3dLayout -mutations 1 -resolution 512 -translate 1 "
                f"-shellSpacing {spc} -tileMargin {mar} -layoutScaleMode 1 -box 0 1 0 1;")
        mel_run("performResetPivot;")
        piv2 = cmds.getAttr(f"{shapes[0]}.uvPivot")[0]
        du = piv1[0] - piv2[0]
        dv = piv1[1] - piv2[1]
        mel_run(f"polyEditUV -u {du} -v {dv};")
        mel_run("performResetPivot;")
        mel_run("toggleSelMode; toggleSelMode; selectMode -object; DeleteHistory;")
        mel_run("SelectMeshUVShell;")
        if sel:
            cmds.select(sel, add=True)
        mel_run("DeleteHistory;")
        print("[PhoenixUV] Pack to pivot complete.")

    _rect_pack_u = 2
    _rect_pack_v = 2

    @run
    def layout_up(self):
        spc, mar = self._spacing(self.local_padding.value(), self.local_map_size)
        mel_run("MoveTool; DeleteHistory;")
        shapes = cmds.ls(sl=True, objectsOnly=True) or []
        mel_run("ConvertSelectionToFaces;")
        sel = cmds.ls(sl=True, fl=True)
        bb = cmds.polyEvaluate(boundingBoxComponent2d=True)
        if shapes and bb:
            cmds.setAttr(f"{shapes[0]}.uvPivot", bb[0], bb[2], type="double2")
        piv1 = cmds.getAttr(f"{shapes[0]}.uvPivot")[0] if shapes else (0, 0)
        mel_run("m341_uvMapper_spinRight;")
        if self.chk_spin.isChecked():
            mel_run("texOrientShells;")
        mel_run(f"u3dLayout -mutations 1 -resolution 512 -translate 1 "
                f"-shellSpacing {spc} -tileMargin {mar} -layoutScaleMode 1 "
                f"-box 0 {self._rect_pack_v} 0 1;")
        self._rect_pack_v += 1
        mel_run("performResetPivot;")
        mel_run("m341_uvMapper_spinLeft;")
        if shapes:
            bb2 = cmds.polyEvaluate(boundingBoxComponent2d=True)
            if bb2:
                cmds.setAttr(f"{shapes[0]}.uvPivot", bb2[0], bb2[2], type="double2")
            piv3 = cmds.getAttr(f"{shapes[0]}.uvPivot")[0]
            du = piv1[0] - piv3[0]
            dv = piv1[1] - piv3[1]
            mel_run(f"polyEditUV -u {du} -v {dv};")
            mel_run("performResetPivot;")
        mel_run("toggleSelMode; toggleSelMode; selectMode -object; DeleteHistory;")
        mel_run("SelectMeshUVShell;")
        if sel:
            cmds.select(sel, add=True)
        mel_run("DeleteHistory;")
        print("[PhoenixUV] Layout Up complete.")

    @run
    def layout_right(self):
        spc, mar = self._spacing(self.local_padding.value(), self.local_map_size)
        mel_run("MoveTool; DeleteHistory;")
        shapes = cmds.ls(sl=True, objectsOnly=True) or []
        mel_run("ConvertSelectionToFaces;")
        sel = cmds.ls(sl=True, fl=True)
        bb = cmds.polyEvaluate(boundingBoxComponent2d=True)
        if shapes and bb:
            cmds.setAttr(f"{shapes[0]}.uvPivot", bb[0], bb[2], type="double2")
        piv1 = cmds.getAttr(f"{shapes[0]}.uvPivot")[0] if shapes else (0, 0)
        if self.chk_spin.isChecked():
            mel_run("texOrientShells;")
        mel_run(f"u3dLayout -mutations 1 -resolution 512 -translate 1 "
                f"-shellSpacing {spc} -tileMargin {mar} -layoutScaleMode 1 "
                f"-box 0 {self._rect_pack_u} 0 1;")
        self._rect_pack_u += 1
        if shapes:
            bb2 = cmds.polyEvaluate(boundingBoxComponent2d=True)
            if bb2:
                cmds.setAttr(f"{shapes[0]}.uvPivot", bb2[0], bb2[2], type="double2")
            mel_run("performResetPivot;")
            piv2 = cmds.getAttr(f"{shapes[0]}.uvPivot")[0]
            du = piv1[0] - piv2[0]
            dv = piv1[1] - piv2[1]
            mel_run(f"polyEditUV -u {du} -v {dv};")
            mel_run("performResetPivot;")
        mel_run("toggleSelMode; toggleSelMode; selectMode -object; DeleteHistory;")
        mel_run("SelectMeshUVShell;")
        if sel:
            cmds.select(sel, add=True)
        mel_run("DeleteHistory;")
        print("[PhoenixUV] Layout Right complete.")

    # ==================================================================
    #  CALLBACKS – LAYOUT GLOBAL  (direct port of m341_uvMapper_LayoutUVs)
    # ==================================================================
    @run
    def layout_uvs(self):
        """Direct port of m341_uvMapper_LayoutUVs MEL proc."""
        import math

        spc, mar   = self._spacing(self.global_padding.value(), self.global_map_size)
        scale_mode = 3 if self.chk_scale.isChecked()   else 0
        translate  = 1 if self.chk_move.isChecked()    else 0
        keep_td    = 1 if self.chk_keep_td.isChecked() else 2
        do_flip    = self.chk_flip.isChecked()
        do_spin    = self.chk_spin.isChecked()
        do_all     = self.chk_lay_all.isChecked()
        do_stack   = self.chk_stack.isChecked()

        # --- snapshot component mode (MEL queries all 6 selectType flags) ---
        comp_face  = cmds.selectType(q=True, facet=True)
        comp_shell = cmds.selectType(q=True, meshUVShell=True)
        comp_vert  = cmds.selectType(q=True, vertex=True)
        comp_edge  = cmds.selectType(q=True, edge=True)
        comp_uv    = cmds.selectType(q=True, polymeshUV=True)
        comp_multi = cmds.selectType(q=True, meshComponents=True)

        orig_sel = cmds.ls(sl=True, fl=True) or []

        # --- go to object mode, get objects (MEL: toggleSelMode x2; selectMode -object) ---
        mel.eval("toggleSelMode;")
        mel.eval("toggleSelMode;")
        mel.eval("selectMode -object;")
        orig_objs = cmds.ls(sl=True) or []
        if not orig_objs:
            cmds.warning("[PhoenixUV] Nothing selected.")
            return

        # --- polyCleanup (MEL does two passes) ---
        mel.eval('polyCleanupArgList 4 { "0","1","1","0","0","0","1","0","0","1e-05","0","1e-05","0","1e-05","0","-1","1","1" };')
        mel.eval('polyCleanupArgList 4 { "0","1","0","0","0","0","0","0","0","1e-05","0","1e-05","0","1e-05","0","1","0","0" };')
        cmds.select(orig_objs)

        # --- build UV selection ---
        # MEL: if layout all OFF -> restore original sel; ConvertSelectionToUVs
        #      if layout all ON  -> just ConvertSelectionToUVs on objects
        if not do_all and orig_sel:
            cmds.select(orig_sel)
        mel.eval("ConvertSelectionToUVs;")
        # MEL: $originalSelection = ls -sl -fl  (stored for restore at end)
        original_uv_sel = cmds.ls(sl=True, fl=True) or []

        # --- pre-passes (flip/spin) ---
        if do_flip:
            mel.eval("polyMultiLayoutUV -lm 0 -sc 0 -rbf 0 -fr 1 -ps 0.2 "
                     "-l 0 -gu 1 -gv 1 -psc 0 -su 1 -sv 1 -ou 0 -ov 0;")
        if do_spin:
            mel.eval("texOrientShells;")

        # --- grouper: deselect vis groups, keep masters + ungrouped ---
        # MEL:
        #   for each group: select -deselect $m341_uvMapperVis{g}
        #   $ungroupedUVs = ls -sl -fl
        #   for each group: select -add $m341_uvMapperMaster{g}
        #   select -add $ungroupedUVs
        grouper = UVGrouperPage.instance
        any_assigned = grouper and any(
            grouper._vis.get(g) for g in range(1, UVGrouperPage.MAX_GROUPS + 1)
        )
        has_groups = (not do_stack) and any_assigned
        print(f"[PhoenixUV] layout: grouper={grouper is not None} any_assigned={any_assigned} has_groups={has_groups} do_stack={do_stack}")

        if has_groups:
            for g in range(1, UVGrouperPage.MAX_GROUPS + 1):
                vis = grouper._vis.get(g, [])
                if vis:
                    try:
                        mel.eval("select -deselect " + " ".join(f'"{u}"' for u in vis) + ";")
                    except Exception:
                        pass

            ungrouped_uvs = cmds.ls(sl=True, fl=True) or []

            for g in range(1, UVGrouperPage.MAX_GROUPS + 1):
                master = grouper._master.get(g, [])
                if master:
                    try:
                        mel.eval("select -add " + " ".join(f'"{u}"' for u in master) + ";")
                    except Exception:
                        pass

            if ungrouped_uvs:
                mel.eval("select -add " + " ".join(f'"{u}"' for u in ungrouped_uvs) + ";")

        # --- run u3dLayout ---
        mel.eval(f"u3dLayout -mutations 1 -resolution 512 "
                 f"-preScaleMode {scale_mode} -translate {translate} "
                 f"-shellSpacing {spc} -tileMargin {mar} "
                 f"-layoutScaleMode {keep_td} -packBox 0 1 0 1;")

        # --- DeleteHistory (MEL: select objects; m341_uvMapper_deleteHistory()) ---
        cmds.select(orig_objs)
        mel.eval("DeleteHistory;")
        mel.eval("ConvertSelectionToUVs;")

        # ---------------------------------------------------------------
        # STACKING LOOP – exact port of MEL custom stacking section
        # MEL iterates all groups; for each with a master:
        #   1. select $master; MoveTool -> get bbox area + uvPivot
        #   2. select $vis; deselect $master -> ConvertSelectionToUVs; texStackShells({})
        #   3. get new uvPivot; polyEditUV delta to snap onto master pivot
        #   4. performResetPivot
        #   5. texGetShells() loop: for each shell sqrt(masterArea/shellArea) scale at master pivot
        # ---------------------------------------------------------------
        if has_groups:
            for g in range(1, UVGrouperPage.MAX_GROUPS + 1):
                master_uvs = grouper._master.get(g, [])
                vis_uvs    = grouper._vis.get(g, [])

                if not master_uvs or not vis_uvs:
                    continue

                # derive shape name from UV string e.g. "pSphereShape1.map[0]"
                master_shape = master_uvs[0].split(".")[0]

                # Exact MEL port:
                # select $master; MoveTool;
                # polyEvaluate -ae -boundingBoxComponent2d  -> master bbox area
                # getAttr shape.uvPivot                      -> master pivot
                m_str = " ".join(f'"{u}"' for u in master_uvs)
                mel.eval(f"select {m_str};")
                mel.eval("MoveTool;")
                m_bb = mel.eval("polyEvaluate -ae -boundingBoxComponent2d;")
                if not m_bb:
                    continue
                # mel returns flat [uMin, uMax, vMin, vMax]
                master_area = (m_bb[1] - m_bb[0]) * (m_bb[3] - m_bb[2])
                raw = cmds.getAttr(f"{master_shape}.uvPivot")
                mpu = float(raw[0][0]) if hasattr(raw[0], '__len__') else float(raw[0])
                mpv = float(raw[0][1]) if hasattr(raw[0], '__len__') else float(raw[1])

                # select $vis; select -deselect $master;
                # ConvertSelectionToUVs; texStackShells({});
                v_str = " ".join(f'"{u}"' for u in vis_uvs)
                mel.eval(f"select {v_str};")
                mel.eval(f"select -deselect {m_str};")
                slaves = cmds.ls(sl=True, fl=True) or []
                if not slaves:
                    continue
                mel.eval("ConvertSelectionToUVs;")
                mel.eval("texStackShells({});")

                # get new pivot; polyEditUV delta; performResetPivot
                slave_shape = (cmds.ls(sl=True, fl=True) or [master_uvs[0]])[0].split(".")[0]
                raw2 = cmds.getAttr(f"{slave_shape}.uvPivot")
                spu = float(raw2[0][0]) if hasattr(raw2[0], '__len__') else float(raw2[0])
                spv = float(raw2[0][1]) if hasattr(raw2[0], '__len__') else float(raw2[1])
                du = mpu - spu
                dv = mpv - spv
                mel.eval(f"polyEditUV -u {du} -v {dv};")
                mel.eval("performResetPivot;")

                # texGetShells() loop:
                # for each shell: polyEvaluate -ae -boundingBoxComponent2d
                #   scaleFactor = sqrt(masterArea / shellArea)
                #   polyEditUV -pu masterPivU -pv masterPivV -su scale -sv scale
                shells = mel.eval("texGetShells();") or []
                for shell_str in shells:
                    try:
                        shell_uvs = shell_str.split()
                        if not shell_uvs:
                            continue
                        su_str = " ".join(f'"{u}"' for u in shell_uvs)
                        mel.eval(f"select {su_str};")
                        s_bb = mel.eval("polyEvaluate -ae -boundingBoxComponent2d;")
                        if not s_bb:
                            continue
                        shell_area = (s_bb[1] - s_bb[0]) * (s_bb[3] - s_bb[2])
                        if shell_area <= 0:
                            continue
                        scale_f = math.sqrt(master_area / shell_area)
                        if abs(scale_f - 1.0) < 1e-6:
                            continue
                        mel.eval(f"polyEditUV -pu {mpu} -pv {mpv} "
                                 f"-su {scale_f} -sv {scale_f};")
                    except Exception as e:
                        cmds.warning(f"[PhoenixUV] shell scale g{g}: {e}")

        # --- stack similar (Maya built-in, optional) ---
        if do_stack:
            cmds.select(orig_objs)
            mel.eval("ConvertSelectionToUVs;")
            shells_str = mel.eval("polyUVStackSimilarShells -to 0.1 -om;") or ""
            mel.eval(f"u3dLayout -mutations 1 -resolution 512 "
                     f"-preScaleMode {scale_mode} -translate {translate} "
                     f"-shellSpacing {spc} -tileMargin {mar} "
                     f"-layoutScaleMode {keep_td} -box 0 1 0 1 {shells_str};")
            mel.eval("polyUVStackSimilarShells -to 0.1;")

        # --- restore original selection ---
        try:
            cmds.select(original_uv_sel) if original_uv_sel else cmds.select(orig_objs)
        except Exception:
            cmds.select(cl=True)

        # --- restore component mode ---
        if   comp_face:  mel.eval("SelectFacetMask;")
        elif comp_shell: mel.eval("SelectMeshUVShell;")
        elif comp_vert:  mel.eval("SelectVertexMask;")
        elif comp_edge:  mel.eval("SelectEdgeMask;")
        elif comp_uv:    mel.eval("SelectUVMask;")
        elif comp_multi: mel.eval("SelectUVMask;")

        print("[PhoenixUV] Layout UVs complete.")

    # ==================================================================
    #  CALLBACKS – TEXEL DENSITY
    # ==================================================================
    @run
    def copy_td(self):
        mel_run("uvTkDoGetTexelDensity;")
        try:
            val = cmds.floatField("uvTkTexelDensityField", q=True, v=True)
            self.td_pix_per_unit.setValue(val)
            print(f"[PhoenixUV] TD copied: {val:.4f} pix/unit")
        except Exception:
            cmds.warning("[PhoenixUV] Could not read TD – is UV Toolkit open?")

    @run
    def paste_td(self):
        ppu      = self.td_pix_per_unit.value()
        map_size = self.td_map_size.value()
        scale    = ppu / map_size
        mel_run("ConvertSelectionToUVs;")
        mel_run(f"unfold -i 0 -ss 0.001 -gb 0 -gmb 0.5 -pub 0 -ps 0 -oa 0 -useScale on -scale {scale};")
        print(f"[PhoenixUV] TD pasted: {ppu:.4f} pix/unit @ {map_size}px")

    # ==================================================================
    #  CALLBACKS – UV GROUPER
    # ==================================================================
    # open_uv_grouper is defined in _build_group_shells_btn above


# =============================================================================
# UV GROUPER  – SEPARATE FLOATING WINDOW
# =============================================================================
class UVGrouperPage(QtWidgets.QWidget):
    """UV Grouper embedded as a page inside PhoenixUVToolbox's QStackedWidget."""
    instance  = None
    MAX_GROUPS = 100
    MIN_VIS    = 50
    MAX_VIS    = 100
    DEF_VIS    = 73

    _COLORS = [
        C_PURPLE2, C_GREEN2,  C_BLUE,     C_GREENYEL, C_YELLOW,
        C_TEAL,    C_RED,     C_ORANGE,   C_PURPLE,   C_GREY,
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        UVGrouperPage.instance = self

        # internal storage – mirrors MEL globals: vis, master, group
        self._vis:    dict[int, list] = {i: [] for i in range(1, self.MAX_GROUPS + 1)}
        self._master: dict[int, list] = {i: [] for i in range(1, self.MAX_GROUPS + 1)}
        self._group:  dict[int, list] = {i: [] for i in range(1, self.MAX_GROUPS + 1)}

        self._visible_count = self.DEF_VIS   # how many group slots to show
        self._sel_btns = {}   # g -> sel QPushButton
        self._num_btns = {}   # g -> num QPushButton

        self._build_ui()

    def mousePressEvent(self, event):
        btn = event.button()
        if btn in (QtCore.Qt.ExtraButton1, QtCore.Qt.ExtraButton2):
            self._go_home()
        else:
            super().mousePressEvent(event)

    def _build_ui(self):
        main = QtWidgets.QVBoxLayout(self)
        main.setContentsMargins(4, 4, 4, 4)
        main.setSpacing(4)

        # ── Home button (full width) ───────────────────────────────────
        home_btn = QtWidgets.QPushButton("← Home")
        home_btn.setFixedHeight(22)
        home_btn.setStyleSheet(btn_style(C_GREY, height=22))
        home_btn.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed
        )
        home_btn.clicked.connect(self._go_home)
        main.addWidget(home_btn)

        # ── visible groups spinbox (full width) ───────────────────────
        self._vis_spin = QtWidgets.QSpinBox()
        self._vis_spin.setRange(self.MIN_VIS, self.MAX_VIS)
        self._vis_spin.setValue(self._visible_count)
        self._vis_spin.setFixedHeight(22)
        self._vis_spin.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed
        )
        self._vis_spin.setPrefix("Visible groups:  ")
        self._vis_spin.setStyleSheet(
            f"QSpinBox{{background:#2a2a2a;color:#ccc;border:1px solid #444;"
            f"border-radius:3px;padding-right:18px;font-size:11px;}}"
            f"QSpinBox::up-button{{width:16px;border-left:1px solid #444;}}"
            f"QSpinBox::down-button{{width:16px;border-left:1px solid #444;}}"
        )
        self._vis_spin.valueChanged.connect(self._on_vis_count_changed)
        main.addWidget(self._vis_spin)
        main.addWidget(hline())

        # ── scroll area containing grid + clear buttons ────────────────
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        # outer container: grid on top, clear buttons just below last row
        self._scroll_content = QtWidgets.QWidget()
        outer = QtWidgets.QVBoxLayout(self._scroll_content)
        outer.setContentsMargins(2, 2, 2, 2)
        outer.setSpacing(4)

        # grid widget
        self._grid_content = QtWidgets.QWidget()
        self._grid = QtWidgets.QGridLayout(self._grid_content)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(4)
        outer.addWidget(self._grid_content)

        # clear buttons sit right below the grid (no spacer between)
        self._clear_hline = hline()
        outer.addWidget(self._clear_hline)
        bc  = make_btn("Clear Selected Group", C_GREY, self._clear_selected, height=22)
        bca = make_btn("Clear All",            C_RED,  self._clear_all,      height=22)
        self._clear_row_w = row(bc, bca)
        outer.addWidget(self._clear_row_w)

        # push everything to top so clear buttons hug last visible row
        outer.addStretch(1)

        scroll.setWidget(self._scroll_content)
        main.addWidget(scroll)

        # build all 100 buttons
        COLS  = 6
        BTN_H = 22

        for c in range(COLS):
            self._grid.setColumnStretch(c, 1)

        for i in range(1, self.MAX_GROUPS + 1):
            col_idx  = (i - 1) % COLS
            row_pair = (i - 1) // COLS
            color    = self._COLORS[(i - 1) % len(self._COLORS)]

            sel_btn = QtWidgets.QPushButton("sel")
            sel_btn.setFixedHeight(BTN_H)
            sel_btn.setSizePolicy(
                QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed
            )
            sel_btn.setStyleSheet(btn_style(color, height=BTN_H))
            sel_btn.clicked.connect(partial(self._select_group, i))
            sel_btn.setContextMenuPolicy(Qt.CustomContextMenu)
            sel_btn.customContextMenuRequested.connect(
                partial(self._sel_context_menu, i)
            )
            self._grid.addWidget(sel_btn, row_pair * 2, col_idx)
            self._sel_btns[i] = sel_btn

            num_btn = QtWidgets.QPushButton(str(i))
            num_btn.setFixedHeight(BTN_H)
            num_btn.setSizePolicy(
                QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed
            )
            num_btn.setStyleSheet(btn_style(color, height=BTN_H))
            num_btn.clicked.connect(partial(self._assign_group, i))
            self._grid.addWidget(num_btn, row_pair * 2 + 1, col_idx)
            self._num_btns[i] = num_btn

        self._apply_visibility()

    def _on_vis_count_changed(self, val: int):
        self._visible_count = val
        self._apply_visibility()

    def _apply_visibility(self):
        for i in range(1, self.MAX_GROUPS + 1):
            vis = i <= self._visible_count
            if i in self._sel_btns:
                self._sel_btns[i].setVisible(vis)
            if i in self._num_btns:
                self._num_btns[i].setVisible(vis)

    def _go_home(self, _=None):
        """Switch back to main tool page."""
        # parent chain: UVGrouperPage → QStackedWidget → PhoenixUVToolbox
        p = self.parent()
        while p is not None:
            if isinstance(p, QtWidgets.QStackedWidget):
                p.setCurrentIndex(0)
                return
            p = p.parent()

    def _sel_context_menu(self, g: int, pos):
        """Right-click context menu on a sel button."""
        menu = QtWidgets.QMenu(self)
        act  = menu.addAction(f"Clear Group {g}")
        act.triggered.connect(partial(self._clear_group, g))
        menu.exec_(QtGui.QCursor.pos())

    def _clear_group(self, g: int, _=None):
        self._vis[g]    = []
        self._master[g] = []
        self._group[g]  = []
        print(f"[PhoenixUV] Group {g} cleared.")

    # ---- group logic
    def _assign_group(self, g: int, _=None):
        """Port of m341_uvMapper_GroupUVsProc.
        Snapshot the selection NOW (before the button steals focus),
        then do the heavy work deferred.
        """
        # capture current selection immediately before focus shifts
        snap = cmds.ls(sl=True, fl=True) or []
        in_obj = cmds.selectMode(q=True, object=True)
        cmds.evalDeferred(lambda: self._assign_group_deferred(g, snap, in_obj))

    def _assign_group_deferred(self, g: int, snap: list, in_obj: bool):
        if not snap:
            cmds.warning("[PhoenixUV] Nothing was selected – select UVs/faces/shells first.")
            return

        # restore the snapshot so MEL conversions work correctly
        cmds.select(snap)
        if in_obj:
            mel.eval("ConvertSelectionToFaces;")

        # expand to full shells then grab all UVs
        # MEL: ConvertSelectionToUVShell; ConvertSelectionToUVs; ls -sl -fl
        mel.eval("ConvertSelectionToUVShell;")
        mel.eval("ConvertSelectionToUVs;")
        vis_uvs = cmds.ls(sl=True, fl=True) or []
        if not vis_uvs:
            cmds.warning("[PhoenixUV] Could not get UVs – select faces, UVs or shells.")
            return

        vis_set = set(vis_uvs)

        # exclusive: remove these UVs from every other group
        # MEL: stringArrayRemove($vis, $otherVis)
        for other in range(1, self.MAX_GROUPS + 1):
            if other == g:
                continue
            old_vis = self._vis.get(other, [])
            if not old_vis:
                continue
            new_vis = [u for u in old_vis if u not in vis_set]
            self._vis[other] = new_vis
            if len(new_vis) < len(old_vis):
                if new_vis:
                    # rebuild master for other group using MEL selection
                    # MEL: select first UV; ConvertSelectionToUVShell; ConvertSelectionToUVs -> first shell = master
                    mel.eval(f'select "{new_vis[0]}";')
                    mel.eval("ConvertSelectionToUVShell;")
                    mel.eval("ConvertSelectionToUVs;")
                    first_shell = cmds.ls(sl=True, fl=True) or []
                    first_set   = set(first_shell)
                    self._master[other] = first_shell
                    self._group[other]  = [u for u in new_vis if u not in first_set]
                else:
                    self._master[other] = []
                    self._group[other]  = []

        # store vis
        self._vis[g] = vis_uvs

        # build master = first shell (MEL: texGetShells()[0] = first shell's UVs)
        # select vis, then ConvertSelectionToUVShell picks ONE shell at a time;
        # instead select just the first UV and expand to its shell
        mel.eval(f'select "{vis_uvs[0]}";')
        mel.eval("ConvertSelectionToUVShell;")
        mel.eval("ConvertSelectionToUVs;")
        first_shell = cmds.ls(sl=True, fl=True) or []
        first_set   = set(first_shell)
        self._master[g] = first_shell
        self._group[g]  = [u for u in vis_uvs if u not in first_set]

        # visual feedback: show assigned faces
        # MEL: select $vis; ConvertSelectionToFaces;
        mel.eval("select " + " ".join(f'"{u}"' for u in vis_uvs) + ";")
        mel.eval("ConvertSelectionToFaces;")
        print(f"[PhoenixUV] Group {g}: vis={len(vis_uvs)} master={len(self._master[g])} slaves={len(self._group[g])}")

    def _select_group(self, g: int, _=None):
        """Port of m341_uvMapper_SelectGroupUVsProc."""
        cmds.evalDeferred(lambda: self._select_group_deferred(g))

    def _select_group_deferred(self, g: int):
        uvs = self._vis.get(g, [])
        if not uvs:
            print(f"[PhoenixUV] Group {g} is empty.")
            return
        mel.eval("setSelectMode components Components;")
        mel.eval("selectType -polymeshUV 1;")
        mel.eval("select " + " ".join(f'"{u}"' for u in uvs) + ";")
        mel.eval("ConvertSelectionToUVs;")
        mel.eval("SelectUVMask;")
        print(f"[PhoenixUV] Group {g} selected ({len(uvs)} UVs).")

    def _clear_selected(self, _=None):
        mel_run("ConvertSelectionToUVShell; ConvertSelectionToUVs;")
        sel_set = set(cmds.ls(sl=True, fl=True) or [])
        if not sel_set:
            cmds.warning("[PhoenixUV] Select something to identify the group.")
            return
        for g in range(1, self.MAX_GROUPS + 1):
            if any(u in sel_set for u in self._vis.get(g, [])):
                self._vis[g]    = []
                self._master[g] = []
                self._group[g]  = []
                print(f"[PhoenixUV] Group {g} cleared.")
                return
        print("[PhoenixUV] Selection not found in any group.")

    def _clear_all(self, _=None):
        for g in range(1, self.MAX_GROUPS + 1):
            self._vis[g]    = []
            self._master[g] = []
            self._group[g]  = []
        print("[PhoenixUV] All groups cleared.")


# =============================================================================
# DOCKING  –  Maya workspaceControl
# =============================================================================
def _maya_main_window():
    ptr = omui.MQtUtil.mainWindow()
    return wrapInstance(int(ptr), QtWidgets.QWidget)


def launch():
    """
    Call this to open / restore the Phoenix UV Toolbox.
    Can be called from a shelf button or userSetup.py.

    Example shelf button:
        import phoenix_uv_toolbox as put; put.launch()
    """
    # destroy stale workspace control
    if cmds.workspaceControl(WORKSPACE_CTRL, q=True, exists=True):
        cmds.workspaceControl(WORKSPACE_CTRL, e=True, close=True)
        cmds.deleteUI(WORKSPACE_CTRL, control=True)

    # create workspace control and embed our widget
    cmds.workspaceControl(
        WORKSPACE_CTRL,
        label=TOOL_VERSION,
        floating=True,
        initialWidth=240,
        minimumWidth=220,
        uiScript=(
            "import phoenix_uv_toolbox as put; put._restore_workspace()"
        ),
        restore=False,
    )
    _restore_workspace()


def _restore_workspace():
    """Called by Maya's workspaceControl uiScript on restore."""
    ctrl = omui.MQtUtil.findControl(WORKSPACE_CTRL)
    if ctrl is None:
        return
    parent = wrapInstance(int(ctrl), QtWidgets.QWidget)

    # remove old instance if any
    for child in parent.findChildren(PhoenixUVToolbox):
        child.setParent(None)
        child.deleteLater()

    widget = PhoenixUVToolbox(parent=parent)
    layout = parent.layout()
    if layout is None:
        layout = QtWidgets.QVBoxLayout(parent)
        layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(widget)
    widget.show()


# =============================================================================
# QUICK RUN  (python script editor)
# =============================================================================
if __name__ == "__main__":
    launch()