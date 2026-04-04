import maya.cmds as cmds
import math

# ✅ Main shelf button function
def create_quad_uv_sphere_smart():
    use_default = cmds.optionVar(q='quadUVSphere_useDefault') if cmds.optionVar(exists='quadUVSphere_useDefault') else 1
    if not use_default:
        open_main_ui()
        return

    subdivisions = cmds.optionVar(q='quadUVSphere_subdivisions') if cmds.optionVar(exists='quadUVSphere_subdivisions') else 4
    radius = cmds.optionVar(q='quadUVSphere_radius') if cmds.optionVar(exists='quadUVSphere_radius') else 1.0

    fast_create_sphere(subdivisions, radius)

# ✅ Sphere generator
def fast_create_sphere(subdivisions, radius):
    name = "quad_uv_sphere"
    cube = cmds.polyCube(w=2, h=2, d=2,
                         sx=subdivisions, sy=subdivisions, sz=subdivisions,
                         name=name)[0]

    verts = cmds.ls(cube + '.vtx[*]', flatten=True)
    positions = cmds.xform(verts, q=True, ws=True, t=True)

    move_positions = []
    for i in range(0, len(positions), 3):
        x, y, z = positions[i:i+3]
        length = math.sqrt(x*x + y*y + z*z)
        if length > 0:
            scale = radius / length
            move_positions.extend([x * scale, y * scale, z * scale])
        else:
            move_positions.extend([x, y, z])

    for i, vtx in enumerate(verts):
        cmds.move(move_positions[i*3], move_positions[i*3+1], move_positions[i*3+2], vtx, a=True, ws=True)

    cmds.polySoftEdge(cube, angle=180, ch=False)
    cmds.delete(cube, ch=True)
    cmds.xform(cube, centerPivots=True)

    cmds.selectType(allComponents=False)
    cmds.select(cube, r=True)

    print(f"[QuadUV] Created {cube} | subdivisions: {subdivisions} | radius: {radius}")

# ✅ Manual sphere creation UI
def open_main_ui():
    if cmds.window('quadUVSphereWin', exists=True):
        cmds.deleteUI('quadUVSphereWin')

    win = cmds.window('quadUVSphereWin', title='Quad UV Sphere', sizeable=False)
    cmds.columnLayout(adjustableColumn=True, rowSpacing=6, columnAlign='center')
    subdiv_field = cmds.intFieldGrp(label='Subdivisions:', value1=4, cw2=(80, 50))
    radius_field = cmds.floatFieldGrp(label='Radius:', value1=1.0, cw2=(80, 50))

    def apply_and_close(*_):
        s = cmds.intFieldGrp(subdiv_field, q=True, value1=True)
        r = cmds.floatFieldGrp(radius_field, q=True, value1=True)
        if s < 2:
            cmds.warning("Subdivisions must be >= 2")
            return
        cmds.deleteUI(win)
        fast_create_sphere(s, r)

    cmds.button(label='Create Sphere', c=apply_and_close)
    cmds.showWindow(win)

# ✅ Settings window
def open_settings_ui():
    if cmds.window('quadUVSphereSettingsWin', exists=True):
        cmds.deleteUI('quadUVSphereSettingsWin')

    s = cmds.optionVar(q='quadUVSphere_subdivisions') if cmds.optionVar(exists='quadUVSphere_subdivisions') else 4
    r = cmds.optionVar(q='quadUVSphere_radius') if cmds.optionVar(exists='quadUVSphere_radius') else 1.0
    d = cmds.optionVar(q='quadUVSphere_useDefault') if cmds.optionVar(exists='quadUVSphere_useDefault') else 1

    win = cmds.window('quadUVSphereSettingsWin', title='Quad UV Sphere Settings', sizeable=False)
    cmds.columnLayout(adjustableColumn=True, rowSpacing=6, columnAlign='center')
    subdiv_field = cmds.intFieldGrp(label='Subdivisions:', value1=s, cw2=(80, 50))
    radius_field = cmds.floatFieldGrp(label='Radius:', value1=r, cw2=(80, 50))
    default_check = cmds.checkBox(label='Use default on button click', value=d)

    def save(*_):
        s = cmds.intFieldGrp(subdiv_field, q=True, value1=True)
        r = cmds.floatFieldGrp(radius_field, q=True, value1=True)
        d = cmds.checkBox(default_check, q=True, value=True)
        cmds.optionVar(iv=('quadUVSphere_subdivisions', s))
        cmds.optionVar(fv=('quadUVSphere_radius', r))
        cmds.optionVar(iv=('quadUVSphere_useDefault', int(d)))
        cmds.deleteUI(win)
        cmds.inViewMessage(amg='✅ Settings saved', pos='midCenter', fade=True)

    cmds.button(label='Save Settings', c=save)
    cmds.button(label='Reset Stored Values', c=reset_settings)
    cmds.showWindow(win)

# ✅ Reset optionVars
def reset_settings(*_):
    for var in ['quadUVSphere_subdivisions', 'quadUVSphere_radius', 'quadUVSphere_useDefault']:
        if cmds.optionVar(exists=var):
            cmds.optionVar(remove=var)
    if cmds.window('quadUVSphereSettingsWin', exists=True):
        cmds.deleteUI('quadUVSphereSettingsWin')
    cmds.inViewMessage(amg='🧹 Quad UV Sphere settings reset', pos='midCenter', fade=True)

# ✅ Manual UI launcher (alias)
def open_custom_sphere_ui():
    open_main_ui()

# ✅ Don't auto-run anything
if __name__ == "__main__":
    pass
