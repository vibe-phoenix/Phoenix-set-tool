# Maya Python — PySide2 / PySide6 compatible UI
# ------------------------------------------------------------
# UI Layout (2 columns x 3 rows, each button ~50% width):
#   Save Set Element | Group Ungrouped
#   Import Blockout  | Export Groups
#   Duplicate        | Clean Up
#
# Notes dropdown (collapsible) — default collapsed (OFF)
# ------------------------------------------------------------

import os
import re
import shutil
import maya.cmds as cmds
import maya.mel as mel
import maya.OpenMayaUI as omui
import maya.app.general.mayaMixin

try:
    from PySide6 import QtWidgets, QtCore
    from shiboken6 import wrapInstance
except Exception:
    from PySide2 import QtWidgets, QtCore
    from shiboken2 import wrapInstance


EMPTY_MA_SOURCE = r"C:\icons-phoenix\mayaFile\setEmptyFile.ma"

# -----------------------------
# Qt / Maya helpers
# -----------------------------
def maya_main_window():
    ptr = omui.MQtUtil.mainWindow()
    return wrapInstance(int(ptr), QtWidgets.QWidget) if ptr else None


def undo_chunk(fn):
    def _wrapped(*args, **kwargs):
        cmds.undoInfo(openChunk=True)
        try:
            return fn(*args, **kwargs)
        finally:
            cmds.undoInfo(closeChunk=True)
    return _wrapped


def safe_fs_name(name):
    name = name.replace(":", "_")
    name = re.sub(r'[<>:"/\\|?*\n\r\t]', "_", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name.strip(" .")


def camel_case_name(name):
    """Convert 'flower pot 01' -> 'flowerPot01'"""
    parts = re.split(r'[\s_\-]+', name.strip())
    if not parts:
        return name
    result = parts[0].lower()
    for part in parts[1:]:
        result += part[0].upper() + part[1:].lower() if part else ""
    return result


def strip_special_for_name(name):
    """Remove apostrophes and other non-filename chars, keep alphanumeric + common chars"""
    return re.sub(r"['\"]", "", name)


def get_default_project_name():
    scene_path = cmds.file(q=True, sn=True)
    if not scene_path:
        return "project"
    base = os.path.basename(scene_path)
    name, _ = os.path.splitext(base)
    return name or "project"


def ensure_obj_export_plugin():
    try:
        if not cmds.pluginInfo("objExport", q=True, loaded=True):
            cmds.loadPlugin("objExport")
        return True
    except Exception:
        return False


def ensure_fbx_export_plugin():
    try:
        if not cmds.pluginInfo("fbxmaya", q=True, loaded=True):
            cmds.loadPlugin("fbxmaya")
        return True
    except Exception:
        return False


def is_new_empty_scene():
    """Check if current scene is a new, unsaved, empty scene."""
    scene_path = cmds.file(q=True, sn=True)
    if scene_path:
        return False
    all_nodes = cmds.ls(dag=True, long=True) or []
    default_nodes = {"persp", "top", "front", "side", "perspShape", "topShape", "frontShape", "sideShape"}
    non_default = [n for n in all_nodes if n.lstrip("|").split("|")[0] not in default_nodes]
    return len(non_default) == 0


# -----------------------------
# Scene helpers
# -----------------------------
def is_mesh_transform(xform_long):
    shapes = cmds.listRelatives(xform_long, shapes=True, fullPath=True) or []
    return any(cmds.nodeType(s) == "mesh" for s in shapes)


def is_group_transform(xform_long):
    if not cmds.objExists(xform_long) or cmds.nodeType(xform_long) != "transform":
        return False
    if cmds.listRelatives(xform_long, shapes=True, fullPath=True) or []:
        return False
    kids = cmds.listRelatives(xform_long, children=True, type="transform", fullPath=True) or []
    return bool(kids)


def top_level_mesh_transforms():
    all_t = cmds.ls(type="transform", long=True) or []
    top = [t for t in all_t if not (cmds.listRelatives(t, parent=True, fullPath=True) or [])]
    return [t for t in top if is_mesh_transform(t)]


def top_level_groups_only():
    transforms = cmds.ls(type="transform", long=True) or []
    top = [t for t in transforms if not (cmds.listRelatives(t, parent=True, fullPath=True) or [])]
    return [t for t in top if is_group_transform(t)]


def _top_level_of(nodes_long):
    s = set(nodes_long)
    out = []
    for n in nodes_long:
        p = cmds.listRelatives(n, parent=True, fullPath=True) or []
        if not p or p[0] not in s:
            out.append(n)
    return out


def _world_bbox(obj_long):
    return cmds.exactWorldBoundingBox(obj_long)


def _bottom_center_from_bb(bb):
    minx, miny, minz, maxx, maxy, maxz = bb
    return [(minx + maxx) * 0.5, miny, (minz + maxz) * 0.5]


def _move_by_delta_world(obj_long, delta_xyz):
    cmds.move(delta_xyz[0], delta_xyz[1], delta_xyz[2], obj_long, r=True, ws=True)


def _ensure_position_refs_group():
    if cmds.objExists("positionRefs"):
        matches = cmds.ls("positionRefs", long=True) or []
        for m in matches:
            if not (cmds.listRelatives(m, parent=True, fullPath=True) or []):
                return m
        return matches[0]
    grp = cmds.group(em=True, name="positionRefs")
    return cmds.ls(grp, long=True)[0]


def _add_or_set_double_attr(node, attr, value):
    if not cmds.attributeQuery(attr, node=node, exists=True):
        cmds.addAttr(node, ln=attr, at="double", dv=value)
        cmds.setAttr(f"{node}.{attr}", e=True, keyable=False, channelBox=False)
    cmds.setAttr(f"{node}.{attr}", value)


# ------------------------------------------------------------
# ACTIONS
# ------------------------------------------------------------
@undo_chunk
def action_group_all_ungrouped(*_):
    meshes = top_level_mesh_transforms()
    if not meshes:
        cmds.inViewMessage(amg="No ungrouped (top-level) meshes found.", pos="topCenter", fade=True)
        return

    for geo_long in meshes:
        name = geo_long.split("|")[-1]
        try:
            tmp = cmds.group(em=True, name=name + "_TMP_GRP#")
            m = cmds.xform(geo_long, q=True, ws=True, m=True)
            cmds.xform(tmp, ws=True, m=m)
            geo_child = cmds.parent(geo_long, tmp)[0]
            cmds.rename(tmp, name)
            cmds.rename(geo_child, name)
        except Exception as e:
            cmds.warning(f"Skipped {name}: {e}")

    cmds.inViewMessage(amg="Grouped all ungrouped meshes.", pos="topCenter", fade=True)


# ============================================================
# CREATE SET STRUCTURE  (Shift+Click on Save Set Element)
# ============================================================

def _build_set_folder_name(base_name, element_name, use_underscore):
    """Build the set element folder name from set name + element camelCase name."""
    clean_base = strip_special_for_name(base_name)
    if use_underscore:
        return f"{clean_base}_{element_name}"
    else:
        # capitalise first letter of element_name when appending without underscore
        elem_cap = element_name[0].upper() + element_name[1:] if element_name else element_name
        return f"{clean_base}{elem_cap}"


def _build_set_file_name(set_name, file_type, with_number, is_blockout=False, version=1):
    """
    Build set-level maya file name.
    file_type: "set" | "props"
    with_number: bool  (checkbox "with _01")
    """
    clean = strip_special_for_name(set_name)
    v_str = f"v{version:02d}"
    if is_blockout:
        if with_number:
            return f"prj_set_{clean}_blockout_01_{v_str}.ma"
        else:
            return f"prj_set_{clean}_blockout_{v_str}.ma"
    else:
        if with_number:
            return f"prj_set_{clean}_mod_01_{v_str}.ma"
        else:
            return f"prj_set_{clean}_mod_{v_str}.ma"


def _build_element_file_name(set_name, element_folder_name, with_number, use_underscore, version=1):
    """Build props maya file name for a set element."""
    clean_set = strip_special_for_name(set_name)
    v_str = f"v{version:02d}"
    if use_underscore:
        base = f"{clean_set}_{element_folder_name.replace(clean_set + '_', '')}"
    else:
        base = element_folder_name

    if with_number:
        return f"prj_props_{base}_mod_01_{v_str}.ma"
    else:
        return f"prj_props_{base}_mod_{v_str}.ma"


class CreateSetStructureDialog(QtWidgets.QDialog):
    """
    Panel opened on Shift+Left-Click of Save Set Element button.
    Creates the full folder structure for a new set.
    """
    def __init__(self, root_folder, parent=maya_main_window()):
        super().__init__(parent)
        self.setWindowTitle("Create Set Structure")
        self.setObjectName("PhoenixCreateSetStructureDialog")
        self.setWindowFlags(self.windowFlags() ^ QtCore.Qt.WindowContextHelpButtonHint)
        self.setMinimumSize(600, 680)

        self._root_folder = root_folder
        self._set_name = os.path.basename(root_folder)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # Set name display
        name_row = QtWidgets.QHBoxLayout()
        name_row.addWidget(QtWidgets.QLabel("Set Name:"))
        self.lbl_set_name = QtWidgets.QLabel(f"<b>{self._set_name}</b>")
        self.lbl_set_name.setToolTip(root_folder)
        name_row.addWidget(self.lbl_set_name)
        name_row.addStretch(1)
        layout.addLayout(name_row)

        sep1 = QtWidgets.QFrame()
        sep1.setFrameShape(QtWidgets.QFrame.HLine)
        layout.addWidget(sep1)

        # Options row
        opts_box = QtWidgets.QGroupBox("Naming & Folder Options")
        opts_layout = QtWidgets.QVBoxLayout(opts_box)

        self.cb_underscore = QtWidgets.QCheckBox("Use underscore separator  (set_element  vs  setElement)")
        self.cb_underscore.setChecked(False)
        opts_layout.addWidget(self.cb_underscore)

        self.cb_with_number = QtWidgets.QCheckBox("Include version number in filename  (_mod_01_v01  vs  _mod_v01)")
        self.cb_with_number.setChecked(False)
        opts_layout.addWidget(self.cb_with_number)

        dir_row = QtWidgets.QHBoxLayout()
        self.cb_use_obj = QtWidgets.QCheckBox("Use 'obj' subfolder name  (mod/obj  vs  mod)")
        self.cb_use_obj.setChecked(False)
        dir_row.addWidget(self.cb_use_obj)
        self.cb_use_srcimgs = QtWidgets.QCheckBox("Use 'srcimgs'  (vs  sourceImages)")
        self.cb_use_srcimgs.setChecked(False)
        dir_row.addWidget(self.cb_use_srcimgs)
        opts_layout.addLayout(dir_row)

        layout.addWidget(opts_box)

        # Set Elements list
        layout.addWidget(QtWidgets.QLabel("Set Element Names  (one per line — spaces/underscores converted to camelCase):"))

        self.elements_edit = QtWidgets.QPlainTextEdit()
        self.elements_edit.setPlaceholderText("flower pot 01\nalcohol A\nbook shelf\n...")
        self.elements_edit.setMinimumHeight(160)
        layout.addWidget(self.elements_edit)

        # Live preview
        layout.addWidget(QtWidgets.QLabel("Preview (first element):"))
        self.lbl_preview = QtWidgets.QLabel("")
        self.lbl_preview.setWordWrap(True)
        self.lbl_preview.setStyleSheet("color: #aaa; font-size: 11px;")
        layout.addWidget(self.lbl_preview)

        sep2 = QtWidgets.QFrame()
        sep2.setFrameShape(QtWidgets.QFrame.HLine)
        layout.addWidget(sep2)

        self.buttons = QtWidgets.QDialogButtonBox()
        self.btn_create = self.buttons.addButton("Create Set Structure", QtWidgets.QDialogButtonBox.AcceptRole)
        self.btn_cancel = self.buttons.addButton(QtWidgets.QDialogButtonBox.Cancel)
        layout.addWidget(self.buttons)

        self.elements_edit.textChanged.connect(self._update_preview)
        self.cb_underscore.toggled.connect(self._update_preview)
        self.cb_with_number.toggled.connect(self._update_preview)
        self.buttons.accepted.connect(self._on_create)
        self.buttons.rejected.connect(self.reject)

        self._update_preview()

    def _parse_elements(self):
        raw = self.elements_edit.toPlainText()
        lines = [l.strip() for l in raw.splitlines() if l.strip()]
        return lines

    def _update_preview(self):
        lines = self._parse_elements()
        use_underscore = self.cb_underscore.isChecked()
        with_number = self.cb_with_number.isChecked()

        if not lines:
            self.lbl_preview.setText("(add element names above to see preview)")
            return

        first = lines[0]
        camel = camel_case_name(first)
        folder_name = _build_set_folder_name(self._set_name, camel, use_underscore)
        set_file = _build_set_file_name(self._set_name, "set", with_number)
        elem_file = _build_element_file_name(self._set_name, folder_name, with_number, use_underscore)

        preview = (
            f"Set maya file:  {set_file}\n"
            f"Element folder: ...\\setElements\\{folder_name}\\\n"
            f"Element maya:   {elem_file}"
        )
        self.lbl_preview.setText(preview)

    def _on_create(self):
        lines = self._parse_elements()
        use_underscore = self.cb_underscore.isChecked()

        # Check for duplicates
        camel_names = [camel_case_name(l) for l in lines]
        seen = set()
        dupes = []
        for n in camel_names:
            if n in seen:
                dupes.append(n)
            seen.add(n)
        if dupes:
            QtWidgets.QMessageBox.warning(
                self, "Duplicate Names",
                f"Duplicate element names detected:\n{', '.join(dupes)}\n\nPlease make names unique."
            )
            return
        self.accept()

    def get_options(self):
        lines = self._parse_elements()
        return {
            "root_folder": self._root_folder,
            "set_name": self._set_name,
            "elements": [camel_case_name(l) for l in lines],
            "use_underscore": self.cb_underscore.isChecked(),
            "with_number": self.cb_with_number.isChecked(),
            "use_obj": self.cb_use_obj.isChecked(),
            "use_srcimgs": self.cb_use_srcimgs.isChecked(),
        }


def _get_mod_folder_name(use_obj):
    return "obj" if use_obj else "mod"


def _get_images_folder_name(use_srcimgs):
    return "srcimgs" if use_srcimgs else "sourceImages"


def _create_set_structure(opts):
    root = opts["root_folder"]
    set_name = opts["set_name"]
    use_underscore = opts["use_underscore"]
    with_number = opts["with_number"]
    use_obj = opts["use_obj"]
    use_srcimgs = opts["use_srcimgs"]
    element_names = opts["elements"]

    mod_name = _get_mod_folder_name(use_obj)
    imgs_name = _get_images_folder_name(use_srcimgs)

    # Main set folders
    main_dirs = [
        os.path.join(root, "maya"),
        os.path.join(root, "maya", "blockout"),
        os.path.join(root, mod_name),
        os.path.join(root, mod_name, "blockout"),
        os.path.join(root, "renders"),
        os.path.join(root, imgs_name),
        os.path.join(root, "ref"),
        os.path.join(root, "setElements"),
    ]
    for d in main_dirs:
        os.makedirs(d, exist_ok=True)

    # Save main maya file
    set_file = _build_set_file_name(set_name, "set", with_number)
    main_ma_path = os.path.join(root, "maya", set_file)
    cmds.file(rename=main_ma_path)
    cmds.file(save=True, type="mayaAscii")

    # Create set element folders
    set_elements_root = os.path.join(root, "setElements")
    for elem_camel in element_names:
        folder_name = _build_set_folder_name(set_name, elem_camel, use_underscore)
        elem_root = os.path.join(set_elements_root, folder_name)

        elem_dirs = [
            os.path.join(elem_root, "maya"),
            os.path.join(elem_root, mod_name),
            os.path.join(elem_root, mod_name, "blockout"),
            os.path.join(elem_root, "ref"),
            os.path.join(elem_root, imgs_name),
        ]
        for d in elem_dirs:
            os.makedirs(d, exist_ok=True)

        # Create element maya file (empty .ma)
        elem_file = _build_element_file_name(set_name, folder_name, with_number, use_underscore)
        elem_ma_path = os.path.join(elem_root, "maya", elem_file)
        with open(elem_ma_path, 'w') as f:
            f.write("//Maya ASCII 2024 scene\n//Placeholder\n")

    return main_ma_path


def action_create_set_structure(*_):
    """Shift+Left-Click on Save Set Element."""
    if not is_new_empty_scene():
        QtWidgets.QMessageBox.warning(
            maya_main_window(),
            "Not an Empty Scene",
            "This function requires a new, empty (unsaved) scene.\n"
            "Please open a new scene (File > New Scene) before creating a set structure."
        )
        return

    folder = cmds.fileDialog2(dialogStyle=2, fm=3, caption="Select the Set Root Folder")
    if not folder:
        return
    root_folder = folder[0]
    if not os.path.isdir(root_folder):
        cmds.warning("Selected path is not a valid folder.")
        return

    dlg = CreateSetStructureDialog(root_folder)
    result = dlg.exec_() if hasattr(dlg, "exec_") else dlg.exec()
    if result != QtWidgets.QDialog.Accepted:
        return

    opts = dlg.get_options()
    try:
        saved_path = _create_set_structure(opts)
        cmds.inViewMessage(
            amg=f"Set structure created! Saved: {os.path.basename(saved_path)}",
            pos="topCenter", fade=True
        )
    except Exception as e:
        QtWidgets.QMessageBox.critical(maya_main_window(), "Error", f"Failed to create set structure:\n{e}")


# -----------------------------
# Export dialog (OBJ/FBX)
# -----------------------------
class ExportSetupDialog(QtWidgets.QDialog):
    def __init__(self, groups_long, parent=maya_main_window()):
        super().__init__(parent)
        self.setWindowTitle("Export Groups — Setup")
        self.setObjectName("PhoenixExportSetupDialog")
        self.setWindowFlags(self.windowFlags() ^ QtCore.Qt.WindowContextHelpButtonHint)
        self.setMinimumSize(560, 740)

        self._groups_long = list(groups_long)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        prefix_row = QtWidgets.QHBoxLayout()
        prefix_row.addWidget(QtWidgets.QLabel("Prefix:"))
        self.prefix_edit = QtWidgets.QLineEdit(get_default_project_name())
        self.prefix_edit.selectAll()
        prefix_row.addWidget(self.prefix_edit, 1)
        self.no_prefix_cb = QtWidgets.QCheckBox("No prefix")
        self.no_prefix_cb.setChecked(False)
        self.no_prefix_cb.setToolTip("Export FBX named after the group only, with no prefix.")
        prefix_row.addWidget(self.no_prefix_cb)
        layout.addLayout(prefix_row)

        self.no_prefix_cb.toggled.connect(lambda v: self.prefix_edit.setEnabled(not v))

        opts_box = QtWidgets.QGroupBox("Export Options")
        opts_layout = QtWidgets.QVBoxLayout(opts_box)

        self.blockout_cb = QtWidgets.QCheckBox("Groups are blockout")
        self.blockout_cb.setChecked(False)
        self.blockout_cb.setToolTip(
            "When checked, exports to mod/<group>_blockout/ instead of mod/"
        )
        opts_layout.addWidget(self.blockout_cb)

        self.create_ma_cb = QtWidgets.QCheckBox("Create .ma files  (copies from setEmptyFile.ma template)")
        self.create_ma_cb.setChecked(False)
        self.create_ma_cb.setToolTip(
            f"Copies {EMPTY_MA_SOURCE} into each group's maya folder,\n"
            "renamed according to prefix + group name."
        )
        opts_layout.addWidget(self.create_ma_cb)

        self.underscore_cb = QtWidgets.QCheckBox("With underscore  (prefix_Group  vs  prefixGroup)")
        self.underscore_cb.setChecked(True)
        opts_layout.addWidget(self.underscore_cb)

        self.with_number_cb = QtWidgets.QCheckBox("Include version number  (_mod_01_v01  vs  _mod_v01)")
        self.with_number_cb.setChecked(False)
        opts_layout.addWidget(self.with_number_cb)

        dir_row2 = QtWidgets.QHBoxLayout()
        self.cb_use_obj = QtWidgets.QCheckBox("Use 'obj' folder  (mod/obj)")
        self.cb_use_obj.setChecked(False)
        dir_row2.addWidget(self.cb_use_obj)
        self.cb_use_srcimgs = QtWidgets.QCheckBox("Use 'srcimgs'  (vs sourceImages)")
        self.cb_use_srcimgs.setChecked(False)
        dir_row2.addWidget(self.cb_use_srcimgs)
        opts_layout.addLayout(dir_row2)

        layout.addWidget(opts_box)

        search_row = QtWidgets.QHBoxLayout()
        search_row.addWidget(QtWidgets.QLabel("Search:"))
        self.search = QtWidgets.QLineEdit()
        self.search.setPlaceholderText("Filter groups...")
        search_row.addWidget(self.search, 1)
        layout.addLayout(search_row)

        self.listw = QtWidgets.QListWidget()
        self.listw.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        layout.addWidget(self.listw, 1)

        hint = QtWidgets.QLabel("Select group(s) you DON'T want to export.")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        btn_row = QtWidgets.QHBoxLayout()
        self.btn_select_all = QtWidgets.QPushButton("Select All (Exclude)")
        self.btn_clear = QtWidgets.QPushButton("Clear Selection")
        btn_row.addWidget(self.btn_select_all)
        btn_row.addWidget(self.btn_clear)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        self.buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        layout.addWidget(self.buttons)

        self._populate()
        self.search.textChanged.connect(self._filter)
        self.btn_select_all.clicked.connect(self._select_all)
        self.btn_clear.clicked.connect(self.listw.clearSelection)
        self.buttons.accepted.connect(self._on_ok)
        self.buttons.rejected.connect(self.reject)

    def _populate(self):
        self.listw.clear()
        def short_name(longp): return longp.split("|")[-1]
        for g_long in sorted(self._groups_long, key=lambda x: short_name(x).lower()):
            item = QtWidgets.QListWidgetItem(short_name(g_long))
            item.setData(QtCore.Qt.UserRole, g_long)
            item.setToolTip(g_long)
            self.listw.addItem(item)

    def _filter(self, text):
        t = (text or "").strip().lower()
        for i in range(self.listw.count()):
            item = self.listw.item(i)
            longp = item.data(QtCore.Qt.UserRole)
            item.setHidden(not (t in item.text().lower() or t in str(longp).lower()))

    def _select_all(self):
        self.listw.clearSelection()
        for i in range(self.listw.count()):
            item = self.listw.item(i)
            if not item.isHidden():
                item.setSelected(True)

    def _on_ok(self):
        if not self.no_prefix_cb.isChecked():
            p = (self.prefix_edit.text() or "").strip()
            if not p:
                QtWidgets.QMessageBox.warning(self, "Prefix Required", "Please enter a prefix, or check 'No prefix'.")
                return
        self.accept()

    def prefix(self):
        if self.no_prefix_cb.isChecked():
            return ""
        return (self.prefix_edit.text() or "").strip()
    def is_blockout(self): return bool(self.blockout_cb.isChecked())
    def create_ma_files(self): return bool(self.create_ma_cb.isChecked())
    def use_underscore(self): return bool(self.underscore_cb.isChecked())
    def with_number(self): return bool(self.with_number_cb.isChecked())
    def use_obj_folder(self): return bool(self.cb_use_obj.isChecked())
    def use_srcimgs_folder(self): return bool(self.cb_use_srcimgs.isChecked())
    def excluded_groups_set(self): return {item.data(QtCore.Qt.UserRole) for item in self.listw.selectedItems()}


def _build_export_folder_name(prefix, group_short, use_underscore):
    clean_prefix = strip_special_for_name(prefix)
    clean_group = group_short
    if not clean_prefix:
        return clean_group
    if use_underscore:
        return f"{clean_prefix}_{clean_group}"
    else:
        g_cap = clean_group[0].upper() + clean_group[1:] if clean_group else clean_group
        return f"{clean_prefix}{g_cap}"


def _build_export_ma_name(prefix, group_short, use_underscore, with_number, is_blockout=False, version=1):
    folder_name = _build_export_folder_name(prefix, group_short, use_underscore)
    v_str = f"v{version:02d}"
    suffix = "blockout" if is_blockout else "mod"
    if with_number:
        return f"prj_props_{folder_name}_{suffix}_01_{v_str}.ma"
    else:
        return f"prj_props_{folder_name}_{suffix}_{v_str}.ma"


def export_group_to_structure(base_folder, prefix, group_long, blockout=False,
                               use_underscore=True, with_number=False,
                               use_obj=False, use_srcimgs=False,
                               create_ma=False):
    group_short = group_long.split("|")[-1]
    folder_name = _build_export_folder_name(prefix, group_short, use_underscore)
    root = os.path.join(base_folder, safe_fs_name(folder_name))

    mod_name = _get_mod_folder_name(use_obj)
    imgs_name = _get_images_folder_name(use_srcimgs)

    for d in ("maya", mod_name, imgs_name, "ref"):
        os.makedirs(os.path.join(root, d), exist_ok=True)

    if not ensure_fbx_export_plugin():
        cmds.warning("FBX plugin (fbxmaya) could not be loaded.")
        return None

    if blockout:
        export_dir = os.path.join(root, mod_name, safe_fs_name(f"{group_short}_blockout"))
    else:
        export_dir = os.path.join(root, mod_name)
    os.makedirs(export_dir, exist_ok=True)

    fbx_path = os.path.join(export_dir, safe_fs_name(group_short) + ".fbx")
    cmds.select(group_long, r=True)
    fbx_path_mel = fbx_path.replace("\\", "/")
    mel.eval("FBXResetExport;")
    mel.eval(f'FBXExport -f "{fbx_path_mel}" -s;')

    if create_ma:
        maya_folder = os.path.join(root, "maya")
        ma_name = _build_export_ma_name(prefix, group_short, use_underscore, with_number, blockout)
        ma_dest = os.path.join(maya_folder, ma_name)
        if os.path.isfile(EMPTY_MA_SOURCE):
            shutil.copy2(EMPTY_MA_SOURCE, ma_dest)
        else:
            with open(ma_dest, 'w') as f:
                f.write("//Maya ASCII 2024 scene\n//Placeholder\n")

    return fbx_path




# ============================================================
# SHIFT+CLICK EXPORT — Smooth, Centre, Cleanup, FBX, Revert
# ============================================================

def _get_asset_root_from_scene_path(scene_path):
    """Walk up from the maya file to find the set-element root (parent of 'maya' folder)."""
    if not scene_path:
        return None
    d = os.path.dirname(scene_path)
    if os.path.basename(d).lower() == "maya":
        return os.path.dirname(d)
    return d


def _current_element_root():
    """
    Derive the current set-element root folder from the open scene path.
    Scene is expected to be at:  <element_root>/maya/<filename>.ma
    Returns the element_root path, or None if it cannot be determined.
    """
    scene_path = cmds.file(q=True, sn=True)
    if not scene_path:
        return None
    d = os.path.dirname(scene_path)
    if os.path.basename(d).lower() == "maya":
        return os.path.dirname(d)   # element_root
    return None


def _scene_set_element_roots():
    """
    Return every sibling set-element folder from the current scene's setElements parent.
    Scene is expected at: <set_root>/setElements/<element>/maya/<file>.ma
    So:  scene → maya/ → element/ → setElements/ → (all siblings)
    """
    scene_path = cmds.file(q=True, sn=True)
    if not scene_path:
        return []
    maya_dir    = os.path.dirname(scene_path)           # .../element/maya
    elem_dir    = os.path.dirname(maya_dir)             # .../element
    se_dir      = os.path.dirname(elem_dir)             # .../setElements  (hopefully)

    if os.path.basename(se_dir).lower() == "setelements" and os.path.isdir(se_dir):
        return [
            os.path.join(se_dir, n)
            for n in sorted(os.listdir(se_dir))
            if os.path.isdir(os.path.join(se_dir, n))
        ]

    # Fallback: look for a setElements sibling next to elem_dir
    parent = os.path.dirname(elem_dir)
    se_dir2 = os.path.join(parent, "setElements")
    if os.path.isdir(se_dir2):
        return [
            os.path.join(se_dir2, n)
            for n in sorted(os.listdir(se_dir2))
            if os.path.isdir(os.path.join(se_dir2, n))
        ]
    return []


def _mod_obj_folder_for_element(element_root):
    """
    Return the export folder inside a set element root.
    Checks for 'mod' first, then 'obj' at the top of the element folder.
    Creates 'mod' if neither exists.
    Never looks inside mod/obj — the FBX goes directly in mod/ or obj/.
    """
    for sub in ("mod", "obj"):
        p = os.path.join(element_root, sub)
        if os.path.isdir(p):
            return p
    # Neither exists — create mod/
    p = os.path.join(element_root, "mod")
    os.makedirs(p, exist_ok=True)
    return p


def _get_bounding_box_world(nodes_long):
    """Return combined world bounding box of a list of nodes."""
    all_bb = [cmds.exactWorldBoundingBox(n) for n in nodes_long]
    if not all_bb:
        return None
    minx = min(b[0] for b in all_bb)
    miny = min(b[1] for b in all_bb)
    minz = min(b[2] for b in all_bb)
    maxx = max(b[3] for b in all_bb)
    maxy = max(b[4] for b in all_bb)
    maxz = max(b[5] for b in all_bb)
    return minx, miny, minz, maxx, maxy, maxz


def _centre_groups_to_origin_y0(groups_long):
    """
    Move each group so its bounding-box base sits at Y=0 and its XZ centre is at world origin.
    Returns a dict {group_long: (tx, ty, tz)} of the translation deltas applied,
    so we can revert afterwards.
    """
    deltas = {}
    for g in groups_long:
        bb = cmds.exactWorldBoundingBox(g)
        minx, miny, minz, maxx, maxy, maxz = bb
        cx = (minx + maxx) * 0.5
        cz = (minz + maxz) * 0.5
        dx = -cx
        dy = -miny
        dz = -cz
        cmds.move(dx, dy, dz, g, r=True, ws=True)
        deltas[g] = (dx, dy, dz)
    return deltas


def _smooth_meshes_in_groups(groups_long, divisions):
    """
    Apply polySmooth to every mesh shape inside the groups, matching Maya's own
    MEL output when you select a group and run Mesh > Smooth:
      - Target: mesh shape nodes (by short name), not transforms
      - mth=0  : Maya Catmull-Clark (not OpenSubdiv — mth=2 fails silently)
      - sdt=2  : subdivision type
      - ovb=1, ofb=1 : boundary rules
      - dv     : user-specified divisions
      - kb=1, ksb=1  : keep border / keep selection border
      - sl=1   : smoothness
      - ps=0.1 : push strength (corner preservation)
      - ro=1   : round sharp
      - ch=1   : keep construction history (needed so undo works)
    """
    smooth_nodes = []
    for g in groups_long:
        all_transforms = (
            cmds.listRelatives(g, allDescendents=True, fullPath=True, type="transform") or []
        )
        all_transforms = [g] + all_transforms

        for xform in all_transforms:
            shapes = cmds.listRelatives(xform, shapes=True, fullPath=True, type="mesh") or []
            shapes = [s for s in shapes if not cmds.getAttr(f"{s}.intermediateObject")]
            if not shapes:
                continue

            for shape in shapes:
                # polySmooth needs the short name of the shape, just like Maya's MEL output
                shape_short = shape.split("|")[-1]
                try:
                    cmds.select(shape_short, r=True)
                    result = cmds.polySmooth(
                        shape_short,
                        mth=0,          # Maya Catmull-Clark
                        sdt=2,          # subdivision type
                        ovb=1,          # OpenSubdiv vertex boundary
                        ofb=1,          # OpenSubdiv face boundary
                        ofc=0,          # face-varying
                        ost=0,
                        ocr=0,
                        dv=divisions,   # subdivision level
                        bnr=1,
                        c=1,
                        kb=1,           # keep border
                        ksb=1,          # keep selection border
                        khe=0,
                        kt=1,
                        kmb=1,
                        suv=1,
                        peh=0,
                        sl=1,           # smoothness
                        dpe=1,
                        ps=0.1,         # push strength — corner preservation
                        ro=1,           # round sharp
                        ch=1,           # construction history (required for undo)
                    )
                    if result:
                        smooth_nodes.extend(result)
                except Exception as e:
                    cmds.warning(f"[PhoenixExport] Smooth failed on {shape_short}: {e}")

    cmds.select(clear=True)
    return smooth_nodes


def _run_phoenix_cleanup_on_groups(groups_long):
    """Run the Phoenix cleanup routine on the given groups."""
    import maya.cmds as _cmds

    def _process_node(node):
        _cmds.xform(node, centerPivots=True)
        _cmds.makeIdentity(node, apply=True, t=True, r=True, s=True, n=False, pn=True)
        _cmds.delete(node, constructionHistory=True)

    def _get_all_descendants(root):
        descendants = _cmds.listRelatives(root, allDescendents=True, fullPath=True) or []
        return [root] + descendants

    def _is_group_node(node):
        shapes = _cmds.listRelatives(node, shapes=True, fullPath=True) or []
        return len(shapes) == 0

    def _is_mesh_node(node):
        shapes = _cmds.listRelatives(node, shapes=True, fullPath=True) or []
        return any(_cmds.nodeType(s) == 'mesh' for s in shapes)

    def _is_pos_ref(node):
        short = node.split('|')[-1].lower()
        return 'positionref' in short

    all_nodes = []
    seen = set()
    for r in groups_long:
        for node in _get_all_descendants(r):
            if node not in seen:
                seen.add(node)
                all_nodes.append(node)

    transforms = [n for n in all_nodes
                  if _cmds.nodeType(n) == 'transform' and not _is_pos_ref(n)]
    transforms.sort(key=lambda n: n.count('|'), reverse=True)

    errors = []
    for node in transforms:
        try:
            _process_node(node)
        except Exception as e:
            errors.append(node)
            _cmds.warning(f"[PhoenixExport] Cleanup skipped {node}: {e}")


def _export_groups_as_single_fbx(groups_long, fbx_path):
    """Select all groups and export as one merged FBX."""
    if not ensure_fbx_export_plugin():
        raise RuntimeError("FBX plugin could not be loaded.")
    cmds.select(groups_long, r=True)
    fbx_path_mel = fbx_path.replace("\\", "/")
    mel.eval("FBXResetExport;")
    mel.eval(f'FBXExport -f "{fbx_path_mel}" -s;')


# ── Step 1: mode picker ──────────────────────────────────────────────────────

class ShiftExportModePicker(QtWidgets.QDialog):
    """
    First window shown on Shift+Click Export Groups.
    Two big buttons: Current Session | All Set Elements.
    """
    # Returned by exec() via done()
    MODE_SESSION  = 2
    MODE_ALL      = 3

    def __init__(self, parent=maya_main_window()):
        super().__init__(parent)
        self.setWindowTitle("Phoenix — Export FBX")
        self.setObjectName("PhoenixShiftExportModePicker")
        self.setWindowFlags(self.windowFlags() ^ QtCore.Qt.WindowContextHelpButtonHint)
        self.setFixedSize(280, 110)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        lbl = QtWidgets.QLabel("Select export scope:")
        lbl.setStyleSheet("font-weight: bold;")
        layout.addWidget(lbl)

        btn_row = QtWidgets.QHBoxLayout()
        btn_row.setSpacing(10)

        self.btn_session = QtWidgets.QPushButton("Current Session")
        self.btn_all     = QtWidgets.QPushButton("All Set Elements")

        for b in (self.btn_session, self.btn_all):
            b.setMinimumHeight(40)
            b.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)

        self.btn_session.setToolTip(
            "Export groups from the currently open Maya session."
        )
        self.btn_all.setToolTip(
            "Iterate every set element folder found on disk and export each one."
        )

        btn_row.addWidget(self.btn_session)
        btn_row.addWidget(self.btn_all)
        layout.addLayout(btn_row)

        self.btn_session.clicked.connect(lambda: self.done(self.MODE_SESSION))
        self.btn_all.clicked.connect(lambda: self.done(self.MODE_ALL))


