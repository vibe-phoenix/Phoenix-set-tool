import maya.cmds as cmds

# Ensure we're on a writable hotkey set
current_set = cmds.hotkeySet(query=True, current=True)
if current_set == 'Maya_Default':
    # Create a custom set if it doesn't exist
    all_sets = cmds.hotkeySet(query=True, hotkeySetArray=True) or []
    if 'PhoenixHotkeys' not in all_sets:
        cmds.hotkeySet('PhoenixHotkeys', source='Maya_Default')
    cmds.hotkeySet('PhoenixHotkeys', edit=True, current=True)
    print('[Phoenix] Switched to PhoenixHotkeys set.')



import maya.cmds as cmds
import os

try:
    from PySide6.QtWidgets import QMessageBox
except ImportError:
    from PySide2.QtWidgets import QMessageBox

# ─── Clear Ctrl+Space ────────────────────────────────────────────────────────

cmds.hotkey(keyShortcut='space', ctl=True, name='', releaseName='')

# ─── Create the Runtime Command ──────────────────────────────────────────────

runtime_cmd_name = 'OpenPhoenixPanel'

if cmds.runTimeCommand(runtime_cmd_name, exists=True):
    cmds.runTimeCommand(runtime_cmd_name, edit=True, delete=True)

cmds.runTimeCommand(
    runtime_cmd_name,
    annotation='Open Phoenix Panel',
    category='User',
    commandLanguage='python',
    command=(
        'import phoenix_panel\n'
        'phoenix_panel.open_phoenix_panel()'
    )
)

# ─── Create a Named Command and bind it ──────────────────────────────────────

named_cmd = cmds.nameCommand(
    runtime_cmd_name + 'NameCmd',
    annotation='Open Phoenix Panel',
    command=runtime_cmd_name,
    sourceType='mel'
)

# ─── Assign Ctrl+Space ───────────────────────────────────────────────────────

cmds.hotkey(keyShortcut='space', ctl=True, name=named_cmd)
print('[Phoenix] Ctrl+Space → open_phoenix_panel() assigned successfully.')

# ─── Remove bootstrap block from userSetup.py ────────────────────────────────

MARKER_START = 'phoenixshortcutupdaterStart'
MARKER_END   = 'phoenixshortcutupdaterEnd'

username = os.getenv('USERNAME')
usersetup_path = os.path.join(
    'C:\\Users', username,
    'OneDrive', 'Documents', 'maya', 'scripts', 'userSetup.py'
)

if os.path.exists(usersetup_path):

    # Read with universal newlines so \r\n and \n are both handled
    with open(usersetup_path, 'r', newline='') as f:
        raw = f.read()

    # Normalize to \n
    raw = raw.replace('\r\n', '\n').replace('\r', '\n')
    lines = raw.splitlines(keepends=True)

    output       = []
    inside_block = False
    found        = False

    for line in lines:
        if MARKER_START in line:
            inside_block = True
            found        = True
            continue
        if MARKER_END in line:
            inside_block = False
            continue
        if not inside_block:
            output.append(line)

    if found:
        with open(usersetup_path, 'w', newline='\n') as f:
            f.writelines(output)
        print('[Phoenix] Bootstrap block removed from userSetup.py successfully.')
    else:
        print('[Phoenix] Markers not found in userSetup.py — nothing removed.')

else:
    cmds.warning('[Phoenix] userSetup.py not found at: {}'.format(usersetup_path))