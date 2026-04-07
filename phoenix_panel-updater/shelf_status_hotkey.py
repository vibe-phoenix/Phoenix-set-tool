import maya.cmds as cmds
import os, re

marker = "# << ctrl_shift_x_shelf_status_hotkey >>"

inner_cmd = """
import maya.cmds as cmds, maya.mel as mel, __main__, time
try:    from PySide6.QtCore import QTimer
except: from PySide2.QtCore import QTimer
if not hasattr(__main__, '_x_timer'): __main__._x_timer = None
if not hasattr(__main__, '_last_x_press'): __main__._last_x_press = [0.0]
now = time.time(); delta = now - __main__._last_x_press[0]
__main__._last_x_press[0] = now
def do_shelf():
    mel.eval("ToggleShelf")
def do_status():
    mel.eval("ToggleStatusLine")
if 0 < delta < 0.25:
    if __main__._x_timer is not None:
        __main__._x_timer.stop()
        __main__._x_timer = None
    __main__._last_x_press[0] = 0.0
    do_status()
else:
    if __main__._x_timer is not None:
        __main__._x_timer.stop()
    t = QTimer()
    t.setSingleShot(True)
    t.timeout.connect(do_shelf)
    t.start(250)
    __main__._x_timer = t
"""

new_block = f"""
{marker}
import maya.cmds as cmds
import maya.utils
def _register_ctrl_shift_x_hotkey():
    cmd_name        = "ctrl_shift_x_shelf_status"
    nc_name         = "ctrl_shift_x_NC"
    nc_release_name = "ctrl_shift_x_Release_NC"
    if cmds.runTimeCommand(cmd_name, exists=True):
        cmds.runTimeCommand(cmd_name, e=True, delete=True)
    cmds.runTimeCommand(
        cmd_name,
        annotation="Ctrl+Shift+X: Toggle Shelf | Ctrl+Shift+X+X: Toggle Status Line",
        category="User",
        commandLanguage="python",
        command={repr(inner_cmd)}
    )
    cmds.nameCommand(nc_name,         annotation="Shelf/StatusLine toggle",  command=cmd_name, sourceType="mel")
    cmds.nameCommand(nc_release_name, annotation="Shelf/StatusLine release", command="",       sourceType="mel")
    cmds.hotkey(keyShortcut="x", ctrlModifier=True, shiftModifier=True, name=nc_name, releaseName=nc_release_name)
maya.utils.executeDeferred(_register_ctrl_shift_x_hotkey)
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