# ── Step 2a: Current Session config dialog ───────────────────────────────────

class ShiftExportSessionDialog(QtWidgets.QDialog):
    """
    Config dialog for Current Session mode.
    Destination is always auto-derived from the current scene path:
        <element_root>/mod/   or   <element_root>/obj/
    No browse button — just groups, smooth, and FBX name.
    """
    def __init__(self, groups_long, element_root, dest_folder, parent=maya_main_window()):
        super().__init__(parent)
        self.setWindowTitle("Export FBX — Current Session")
        self.setObjectName("PhoenixShiftExportSessionDialog")
        self.setWindowFlags(self.windowFlags() ^ QtCore.Qt.WindowContextHelpButtonHint)
        self.setMinimumSize(500, 480)

        self._groups_long  = list(groups_long)
        self._dest_folder  = dest_folder
        self._element_root = element_root

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # ── Destination info (read-only) ──────────────────────────
        info_box = QtWidgets.QGroupBox("Export Destination  (auto)")
        info_layout = QtWidgets.QVBoxLayout(info_box)
        dest_lbl = QtWidgets.QLabel(dest_folder)
        dest_lbl.setWordWrap(True)
        dest_lbl.setStyleSheet("color: #aaa; font-size: 11px;")
        dest_lbl.setToolTip(dest_folder)
        info_layout.addWidget(dest_lbl)
        layout.addWidget(info_box)

        # ── Group list ────────────────────────────────────────────
        layout.addWidget(QtWidgets.QLabel("Groups to export  (select one or more):"))
        self.listw = QtWidgets.QListWidget()
        self.listw.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.listw.setMinimumHeight(150)
        for g in sorted(self._groups_long, key=lambda x: x.split("|")[-1].lower()):
            short = g.split("|")[-1]
            it = QtWidgets.QListWidgetItem(short)
            it.setData(QtCore.Qt.UserRole, g)
            it.setToolTip(g)
            self.listw.addItem(it)
        if self.listw.count():
            self.listw.selectAll()
        layout.addWidget(self.listw, 1)

        # ── Smooth ────────────────────────────────────────────────
        smooth_box = QtWidgets.QGroupBox("Smooth")
        smooth_layout = QtWidgets.QHBoxLayout(smooth_box)
        self.smooth_cb = QtWidgets.QCheckBox("Apply smooth divisions:")
        self.smooth_cb.setChecked(True)
        self.smooth_spin = QtWidgets.QSpinBox()
        self.smooth_spin.setRange(0, 6)
        self.smooth_spin.setValue(2)
        self.smooth_spin.setMinimumWidth(55)
        smooth_layout.addWidget(self.smooth_cb)
        smooth_layout.addWidget(self.smooth_spin)
        smooth_layout.addStretch(1)
        layout.addWidget(smooth_box)
        self.smooth_cb.toggled.connect(self.smooth_spin.setEnabled)

        # ── FBX name ──────────────────────────────────────────────
        name_row = QtWidgets.QHBoxLayout()
        name_row.addWidget(QtWidgets.QLabel("FBX name:"))
        self.name_edit = QtWidgets.QLineEdit(os.path.basename(element_root) if element_root else "")
        self.name_edit.setPlaceholderText("filename (no extension)")
        name_row.addWidget(self.name_edit, 1)
        layout.addLayout(name_row)

        # ── Buttons ───────────────────────────────────────────────
        self.buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        self.buttons.button(QtWidgets.QDialogButtonBox.Ok).setText("Export FBX")
        layout.addWidget(self.buttons)
        self.buttons.accepted.connect(self._on_ok)
        self.buttons.rejected.connect(self.reject)

    def _on_ok(self):
        if not self.listw.selectedItems():
            QtWidgets.QMessageBox.warning(self, "No Groups", "Select at least one group.")
            return
        if not self.name_edit.text().strip():
            QtWidgets.QMessageBox.warning(self, "No Name", "Enter a name for the FBX.")
            return
        self.accept()

    def selected_groups(self):  return [it.data(QtCore.Qt.UserRole) for it in self.listw.selectedItems()]
    def smooth_enabled(self):   return bool(self.smooth_cb.isChecked())
    def smooth_divisions(self): return int(self.smooth_spin.value())
    def mesh_name(self):        return self.name_edit.text().strip()
    def destination(self):      return self._dest_folder


