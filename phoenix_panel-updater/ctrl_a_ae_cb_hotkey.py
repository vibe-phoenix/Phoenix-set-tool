import maya.cmds as cmds
import os, re

marker = "# << ctrl_a_ae_cb_hotkey >>"

inner_cmd = """
import time, maya.cmds as cmds, maya.mel as mel, __main__
if not hasattr(__main__, '_last_a_press'): __main__._last_a_press = [0.0]
now = time.time(); delta = now - __main__._last_a_press[0]
ae='AttributeEditor'; cb='ChannelBoxLayerEditor'; uv='UVToolkitDockControl'; phx='PhoenixUVToolboxWorkspaceControl'
ae_e=cmds.workspaceControl(ae,exists=True); cb_e=cmds.workspaceControl(cb,exists=True); uv_e=cmds.workspaceControl(uv,exists=True); phx_e=cmds.workspaceControl(phx,exists=True)
try:    current_ws = cmds.workspaceLayoutManager(q=True, current=True)
except: current_ws = ''
is_uv_ws = (current_ws == 'Phoenix-UV')
uv_mel_4 = "if(`workspaceControl -q -r UVToolkitDockControl`){workspaceControl -e -collapse false -r AttributeEditor;}else if(`workspaceControl -q -r AttributeEditor`){workspaceControl -e -collapse false -r ChannelBoxLayerEditor;}else if(`workspaceControl -q -r ChannelBoxLayerEditor`){workspaceControl -e -collapse false -r PhoenixUVToolboxWorkspaceControl;}else if(`workspaceControl -q -r PhoenixUVToolboxWorkspaceControl`){workspaceControl -e -collapse false -r UVToolkitDockControl;}else{workspaceControl -e -collapse false -r PhoenixUVToolboxWorkspaceControl;}"
uv_mel_3 = "if(`workspaceControl -q -r UVToolkitDockControl`){workspaceControl -e -collapse false -r AttributeEditor;}else if(`workspaceControl -q -r AttributeEditor`){workspaceControl -e -collapse false -r ChannelBoxLayerEditor;}else if(`workspaceControl -q -r ChannelBoxLayerEditor`){workspaceControl -e -collapse false -r UVToolkitDockControl;}else{workspaceControl -e -collapse false -r UVToolkitDockControl;}"
ae_mel  = "if(`isAttributeEditorRaised`){if(!`isChannelBoxVisible`){setChannelBoxVisible(1);}else{raiseChannelBox;}}else{openAEWindow;}"
if 0 < delta < 0.25:
    if is_uv_ws:
        ae_r  = cmds.workspaceControl(ae,  q=True, r=True) if ae_e  else False
        cb_r  = cmds.workspaceControl(cb,  q=True, r=True) if cb_e  else False
        uv_r  = cmds.workspaceControl(uv,  q=True, r=True) if uv_e  else False
        phx_r = cmds.workspaceControl(phx, q=True, r=True) if phx_e else False
        if   ae_r:  cmds.workspaceControl(ae,  e=True, collapse=True)
        elif cb_r:  cmds.workspaceControl(cb,  e=True, collapse=True)
        elif uv_r:  cmds.workspaceControl(uv,  e=True, collapse=True)
        elif phx_r: cmds.workspaceControl(phx, e=True, collapse=True)
    else:
        ae_r = cmds.workspaceControl(ae, q=True, r=True) if ae_e else False
        cb_r = cmds.workspaceControl(cb, q=True, r=True) if cb_e else False
        if   ae_r: cmds.workspaceControl(ae, e=True, collapse=True)
        elif cb_r: cmds.workspaceControl(cb, e=True, collapse=True)
    __main__._last_a_press[0] = 0.0
else:
    __main__._last_a_press[0] = now
    if is_uv_ws:
        mel.eval(uv_mel_4 if phx_e else uv_mel_3)
    else:
        mel.eval(ae_mel)
"""

new_block = f"""
{marker}
import maya.cmds as cmds
import maya.utils
def _register_ctrl_a_hotkey():
    cmd_name        = "ctrl_a_ae_cb"
    nc_name         = "ctrl_a_ae_cb_NC"
    nc_release_name = "ctrl_a_ae_cb_Release_NC"
    if cmds.runTimeCommand(cmd_name, exists=True):
        cmds.runTimeCommand(cmd_name, e=True, delete=True)
    cmds.runTimeCommand(
        cmd_name,
        annotation="Ctrl+A: Switch AE/CB | Ctrl+A+A: Toggle collapse",
        category="User",
        commandLanguage="python",
        command={repr(inner_cmd)}
    )
    cmds.nameCommand(nc_name,         annotation="AE/CB controller", command=cmd_name, sourceType="mel")
    cmds.nameCommand(nc_release_name, annotation="AE/CB release",    command="",       sourceType="mel")
    cmds.hotkey(keyShortcut="a", ctrlModifier=True, name=nc_name, releaseName=nc_release_name)
maya.utils.executeDeferred(_register_ctrl_a_hotkey)
{marker} end
"""

maya_app_dir = cmds.internalVar(userAppDir=True)
script_dir   = os.path.join(maya_app_dir, "scripts")
setup_path   = os.path.join(script_dir, "userSetup.py")

existing = ""
if os.path.exists(setup_path):
    with open(setup_path, "r") as f:
        existing = f.read()

if marker in existing:
    pattern = rf"{re.escape(marker)}.*?{re.escape(marker)} end"
    updated = re.sub(pattern, new_block.strip(), existing, flags=re.DOTALL)
    with open(setup_path, "w") as f:
        f.write(updated)
    print("Updated:", setup_path)
else:
    with open(setup_path, "a") as f:
        f.write(new_block)
    print("Appended:", setup_path)

print("Done — restart Maya to apply.")