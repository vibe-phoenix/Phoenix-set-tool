import maya.cmds as cmds

# ------------------------------------------------------------
# UV Copy/Paste Tool (Transfer Attributes) - FINAL (no preserveUVs flag)
# ------------------------------------------------------------

_UV_COPY_STATE = {
    "source": None,               # stored transform
    "sampleSpace": "topology",    # topology for true duplicates; closestPoint for similar meshes
    "searchMethod": "closestPoint",
    "deleteHistory": True,
    "flipUVs": False,
}

def _get_mesh_shape(node):
    """Return a non-intermediate mesh shape for a transform, or node if it is a mesh shape."""
    if not node or not cmds.objExists(node):
        return None

    ntype = cmds.nodeType(node)
    if ntype == "mesh":
        return node

    if ntype == "transform":
        shapes = cmds.listRelatives(node, shapes=True, fullPath=True) or []
        # prefer visible/non-intermediate mesh
        for s in shapes:
            if cmds.nodeType(s) == "mesh" and not cmds.getAttr(s + ".intermediateObject"):
                return s
        # fallback
        for s in shapes:
            if cmds.nodeType(s) == "mesh":
                return s

    return None

def _as_transform(node):
    """If node is a mesh shape, return its parent transform; otherwise return node."""
    if not node or not cmds.objExists(node):
        return None
    if cmds.nodeType(node) == "mesh":
        p = cmds.listRelatives(node, parent=True, fullPath=True) or []
        return p[0] if p else None
    return node

def _is_poly_mesh(node):
    return _get_mesh_shape(node) is not None

def _set_status(text):
    if cmds.control("uvcp_status", exists=True):
        cmds.text("uvcp_status", edit=True, label=text)

def uvcp_copy_source(*_):
    sel = cmds.ls(selection=True, long=True) or []
    if not sel:
        cmds.warning("Select the UV'd source mesh, then click Copy Source.")
        _set_status("No selection.")
        return

    src = sel[0]
    if not _is_poly_mesh(src):
        cmds.warning("Selection is not a polygon mesh.")
        _set_status("Invalid source.")
        return

    _UV_COPY_STATE["source"] = _as_transform(src)
    _set_status("Source: " + _UV_COPY_STATE["source"])
    print("[UV CopyPaste] Source set:", _UV_COPY_STATE["source"])

def uvcp_paste_uvs(*_):
    src = _UV_COPY_STATE.get("source")
    if not src or not cmds.objExists(src):
        cmds.warning("No source stored. Select UV'd mesh and click Copy Source first.")
        _set_status("No source stored.")
        return

    sel = cmds.ls(selection=True, long=True) or []
    if not sel:
        cmds.warning("Select one or more target meshes, then click Paste UVs.")
        _set_status("No targets selected.")
        return

    targets = [t for t in sel if _is_poly_mesh(t)]
    if not targets:
        cmds.warning("No valid polygon targets selected.")
        _set_status("Invalid targets.")
        return

    sample_space_map = {
        "world": 0,
        "local": 1,
        "uv": 2,
        "component": 3,
        "topology": 4,
        "closestPoint": 5
    }
    search_method_map = {
        "alongNormal": 0,
        "closestPoint": 1,
        "rayCast": 2
    }

    ss_val = sample_space_map.get(_UV_COPY_STATE["sampleSpace"], 4)
    sm_val = search_method_map.get(_UV_COPY_STATE["searchMethod"], 1)

    ok = 0
    failed = []

    original_sel = sel[:]

    for tgt in targets:
        if _as_transform(tgt) == _as_transform(src):
            continue

        try:
            cmds.select(src, tgt, replace=True)

            # NOTE:
            # Some Maya builds do NOT support flags like preserveUVs or colorBorders in Python.
            # This call uses only widely-supported flags.
            cmds.transferAttributes(
                transferPositions=0,
                transferNormals=0,
                transferUVs=2,   # transfer current UV set
                transferColors=0,
                sampleSpace=ss_val,
                searchMethod=sm_val,
                flipUVs=_UV_COPY_STATE["flipUVs"]
            )

            if _UV_COPY_STATE["deleteHistory"]:
                cmds.delete(tgt, constructionHistory=True)

            ok += 1

        except Exception as e:
            failed.append(tgt)
            print("[UV CopyPaste] Failed on:", tgt, "| Error:", e)

    cmds.select(original_sel, replace=True)

    if failed:
        cmds.warning("Paste UVs done. Success: %d | Failed: %d (see Script Editor)" % (ok, len(failed)))
        _set_status("Done. Success: %d | Failed: %d" % (ok, len(failed)))
    else:
        _set_status("Done. Success: %d" % ok)
        print("[UV CopyPaste] Paste UVs complete. Success:", ok)