# ── Step 2b: Per-element config dialog (All Set Elements mode) ───────────────

# Sentinel return codes
_ELEM_EXPORT = QtWidgets.QDialog.Accepted   # = 1
_ELEM_SKIP   = 2
_ELEM_CANCEL = QtWidgets.QDialog.Rejected   # = 0

class ShiftExportElementDialog(QtWidgets.QDialog):
    """
    Shown once per set-element folder when running 'All Set Elements' mode.
    Destination is always <element_root>/mod/ or <element_root>/obj/ — auto-resolved.
    Buttons: Export FBX | Skip | Cancel All.
    """
    def __init__(self, element_root, groups_long, parent=maya_main_window()):
        super().__init__(parent)
        elem_name = os.path.basename(element_root)
        self.setWindowTitle(f"Export FBX — {elem_name}")
        self.setObjectName("PhoenixShiftExportElementDialog")
        self.setWindowFlags(self.windowFlags() ^ QtCore.Qt.WindowContextHelpButtonHint)
        self.setMinimumSize(480, 460)

        self._element_root = element_root
        self._dest_folder  = _mod_obj_folder_for_element(element_root)
        self._groups_long  = list(groups_long)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # Element header + auto dest
        hdr = QtWidgets.QLabel(f"<b>Set Element:</b>  {elem_name}")
        hdr.setToolTip(element_root)
        layout.addWidget(hdr)

        dest_lbl = QtWidgets.QLabel(self._dest_folder)
        dest_lbl.setWordWrap(True)
        dest_lbl.setStyleSheet("color: #aaa; font-size: 11px;")
        dest_lbl.setToolTip(self._dest_folder)
        layout.addWidget(dest_lbl)

        sep = QtWidgets.QFrame()
        sep.setFrameShape(QtWidgets.QFrame.HLine)
        layout.addWidget(sep)

        # ── Group list ────────────────────────────────────────────
        layout.addWidget(QtWidgets.QLabel("Groups to export  (select one or more):"))
        self.listw = QtWidgets.QListWidget()
        self.listw.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.listw.setMinimumHeight(130)
        for g in sorted(self._groups_long, key=lambda x: x.split("|")[-1].lower()):
            short = g.split("|")[-1]
            it = QtWidgets.QListWidgetItem(short)
            it.setData(QtCore.Qt.UserRole, g)
            it.setToolTip(g)
            self.listw.addItem(it)
        if self.listw.count():
            self.listw.selectAll()
        layout.addWidget(self.listw, 1)

        # ── Smooth ────────────────────────────────────────────────
        smooth_box = QtWidgets.QGroupBox("Smooth")
        smooth_layout = QtWidgets.QHBoxLayout(smooth_box)
        self.smooth_cb = QtWidgets.QCheckBox("Apply smooth divisions:")
        self.smooth_cb.setChecked(True)
        self.smooth_spin = QtWidgets.QSpinBox()
        self.smooth_spin.setRange(0, 6)
        self.smooth_spin.setValue(2)
        self.smooth_spin.setMinimumWidth(55)
        smooth_layout.addWidget(self.smooth_cb)
        smooth_layout.addWidget(self.smooth_spin)
        smooth_layout.addStretch(1)
        layout.addWidget(smooth_box)
        self.smooth_cb.toggled.connect(self.smooth_spin.setEnabled)

        # ── FBX name ──────────────────────────────────────────────
        name_row = QtWidgets.QHBoxLayout()
        name_row.addWidget(QtWidgets.QLabel("FBX name:"))
        self.name_edit = QtWidgets.QLineEdit(elem_name)
        name_row.addWidget(self.name_edit, 1)
        layout.addLayout(name_row)

        # ── Buttons: Export | Skip | Cancel All ───────────────────
        btn_row = QtWidgets.QHBoxLayout()
        btn_row.setSpacing(8)
        self.btn_export = QtWidgets.QPushButton("Export FBX")
        self.btn_skip   = QtWidgets.QPushButton("Skip")
        self.btn_cancel = QtWidgets.QPushButton("Cancel All")
        for b in (self.btn_export, self.btn_skip, self.btn_cancel):
            b.setMinimumHeight(36)
            b.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        self.btn_skip.setToolTip("Skip this element and continue to the next.")
        self.btn_cancel.setToolTip("Abort the entire All Set Elements run.")
        btn_row.addWidget(self.btn_export)
        btn_row.addWidget(self.btn_skip)
        btn_row.addWidget(self.btn_cancel)
        layout.addLayout(btn_row)

        self.btn_export.clicked.connect(self._on_export)
        self.btn_skip.clicked.connect(lambda: self.done(_ELEM_SKIP))
        self.btn_cancel.clicked.connect(self.reject)

    def _on_export(self):
        if not self.listw.selectedItems():
            QtWidgets.QMessageBox.warning(self, "No Groups", "Select at least one group.")
            return
        if not self.name_edit.text().strip():
            QtWidgets.QMessageBox.warning(self, "No Name", "Enter a name for the FBX.")
            return
        self.accept()

    def selected_groups(self):  return [it.data(QtCore.Qt.UserRole) for it in self.listw.selectedItems()]
    def smooth_enabled(self):   return bool(self.smooth_cb.isChecked())
    def smooth_divisions(self): return int(self.smooth_spin.value())
    def mesh_name(self):        return self.name_edit.text().strip()
    def destination(self):      return self._dest_folder


# ── Shared export execution ───────────────────────────────────────────────────

def _execute_shift_export(chosen_groups, mesh_name, dest_folder, do_smooth, smooth_divs):
    """
    Core export routine used by both session and all-elements modes.
    1. Centre groups to Y=0 world origin.
    2. Smooth meshes (optional).
    3. Phoenix cleanup (freeze + delete history).
    4. Export as single FBX.
    5. Undo the whole chunk — restores scene to pre-export state.
    Returns the exported fbx path on success.
    """
    if not os.path.isdir(dest_folder):
        os.makedirs(dest_folder, exist_ok=True)

    fbx_path = os.path.join(dest_folder, safe_fs_name(mesh_name) + ".fbx")

    cmds.undoInfo(openChunk=True, chunkName="PhoenixShiftExport")
    try:
        _centre_groups_to_origin_y0(chosen_groups)
        if do_smooth and smooth_divs > 0:
            _smooth_meshes_in_groups(chosen_groups, smooth_divs)
        _run_phoenix_cleanup_on_groups(chosen_groups)
        _export_groups_as_single_fbx(chosen_groups, fbx_path)
    finally:
        cmds.undoInfo(closeChunk=True)

    cmds.undo()   # revert everything: positions, smooth, history
    return fbx_path


# ── Entry point ───────────────────────────────────────────────────────────────

def action_shift_export_groups(*_):
    """
    Shift+Click on Export Groups.
    Step 1 — show mode picker (Current Session | All Set Elements).
    Step 2a — Current Session: pick groups + config → export → revert.
    Step 2b — All Set Elements: iterate every element folder, show per-element
               config dialog with Export / Skip / Cancel All.
    """
    # ── Step 1: mode picker ───────────────────────────────────────
    picker = ShiftExportModePicker()
    mode = picker.exec_() if hasattr(picker, "exec_") else picker.exec()

    # ── Step 2a: Current Session ──────────────────────────────────
    if mode == ShiftExportModePicker.MODE_SESSION:
        transforms = cmds.ls(type="transform", long=True) or []
        groups_long = [t for t in transforms if is_group_transform(t)]
        if not groups_long:
            cmds.inViewMessage(amg="No groups in scene to export.", pos="topCenter", fade=True)
            return

        # Derive destination from scene path
        element_root = _current_element_root()
        if not element_root:
            QtWidgets.QMessageBox.warning(
                maya_main_window(),
                "Cannot Derive Path",
                "The scene does not appear to be inside a set element's maya/ folder.\n"
                "Expected: <element_root>/maya/<file>.ma"
            )
            return
        dest_folder = _mod_obj_folder_for_element(element_root)

        dlg = ShiftExportSessionDialog(groups_long, element_root, dest_folder)
        result = dlg.exec_() if hasattr(dlg, "exec_") else dlg.exec()
        if result != QtWidgets.QDialog.Accepted:
            return

        chosen = dlg.selected_groups()
        if not chosen:
            return

        prev_sel = cmds.ls(sl=True, long=True) or []
        try:
            fbx_path = _execute_shift_export(
                chosen, dlg.mesh_name(), dlg.destination(),
                dlg.smooth_enabled(), dlg.smooth_divisions()
            )
            cmds.inViewMessage(
                amg=f"Exported → {os.path.basename(fbx_path)}  (scene reverted)",
                pos="topCenter", fade=True, fadeStayTime=3000
            )
        except Exception as e:
            QtWidgets.QMessageBox.critical(maya_main_window(), "Export Failed", str(e))
        finally:
            try:
                cmds.select(prev_sel, r=True) if prev_sel else cmds.select(clear=True)
            except Exception:
                cmds.select(clear=True)

    # ── Step 2b: All Set Elements ─────────────────────────────────
    elif mode == ShiftExportModePicker.MODE_ALL:
        element_roots = _scene_set_element_roots()
        if not element_roots:
            QtWidgets.QMessageBox.warning(
                maya_main_window(),
                "No Set Elements Found",
                "Could not locate a 'setElements' folder relative to the current scene.\n"
                "Please make sure the scene is saved inside a set element's maya/ folder."
            )
            return

        # Gather current-scene groups (same groups for every element — they share the scene)
        transforms = cmds.ls(type="transform", long=True) or []
        groups_long = [t for t in transforms if is_group_transform(t)]
        if not groups_long:
            cmds.inViewMessage(amg="No groups in scene to export.", pos="topCenter", fade=True)
            return

        exported_count = 0
        skipped_count  = 0

        for elem_root in sorted(element_roots):
            dlg = ShiftExportElementDialog(elem_root, groups_long)
            result = dlg.exec_() if hasattr(dlg, "exec_") else dlg.exec()

            if result == _ELEM_SKIP:
                skipped_count += 1
                continue
            if result == QtWidgets.QDialog.Rejected:   # Cancel All
                break

            # Accepted — export
            chosen = dlg.selected_groups()
            if not chosen:
                skipped_count += 1
                continue

            prev_sel = cmds.ls(sl=True, long=True) or []
            try:
                _execute_shift_export(
                    chosen, dlg.mesh_name(), dlg.destination(),
                    dlg.smooth_enabled(), dlg.smooth_divisions()
                )
                exported_count += 1
            except Exception as e:
                cmds.warning(f"[PhoenixExport] Failed for {os.path.basename(elem_root)}: {e}")
            finally:
                try:
                    cmds.select(prev_sel, r=True) if prev_sel else cmds.select(clear=True)
                except Exception:
                    cmds.select(clear=True)

        if exported_count or skipped_count:
            cmds.inViewMessage(
                amg=f"Export done — {exported_count} exported, {skipped_count} skipped  (scene reverted)",
                pos="topCenter", fade=True, fadeStayTime=3500
            )


@undo_chunk
def action_export_groups(*_):
    scene_path = cmds.file(q=True, sn=True)
    if not scene_path:
        cmds.warning("Please save the scene before exporting.")
        return

    transforms = cmds.ls(type="transform", long=True) or []
    groups_long = [t for t in transforms if is_group_transform(t)]
    if not groups_long:
        cmds.inViewMessage(amg="No groups found to export.", pos="topCenter", fade=True)
        return

    dlg = ExportSetupDialog(groups_long)
    result = dlg.exec_() if hasattr(dlg, "exec_") else dlg.exec()
    if result != QtWidgets.QDialog.Accepted:
        return

    prefix = dlg.prefix()
    blockout = dlg.is_blockout()
    excluded = dlg.excluded_groups_set()
    create_ma = dlg.create_ma_files()
    use_underscore = dlg.use_underscore()
    with_number = dlg.with_number()
    use_obj = dlg.use_obj_folder()
    use_srcimgs = dlg.use_srcimgs_folder()

    base = cmds.fileDialog2(dialogStyle=2, fm=3, caption="Choose Base Export Location")
    if not base:
        return
    base_folder = base[0]

    prev_sel = cmds.ls(sl=True, long=True) or []
    for g_long in groups_long:
        if g_long in excluded:
            continue
        try:
            export_group_to_structure(
                base_folder, prefix, g_long, blockout=blockout,
                use_underscore=use_underscore, with_number=with_number,
                use_obj=use_obj, use_srcimgs=use_srcimgs, create_ma=create_ma
            )
        except Exception as e:
            cmds.warning(f"Failed exporting {g_long.split('|')[-1]}: {e}")

    if prev_sel:
        cmds.select(prev_sel, r=True)
    else:
        cmds.select(clear=True)

    cmds.inViewMessage(amg="Export complete.", pos="topCenter", fade=True)


# -----------------------------
# Duplicate + positionRef
# -----------------------------
@undo_chunk
def action_duplicate_with_position_reference(*_):
    sel = cmds.ls(sl=True, long=True) or []
    if not sel:
        cmds.warning("Select a mesh transform or a group transform first.")
        return

    src = sel[0]
    src_short = src.split("|")[-1]

    dup = cmds.duplicate(src, rr=True)[0]
    dup = cmds.rename(dup, f"{src_short}_dup")
    dup_long = cmds.ls(dup, long=True)[0]

    bb = _world_bbox(dup_long)
    minx, miny, minz, maxx, maxy, maxz = bb
    sx, sy, sz = (maxx - minx), (maxy - miny), (maxz - minz)
    cx, cy, cz = (minx + maxx) * 0.5, (miny + maxy) * 0.5, (minz + maxz) * 0.5

    cube_name = f"{src_short}_positionRef"
    cube = cmds.polyCube(name=cube_name + "#")[0]
    cube_long = cmds.ls(cube, long=True)[0]

    cmds.xform(cube_long, ws=True, t=(cx, cy, cz))
    cmds.xform(
        cube_long, ws=True,
        s=(sx if sx > 1e-6 else 1e-6,
           sy if sy > 1e-6 else 1e-6,
           sz if sz > 1e-6 else 1e-6)
    )

    cmds.delete(cube_long, ch=True)
    cmds.makeIdentity(cube_long, apply=True, t=True, r=True, s=True, n=False)

    pr_grp = _ensure_position_refs_group()
    cube_long = cmds.parent(cube_long, pr_grp)[0]

    cube_bb = _world_bbox(cube_long)
    pivot_world = _bottom_center_from_bb(cube_bb)

    _add_or_set_double_attr(cube_long, "origPivotX", pivot_world[0])
    _add_or_set_double_attr(cube_long, "origPivotY", pivot_world[1])
    _add_or_set_double_attr(cube_long, "origPivotZ", pivot_world[2])

    cmds.xform(cube_long, ws=True, piv=pivot_world)
    cmds.xform(dup_long, ws=True, piv=pivot_world)

    delta_to_origin = [-pivot_world[0], -pivot_world[1], -pivot_world[2]]
    _move_by_delta_world(dup_long, delta_to_origin)
    _move_by_delta_world(cube_long, delta_to_origin)

    cmds.setAttr(f"{cube_long}.visibility", 0)

    cmds.select(dup_long, r=True)
    cmds.inViewMessage(amg="Duplicated + created positionRef (hidden).", pos="topCenter", fade=True)


class PositionRefPicker(QtWidgets.QDialog):
    def __init__(self, ref_nodes_long, parent=maya_main_window()):
        super().__init__(parent)
        self.setWindowTitle("Restore Position — Choose PositionRef")
        self.setObjectName("PhoenixPositionRefPicker")
        self.setWindowFlags(self.windowFlags() ^ QtCore.Qt.WindowContextHelpButtonHint)
        self.setMinimumSize(560, 520)

        self._refs = list(ref_nodes_long)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        row = QtWidgets.QHBoxLayout()
        row.addWidget(QtWidgets.QLabel("Search:"))
        self.search = QtWidgets.QLineEdit()
        self.search.setPlaceholderText("Type to filter...")
        row.addWidget(self.search, 1)
        layout.addLayout(row)

        self.listw = QtWidgets.QListWidget()
        self.listw.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        layout.addWidget(self.listw, 1)

        self.buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        layout.addWidget(self.buttons)

        self._populate()
        self.search.textChanged.connect(self._filter)
        self.buttons.accepted.connect(self._on_ok)
        self.buttons.rejected.connect(self.reject)

    def _populate(self):
        self.listw.clear()
        labeled = []
        for r in self._refs:
            label = r.split("|")[-1]
            labeled.append((label.lower(), label, r))
        for _, label, r in sorted(labeled, key=lambda x: x[0]):
            it = QtWidgets.QListWidgetItem(label)
            it.setToolTip(r)
            it.setData(QtCore.Qt.UserRole, r)
            self.listw.addItem(it)
        if self.listw.count():
            self.listw.setCurrentRow(0)

    def _filter(self, text):
        t = (text or "").strip().lower()
        for i in range(self.listw.count()):
            it = self.listw.item(i)
            r = it.data(QtCore.Qt.UserRole)
            it.setHidden(not (t in it.text().lower() or t in str(r).lower()))

    def _on_ok(self):
        if not self.listw.currentItem():
            QtWidgets.QMessageBox.warning(self, "Pick one", "Select a positionRef to use.")
            return
        self.accept()

    def selected_ref(self):
        it = self.listw.currentItem()
        return it.data(QtCore.Qt.UserRole) if it else None


def _list_position_refs_under_group():
    if not cmds.objExists("positionRefs"):
        return []
    grp = _ensure_position_refs_group()
    kids = cmds.listRelatives(grp, children=True, type="transform", fullPath=True) or []
    return [
        k for k in kids
        if cmds.attributeQuery("origPivotX", node=k, exists=True)
        and cmds.attributeQuery("origPivotY", node=k, exists=True)
        and cmds.attributeQuery("origPivotZ", node=k, exists=True)
    ]


