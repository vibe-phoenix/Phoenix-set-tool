import maya.cmds as cmds
import os

def get_all_meshes_under(node):
    """Return all mesh transforms under a given node (group)."""
    shapes = cmds.listRelatives(node, allDescendents=True, type='mesh') or []
    meshes = list(set(cmds.listRelatives(shapes, parent=True, fullPath=False) or []))
    return meshes


def apply_ai_standard_with_prefix():
    sel = cmds.ls(sl=True, long=True)
    if not sel:
        cmds.warning("Select one or more meshes or groups.")
        return

    # --- Get scene filename as default prefix ---
    scene_path = cmds.file(query=True, sceneName=True)
    if scene_path:
        default_prefix = os.path.splitext(os.path.basename(scene_path))[0]
    else:
        default_prefix = "untitled"

    # Ask user for prefix, pre-filled with scene filename
    prefix_status = cmds.promptDialog(
        title='Shading Engine Prefix',
        message='Enter prefix for shading engine (DO NOT end with "_"):\n(It will be auto-corrected anyway)',
        text=default_prefix,                  # <-- pre-filled
        button=['OK', 'Cancel'],
        defaultButton='OK',
        cancelButton='Cancel',
        dismissString='Cancel'
    )

    if prefix_status != 'OK':
        return

    user_prefix = cmds.promptDialog(query=True, text=True).strip()
    if user_prefix.endswith("_"):
        user_prefix = user_prefix[:-1]

    # Collect meshes explicitly selected
    selected_meshes = []
    selected_groups = []

    for obj in sel:
        short = obj.split("|")[-1]
        if cmds.objectType(obj) == "transform":
            children = cmds.listRelatives(obj, children=True, fullPath=False) or []
            if any(cmds.objectType(c) == "mesh" for c in children):
                selected_meshes.append(short)
            else:
                selected_groups.append(short)
        else:
            selected_meshes.append(short)

    group_mesh_map = {}
    all_group_meshes = set()

    for grp in selected_groups:
        meshes = get_all_meshes_under(grp)
        group_mesh_map[grp] = meshes
        all_group_meshes.update(meshes)

    mesh_to_group = {}
    for grp, meshes in group_mesh_map.items():
        for m in meshes:
            mesh_to_group[m] = grp

    sel_mesh_set = set(selected_meshes)
    tasks = []

    for mesh in selected_meshes:
        shd = f"{mesh}_shd"
        se = f"{user_prefix}_{mesh}"
        tasks.append((mesh, shd, se))

    for grp, meshes in group_mesh_map.items():
        for mesh in meshes:
            if mesh not in sel_mesh_set:
                shd = f"{grp}_shd"
                se = f"{user_prefix}_{grp}"
                tasks.append((mesh, shd, se))

    def create_shader_if_needed(shader_name):
        if cmds.objExists(shader_name):
            return shader_name
        return cmds.shadingNode("aiStandardSurface", asShader=True, name=shader_name)

    def create_se_if_needed(se_name):
        if cmds.objExists(se_name):
            return se_name
        return cmds.sets(renderable=True, noSurfaceShader=True, empty=True, name=se_name)

    for mesh, shader_name, se_name in tasks:
        shader = create_shader_if_needed(shader_name)
        se = create_se_if_needed(se_name)

        try:
            cmds.connectAttr(f"{shader}.outColor", f"{se}.surfaceShader", force=True)
        except:
            pass

        try:
            cmds.sets(mesh, edit=True, forceElement=se)
        except:
            cmds.warning(f"Could not assign {se} to {mesh}")

    cmds.inViewMessage(amg='<span style="color:#4fff7a;">Shaders Applied ?</span>', pos='topCenter', fade=True)


apply_ai_standard_with_prefix()