def show_uv_copy_paste_ui():
    win = "UV_CopyPaste_Tool"
    if cmds.window(win, exists=True):
        cmds.deleteUI(win)

    cmds.window(win, title="UV Copy / Paste (Transfer Attributes)", sizeable=False)
    cmds.columnLayout(adj=True, rowSpacing=8)

    cmds.frameLayout(label="Workflow", collapsable=False, marginWidth=10, marginHeight=8)
    cmds.columnLayout(adj=True, rowSpacing=4)
    cmds.text(label="1) Select UV'd source mesh ? Copy Source")
    cmds.text(label="2) Select target meshes ? Paste UVs")
    cmds.setParent("..")
    cmds.setParent("..")

    cmds.rowLayout(numberOfColumns=2, adjustableColumn=2, columnWidth2=(140, 260), columnAlign2=("right", "left"))
    cmds.text(label="Stored Source:")
    cmds.text("uvcp_status", label="(none)", align="left")
    cmds.setParent("..")

    cmds.rowLayout(numberOfColumns=2, columnWidth2=(170, 170), columnAlign2=("center", "center"))
    cmds.button(label="Copy Source", height=32, command=uvcp_copy_source)
    cmds.button(label="Paste UVs", height=32, command=uvcp_paste_uvs)
    cmds.setParent("..")

    cmds.separator(height=10, style="in")

    cmds.frameLayout(label="Options", collapsable=True, collapse=False, marginWidth=10, marginHeight=8)
    cmds.columnLayout(adj=True, rowSpacing=6)

    match_menu = cmds.optionMenuGrp(
        label="Match Method",
        changeCommand=lambda x: _UV_COPY_STATE.__setitem__("sampleSpace", x)
    )
    for lbl in ["topology", "closestPoint", "component", "world", "local", "uv"]:
        cmds.menuItem(label=lbl)
    cmds.optionMenuGrp(match_menu, edit=True, value=_UV_COPY_STATE["sampleSpace"])

    search_menu = cmds.optionMenuGrp(
        label="Closest Search",
        changeCommand=lambda x: _UV_COPY_STATE.__setitem__("searchMethod", x)
    )
    for lbl in ["closestPoint", "alongNormal", "rayCast"]:
        cmds.menuItem(label=lbl)
    cmds.optionMenuGrp(search_menu, edit=True, value=_UV_COPY_STATE["searchMethod"])

    cmds.checkBoxGrp(
        numberOfCheckBoxes=1,
        label="Delete History (bake)",
        value1=_UV_COPY_STATE["deleteHistory"],
        changeCommand1=lambda v: _UV_COPY_STATE.__setitem__("deleteHistory", bool(v))
    )

    cmds.checkBoxGrp(
        numberOfCheckBoxes=1,
        label="Flip UVs",
        value1=_UV_COPY_STATE["flipUVs"],
        changeCommand1=lambda v: _UV_COPY_STATE.__setitem__("flipUVs", bool(v))
    )

    cmds.setParent("..")
    cmds.setParent("..")

    cmds.separator(height=8, style="none")
    cmds.text(label="Tip: topology = best for true duplicates. closestPoint = best for similar meshes.", align="left")

    cmds.showWindow(win)

# Run:
show_uv_copy_paste_ui()