@undo_chunk
def action_restore_position(*_):
    sel = cmds.ls(sl=True, long=True) or []
    if not sel:
        cmds.warning("Select the group/mesh you want to move.")
        return
    move_obj = sel[0]

    refs = _list_position_refs_under_group()
    if not refs:
        cmds.warning("No position refs found under top-level group 'positionRefs'.")
        return

    if len(refs) == 1:
        ref = refs[0]
    else:
        dlg = PositionRefPicker(refs)
        result = dlg.exec_() if hasattr(dlg, "exec_") else dlg.exec()
        if result != QtWidgets.QDialog.Accepted:
            return
        ref = dlg.selected_ref()

    desired = [
        cmds.getAttr(f"{ref}.origPivotX"),
        cmds.getAttr(f"{ref}.origPivotY"),
        cmds.getAttr(f"{ref}.origPivotZ"),
    ]

    bb_obj = _world_bbox(move_obj)
    cur_pivot = _bottom_center_from_bb(bb_obj)
    cmds.xform(move_obj, ws=True, piv=cur_pivot)

    delta = [desired[0] - cur_pivot[0], desired[1] - cur_pivot[1], desired[2] - cur_pivot[2]]
    _move_by_delta_world(move_obj, delta)

    cmds.select(move_obj, r=True)
    cmds.inViewMessage(amg=f"Restored using: {ref.split('|')[-1]}", pos="topCenter", fade=True)


# Duplicate right-click = Restore Position
def action_duplicate_right_click(*_):
    action_restore_position()


# -----------------------------
# Import Blockout (Left click)
# -----------------------------
class ImportBlockoutDialog(QtWidgets.QDialog):
    def __init__(self, obj_paths, parent=maya_main_window()):
        super().__init__(parent)
        self.setWindowTitle("Import Blockout — Choose OBJ / FBX")
        self.setObjectName("PhoenixImportBlockoutDialog")
        self.setWindowFlags(self.windowFlags() ^ QtCore.Qt.WindowContextHelpButtonHint)
        self.setMinimumSize(620, 520)

        self._obj_paths = list(obj_paths)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        row = QtWidgets.QHBoxLayout()
        row.addWidget(QtWidgets.QLabel("Search:"))
        self.search = QtWidgets.QLineEdit()
        self.search.setPlaceholderText("Filter by file/folder name...")
        row.addWidget(self.search, 1)
        layout.addLayout(row)

        self.listw = QtWidgets.QListWidget()
        self.listw.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        layout.addWidget(self.listw, 1)

        self.buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        layout.addWidget(self.buttons)

        self._populate()
        self.search.textChanged.connect(self._filter)
        self.buttons.accepted.connect(self._on_ok)
        self.buttons.rejected.connect(self.reject)

    def _populate(self):
        self.listw.clear()
        labeled = []
        for p in self._obj_paths:
            obj = os.path.basename(p)
            folder = os.path.basename(os.path.dirname(p))
            label = f"{folder} / {obj}"
            labeled.append((label.lower(), label, p))
        for _, label, path in sorted(labeled, key=lambda x: x[0]):
            item = QtWidgets.QListWidgetItem(label)
            item.setToolTip(path)
            item.setData(QtCore.Qt.UserRole, path)
            self.listw.addItem(item)
        if self.listw.count():
            self.listw.setCurrentRow(0)

    def _filter(self, text):
        t = (text or "").strip().lower()
        for i in range(self.listw.count()):
            it = self.listw.item(i)
            p = it.data(QtCore.Qt.UserRole)
            it.setHidden(not (t in it.text().lower() or t in str(p).lower()))

    def _on_ok(self):
        if not self.listw.currentItem():
            QtWidgets.QMessageBox.warning(self, "Select a File", "Please select an OBJ or FBX to import.")
            return
        self.accept()

    def selected_path(self):
        it = self.listw.currentItem()
        return it.data(QtCore.Qt.UserRole) if it else None


def _derive_asset_root_from_scene(scene_path):
    if not scene_path:
        return None
    scene_dir = os.path.dirname(scene_path)
    if os.path.basename(scene_dir).lower() == "maya":
        return os.path.dirname(scene_dir)
    parts = scene_path.replace("/", "\\").split("\\")
    lower = [p.lower() for p in parts]
    if "maya" in lower:
        idx = lower.index("maya")
        if idx > 0:
            return "\\".join(parts[:idx])
    return None


def _find_blockout_objs(asset_root):
    found = []
    for folder_name in ("mod", "obj"):
        search_dir = os.path.join(asset_root, folder_name)
        if not os.path.isdir(search_dir):
            continue
        for entry in os.listdir(search_dir):
            full = os.path.join(search_dir, entry)
            if os.path.isdir(full) and entry.lower().endswith("_blockout"):
                for f in os.listdir(full):
                    if f.lower().endswith(".obj") or f.lower().endswith(".fbx"):
                        found.append(os.path.join(full, f))
    return found


def _import_obj(obj_path):
    before = set(cmds.ls(long=True) or [])
    cmds.file(obj_path, i=True, type="OBJ", ignoreVersion=True, ra=True,
              mergeNamespacesOnClash=False, options="mo=1", pr=True)
    after = set(cmds.ls(long=True) or [])
    new_nodes = list(after - before)

    new_mesh_xforms = []
    for n in new_nodes:
        if cmds.nodeType(n) == "transform" and is_mesh_transform(n):
            new_mesh_xforms.append(n)
    return _top_level_of(new_mesh_xforms)


def _import_fbx(fbx_path):
    if not ensure_fbx_export_plugin():
        cmds.warning("FBX plugin (fbxmaya) could not be loaded.")
        return []

    before = set(cmds.ls(long=True) or [])
    cmds.file(fbx_path, i=True, type="FBX", ignoreVersion=True, ra=True,
              mergeNamespacesOnClash=False, pr=True)
    after = set(cmds.ls(long=True) or [])
    new_nodes = list(after - before)

    new_xforms = []
    for n in new_nodes:
        if cmds.nodeType(n) == "transform":
            new_xforms.append(n)
    return _top_level_of(new_xforms)


@undo_chunk
def action_import_blockout(*_):
    scene_path = cmds.file(q=True, sn=True)
    asset_root = _derive_asset_root_from_scene(scene_path)
    if not asset_root:
        cmds.warning("Could not derive asset root (expected scene inside an asset '/maya' folder).")
        return

    obj_paths = _find_blockout_objs(asset_root)
    if not obj_paths:
        cmds.warning(f"No blockout OBJ/FBX found under: {asset_root}\\(mod|obj)\\*_blockout\\*.obj|*.fbx")
        return

    if len(obj_paths) == 1:
        obj_path = obj_paths[0]
    else:
        dlg = ImportBlockoutDialog(obj_paths)
        result = dlg.exec_() if hasattr(dlg, "exec_") else dlg.exec()
        if result != QtWidgets.QDialog.Accepted:
            return
        obj_path = dlg.selected_path()

    if not obj_path or not os.path.isfile(obj_path):
        cmds.warning("Selected file path is invalid.")
        return

    obj_name = os.path.splitext(os.path.basename(obj_path))[0]
    ext = os.path.splitext(obj_path)[1].lower()
    if ext == ".fbx":
        new_mesh_xforms = _import_fbx(obj_path)
    else:
        new_mesh_xforms = _import_obj(obj_path)
    if not new_mesh_xforms:
        cmds.warning("Imported file, but couldn't detect new mesh transforms to group.")
        return

    grp = cmds.group(new_mesh_xforms, name=obj_name)
    cmds.select(grp, r=True)
    cmds.inViewMessage(amg=f"Imported: {os.path.basename(obj_path)} grouped as '{obj_name}'",
                       pos="topCenter", fade=True)


# -----------------------------
# Right-click Import Blockout
# -----------------------------
def _get_set_root_any(scene_path):
    if not scene_path:
        return None
    parts = scene_path.replace("/", "\\").split("\\")
    lower = [p.lower() for p in parts]

    if "setelements" in lower:
        idx = lower.index("setelements")
        if idx > 0:
            return "\\".join(parts[:idx])

    if "maya" in lower:
        idx = lower.index("maya")
        if idx > 0:
            return "\\".join(parts[:idx])

    return None


def _collect_asset_mod_files(set_root):
    out = {}
    if not set_root:
        return out

    set_elements = os.path.join(set_root, "setElements")
    if not os.path.isdir(set_elements):
        return out

    for asset_folder in sorted(os.listdir(set_elements)):
        asset_path = os.path.join(set_elements, asset_folder)
        if not os.path.isdir(asset_path):
            continue

        folder_map = {}

        # ── maya/ folder → .ma / .mb files ──────────────────────────────
        maya_dir = os.path.join(asset_path, "maya")
        if os.path.isdir(maya_dir):
            try:
                maya_files = []
                for f in sorted(os.listdir(maya_dir)):
                    lf = f.lower()
                    if lf.endswith(".ma") or lf.endswith(".mb"):
                        maya_files.append(os.path.join(maya_dir, f))
                if maya_files:
                    folder_map["maya"] = maya_files
            except Exception:
                pass

        # ── mod/ (or obj/) folder → OBJ / FBX files ─────────────────────
        mod_dir = os.path.join(asset_path, "mod")
        if not os.path.isdir(mod_dir):
            mod_dir = os.path.join(asset_path, "obj")

        if os.path.isdir(mod_dir):
            # *_blockout sub-folders
            try:
                for entry in sorted(os.listdir(mod_dir)):
                    full = os.path.join(mod_dir, entry)
                    if os.path.isdir(full) and entry.lower().endswith("_blockout"):
                        files = []
                        for f in sorted(os.listdir(full)):
                            lf = f.lower()
                            if lf.endswith(".obj") or lf.endswith(".fbx"):
                                files.append(os.path.join(full, f))
                        if files:
                            folder_map[entry] = files
            except Exception:
                pass

            # root mod/ files
            try:
                root_files = []
                for f in sorted(os.listdir(mod_dir)):
                    full = os.path.join(mod_dir, f)
                    lf = f.lower()
                    if os.path.isfile(full) and (lf.endswith(".obj") or lf.endswith(".fbx")):
                        root_files.append(full)
                if root_files:
                    folder_map["mod"] = root_files
            except Exception:
                pass

            # final/ sub-folder
            final_dir = os.path.join(mod_dir, "final")
            if os.path.isdir(final_dir):
                try:
                    final_files = []
                    for f in sorted(os.listdir(final_dir)):
                        full = os.path.join(final_dir, f)
                        lf = f.lower()
                        if os.path.isfile(full) and (lf.endswith(".obj") or lf.endswith(".fbx")):
                            final_files.append(full)
                    if final_files:
                        folder_map["final"] = final_files
                except Exception:
                    pass

        if folder_map:
            out[asset_folder] = folder_map

    return out


class _ModFileItemDelegate(QtWidgets.QStyledItemDelegate):
    def paint(self, painter, option, index):
        super().paint(painter, option, index)
        kind = index.data(QtCore.Qt.UserRole + 1)
        if kind != "file":
            return
        path = index.data(QtCore.Qt.UserRole) or ""
        ext = os.path.splitext(path)[1].upper().lstrip(".")
        if not ext:
            return
        painter.save()
        painter.setPen(QtCore.Qt.gray)
        font = painter.font()
        font.setPointSize(font.pointSize() - 1)
        painter.setFont(font)
        rect = option.rect.adjusted(0, 0, -16, 0)
        painter.drawText(rect, QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter, ext)
        painter.restore()


class ImportAssetModFilesPanel(maya.app.general.mayaMixin.MayaQWidgetDockableMixin, QtWidgets.QWidget):
    WINDOW_NAME = "PhoenixImportAssetModFiles"
    ROLE_PATH = QtCore.Qt.UserRole
    ROLE_KIND = QtCore.Qt.UserRole + 1
    ROLE_ASSET = QtCore.Qt.UserRole + 2
    KIND_HEADER = "header"
    KIND_FILE = "file"
    _instance = None

    def __init__(self, asset_to_folders, parent=None):
        super().__init__(parent)
        self.setObjectName(self.WINDOW_NAME)
        self.setWindowTitle("Import — SetElements Files")
        self._data = asset_to_folders

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(4)

        filter_row = QtWidgets.QHBoxLayout()
        filter_row.setSpacing(6)
        self.cb_ma = QtWidgets.QCheckBox("MA/MB")
        self.cb_obj = QtWidgets.QCheckBox("OBJ")
        self.cb_fbx = QtWidgets.QCheckBox("FBX")
        self.cb_ma.setChecked(True)
        self.cb_obj.setChecked(True)
        self.cb_fbx.setChecked(True)
        self.cb_ma.toggled.connect(self._rebuild)
        self.cb_obj.toggled.connect(self._rebuild)
        self.cb_fbx.toggled.connect(self._rebuild)
        filter_row.addWidget(self.cb_ma)
        filter_row.addWidget(self.cb_obj)
        filter_row.addWidget(self.cb_fbx)
        filter_row.addSpacing(4)
        self.cb_blockouts = QtWidgets.QCheckBox("Blockouts")
        self.cb_blockouts.setChecked(False)
        self.cb_blockouts.toggled.connect(self._rebuild)
        filter_row.addWidget(self.cb_blockouts)
        filter_row.addSpacing(4)
        self.cb_as_ref = QtWidgets.QCheckBox("As Reference")
        self.cb_as_ref.setChecked(True)
        self.cb_as_ref.setToolTip("Import MA/MB files as references (checked) or directly (unchecked)")
        filter_row.addWidget(self.cb_as_ref)
        filter_row.addSpacing(8)
        self.search = QtWidgets.QLineEdit()
        self.search.setPlaceholderText("Search...")
        self.search.textChanged.connect(self._rebuild)
        filter_row.addWidget(self.search, 1)
        root.addLayout(filter_row)

        self.listw = QtWidgets.QListWidget()
        self.listw.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.listw.setItemDelegate(_ModFileItemDelegate(self.listw))
        root.addWidget(self.listw, 1)

        bottom = QtWidgets.QHBoxLayout()
        bottom.setSpacing(6)
        self.btn_select_all = QtWidgets.QPushButton("Select All")
        self.btn_clear = QtWidgets.QPushButton("Clear")
        self.btn_import = QtWidgets.QPushButton("Import Selected")
        self.btn_select_all.clicked.connect(self._select_all_visible)
        self.btn_clear.clicked.connect(self.listw.clearSelection)
        self.btn_import.clicked.connect(self._do_import)
        bottom.addWidget(self.btn_select_all)
        bottom.addWidget(self.btn_clear)
        bottom.addStretch(1)
        bottom.addWidget(self.btn_import)
        root.addLayout(bottom)

        self._rebuild()
        self.search.setFocus()

    def _folder_sort_key(self, folder_label):
        low = folder_label.lower()
        if low == "maya":
            return (0, low)
        if low.endswith("_blockout"):
            return (1, low)
        if low == "mod":
            return (2, low)
        if low == "final":
            return (3, low)
        return (4, low)

    def _want_ext(self, path):
        ext = os.path.splitext(path)[1].lower()
        if ext in (".ma", ".mb"): return self.cb_ma.isChecked()
        if ext == ".obj": return self.cb_obj.isChecked()
        if ext == ".fbx": return self.cb_fbx.isChecked()
        return False

    def _matches_search(self, query, hay):
        return not query or query in hay.lower()

    def _rebuild(self, *_):
        self.listw.clear()
        query = (self.search.text() or "").strip().lower()
        show_blockouts = self.cb_blockouts.isChecked()

        for asset_folder in sorted(self._data.keys(), key=lambda x: x.lower()):
            folder_map = self._data[asset_folder]
            has_visible = False
            for folder_label in folder_map:
                if not show_blockouts and folder_label.lower().endswith("_blockout"):
                    continue
                for p in folder_map[folder_label]:
                    if not os.path.isfile(p): continue
                    if not self._want_ext(p): continue
                    if self._matches_search(query, f"{asset_folder} {folder_label} {os.path.basename(p)} {p}"):
                        has_visible = True
                        break
                if has_visible: break
            if not has_visible:
                continue

            hdr = QtWidgets.QListWidgetItem(f"--{asset_folder}--")
            hdr.setFlags(QtCore.Qt.NoItemFlags)
            hdr.setData(self.ROLE_KIND, self.KIND_HEADER)
            font = hdr.font(); font.setBold(True); hdr.setFont(font)
            hdr.setForeground(QtCore.Qt.gray)
            self.listw.addItem(hdr)

            for folder_label in sorted(folder_map.keys(), key=self._folder_sort_key):
                if not show_blockouts and folder_label.lower().endswith("_blockout"):
                    continue
                paths = [
                    p for p in folder_map[folder_label]
                    if os.path.isfile(p) and self._want_ext(p)
                    and self._matches_search(query, f"{asset_folder} {folder_label} {os.path.basename(p)} {p}")
                ]
                if not paths: continue
                indent = " " * (len(folder_label) + 2)
                for i, p in enumerate(paths):
                    fname = os.path.basename(p)
                    display = f"{folder_label}: {fname}" if i == 0 else f"{indent}{fname}"
                    item = QtWidgets.QListWidgetItem(display)
                    item.setToolTip(p)
                    item.setData(self.ROLE_PATH, p)
                    item.setData(self.ROLE_KIND, self.KIND_FILE)
                    item.setData(self.ROLE_ASSET, asset_folder)
                    self.listw.addItem(item)

            spacer = QtWidgets.QListWidgetItem("")
            spacer.setFlags(QtCore.Qt.NoItemFlags)
            spacer.setData(self.ROLE_KIND, "spacer")
            spacer.setSizeHint(QtCore.QSize(0, 8))
            self.listw.addItem(spacer)

    def _select_all_visible(self):
        self.listw.clearSelection()
        for i in range(self.listw.count()):
            item = self.listw.item(i)
            if item.data(self.ROLE_KIND) == self.KIND_FILE and not item.isHidden():
                item.setSelected(True)

    def selected_paths(self):
        return [it.data(self.ROLE_PATH) for it in self.listw.selectedItems()
                if it.data(self.ROLE_KIND) == self.KIND_FILE and it.data(self.ROLE_PATH)]

    def _do_import(self):
        selected = self.selected_paths()
        if not selected:
            QtWidgets.QMessageBox.warning(self, "Select file(s)", "Please select at least one file.")
            return
        as_ref = self.cb_as_ref.isChecked()
        imported = 0
        for path in selected:
            if not os.path.isfile(path): continue
            ext = os.path.splitext(path)[1].lower()
            base_name = os.path.splitext(os.path.basename(path))[0]
            try:
                if ext in (".ma", ".mb"):
                    if as_ref:
                        namespace = re.sub(r'[^a-zA-Z0-9_]', '_', base_name)
                        cmds.file(path, reference=True, namespace=namespace)
                    else:
                        cmds.file(path, i=True, ignoreVersion=True, ra=True,
                                  mergeNamespacesOnClash=False, pr=True)
                    imported += 1
                elif ext == ".obj":
                    new_mesh = _import_obj(path)
                    if new_mesh:
                        grp = cmds.group(new_mesh, name=base_name)
                        cmds.select(grp, r=True)
                    imported += 1
                elif ext == ".fbx":
                    new_xforms = _import_fbx(path)
                    if new_xforms:
                        grp = cmds.group(new_xforms, name=base_name)
                        cmds.select(grp, r=True)
                    imported += 1
            except Exception as e:
                cmds.warning(f"Failed to import {os.path.basename(path)}: {e}")
        if imported:
            mode = " (as reference)" if as_ref else ""
            cmds.inViewMessage(amg=f"Imported {imported} file(s){mode}.", pos="topCenter", fade=True)

    @classmethod
    def show_panel(cls, asset_to_folders):
        if cls._instance is not None:
            try: cls._instance.close()
            except Exception: pass
            cls._instance = None
        ws_name = cls.WINDOW_NAME + "WorkspaceControl"
        if cmds.workspaceControl(ws_name, q=True, exists=True):
            cmds.deleteUI(ws_name)
        panel = cls(asset_to_folders)
        cls._instance = panel
        panel.show(dockable=True, floating=True, width=700, height=500)


