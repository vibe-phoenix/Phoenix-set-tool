import maya.cmds as cmds
import maya.mel as mel
import maya.utils as utils
import urllib.request
import os
import hashlib


# ── paths (auto-resolved per user) ───────────────────────────────────────────

MAYA_APP_DIR      = mel.eval("getenv MAYA_APP_DIR")
PHOENIXTOOLS_PATH = os.path.join(MAYA_APP_DIR, "phoenixtools")
UPDATER_PATH      = os.path.join(PHOENIXTOOLS_PATH, "PhoenixPanel-updater")

UPDATE_URL        = "https://raw.githubusercontent.com/vibe-phoenix/Phoenix-set-tool/main/phoenix_panel-updater/update.py"
UPDATE_CLEAN_URL  = "https://raw.githubusercontent.com/vibe-phoenix/Phoenix-set-tool/main/phoenix_panel-updater/update_and_clear"

UPDATE_FILE       = os.path.join(UPDATER_PATH, "update.py")
UPDATE_CLEAN_FILE = os.path.join(UPDATER_PATH, "update_and_clear.py")
SHORTCUT_FILE     = os.path.join(UPDATER_PATH, "assignshortcutcustom.py")


# ── utils ─────────────────────────────────────────────────────────────────────

def _file_hash(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def _remote_content(url):
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            return r.read()
    except Exception as e:
        cmds.warning("[Phoenix] Could not reach: " + url + " | " + str(e))
        return None


def _ensure_folder():
    if not os.path.exists(UPDATER_PATH):
        os.makedirs(UPDATER_PATH)
        print("[Phoenix] Created folder: " + UPDATER_PATH)


def _check_and_download(url, local_path):
    _ensure_folder()

    content = _remote_content(url)
    if content is None:
        return False

    remote_hash = hashlib.md5(content).hexdigest()

    if os.path.exists(local_path):
        if _file_hash(local_path) == remote_hash:
            print("[Phoenix] Already up to date: " + os.path.basename(local_path))
            return True

    with open(local_path, "wb") as f:
        f.write(content)
    print("[Phoenix] Downloaded latest: " + os.path.basename(local_path))
    return True


def _run_file(path):
    if not os.path.exists(path):
        cmds.warning("[Phoenix] File not found: " + path)
        return
    with open(path, "r") as f:
        code = f.read()
    exec(compile(code, path, "exec"), {"__file__": path})


# ── commands ──────────────────────────────────────────────────────────────────

def cmd_update(*_):
    print("[Phoenix] Checking update.py ...")
    if _check_and_download(UPDATE_URL, UPDATE_FILE):
        _run_file(UPDATE_FILE)
    else:
        cmds.warning("[Phoenix] Update failed — could not fetch file.")


def cmd_update_and_clean(*_):
    print("[Phoenix] Checking update_and_clear.py ...")
    if _check_and_download(UPDATE_CLEAN_URL, UPDATE_CLEAN_FILE):
        _run_file(UPDATE_CLEAN_FILE)
    else:
        cmds.warning("[Phoenix] Update failed — could not fetch file.")


def cmd_assign_shortcut(*_):
    print("[Phoenix] Running assignshortcutcustom.py ...")
    _run_file(SHORTCUT_FILE)


# ── menu install ──────────────────────────────────────────────────────────────

def install():
    edit_menu = mel.eval("$tmp = $gMainEditMenu")
    mel.eval('buildEditMenu "' + edit_menu + '"')

    for item_id in ["phoenixTool_divider", "phoenixTool_subMenu"]:
        if cmds.menuItem(item_id, query=True, exists=True):
            cmds.deleteUI(item_id, menuItem=True)

    cmds.menuItem("phoenixTool_divider",
                  divider=True,
                  dividerLabel="Phoenix",
                  parent=edit_menu)

    phoenix_sub = cmds.menuItem("phoenixTool_subMenu",
                                label="Phoenix Tool",
                                subMenu=True,
                                tearOff=True,
                                parent=edit_menu)

    panel_sub = cmds.menuItem("phoenixTool_panelSubMenu",
                              label="PhoenixPanel",
                              subMenu=True,
                              tearOff=True,
                              parent=phoenix_sub)

    cmds.menuItem("phoenixTool_update",
                  label="Update",
                  annotation="Check for updates and run update.py",
                  parent=panel_sub,
                  command=cmd_update)

    cmds.menuItem("phoenixTool_updateClean",
                  label="Update and Clean",
                  annotation="Check for updates and run update_and_clear.py",
                  parent=panel_sub,
                  command=cmd_update_and_clean)

    cmds.menuItem(divider=True, parent=panel_sub)

    cmds.menuItem("phoenixTool_assignShortcut",
                  label="Assign Shortcut",
                  annotation="Run assignshortcutcustom.py",
                  parent=panel_sub,
                  command=cmd_assign_shortcut)

    print("[Phoenix] Edit menu installed. Maya dir: " + MAYA_APP_DIR)


utils.executeDeferred(install)