@undo_chunk
def action_import_blockout_right_click(*_):
    scene_path = cmds.file(q=True, sn=True)
    set_root = _get_set_root_any(scene_path)

    # If auto-detection failed OR derived root has no setElements folder, ask the user
    if not set_root or not os.path.isdir(set_root) or \
            not os.path.isdir(os.path.join(set_root, "setElements")):
        folder = cmds.fileDialog2(
            dialogStyle=2, fm=3,
            caption="Select Set Root Folder (the folder containing 'setElements')"
        )
        if not folder:
            return
        set_root = folder[0]

    if not os.path.isdir(set_root):
        cmds.warning("Selected path is not a valid folder.")
        return

    data = _collect_asset_mod_files(set_root)
    if not data:
        cmds.warning(f"No files found under: {os.path.join(set_root, 'setElements')}")
        return
    ImportAssetModFilesPanel.show_panel(data)


# -----------------------------
# PureRef
# -----------------------------
class PureRefPickerDialog(QtWidgets.QDialog):
    def __init__(self, pur_paths, parent=maya_main_window()):
        super().__init__(parent)
        self.setWindowTitle("Open PureRef — Choose File(s)")
        self.setObjectName("PhoenixPureRefPickerDialog")
        self.setWindowFlags(self.windowFlags() ^ QtCore.Qt.WindowContextHelpButtonHint)
        self.setMinimumSize(620, 480)
        self._pur_paths = list(pur_paths)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        row = QtWidgets.QHBoxLayout()
        row.addWidget(QtWidgets.QLabel("Search:"))
        self.search = QtWidgets.QLineEdit()
        self.search.setPlaceholderText("Filter by filename...")
        row.addWidget(self.search, 1)
        layout.addLayout(row)

        self.listw = QtWidgets.QListWidget()
        self.listw.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        layout.addWidget(self.listw, 1)

        btn_row = QtWidgets.QHBoxLayout()
        self.btn_select_all = QtWidgets.QPushButton("Select All")
        self.btn_clear = QtWidgets.QPushButton("Clear Selection")
        btn_row.addWidget(self.btn_select_all)
        btn_row.addWidget(self.btn_clear)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        self.buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        layout.addWidget(self.buttons)

        self._populate()
        self.search.textChanged.connect(self._filter)
        self.btn_select_all.clicked.connect(self._select_all)
        self.btn_clear.clicked.connect(self.listw.clearSelection)
        self.buttons.accepted.connect(self._on_ok)
        self.buttons.rejected.connect(self.reject)

    def _populate(self):
        self.listw.clear()
        labeled = []
        for p in self._pur_paths:
            filename = os.path.basename(p)
            folder = os.path.basename(os.path.dirname(p))
            label = f"{folder} / {filename}"
            labeled.append((label.lower(), label, p))
        for _, label, path in sorted(labeled, key=lambda x: x[0]):
            item = QtWidgets.QListWidgetItem(label)
            item.setToolTip(path)
            item.setData(QtCore.Qt.UserRole, path)
            self.listw.addItem(item)
        if self.listw.count():
            self.listw.setCurrentRow(0)

    def _filter(self, text):
        t = (text or "").strip().lower()
        for i in range(self.listw.count()):
            it = self.listw.item(i)
            p = it.data(QtCore.Qt.UserRole)
            it.setHidden(not (t in it.text().lower() or t in str(p).lower()))

    def _select_all(self):
        self.listw.clearSelection()
        for i in range(self.listw.count()):
            item = self.listw.item(i)
            if not item.isHidden():
                item.setSelected(True)

    def _on_ok(self):
        if not self.listw.selectedItems():
            QtWidgets.QMessageBox.warning(self, "Select a file", "Please select at least one PureRef file.")
            return
        self.accept()

    def selected_paths(self):
        return [item.data(QtCore.Qt.UserRole) for item in self.listw.selectedItems()]


def _find_pureref_files(folder):
    if not folder or not os.path.isdir(folder):
        return []
    return [os.path.join(folder, f) for f in os.listdir(folder) if f.lower().endswith(".pur")]


def _get_set_root_from_scene(scene_path):
    if not scene_path: return None
    parts = scene_path.replace("/", "\\").split("\\")
    lower = [p.lower() for p in parts]
    if "setelements" in lower:
        idx = lower.index("setelements")
        if idx > 0:
            return "\\".join(parts[:idx])
    return None


def _get_asset_root_from_scene(scene_path):
    if not scene_path: return None
    scene_dir = os.path.dirname(scene_path)
    if os.path.basename(scene_dir).lower() == "maya":
        return os.path.dirname(scene_dir)
    parts = scene_path.replace("/", "\\").split("\\")
    lower = [p.lower() for p in parts]
    if "maya" in lower:
        idx = lower.index("maya")
        if idx > 0:
            return "\\".join(parts[:idx])
    return None


def _open_pureref_files(pur_paths):
    for p in pur_paths:
        if os.path.isfile(p):
            try: os.startfile(p)
            except Exception as e: cmds.warning(f"Failed to open {p}: {e}")


def action_open_pureref_set_level(*_):
    scene_path = cmds.file(q=True, sn=True)
    set_root = _get_set_root_from_scene(scene_path)
    if not set_root:
        cmds.warning("Could not derive set root folder from scene path.")
        return
    ref_folder = os.path.join(set_root, "ref")
    pur_files = _find_pureref_files(ref_folder)
    if not pur_files:
        cmds.warning(f"No PureRef files found in: {ref_folder}")
        return
    if len(pur_files) == 1:
        _open_pureref_files(pur_files)
        cmds.inViewMessage(amg=f"Opened: {os.path.basename(pur_files[0])}", pos="topCenter", fade=True)
    else:
        dlg = PureRefPickerDialog(pur_files)
        result = dlg.exec_() if hasattr(dlg, "exec_") else dlg.exec()
        if result == QtWidgets.QDialog.Accepted:
            selected = dlg.selected_paths()
            _open_pureref_files(selected)
            cmds.inViewMessage(amg=f"Opened {len(selected)} PureRef file(s)", pos="topCenter", fade=True)


def action_open_pureref_asset_level(*_):
    scene_path = cmds.file(q=True, sn=True)
    asset_root = _get_asset_root_from_scene(scene_path)
    if not asset_root:
        cmds.warning("Could not derive asset root folder from scene path.")
        return
    ref_folder = os.path.join(asset_root, "ref")
    pur_files = _find_pureref_files(ref_folder)
    if not pur_files:
        set_root = _get_set_root_from_scene(scene_path)
        if set_root:
            set_ref = os.path.join(set_root, "ref")
            pur_files = _find_pureref_files(set_ref)
            if pur_files:
                cmds.warning(f"No PureRef in asset ref folder, using set-level: {set_ref}")
    if not pur_files:
        cmds.warning("No PureRef files found in asset or set ref folders.")
        return
    if len(pur_files) == 1:
        _open_pureref_files(pur_files)
        cmds.inViewMessage(amg=f"Opened: {os.path.basename(pur_files[0])}", pos="topCenter", fade=True)
    else:
        dlg = PureRefPickerDialog(pur_files)
        result = dlg.exec_() if hasattr(dlg, "exec_") else dlg.exec()
        if result == QtWidgets.QDialog.Accepted:
            selected = dlg.selected_paths()
            _open_pureref_files(selected)
            cmds.inViewMessage(amg=f"Opened {len(selected)} PureRef file(s)", pos="topCenter", fade=True)


# -----------------------------
# Import Set Elements (Shift+Click on Import Blockout)
# -----------------------------
def _is_scene_in_main_maya_folder(scene_path):
    if not scene_path: return False
    parts = scene_path.replace("/", "\\").split("\\")
    lower = [p.lower() for p in parts]
    if "setelements" in lower: return False
    if len(parts) >= 2:
        return parts[-2].lower() == "maya"
    return False


def _get_set_root_from_main_maya(scene_path):
    if not scene_path: return None
    parts = scene_path.replace("/", "\\").split("\\")
    lower = [p.lower() for p in parts]
    if "maya" in lower:
        idx = lower.index("maya")
        if idx > 0:
            return "\\".join(parts[:idx])
    return None


def _simplify_set_element_name(filename, folder_name):
    name_no_ext, ext = os.path.splitext(filename)
    folder_parts = folder_name.split("_")
    if len(folder_parts) > 1:
        unique_id = folder_parts[-1]
        common_prefix = "_".join(folder_parts[:-1])
        patterns = [
            f"prj_props_{common_prefix}_", f"prj_props_{folder_name}_",
            f"{common_prefix}_", f"{folder_name}_",
        ]
        for pattern in patterns:
            if name_no_ext.startswith(pattern):
                remainder = name_no_ext[len(pattern):]
                if remainder: return remainder + ext
            if name_no_ext.lower().startswith(pattern.lower()):
                remainder = name_no_ext[len(pattern):]
                if remainder: return remainder + ext
        if unique_id in name_no_ext:
            idx = name_no_ext.find(unique_id)
            return name_no_ext[idx:] + ext
    return filename


def _find_set_elements_for_import(set_root):
    if not set_root: return []
    set_elements_folder = os.path.join(set_root, "setElements")
    if not os.path.isdir(set_elements_folder): return []
    results = []
    for entry in os.listdir(set_elements_folder):
        asset_folder = os.path.join(set_elements_folder, entry)
        if not os.path.isdir(asset_folder): continue
        maya_folder = os.path.join(asset_folder, "maya")
        if not os.path.isdir(maya_folder): continue
        for f in os.listdir(maya_folder):
            if f.lower().endswith(".ma") or f.lower().endswith(".mb"):
                full_path = os.path.join(maya_folder, f)
                simplified = _simplify_set_element_name(f, entry)
                display = f"{entry} / {simplified}"
                results.append((full_path, display, entry))
    return results


class ImportSetElementsDialog(QtWidgets.QDialog):
    def __init__(self, element_data, parent=maya_main_window()):
        super().__init__(parent)
        self.setWindowTitle("Import Set Elements")
        self.setObjectName("PhoenixImportSetElementsDialog")
        self.setWindowFlags(self.windowFlags() ^ QtCore.Qt.WindowContextHelpButtonHint)
        self.setMinimumSize(700, 580)
        self._element_data = list(element_data)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        options_row = QtWidgets.QHBoxLayout()
        self.as_reference_cb = QtWidgets.QCheckBox("Import as Reference")
        self.as_reference_cb.setChecked(True)
        options_row.addWidget(self.as_reference_cb)
        options_row.addStretch(1)
        layout.addLayout(options_row)

        search_row = QtWidgets.QHBoxLayout()
        search_row.addWidget(QtWidgets.QLabel("Search:"))
        self.search = QtWidgets.QLineEdit()
        self.search.setPlaceholderText("Filter by filename or folder...")
        search_row.addWidget(self.search, 1)
        layout.addLayout(search_row)

        self.listw = QtWidgets.QListWidget()
        self.listw.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        layout.addWidget(self.listw, 1)

        btn_row = QtWidgets.QHBoxLayout()
        self.btn_select_all = QtWidgets.QPushButton("Select All")
        self.btn_clear = QtWidgets.QPushButton("Clear Selection")
        btn_row.addWidget(self.btn_select_all)
        btn_row.addWidget(self.btn_clear)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        hint = QtWidgets.QLabel("Select files to import. Use Ctrl+Click for multi-select.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #666;")
        layout.addWidget(hint)

        self.buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        layout.addWidget(self.buttons)

        self._populate()
        self.search.textChanged.connect(self._filter)
        self.btn_select_all.clicked.connect(self._select_all)
        self.btn_clear.clicked.connect(self.listw.clearSelection)
        self.buttons.accepted.connect(self._on_ok)
        self.buttons.rejected.connect(self.reject)
        self.search.setFocus()

    def _populate(self):
        self.listw.clear()
        sorted_data = sorted(self._element_data, key=lambda x: (x[2].lower(), x[1].lower()))
        for path, display, folder in sorted_data:
            item = QtWidgets.QListWidgetItem(display)
            item.setToolTip(path)
            item.setData(QtCore.Qt.UserRole, path)
            self.listw.addItem(item)

    def _filter(self, text):
        t = (text or "").strip().lower()
        for i in range(self.listw.count()):
            it = self.listw.item(i)
            p = it.data(QtCore.Qt.UserRole)
            it.setHidden(not (t in it.text().lower() or t in str(p).lower()))

    def _select_all(self):
        self.listw.clearSelection()
        for i in range(self.listw.count()):
            item = self.listw.item(i)
            if not item.isHidden():
                item.setSelected(True)

    def _on_ok(self):
        if not self.listw.selectedItems():
            QtWidgets.QMessageBox.warning(self, "Select files", "Please select at least one file to import.")
            return
        self.accept()

    def import_as_reference(self): return self.as_reference_cb.isChecked()
    def selected_paths(self): return [item.data(QtCore.Qt.UserRole) for item in self.listw.selectedItems()]


@undo_chunk
def action_import_set_elements(*_):
    scene_path = cmds.file(q=True, sn=True)
    set_root = _get_set_root_any(scene_path)

    if not set_root or not os.path.isdir(set_root) or \
            not os.path.isdir(os.path.join(set_root, "setElements")):
        folder = cmds.fileDialog2(
            dialogStyle=2, fm=3,
            caption="Select Set Root Folder (the folder containing 'setElements')"
        )
        if not folder:
            return
        set_root = folder[0]

    element_data = _find_set_elements_for_import(set_root)
    if not element_data:
        cmds.warning(f"No Maya files found in: {os.path.join(set_root, 'setElements')}")
        return

    dlg = ImportSetElementsDialog(element_data)
    result = dlg.exec_() if hasattr(dlg, "exec_") else dlg.exec()
    if result != QtWidgets.QDialog.Accepted: return

    selected_paths = dlg.selected_paths()
    as_reference = dlg.import_as_reference()
    if not selected_paths: return

    imported_count = 0
    for path in selected_paths:
        if not os.path.isfile(path):
            cmds.warning(f"File not found: {path}")
            continue
        try:
            if as_reference:
                namespace = re.sub(r'[^a-zA-Z0-9_]', '_', os.path.splitext(os.path.basename(path))[0])
                cmds.file(path, reference=True, namespace=namespace)
            else:
                cmds.file(path, i=True, ignoreVersion=True, ra=True, mergeNamespacesOnClash=False, pr=True)
            imported_count += 1
        except Exception as e:
            cmds.warning(f"Failed to import {os.path.basename(path)}: {e}")

    mode = "as references" if as_reference else "directly"
    cmds.inViewMessage(amg=f"Imported {imported_count} file(s) {mode}.", pos="topCenter", fade=True)


# -----------------------------
# Save Set Element
# -----------------------------
def _derive_set_element_filename_from_maya_folder(maya_folder):
    asset_name = os.path.basename(os.path.dirname(maya_folder.rstrip("\\/")))
    asset_name = safe_fs_name(asset_name)
    return f"prj_props_{asset_name}_mod_001_v001_v001".replace("_v001_v001", "_v001")


@undo_chunk
def action_save_set_element(*_):
    folder = cmds.fileDialog2(dialogStyle=2, fm=3, caption="Choose 'maya' folder to save into")
    if not folder: return
    maya_folder = folder[0]
    if not os.path.isdir(maya_folder):
        cmds.warning("Invalid folder selected.")
        return
    filename = _derive_set_element_filename_from_maya_folder(maya_folder)
    fullpath = os.path.join(maya_folder, filename + ".ma")
    os.makedirs(maya_folder, exist_ok=True)
    try:
        cmds.file(rename=fullpath)
        cmds.file(save=True, type="mayaAscii")
        cmds.inViewMessage(amg=f"Saved: {filename}.ma", pos="topCenter", fade=True)
    except Exception as e:
        cmds.warning(f"Save failed: {e}")


# -----------------------------
# Set Element Switcher (Right-click on Save)
# -----------------------------
def _get_set_elements_folder_from_scene(scene_path):
    if not scene_path: return None
    parts = scene_path.replace("/", "\\").split("\\")
    lower = [p.lower() for p in parts]
    if "setelements" in lower:
        idx = lower.index("setelements")
        return "\\".join(parts[:idx + 1])
    return None


def _get_set_root_folder_from_scene(scene_path):
    if not scene_path: return None
    parts = scene_path.replace("/", "\\").split("\\")
    lower = [p.lower() for p in parts]
    if "setelements" in lower:
        idx = lower.index("setelements")
        if idx > 0:
            return "\\".join(parts[:idx])
    return None


def _find_all_set_element_maya_files(set_elements_folder):
    if not set_elements_folder or not os.path.isdir(set_elements_folder): return []
    ma_files = []
    for entry in os.listdir(set_elements_folder):
        asset_folder = os.path.join(set_elements_folder, entry)
        if not os.path.isdir(asset_folder): continue
        maya_folder = os.path.join(asset_folder, "maya")
        if not os.path.isdir(maya_folder): continue
        for f in os.listdir(maya_folder):
            if f.lower().endswith(".ma") or f.lower().endswith(".mb"):
                ma_files.append(os.path.join(maya_folder, f))
    return ma_files


def _find_main_maya_files(set_root_folder):
    if not set_root_folder: return []
    maya_folder = os.path.join(set_root_folder, "maya")
    if not os.path.isdir(maya_folder): return []
    return [os.path.join(maya_folder, f) for f in os.listdir(maya_folder)
            if f.lower().endswith(".ma") or f.lower().endswith(".mb")]


def _find_blockout_maya_files(set_root_folder):
    if not set_root_folder: return []
    blockout_folder = os.path.join(set_root_folder, "maya", "blockout")
    if not os.path.isdir(blockout_folder): return []
    return [os.path.join(blockout_folder, f) for f in os.listdir(blockout_folder)
            if f.lower().endswith(".ma") or f.lower().endswith(".mb")]


class SetElementSwitcherDialog(QtWidgets.QDialog):
    SECTION_MAIN = "main"
    SECTION_BLOCKOUT = "blockout"
    SECTION_ELEMENTS = "elements"

    def __init__(self, main_files, blockout_files, element_files, current_file, parent=maya_main_window()):
        super().__init__(parent)
        self.setWindowTitle("Switch Set Element")
        self.setObjectName("PhoenixSetElementSwitcherDialog")
        self.setWindowFlags(self.windowFlags() ^ QtCore.Qt.WindowContextHelpButtonHint)
        self.setMinimumSize(700, 580)

        self._main_files = list(main_files)
        self._blockout_files = list(blockout_files)
        self._element_files = list(element_files)
        self._current_file = current_file

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        current_label = QtWidgets.QLabel(f"Current: {os.path.basename(current_file) if current_file else 'Untitled'}")
        current_label.setToolTip(current_file or "")
        current_label.setStyleSheet("color: #888; font-style: italic;")
        layout.addWidget(current_label)

        options_row = QtWidgets.QHBoxLayout()
        self.include_blockout_cb = QtWidgets.QCheckBox("Include Blockouts")
        self.include_blockout_cb.setChecked(False)
        self.include_blockout_cb.toggled.connect(self._populate)
        options_row.addWidget(self.include_blockout_cb)
        options_row.addStretch(1)
        layout.addLayout(options_row)

        search_row = QtWidgets.QHBoxLayout()
        search_row.addWidget(QtWidgets.QLabel("Search:"))
        self.search = QtWidgets.QLineEdit()
        self.search.setPlaceholderText("Filter by filename or folder...")
        search_row.addWidget(self.search, 1)
        layout.addLayout(search_row)

        self.listw = QtWidgets.QListWidget()
        self.listw.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        layout.addWidget(self.listw, 1)

        hint = QtWidgets.QLabel("Select a file and press Enter (or OK) to save current and open selected.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #666;")
        layout.addWidget(hint)

        self.buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        layout.addWidget(self.buttons)

        self._populate()
        self.search.textChanged.connect(self._filter)
        self.listw.itemDoubleClicked.connect(self._on_double_click)
        self.buttons.accepted.connect(self._on_ok)
        self.buttons.rejected.connect(self.reject)
        self.search.setFocus()

    def _is_current(self, path):
        if not self._current_file: return False
        return os.path.normcase(os.path.normpath(path)) == os.path.normcase(os.path.normpath(self._current_file))

    def _add_section_header(self, title):
        item = QtWidgets.QListWidgetItem(title)
        item.setFlags(QtCore.Qt.NoItemFlags)
        item.setData(QtCore.Qt.UserRole, None)
        item.setData(QtCore.Qt.UserRole + 1, "header")
        font = item.font(); font.setBold(True); item.setFont(font)
        item.setForeground(QtCore.Qt.gray)
        self.listw.addItem(item)

    def _add_file_item(self, path, display_name, section):
        is_current = self._is_current(path)
        item = QtWidgets.QListWidgetItem(f"  {display_name}" if is_current else f"   {display_name}")
        item.setToolTip(path)
        item.setData(QtCore.Qt.UserRole, path)
        item.setData(QtCore.Qt.UserRole + 1, section)
        if is_current:
            item.setForeground(QtCore.Qt.gray)
        self.listw.addItem(item)

    def _populate(self):
        self.listw.clear()
        include_blockout = self.include_blockout_cb.isChecked()
        first_selectable_row = None

        if self._main_files:
            self._add_section_header("Main File")
            for p in sorted(self._main_files, key=lambda x: os.path.basename(x).lower()):
                self._add_file_item(p, os.path.basename(p), self.SECTION_MAIN)
                if first_selectable_row is None and not self._is_current(p):
                    first_selectable_row = self.listw.count() - 1

        if include_blockout and self._blockout_files:
            self._add_section_header("Blockouts")
            for p in sorted(self._blockout_files, key=lambda x: os.path.basename(x).lower()):
                self._add_file_item(p, os.path.basename(p), self.SECTION_BLOCKOUT)
                if first_selectable_row is None and not self._is_current(p):
                    first_selectable_row = self.listw.count() - 1

        if self._element_files:
            self._add_section_header("Set Elements")
            sorted_elements = sorted(
                self._element_files,
                key=lambda x: (os.path.basename(os.path.dirname(os.path.dirname(x))).lower(),
                               os.path.basename(x).lower())
            )
            for p in sorted_elements:
                filename = os.path.basename(p)
                asset_folder = os.path.basename(os.path.dirname(os.path.dirname(p)))
                simplified_name = _simplify_set_element_name(filename, asset_folder)
                self._add_file_item(p, f"{asset_folder} / {simplified_name}", self.SECTION_ELEMENTS)
                if first_selectable_row is None and not self._is_current(p):
                    first_selectable_row = self.listw.count() - 1

        if first_selectable_row is not None:
            self.listw.setCurrentRow(first_selectable_row)

    def _filter(self, text):
        t = (text or "").strip().lower()
        section_has_visible = {self.SECTION_MAIN: False, self.SECTION_BLOCKOUT: False, self.SECTION_ELEMENTS: False}
        header_rows = {}
        for i in range(self.listw.count()):
            it = self.listw.item(i)
            section = it.data(QtCore.Qt.UserRole + 1)
            if section == "header":
                header_text = it.text().lower()
                if "main" in header_text: header_rows[self.SECTION_MAIN] = i
                elif "blockout" in header_text: header_rows[self.SECTION_BLOCKOUT] = i
                elif "element" in header_text: header_rows[self.SECTION_ELEMENTS] = i
                continue
            p = it.data(QtCore.Qt.UserRole)
            matches = not t or (t in it.text().lower() or t in str(p).lower())
            it.setHidden(not matches)
            if matches and section in section_has_visible:
                section_has_visible[section] = True
        for section, row in header_rows.items():
            self.listw.item(row).setHidden(not section_has_visible.get(section, False))

    def _on_double_click(self, item):
        if item.data(QtCore.Qt.UserRole + 1) == "header": return
        self._on_ok()

    def _on_ok(self):
        current = self.listw.currentItem()
        if not current or current.data(QtCore.Qt.UserRole + 1) == "header":
            QtWidgets.QMessageBox.warning(self, "Select a file", "Please select a Maya file to open.")
            return
        self.accept()

    def keyPressEvent(self, event):
        if event.key() in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter):
            current = self.listw.currentItem()
            if current and current.data(QtCore.Qt.UserRole + 1) != "header":
                self._on_ok(); return
        super().keyPressEvent(event)

    def selected_path(self):
        it = self.listw.currentItem()
        if it and it.data(QtCore.Qt.UserRole + 1) != "header":
            return it.data(QtCore.Qt.UserRole)
        return None



# ============================================================
# FILE NAVIGATION  (Prev / Next / Main)
# ============================================================

def _get_ordered_set_files(set_root_folder):
    """
    Return (main_files, element_files) where:
      main_files    = sorted .ma/.mb from <set_root>/maya/  (excludes blockout/)
      element_files = sorted .ma/.mb from <set_root>/setElements/*/maya/
    Both lists are sorted alphabetically for consistent ordering.
    """
    # Main files (top-level maya folder only, not blockout subfolder)
    main_files = []
    maya_dir = os.path.join(set_root_folder, "maya")
    if os.path.isdir(maya_dir):
        for f in sorted(os.listdir(maya_dir)):
            if f.lower().endswith((".ma", ".mb")):
                main_files.append(os.path.join(maya_dir, f))

    # Element files
    element_files = []
    se_dir = os.path.join(set_root_folder, "setElements")
    if os.path.isdir(se_dir):
        for entry in sorted(os.listdir(se_dir)):
            asset_path = os.path.join(se_dir, entry)
            if not os.path.isdir(asset_path):
                continue
            asset_maya = os.path.join(asset_path, "maya")
            if not os.path.isdir(asset_maya):
                continue
            for f in sorted(os.listdir(asset_maya)):
                if f.lower().endswith((".ma", ".mb")):
                    element_files.append(os.path.join(asset_maya, f))

    return main_files, element_files


def _norm(p):
    return os.path.normcase(os.path.normpath(p))


def _is_main_file(scene_path, main_files):
    n = _norm(scene_path)
    return any(_norm(m) == n for m in main_files)


def _save_and_open(target_path):
    """Save current scene (if saved before) then open target."""
    scene_path = cmds.file(q=True, sn=True)
    if scene_path:
        try:
            cmds.file(save=True)
        except Exception as e:
            result = QtWidgets.QMessageBox.question(
                maya_main_window(), "Save Failed",
                f"Could not save current file:\n{e}\n\nOpen anyway?",
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
            )
            if result != QtWidgets.QMessageBox.Yes:
                return
    try:
        cmds.file(target_path, open=True, force=True)
        cmds.inViewMessage(
            amg=f"Opened: {os.path.basename(target_path)}",
            pos="topCenter", fade=True
        )
    except Exception as e:
        cmds.warning(f"Failed to open {os.path.basename(target_path)}: {e}")


def _resolve_set_root_for_nav():
    """
    Return set_root_folder or None.
    Tries auto-detection first; falls back to folder picker.
    """
    scene_path = cmds.file(q=True, sn=True)
    set_root = _get_set_root_any(scene_path)
    if set_root and os.path.isdir(set_root):
        return set_root
    # Fallback picker
    folder = cmds.fileDialog2(
        dialogStyle=2, fm=3,
        caption="Select Set Root Folder (containing 'maya' and 'setElements')"
    )
    if not folder:
        return None
    return folder[0]


def action_nav_main(*_):
    """Switch to the first main maya file."""
    set_root = _resolve_set_root_for_nav()
    if not set_root:
        return
    main_files, _ = _get_ordered_set_files(set_root)
    if not main_files:
        cmds.warning("No main Maya files found.")
        return
    # If already on a main file, stay (or go to first if multiple)
    scene_path = cmds.file(q=True, sn=True)
    if scene_path and _is_main_file(scene_path, main_files):
        cmds.inViewMessage(amg="Already on main file.", pos="topCenter", fade=True)
        return
    _save_and_open(main_files[0])


def action_nav_next(*_):
    """
    If on a main file  → open first element file.
    If on an element file → open next element file (wraps to first).
    If on nothing known → open first element file.
    """
    set_root = _resolve_set_root_for_nav()
    if not set_root:
        return
    main_files, element_files = _get_ordered_set_files(set_root)
    if not element_files:
        cmds.warning("No set element Maya files found.")
        return

    scene_path = cmds.file(q=True, sn=True)
    norm_scene = _norm(scene_path) if scene_path else ""

    if _is_main_file(scene_path, main_files):
        # On main → go to first element
        target = element_files[0]
    else:
        # Find current in element list
        idx = next((i for i, p in enumerate(element_files) if _norm(p) == norm_scene), None)
        if idx is None:
            target = element_files[0]
        else:
            target = element_files[(idx + 1) % len(element_files)]

    if _norm(target) == norm_scene:
        cmds.inViewMessage(amg="Already on this file.", pos="topCenter", fade=True)
        return
    _save_and_open(target)


def action_nav_prev(*_):
    """
    If on a main file  → open last element file.
    If on an element file → open previous element file (wraps to last).
    If on nothing known → open last element file.
    """
    set_root = _resolve_set_root_for_nav()
    if not set_root:
        return
    main_files, element_files = _get_ordered_set_files(set_root)
    if not element_files:
        cmds.warning("No set element Maya files found.")
        return

    scene_path = cmds.file(q=True, sn=True)
    norm_scene = _norm(scene_path) if scene_path else ""

    if _is_main_file(scene_path, main_files):
        # On main → go to last element
        target = element_files[-1]
    else:
        idx = next((i for i, p in enumerate(element_files) if _norm(p) == norm_scene), None)
        if idx is None:
            target = element_files[-1]
        else:
            target = element_files[(idx - 1) % len(element_files)]

    if _norm(target) == norm_scene:
        cmds.inViewMessage(amg="Already on this file.", pos="topCenter", fade=True)
        return
    _save_and_open(target)


def action_switch_set_element(*_):
    scene_path = cmds.file(q=True, sn=True)

    # Derive set root from scene path (works from main maya/ or setElements/*/maya/)
    set_root_folder = _get_set_root_any(scene_path)

    # If that failed or folder doesn't exist, ask the user to pick it
    if not set_root_folder or not os.path.isdir(set_root_folder):
        folder = cmds.fileDialog2(
            dialogStyle=2, fm=3,
            caption="Select Set Root Folder (the folder containing 'maya' and 'setElements')"
        )
        if not folder:
            return
        set_root_folder = folder[0]

    set_elements_folder = os.path.join(set_root_folder, "setElements")
    if not os.path.isdir(set_elements_folder):
        set_elements_folder = None

    main_files = _find_main_maya_files(set_root_folder)
    blockout_files = _find_blockout_maya_files(set_root_folder)
    element_files = _find_all_set_element_maya_files(set_elements_folder) if set_elements_folder else []

    if not main_files and not blockout_files and not element_files:
        cmds.warning("No Maya files found in the set folder structure.")
        return

    dlg = SetElementSwitcherDialog(main_files, blockout_files, element_files, scene_path)
    result = dlg.exec_() if hasattr(dlg, "exec_") else dlg.exec()
    if result != QtWidgets.QDialog.Accepted: return

    selected_path = dlg.selected_path()
    if not selected_path or not os.path.isfile(selected_path):
        cmds.warning("Selected file is invalid.")
        return

    if scene_path and os.path.normcase(os.path.normpath(selected_path)) == os.path.normcase(os.path.normpath(scene_path)):
        cmds.inViewMessage(amg="Already in this file.", pos="topCenter", fade=True)
        return

    if scene_path:
        try:
            cmds.file(save=True)
            cmds.inViewMessage(amg=f"Saved: {os.path.basename(scene_path)}", pos="topCenter", fade=True)
        except Exception as e:
            result2 = QtWidgets.QMessageBox.question(
                maya_main_window(), "Save Failed",
                f"Failed to save current file: {e}\n\nOpen selected file anyway?",
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
            )
            if result2 != QtWidgets.QMessageBox.Yes: return

    try:
        cmds.file(selected_path, open=True, force=True)
        cmds.inViewMessage(amg=f"Opened: {os.path.basename(selected_path)}", pos="topCenter", fade=True)
    except Exception as e:
        cmds.warning(f"Failed to open file: {e}")


# ============================================================
# CLEAN UP BUTTON  (replaces Restore)
# ============================================================

DEFAULT_CAMERAS = {"persp", "top", "front", "side", "perspShape", "topShape", "frontShape", "sideShape"}
POSITION_REFS_GROUP = "positionRefs"


def _get_world_top_level_objects():
    """Return all transforms directly parented to world."""
    all_t = cmds.ls(type="transform", long=True) or []
    return [t for t in all_t if not (cmds.listRelatives(t, parent=True, fullPath=True) or [])]


def _is_default_camera(node_long):
    short = node_long.lstrip("|").split("|")[0]
    return short in DEFAULT_CAMERAS


def _collect_world_children_info():
    """Return list of (long_name, short_name, node_type, is_camera) for world children."""
    top = _get_world_top_level_objects()
    result = []
    for t in top:
        short = t.split("|")[-1]
        shapes = cmds.listRelatives(t, shapes=True, fullPath=True) or []
        node_type = "camera" if any(cmds.nodeType(s) == "camera" for s in shapes) else cmds.nodeType(t)
        is_default_cam = short in DEFAULT_CAMERAS
        result.append((t, short, node_type, is_default_cam))
    return result


# ------ Manual Clean Up Dialog ------

class ManualCleanupDialog(QtWidgets.QDialog):
    """
    Shows all world-level objects for one file.
    User selects what to KEEP, then clicks 'Keep & Next'.
    positionRefs is auto-selected for deletion (not pre-selected in keep list).
    """
    def __init__(self, file_path, objects_info, file_index, total_files, parent=maya_main_window()):
        super().__init__(parent)
        self.setWindowTitle(f"Manual Clean Up  [{file_index}/{total_files}]")
        self.setObjectName("PhoenixManualCleanupDialog")
        self.setWindowFlags(self.windowFlags() ^ QtCore.Qt.WindowContextHelpButtonHint)
        self.setMinimumSize(680, 560)

        self._objects_info = list(objects_info)
        self._result = None  # "keep_and_next" | "skip" | "stop"

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        file_label = QtWidgets.QLabel(f"File: <b>{os.path.basename(file_path)}</b>")
        file_label.setToolTip(file_path)
        file_label.setWordWrap(True)
        layout.addWidget(file_label)

        hint = QtWidgets.QLabel(
            "Select objects to <b>KEEP</b>. Everything else (except default cameras) will be deleted.\n"
            "<i>positionRefs</i> is NOT pre-selected (will be deleted by default)."
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        search_row = QtWidgets.QHBoxLayout()
        search_row.addWidget(QtWidgets.QLabel("Search:"))
        self.search = QtWidgets.QLineEdit()
        self.search.setPlaceholderText("Filter objects...")
        search_row.addWidget(self.search, 1)
        layout.addLayout(search_row)

        self.listw = QtWidgets.QListWidget()
        self.listw.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        layout.addWidget(self.listw, 1)

        btn_row = QtWidgets.QHBoxLayout()
        self.btn_sel_all = QtWidgets.QPushButton("Select All")
        self.btn_clear = QtWidgets.QPushButton("Clear")
        btn_row.addWidget(self.btn_sel_all)
        btn_row.addWidget(self.btn_clear)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        action_row = QtWidgets.QHBoxLayout()
        self.btn_keep_next = QtWidgets.QPushButton("Keep Selected & Proceed")
        self.btn_keep_next.setMinimumHeight(38)
        self.btn_skip = QtWidgets.QPushButton("Skip (no changes)")
        self.btn_stop = QtWidgets.QPushButton("Stop Clean Up")
        self.btn_stop.setStyleSheet("color: #c44;")
        action_row.addWidget(self.btn_keep_next, 2)
        action_row.addWidget(self.btn_skip)
        action_row.addWidget(self.btn_stop)
        layout.addLayout(action_row)

        self._populate()
        self.search.textChanged.connect(self._filter)
        self.btn_sel_all.clicked.connect(self._select_all)
        self.btn_clear.clicked.connect(self.listw.clearSelection)
        self.btn_keep_next.clicked.connect(self._on_keep)
        self.btn_skip.clicked.connect(self._on_skip)
        self.btn_stop.clicked.connect(self._on_stop)

    def _populate(self):
        self.listw.clear()
        for long_name, short_name, node_type, is_default_cam in self._objects_info:
            if is_default_cam:
                continue  # don't show default cameras, they're always kept

            label = f"{short_name}  [{node_type}]"
            item = QtWidgets.QListWidgetItem(label)
            item.setToolTip(long_name)
            item.setData(QtCore.Qt.UserRole, long_name)

            # Auto-select everything except positionRefs for keeping
            if short_name != POSITION_REFS_GROUP:
                item.setSelected(True)

            self.listw.addItem(item)

        # Select all that should be kept by default (non-positionRefs)
        for i in range(self.listw.count()):
            item = self.listw.item(i)
            long_name = item.data(QtCore.Qt.UserRole)
            short = long_name.split("|")[-1]
            if short != POSITION_REFS_GROUP:
                item.setSelected(True)

    def _filter(self, text):
        t = (text or "").strip().lower()
        for i in range(self.listw.count()):
            it = self.listw.item(i)
            it.setHidden(bool(t) and t not in it.text().lower())

    def _select_all(self):
        for i in range(self.listw.count()):
            item = self.listw.item(i)
            if not item.isHidden():
                item.setSelected(True)

    def _on_keep(self): self._result = "keep_and_next"; self.accept()
    def _on_skip(self): self._result = "skip"; self.accept()
    def _on_stop(self): self._result = "stop"; self.reject()

    def get_result(self): return self._result

    def get_objects_to_keep(self):
        return {item.data(QtCore.Qt.UserRole) for item in self.listw.selectedItems()}


def _delete_unwanted_objects(keep_set):
    """Delete all world-level objects not in keep_set (except default cameras)."""
    top = _get_world_top_level_objects()
    to_delete = []
    for t in top:
        short = t.split("|")[-1]
        if _is_default_camera(t):
            continue
        if t not in keep_set:
            to_delete.append(t)

    if to_delete:
        try:
            cmds.delete(to_delete)
        except Exception as e:
            cmds.warning(f"Delete error: {e}")


def _collect_all_set_element_ma_files(set_elements_folder):
    """Return list of all .ma/.mb files in setElements/*/maya/"""
    files = []
    if not os.path.isdir(set_elements_folder):
        return files
    for entry in sorted(os.listdir(set_elements_folder)):
        asset_path = os.path.join(set_elements_folder, entry)
        if not os.path.isdir(asset_path): continue
        maya_folder = os.path.join(asset_path, "maya")
        if not os.path.isdir(maya_folder): continue
        for f in sorted(os.listdir(maya_folder)):
            if f.lower().endswith(".ma") or f.lower().endswith(".mb"):
                files.append(os.path.join(maya_folder, f))
    return files


def _auto_detect_groups_to_keep(file_path, set_elements_folder):
    """
    Auto mode: figure out which group(s) to keep based on folder name and file name.
    Returns a set of short names to look for.
    """
    # Derive element folder name from file path
    parts = file_path.replace("/", "\\").split("\\")
    lower = [p.lower() for p in parts]
    if "setelements" not in lower:
        return set()
    idx = lower.index("setelements")
    if idx + 1 >= len(parts):
        return set()
    element_folder = parts[idx + 1]

    # Build candidate names: full folder name, name without prefix (after last _)
    candidates = {element_folder}
    # Also try without leading set prefix (split by _ and take last meaningful segment)
    folder_parts = element_folder.split("_")
    if len(folder_parts) > 1:
        candidates.add(folder_parts[-1])
        candidates.add("_".join(folder_parts[1:]))
    return candidates


def action_cleanup(*_):
    """Clean Up button action."""
    folder = cmds.fileDialog2(dialogStyle=2, fm=3, caption="Select setElements Folder")
    if not folder: return
    set_elements_folder = folder[0]
    if not os.path.isdir(set_elements_folder):
        cmds.warning("Selected path is not a valid folder.")
        return

    ma_files = _collect_all_set_element_ma_files(set_elements_folder)
    if not ma_files:
        cmds.warning("No Maya files found in the selected setElements folder.")
        return

    # Mode selection
    mode_dlg = QtWidgets.QDialog(maya_main_window())
    mode_dlg.setWindowTitle("Clean Up Mode")
    mode_dlg.setObjectName("PhoenixCleanUpModeDialog")
    mode_dlg.setWindowFlags(mode_dlg.windowFlags() ^ QtCore.Qt.WindowContextHelpButtonHint)
    mode_dlg.setMinimumWidth(420)
    mode_layout = QtWidgets.QVBoxLayout(mode_dlg)
    mode_layout.setContentsMargins(12, 12, 12, 12)
    mode_layout.setSpacing(10)

    mode_layout.addWidget(QtWidgets.QLabel(
        f"<b>Found {len(ma_files)} Maya file(s)</b> in:<br><i>{set_elements_folder}</i>"
    ))
    mode_layout.addWidget(QtWidgets.QLabel(
        "Choose clean-up mode:"
    ))

    mode_group = QtWidgets.QButtonGroup(mode_dlg)
    rb_manual = QtWidgets.QRadioButton("Manual (Recommended) — Review each file before deleting")
    rb_auto = QtWidgets.QRadioButton("Auto — Delete non-relevant objects automatically")
    rb_manual.setChecked(True)
    mode_group.addButton(rb_manual)
    mode_group.addButton(rb_auto)
    mode_layout.addWidget(rb_manual)
    mode_layout.addWidget(rb_auto)

    auto_warn = QtWidgets.QLabel(
        "<font color='#c88'>⚠ Auto mode may delete important data. A backup option will be offered.</font>"
    )
    auto_warn.setWordWrap(True)
    auto_warn.setVisible(False)
    mode_layout.addWidget(auto_warn)
    rb_auto.toggled.connect(lambda checked: auto_warn.setVisible(checked))

    btns = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
    btns.accepted.connect(mode_dlg.accept)
    btns.rejected.connect(mode_dlg.reject)
    mode_layout.addWidget(btns)

    mode_result = mode_dlg.exec_() if hasattr(mode_dlg, "exec_") else mode_dlg.exec()
    if mode_result != QtWidgets.QDialog.Accepted: return

    use_auto = rb_auto.isChecked()

    if use_auto:
        backup_result = QtWidgets.QMessageBox.question(
            maya_main_window(), "Auto Mode — Backup?",
            "Auto mode might delete important objects.\n\n"
            "Do you want to create a backup of the setElements folder first?\n"
            "(A copy named 'setElements_backup' will be created next to it)",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No | QtWidgets.QMessageBox.Cancel
        )
        if backup_result == QtWidgets.QMessageBox.Cancel:
            return
        if backup_result == QtWidgets.QMessageBox.Yes:
            parent_folder = os.path.dirname(set_elements_folder)
            backup_dest = os.path.join(parent_folder, "setElements_backup")
            try:
                if os.path.isdir(backup_dest):
                    shutil.rmtree(backup_dest)
                shutil.copytree(set_elements_folder, backup_dest)
                cmds.inViewMessage(amg="Backup created: setElements_backup", pos="topCenter", fade=True)
            except Exception as e:
                err = QtWidgets.QMessageBox.critical(
                    maya_main_window(), "Backup Failed",
                    f"Failed to create backup:\n{e}\n\nContinue anyway?",
                    QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
                )
                if err != QtWidgets.QMessageBox.Yes: return

    # Save current file path so we can return after
    original_scene = cmds.file(q=True, sn=True)

    for i, file_path in enumerate(ma_files):
        if not os.path.isfile(file_path):
            continue

        # Open the file
        try:
            cmds.file(file_path, open=True, force=True)
        except Exception as e:
            cmds.warning(f"Could not open {os.path.basename(file_path)}: {e}")
            continue

        if use_auto:
            # Auto: determine which groups to keep
            candidates = _auto_detect_groups_to_keep(file_path, set_elements_folder)
            top = _get_world_top_level_objects()
            keep_set = set()

            for t in top:
                short = t.split("|")[-1]
                if _is_default_camera(t):
                    keep_set.add(t)
                    continue
                if short == POSITION_REFS_GROUP:
                    continue  # always delete positionRefs in auto
                # Keep if short name matches any candidate (case-insensitive)
                for cand in candidates:
                    if short.lower() == cand.lower() or cand.lower() in short.lower():
                        keep_set.add(t)
                        break

            _delete_unwanted_objects(keep_set)
            try:
                cmds.file(save=True, type="mayaAscii")
            except Exception as e:
                cmds.warning(f"Failed to save {os.path.basename(file_path)}: {e}")
        else:
            # Manual
            objects_info = _collect_world_children_info()
            dlg = ManualCleanupDialog(file_path, objects_info, i + 1, len(ma_files))
            result = dlg.exec_() if hasattr(dlg, "exec_") else dlg.exec()

            action = dlg.get_result()
            if action == "stop":
                cmds.inViewMessage(amg="Clean Up stopped by user.", pos="topCenter", fade=True)
                break
            elif action == "skip":
                continue
            elif action == "keep_and_next":
                keep_set = dlg.get_objects_to_keep()
                # Always keep default cameras
                top = _get_world_top_level_objects()
                for t in top:
                    if _is_default_camera(t):
                        keep_set.add(t)
                _delete_unwanted_objects(keep_set)
                try:
                    cmds.file(save=True, type="mayaAscii")
                except Exception as e:
                    cmds.warning(f"Failed to save {os.path.basename(file_path)}: {e}")

    cmds.inViewMessage(amg="Clean Up complete.", pos="topCenter", fade=True)

    # Optionally return to original scene
    if original_scene and os.path.isfile(original_scene):
        try:
            cmds.file(original_scene, open=True, force=True)
        except Exception:
            pass


# ------------------------------------------------------------
# Notes dropdown widget
# ------------------------------------------------------------
class NotesPanel(maya.app.general.mayaMixin.MayaQWidgetDockableMixin, QtWidgets.QWidget):
    """
    Dockable notes panel — sidebar tab list on the left, rich content on the right.
    Each tab corresponds to one button/feature of Phoenix Set Tools.
    """
    WINDOW_NAME = "PhoenixNotesPanel"
    _instance   = None

    # (tab_label, [(action_label, description), ...])
    # action_label="" means plain italic paragraph (overview), non-empty = action row
    SECTIONS = [
        ("Save Set Element", [
            ("", "Saves the current Maya scene into a set element or set folder structure "
                 "with a standardised file name derived from the asset folder name."),
            ("Left Click",
             "Opens a folder-picker asking you to choose a 'maya' folder.\n"
             "The scene is saved there with an auto-generated name:\n"
             "  prj_props_<assetFolderName>_mod_001_v001.ma"),
            ("Shift + Click",
             "Only works on a brand-new unsaved empty scene.\n"
             "Prompts you to select the set root folder, then opens the Create Set Structure panel:\n"
             "  • Enter element names (one per line) — spaces auto-converted to camelCase.\n"
             "  • Toggle underscore separator: set_element vs setElement.\n"
             "  • Toggle version-number style: _mod_01_v01 vs _mod_v01.\n"
             "  • Choose folder names: mod vs obj, sourceImages vs srcimgs.\n"
             "Creates the full hierarchy including maya/, mod/, renders/, ref/, setElements/,\n"
             "and per-element maya/ + mod/ + ref/ + sourceImages/ sub-folders.\n"
             "Saves the main scene and creates placeholder .ma files in each element's maya/ folder."),
            ("Right Click",
             "Opens the Set Element Switcher showing:\n"
             "  Main File    — <setRoot>/maya/*.ma\n"
             "  Blockouts    — <setRoot>/maya/blockout/*.ma  (toggle checkbox)\n"
             "  Set Elements — <setRoot>/setElements/*/maya/*.ma\n"
             "Selecting a file saves the current scene first then opens the target.\n"
             "Auto-detects set root from scene path; falls back to a folder picker."),
        ]),
        ("Group Ungrouped", [
            ("", "Finds mesh transforms that are direct children of the world (no parent group) "
                 "and wraps each one in a new group with the same name, producing the |name|name hierarchy."),
            ("Left Click",
             "Scans for all top-level mesh transforms.\n"
             "For each: creates an empty group matching the mesh world transform,\n"
             "parents the mesh into it, then renames both group and mesh to the original name.\n"
             "Entire operation is one undo chunk."),
        ]),
        ("Import Blockout", [
            ("", "Three different import workflows depending on modifier or mouse button. "
                 "Scene path is used to auto-derive the asset or set root."),
            ("Left Click",
             "Derives asset root from current scene path (looks for 'maya' folder in path).\n"
             "Scans <assetRoot>/mod/*_blockout/ for .obj files.\n"
             "One file found → imported immediately.\n"
             "Multiple found → searchable single-select picker is shown.\n"
             "Imported meshes are grouped under the OBJ file base name."),
            ("Shift + Click",
             "Shows all .ma/.mb files under <setRoot>/setElements/*/maya/.\n"
             "Supports multi-select.\n"
             "'As Reference' checkbox (default ON) — imports as Maya reference vs direct merge.\n"
             "Auto-detects set root; falls back to a folder picker if needed."),
            ("Right Click",
             "Opens the SetElements Import dockable panel.\n"
             "Collects files from every asset under <setRoot>/setElements/:\n"
             "  maya/           → .ma / .mb files\n"
             "  mod/*_blockout/ → OBJ / FBX\n"
             "  mod/ (root)     → OBJ / FBX\n"
             "  mod/final/      → OBJ / FBX\n"
             "Filter toggles: MA/MB, OBJ, FBX, Blockouts.\n"
             "'As Reference' toggle for MA/MB files.\n"
             "Supports multi-select and Select All.\n"
             "Auto-detects set root; falls back to a folder picker."),
        ]),
        ("Notes", [
            ("", "The Notes button opens this reference panel and doubles as a PureRef launcher."),
            ("Left Click",  "Opens this tabbed reference panel.\nIf already open, raises it to the front."),
            ("Shift + Click",
             "Scans <setRoot>/ref/ for .pur files and opens them in PureRef.\n"
             "Multiple files → multi-select picker is shown.\n"
             "Uses the set-level ref folder (next to maya/ and setElements/)."),
            ("Right Click",
             "Same as Shift+Click but uses <assetRoot>/ref/ first.\n"
             "Falls back to set-level ref folder if nothing is found there."),
        ]),
        ("Export Groups", [
            ("", "Exports scene groups as FBX files into a structured folder hierarchy. "
                 "Operates on all groups in the scene (transforms with child transforms, no shapes). "
                 "The scene must be saved."),
            ("Left Click",
             "Opens the Export Groups Setup dialog — configure:\n"
             "  Prefix                — defaults to scene file name.\n"
             "  Groups are blockout   — exports into mod/<group>_blockout/.\n"
             "  Create .ma files      — copies C:/icons-phoenix/mayaFile/setEmptyFile.ma\n"
             "                          into each group's maya/ folder, renamed to match.\n"
             "  With underscore       — prefix_Group vs prefixGroup.\n"
             "  Version number        — _mod_01_v01 vs _mod_v01.\n"
             "  Use 'obj' folder      — mod/ vs obj/ sub-folder name.\n"
             "  Use 'srcimgs'         — sourceImages/ vs srcimgs/.\n"
             "  Exclude list          — multi-select groups to skip.\n"
             "Then prompts for a base export location and creates per-group folders:\n"
             "  <base>/<prefix>_<group>/maya/\n"
             "  <base>/<prefix>_<group>/mod/  (or mod/<group>_blockout/)\n"
             "  <base>/<prefix>_<group>/sourceImages/\n"
             "  <base>/<prefix>_<group>/ref/\n"
             "Exports each group as FBX; optionally copies the .ma template."),
            ("Right Click",
             "Finds all top-level (world-parent) groups.\n"
             "Multiple groups → searchable multi-select picker.\n"
             "Exports each selected group as FBX into <assetRoot>/mod/final/\n"
             "(folder is created if it does not exist).\n"
             "Asset root = parent of the scene's maya/ folder."),
        ]),
        ("Duplicate", [
            ("", "Duplicates the selection and records its original world position via a hidden "
                 "bounding-box proxy cube (positionRef). Move the duplicate to the origin for clean "
                 "modelling, then restore it precisely later."),
            ("Left Click",
             "Duplicates selected mesh or group as <n>_dup.\n"
             "Computes world bounding box; creates a polyCube (positionRef) scaled to match.\n"
             "Parents positionRef into a top-level 'positionRefs' group and hides it.\n"
             "Stores bottom-centre world position as custom attrs (origPivotX/Y/Z).\n"
             "Moves both duplicate and positionRef so bottom-centre sits at world origin.\n"
             "Selects the duplicate on completion. Fully undoable."),
            ("Right Click",
             "Restore Position workflow.\n"
             "One positionRef found → used automatically.\n"
             "Multiple found → searchable single-select picker.\n"
             "Moves the currently selected object so its bottom-centre matches\n"
             "the stored origPivot of the chosen positionRef."),
        ]),
        ("Clean Up", [
            ("", "Batch-cleans Maya files across all set element folders. "
                 "Opens each .ma/.mb one by one in the current Maya session, "
                 "removes unwanted scene content, and re-saves. "
                 "Prompts you to select the setElements folder first."),
            ("Manual Mode",
             "Recommended. For each file, shows a panel listing every world-level object\n"
             "(default cameras are always excluded from deletion).\n"
             "positionRefs is NOT pre-selected — it will be deleted by default.\n"
             "Select every object to KEEP, then:\n"
             "  Keep Selected & Proceed — deletes the rest and saves the file.\n"
             "  Skip                   — moves to the next file with no changes.\n"
             "  Stop Clean Up          — exits immediately."),
            ("Auto Mode",
             "Automatically determines which group to keep based on element folder name.\n"
             "Matches world-level groups whose name contains the element folder name\n"
             "(case-insensitive, also tries the suffix after the last underscore).\n"
             "Deletes all other world objects including positionRefs, unmatched groups,\n"
             "and non-default cameras.\n"
             "Before processing, offers to back up the entire setElements folder\n"
             "as 'setElements_backup'. Strongly recommended."),
        ]),
        ("Prev / Main / Next", [
            ("", "Navigation buttons for cycling through set element files without the switcher dialog. "
                 "Auto-detects set root from scene path; falls back to folder picker. "
                 "Current scene is always saved before switching."),
            ("◀  Prev",
             "On a set element file: opens the previous element (alphabetical order, wraps to last).\n"
             "On the main file: jumps to the last element file."),
            ("Main",
             "Opens the first .ma/.mb found in <setRoot>/maya/ (the main set file).\n"
             "If already on the main file, shows a message and does nothing."),
            ("Next  ▶",
             "On a set element file: opens the next element (alphabetical order, wraps to first).\n"
             "On the main file: jumps to the first element file."),
        ]),
        ("Group & Rename", [
            ("", "Quick helper for setting up a standard group hierarchy: "
                 "selection → geo group → named outer group. "
                 "Matches the pipeline convention outerName > geo > meshes."),
            ("Left Click",
             "Opens a dialog pre-filled with the current scene file name as the outer group name.\n"
             "Edit and press Enter or click Rename.\n"
             "Result: <outerName> (group) > geo (group) > your selected objects.\n"
             "Outer group is selected on completion."),
        ]),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName(self.WINDOW_NAME)

        root_layout = QtWidgets.QHBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # ── Left sidebar ──────────────────────────────────────────────────
        sidebar = QtWidgets.QWidget()
        sidebar.setFixedWidth(160)
        sidebar.setObjectName("NotesSidebar")
        sidebar.setStyleSheet(
            "#NotesSidebar { background: palette(window); border-right: 1px solid palette(mid); }"
        )
        side_layout = QtWidgets.QVBoxLayout(sidebar)
        side_layout.setContentsMargins(0, 8, 0, 8)
        side_layout.setSpacing(1)

        self._tab_buttons = []
        for i, (label, _) in enumerate(self.SECTIONS):
            btn = QtWidgets.QPushButton(label)
            btn.setCheckable(True)
            btn.setAutoExclusive(True)
            btn.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
            btn.setMinimumHeight(36)
            btn.setStyleSheet("""
                QPushButton {
                    text-align: left;
                    padding: 7px 14px;
                    border: none;
                    border-radius: 0px;
                    background: transparent;
                }
                QPushButton:hover {
                    background: palette(highlight);
                    color: palette(highlightedText);
                }
                QPushButton:checked {
                    background: palette(highlight);
                    color: palette(highlightedText);
                    font-weight: bold;
                }
            """)
            btn.clicked.connect(lambda checked, n=i: self._stack.setCurrentIndex(n))
            side_layout.addWidget(btn)
            self._tab_buttons.append(btn)

        side_layout.addStretch(1)
        root_layout.addWidget(sidebar)

        # ── Right content stack ───────────────────────────────────────────
        self._stack = QtWidgets.QStackedWidget()
        root_layout.addWidget(self._stack, 1)

        for tab_label, entries in self.SECTIONS:
            self._stack.addWidget(self._make_page(tab_label, entries))

        if self._tab_buttons:
            self._tab_buttons[0].setChecked(True)
        self._stack.setCurrentIndex(0)

    def _make_page(self, title, entries):
        outer = QtWidgets.QWidget()
        outer_v = QtWidgets.QVBoxLayout(outer)
        outer_v.setContentsMargins(0, 0, 0, 0)
        outer_v.setSpacing(0)

        # Title bar
        title_bar = QtWidgets.QWidget()
        title_bar.setObjectName("NotesTitleBar")
        title_bar.setStyleSheet("#NotesTitleBar { background: palette(mid); }")
        title_bar.setFixedHeight(38)
        tb_h = QtWidgets.QHBoxLayout(title_bar)
        tb_h.setContentsMargins(16, 0, 16, 0)
        title_lbl = QtWidgets.QLabel(title)
        f = title_lbl.font(); f.setBold(True); f.setPointSize(f.pointSize() + 2)
        title_lbl.setFont(f)
        tb_h.addWidget(title_lbl)
        outer_v.addWidget(title_bar)

        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        outer_v.addWidget(scroll, 1)

        container = QtWidgets.QWidget()
        scroll.setWidget(container)
        vbox = QtWidgets.QVBoxLayout(container)
        vbox.setContentsMargins(16, 14, 16, 16)
        vbox.setSpacing(8)

        for action_label, desc in entries:
            if not action_label:
                para = QtWidgets.QLabel(desc)
                para.setWordWrap(True)
                para.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
                f2 = para.font(); f2.setItalic(True); para.setFont(f2)
                para.setStyleSheet("color: palette(placeholderText); padding-bottom: 4px;")
                vbox.addWidget(para)
            else:
                card = QtWidgets.QFrame()
                card.setObjectName("NotesCard")
                card.setStyleSheet(
                    "#NotesCard {"
                    "  background: palette(base);"
                    "  border: 1px solid palette(mid);"
                    "  border-radius: 5px;"
                    "}"
                )
                card_h = QtWidgets.QHBoxLayout(card)
                card_h.setContentsMargins(0, 0, 12, 0)
                card_h.setSpacing(0)

                tag = QtWidgets.QLabel(action_label)
                tag.setFixedWidth(130)
                tag.setAlignment(QtCore.Qt.AlignCenter | QtCore.Qt.AlignTop)
                tag.setObjectName("NotesTag")
                tag.setStyleSheet(
                    "#NotesTag {"
                    "  background: palette(highlight);"
                    "  color: palette(highlightedText);"
                    "  font-weight: bold;"
                    "  padding: 10px 6px;"
                    "  border-top-left-radius: 4px;"
                    "  border-bottom-left-radius: 4px;"
                    "  min-height: 32px;"
                    "}"
                )

                desc_lbl = QtWidgets.QLabel(desc)
                desc_lbl.setWordWrap(True)
                desc_lbl.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
                desc_lbl.setAlignment(QtCore.Qt.AlignTop | QtCore.Qt.AlignLeft)
                desc_lbl.setContentsMargins(12, 8, 0, 8)

                card_h.addWidget(tag)
                card_h.addWidget(desc_lbl, 1)
                vbox.addWidget(card)

        vbox.addStretch(1)
        return outer

    @classmethod
    def open_panel(cls, tab_index=0):
        ws_name = cls.WINDOW_NAME + "WorkspaceControl"

        # If workspace control already exists, just show/raise it
        if cmds.workspaceControl(ws_name, q=True, exists=True):
            cmds.workspaceControl(ws_name, e=True, restore=True)
            # Switch tab on the live instance if we can reach it
            if cls._instance is not None:
                try:
                    cls._instance._switch_tab(tab_index)
                except Exception:
                    pass
            return

        # Create fresh
        if cls._instance is not None:
            try:
                cls._instance.close()
            except Exception:
                pass
            cls._instance = None

        panel = cls()
        cls._instance = panel
        panel.show(
            dockable=True,
            floating=True,
            width=900,
            height=660,
            uiScript=""  # no restore script needed for simple use
        )
        panel._switch_tab(tab_index)

    def _switch_tab(self, index):
        if 0 <= index < len(self._tab_buttons):
            self._tab_buttons[index].setChecked(True)
            self._stack.setCurrentIndex(index)

    @classmethod
    def open_panel_at(cls, tab_index):
        cls.open_panel(tab_index=tab_index)


class NotesButton(QtWidgets.QPushButton):
    """
    Styled push-button for the Notes action.
    Left-click  → open NotesPanel
    Shift+click → PureRef set-level
    Right-click → PureRef asset-level
    """
    def __init__(self, on_shift_click=None, on_right_click=None, parent=None):
        super().__init__("Notes", parent)
        self._on_shift_click = on_shift_click
        self._on_right_click = on_right_click
        self.setMinimumHeight(26)
        self.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Fixed)
        self.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_right)
        self.setToolTip(
            "Left-Click: Open reference panel\n"
            "Shift+Click: Open PureRef (set-level ref)\n"
            "Right-Click: Open PureRef (asset-level ref)"
        )

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            if event.modifiers() & QtCore.Qt.ShiftModifier:
                if callable(self._on_shift_click):
                    self._on_shift_click()
                event.accept()
                return
            NotesPanel.open_panel()
            event.accept()
            return
        super().mousePressEvent(event)

    def _on_right(self):
        if callable(self._on_right_click):
            self._on_right_click()
# ------------------------------------------------------------
# FBX Right-click export picker
# ------------------------------------------------------------
class TopGroupFBXPicker(QtWidgets.QDialog):
    def __init__(self, groups_long, parent=maya_main_window()):
        super().__init__(parent)
        self.setWindowTitle("FBX Export — Choose Top-Level Group(s)")
        self.setObjectName("PhoenixTopGroupFBXPicker")
        self.setWindowFlags(self.windowFlags() ^ QtCore.Qt.WindowContextHelpButtonHint)
        self.setMinimumSize(620, 560)
        self._groups_long = list(groups_long)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        row = QtWidgets.QHBoxLayout()
        row.addWidget(QtWidgets.QLabel("Search:"))
        self.search = QtWidgets.QLineEdit()
        self.search.setPlaceholderText("Filter top-level groups...")
        row.addWidget(self.search, 1)
        layout.addLayout(row)

        self.listw = QtWidgets.QListWidget()
        self.listw.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        layout.addWidget(self.listw, 1)

        btn_row = QtWidgets.QHBoxLayout()
        self.btn_select_all = QtWidgets.QPushButton("Select All")
        self.btn_clear = QtWidgets.QPushButton("Clear Selection")
        btn_row.addWidget(self.btn_select_all)
        btn_row.addWidget(self.btn_clear)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        self.buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        layout.addWidget(self.buttons)

        self._populate()
        self.search.textChanged.connect(self._filter)
        self.btn_select_all.clicked.connect(self._select_all)
        self.btn_clear.clicked.connect(self.listw.clearSelection)
        self.buttons.accepted.connect(self._on_ok)
        self.buttons.rejected.connect(self.reject)

    def _populate(self):
        self.listw.clear()
        labeled = [(g.split("|")[-1].lower(), g.split("|")[-1], g) for g in self._groups_long]
        for _, short, g in sorted(labeled):
            it = QtWidgets.QListWidgetItem(short)
            it.setToolTip(g)
            it.setData(QtCore.Qt.UserRole, g)
            self.listw.addItem(it)
        if self.listw.count():
            self.listw.setCurrentRow(0)

    def _filter(self, text):
        t = (text or "").strip().lower()
        for i in range(self.listw.count()):
            it = self.listw.item(i)
            g = it.data(QtCore.Qt.UserRole)
            it.setHidden(not (t in it.text().lower() or t in str(g).lower()))

    def _select_all(self):
        self.listw.clearSelection()
        for i in range(self.listw.count()):
            it = self.listw.item(i)
            if not it.isHidden(): it.setSelected(True)

    def _on_ok(self):
        if not self.listw.selectedItems():
            QtWidgets.QMessageBox.warning(self, "Select group(s)", "Please select at least one top-level group.")
            return
        self.accept()

    def selected_groups(self):
        return [it.data(QtCore.Qt.UserRole) for it in self.listw.selectedItems()]


def _fbx_export_selected(path):
    path = path.replace("\\", "/")
    mel.eval("FBXResetExport;")
    mel.eval(f'FBXExport -f "{path}" -s;')


@undo_chunk
def action_export_top_group_fbx_final(*_):
    if not ensure_fbx_export_plugin():
        cmds.warning("FBX plugin (fbxmaya) could not be loaded.")
        return

    scene_path = cmds.file(q=True, sn=True)
    asset_root = _get_asset_root_from_scene(scene_path)
    if not asset_root:
        cmds.warning("Could not derive asset root from scene path.")
        return

    final_dir = os.path.join(asset_root, "mod", "final")
    os.makedirs(final_dir, exist_ok=True)

    groups_long = top_level_groups_only()
    if not groups_long:
        cmds.inViewMessage(amg="No top-level (world-parent) groups found.", pos="topCenter", fade=True)
        return

    if len(groups_long) == 1:
        chosen = groups_long
    else:
        dlg = TopGroupFBXPicker(groups_long)
        result = dlg.exec_() if hasattr(dlg, "exec_") else dlg.exec()
        if result != QtWidgets.QDialog.Accepted: return
        chosen = dlg.selected_groups()

    prev_sel = cmds.ls(sl=True, long=True) or []
    exported = 0
    for g in chosen:
        try:
            short = g.split("|")[-1]
            out_path = os.path.join(final_dir, safe_fs_name(short) + ".fbx")
            cmds.select(g, r=True)
            _fbx_export_selected(out_path)
            exported += 1
        except Exception as e:
            cmds.warning(f"FBX export failed for {g.split('|')[-1]}: {e}")

    if prev_sel: cmds.select(prev_sel, r=True)
    else: cmds.select(clear=True)

    if exported:
        cmds.inViewMessage(amg=f"FBX exported to: {final_dir}  ({exported} file(s))", pos="topCenter", fade=True)


# -----------------------------
# Group & Rename
# -----------------------------
class GroupRenameDialog(QtWidgets.QDialog):
    def __init__(self, default_name, parent=maya_main_window()):
        super().__init__(parent)
        self.setWindowTitle("Group & Rename")
        self.setObjectName("PhoenixGroupRenameDialog")
        self.setWindowFlags(self.windowFlags() ^ QtCore.Qt.WindowContextHelpButtonHint)
        self.setMinimumWidth(350)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        layout.addWidget(QtWidgets.QLabel("Outer group name:"))
        self.name_edit = QtWidgets.QLineEdit(default_name)
        self.name_edit.selectAll()
        self.name_edit.returnPressed.connect(self.accept)
        layout.addWidget(self.name_edit)

        btn_row = QtWidgets.QHBoxLayout()
        btn_row.addStretch(1)
        self.btn_rename = QtWidgets.QPushButton("Rename")
        self.btn_cancel = QtWidgets.QPushButton("Cancel")
        self.btn_rename.clicked.connect(self.accept)
        self.btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(self.btn_rename)
        btn_row.addWidget(self.btn_cancel)
        layout.addLayout(btn_row)

    def get_name(self): return self.name_edit.text().strip()


@undo_chunk
def action_group_and_rename(*_):
    sel = cmds.ls(sl=True, long=True)
    if not sel:
        cmds.warning("Nothing selected. Select objects to group.")
        return
    scene = cmds.file(q=True, sn=True, shortName=True) or ""
    default_name = os.path.splitext(scene)[0] if scene else "untitled"
    dlg = GroupRenameDialog(default_name)
    result = dlg.exec_() if hasattr(dlg, "exec_") else dlg.exec()
    if result != QtWidgets.QDialog.Accepted: return
    outer_name = dlg.get_name()
    if not outer_name:
        cmds.warning("No name entered.")
        return
    geo_grp = cmds.group(sel, name="geo")
    outer_grp = cmds.group(geo_grp, name=outer_name)
    cmds.select(outer_grp, r=True)
    cmds.inViewMessage(amg=f"Created: {outer_name} > geo", pos="topCenter", fade=True)


# ------------------------------------------------------------
# MAIN UI
# ------------------------------------------------------------
class PhoenixSetToolsUI(QtWidgets.QDialog):
    def __init__(self, parent=maya_main_window()):
        super().__init__(parent)
        self.setWindowTitle("Phoenix — Set Tools")
        self.setObjectName("PhoenixSetToolsUI")
        self.setWindowFlags(self.windowFlags() ^ QtCore.Qt.WindowContextHelpButtonHint)
        self.setMinimumWidth(280)

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(10)

        grid = QtWidgets.QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(10)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)

        self.btn_save    = QtWidgets.QPushButton("Save Set Element")
        self.btn_group   = QtWidgets.QPushButton("Group Ungrouped")
        self.btn_import  = QtWidgets.QPushButton("Import Blockout")
        self.btn_export  = QtWidgets.QPushButton("Export Groups")
        self.btn_dup     = QtWidgets.QPushButton("Duplicate")
        self.btn_cleanup = QtWidgets.QPushButton("Clean Up")

        for b in (self.btn_save, self.btn_group, self.btn_import,
                  self.btn_export, self.btn_dup, self.btn_cleanup):
            b.setMinimumHeight(46)
            b.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)

        self.btn_save.setToolTip(
            "Left-Click: Save scene to selected 'maya' folder with auto-generated name\n"
            "Shift+Click: Create full set folder structure (requires new empty scene)\n"
            "Right-Click: Switch between set element files"
        )
        self.btn_group.setToolTip("Wrap each top-level mesh in a group with matching name")
        self.btn_import.setToolTip(
            "Left-Click: Import blockout OBJ from asset's mod folder\n"
            "Shift+Click: Import set elements as references\n"
            "Right-Click: Browse/import OBJ+FBX from setElements asset mod folders"
        )
        self.btn_export.setToolTip(
            "Left-Click: Export groups as FBX (with structure)\n"
            "Shift+Click: Select groups → centre Y=0, smooth, cleanup, export merged FBX to set element mod/obj, revert\n"
            "Right-Click: Export top-level groups as FBX into mod/final"
        )
        self.btn_dup.setToolTip(
            "Left-Click: Duplicate selection to origin with position reference cube\n"
            "Right-Click: Restore position using stored reference"
        )
        self.btn_cleanup.setToolTip(
            "Open setElements folder and clean up each Maya file:\n"
            "- Manual: review each file and choose what to keep\n"
            "- Auto: automatically removes non-relevant objects and positionRefs"
        )

        # Context menus
        self.btn_save.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.btn_save.customContextMenuRequested.connect(lambda pos: action_switch_set_element())

        self.btn_export.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.btn_export.customContextMenuRequested.connect(lambda pos: action_export_top_group_fbx_final())

        self.btn_import.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.btn_import.customContextMenuRequested.connect(lambda pos: action_import_blockout_right_click())

        self.btn_dup.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.btn_dup.customContextMenuRequested.connect(lambda pos: action_duplicate_right_click())

        grid.addWidget(self.btn_save,    0, 0)
        grid.addWidget(self.btn_group,   0, 1)
        grid.addWidget(self.btn_import,  1, 0)
        grid.addWidget(self.btn_export,  1, 1)
        grid.addWidget(self.btn_dup,     2, 0)
        grid.addWidget(self.btn_cleanup, 2, 1)
        root.addLayout(grid)

        self.btn_notes = NotesButton(
            on_shift_click=action_open_pureref_set_level,
            on_right_click=action_open_pureref_asset_level
        )
        self.btn_notes.setToolTip(
            "Left-Click: Open notes panel\n"
            "Shift+Click: Open PureRef (set-level ref)\n"
            "Right-Click: Open PureRef (asset-level ref)"
        )

        notes_row = QtWidgets.QHBoxLayout()
        notes_row.setSpacing(10)
        notes_row.addWidget(self.btn_notes, 0, QtCore.Qt.AlignTop)

        self.btn_grp_rename = QtWidgets.QPushButton("Group && Rename")
        self.btn_grp_rename.setMinimumHeight(28)
        self.btn_grp_rename.setToolTip(
            "Group selection into 'geo', wrap in outer group.\n"
            "Defaults outer group name to current scene file name."
        )
        self.btn_grp_rename.clicked.connect(action_group_and_rename)
        notes_row.addWidget(self.btn_grp_rename, 0, QtCore.Qt.AlignTop)
        root.addLayout(notes_row)

        # Nav row: Prev | Main | Next
        nav_row = QtWidgets.QHBoxLayout()
        nav_row.setSpacing(4)

        self.btn_nav_prev = QtWidgets.QPushButton("◀  Prev")
        self.btn_nav_main = QtWidgets.QPushButton("Main")
        self.btn_nav_next = QtWidgets.QPushButton("Next  ▶")

        for b in (self.btn_nav_prev, self.btn_nav_main, self.btn_nav_next):
            b.setMinimumHeight(26)
            b.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)

        self.btn_nav_prev.setToolTip(
            "Previous set element file.\n"
            "From main file: jumps to last element."
        )
        self.btn_nav_main.setToolTip("Switch to the main set Maya file.")
        self.btn_nav_next.setToolTip(
            "Next set element file.\n"
            "From main file: jumps to first element."
        )

        self.btn_nav_prev.clicked.connect(action_nav_prev)
        self.btn_nav_main.clicked.connect(action_nav_main)
        self.btn_nav_next.clicked.connect(action_nav_next)

        nav_row.addWidget(self.btn_nav_prev)
        nav_row.addWidget(self.btn_nav_main)
        nav_row.addWidget(self.btn_nav_next)
        root.addLayout(nav_row)

        # Wire up button actions
        self.btn_save.clicked.connect(action_save_set_element)
        self.btn_group.clicked.connect(action_group_all_ungrouped)
        self.btn_export.clicked.connect(action_export_groups)
        self.btn_cleanup.clicked.connect(action_cleanup)

        # Install event filters for Shift+Click behaviour
        self.btn_import.installEventFilter(self)
        self.btn_save.installEventFilter(self)
        self.btn_dup.installEventFilter(self)
        self.btn_export.installEventFilter(self)

    def eventFilter(self, obj, event):
        if event.type() == QtCore.QEvent.MouseButtonPress:
            if obj == self.btn_import and event.button() == QtCore.Qt.LeftButton:
                if event.modifiers() & QtCore.Qt.ShiftModifier:
                    action_import_set_elements(); return True
                else:
                    action_import_blockout(); return True
            if obj == self.btn_save and event.button() == QtCore.Qt.LeftButton:
                if event.modifiers() & QtCore.Qt.ShiftModifier:
                    action_create_set_structure(); return True
                # Fall through to normal clicked signal for left without shift
            if obj == self.btn_dup and event.button() == QtCore.Qt.LeftButton:
                action_duplicate_with_position_reference(); return True
            if obj == self.btn_export and event.button() == QtCore.Qt.LeftButton:
                if event.modifiers() & QtCore.Qt.ShiftModifier:
                    action_shift_export_groups(); return True
                # Fall through to normal clicked signal for plain left-click
        return super().eventFilter(obj, event)


def show_phoenix_ui():
    for w in QtWidgets.QApplication.topLevelWidgets():
        if w.objectName() == "PhoenixSetToolsUI":
            try: w.close(); w.deleteLater()
            except Exception: pass

    dlg = PhoenixSetToolsUI()
    dlg.show()
    return dlg


show_phoenix_ui()