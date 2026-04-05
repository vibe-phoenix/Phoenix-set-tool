# assignShortcutCustom.py
# Place in: C:\Users\<user>\OneDrive\Documents\maya\phoenixtools\PhoenixPanel-updater\

import maya.cmds as cmds
import maya.mel  as mel

try:
    from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout,
                                   QLabel, QLineEdit, QPushButton)
    from PySide6.QtCore    import Qt
    from PySide6.QtGui     import QFont
except ImportError:
    from PySide2.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout,
                                   QLabel, QLineEdit, QPushButton)
    from PySide2.QtCore    import Qt
    from PySide2.QtGui     import QFont

try:
    import maya.OpenMayaUI as omui
    from shiboken6 import wrapInstance
except ImportError:
    try:
        from shiboken2 import wrapInstance
        import maya.OpenMayaUI as omui
    except ImportError:
        omui         = None
        wrapInstance = None


# ─── Constants ────────────────────────────────────────────────────────────────

VALID_SINGLE_KEYS = set(
    list('abcdefghijklmnopqrstuvwxyz') +
    list('0123456789') +
    ['space', 'tab', 'backspace', 'delete', 'insert',
     'home', 'end', 'pageup', 'pagedown',
     'left', 'right', 'up', 'down', 'escape', 'enter', 'return']
)

QT_KEY_MAP = {
    Qt.Key_Space:     'space',    Qt.Key_Tab:      'tab',
    Qt.Key_Backspace: 'backspace',Qt.Key_Delete:   'delete',
    Qt.Key_Insert:    'insert',   Qt.Key_Home:     'home',
    Qt.Key_End:       'end',      Qt.Key_PageUp:   'pageup',
    Qt.Key_PageDown:  'pagedown', Qt.Key_Left:     'left',
    Qt.Key_Right:     'right',    Qt.Key_Up:       'up',
    Qt.Key_Down:      'down',     Qt.Key_Escape:   'escape',
    Qt.Key_Return:    'return',   Qt.Key_Enter:    'return',
}

MAYA_MOD_FLAGS = {
    'ctrl':  {'ctl': True},
    'shift': {'sht': True},
    'alt':   {'alt': True},
}

MONO = '"Courier New", monospace'


# ─── Hotkey conflict checker ──────────────────────────────────────────────────

def get_existing_hotkey_name(trigger, mods):
    """
    Query Maya for whatever nameCommand is on this combo.
    Correct MEL syntax: hotkey -query -ctl -sht -name "key"
    Returns the command name string, or None if unbound.
    """
    mod_flags = ''
    if 'ctrl'  in mods: mod_flags += ' -ctl'
    if 'shift' in mods: mod_flags += ' -sht'
    if 'alt'   in mods: mod_flags += ' -alt'

    mel_cmd = 'hotkey -query{} -name "{}"'.format(mod_flags, trigger)
    print('[Phoenix] Querying hotkey:', mel_cmd)
    try:
        result = mel.eval(mel_cmd)
        print('[Phoenix] Existing binding:', repr(result))
        if result and result.strip():
            return result.strip()
    except Exception as e:
        print('[Phoenix] Query failed:', e)
    return None


# ─── Shared stylesheet ────────────────────────────────────────────────────────

BASE_STYLE = '''
    QDialog {{
        background: #16161c;
    }}
    QLabel#title {{
        font-family: {mono};
        font-size: 22px;
        font-weight: 900;
        letter-spacing: 7px;
        color: #e8a020;
    }}
    QLabel#sub {{
        font-family: {mono};
        font-size: 13px;
        font-weight: 700;
        color: #50505d;
        letter-spacing: 1px;
    }}
    QLabel#fieldLabel {{
        font-family: {mono};
        font-size: 12px;
        font-weight: 900;
        letter-spacing: 5px;
        color: #383848;
    }}
    QLabel#hintLbl {{
        font-family: {mono};
        font-size: 12px;
        font-weight: 700;
        color: #333340;
        letter-spacing: 1px;
    }}
    QLineEdit#hotkeyField {{
        background: #0c0c12;
        border: 2px solid #252535;
        border-radius: 6px;
        color: #e8a020;
        font-family: {mono};
        font-size: 22px;
        font-weight: 900;
        letter-spacing: 5px;
        padding: 0 18px;
    }}
    QLineEdit#hotkeyField:focus {{
        border: 2px solid #3a3a55;
    }}
    QLineEdit#hotkeyField[state="captured"] {{
        border: 2px solid #e8a020;
        color: #e8a020;
    }}
    QLineEdit#hotkeyField[state="error"] {{
        border: 2px solid #ff6060;
        color: #ff6060;
    }}
    QPushButton#clearBtn {{
        background: #0c0c12;
        border: 2px solid #252535;
        border-radius: 6px;
        color: #454555;
        font-size: 20px;
        font-weight: 900;
    }}
    QPushButton#clearBtn:hover {{
        border-color: #ff6060;
        color: #ff6060;
        background: #1a0c0c;
    }}
    QPushButton#clearBtn:pressed {{ background: #2a1010; }}
    QLabel#warn {{
        font-family: {mono};
        font-size: 12px;
        font-weight: 700;
        color: #ff6060;
        letter-spacing: 1px;
    }}
    QPushButton#cancelBtn {{
        background: transparent;
        border: 2px solid #252535;
        border-radius: 6px;
        color: #454555;
        font-family: {mono};
        font-size: 13px;
        font-weight: 700;
        letter-spacing: 3px;
    }}
    QPushButton#cancelBtn:hover {{
        border-color: #606070;
        color: #909098;
    }}
    QPushButton#assignBtn {{
        background: #e8a020;
        border: none;
        border-radius: 6px;
        color: #0c0c12;
        font-family: {mono};
        font-size: 13px;
        font-weight: 900;
        letter-spacing: 3px;
    }}
    QPushButton#assignBtn:hover  {{ background: #f5b535; }}
    QPushButton#assignBtn:pressed {{ background: #c88010; }}
'''.format(mono=MONO)


# ─── Key capture field ────────────────────────────────────────────────────────

class HotkeyField(QLineEdit):

    def __init__(self, parent=None):
        super(HotkeyField, self).__init__(parent)
        self.setReadOnly(True)
        self._modifiers = []
        self._trigger   = None
        self._valid     = False

    def get_combo(self):
        return self._modifiers, self._trigger

    def clear_combo(self):
        self._modifiers = []
        self._trigger   = None
        self._valid     = False
        self.clear()
        self._set_state('idle')

    def _set_state(self, state):
        self.setProperty('state', state)
        self.style().unpolish(self)
        self.style().polish(self)

    def keyPressEvent(self, event):
        key      = event.key()
        mod_bits = event.modifiers()

        mods = []
        if mod_bits & Qt.ControlModifier: mods.append('ctrl')
        if mod_bits & Qt.ShiftModifier:   mods.append('shift')
        if mod_bits & Qt.AltModifier:     mods.append('alt')

        # Pure modifier key held
        if key in (Qt.Key_Control, Qt.Key_Shift, Qt.Key_Alt,
                   Qt.Key_Meta, Qt.Key_AltGr):
            partial = ('  +  '.join(m.upper() for m in mods) + '  +  ...') if mods else '...'
            self.setText(partial)
            self._valid   = False
            self._trigger = None
            self._set_state('idle')
            return

        # Block function keys
        if Qt.Key_F1 <= key <= Qt.Key_F35:
            self.setText('Function keys are not supported')
            self._valid   = False
            self._trigger = None
            self._set_state('error')
            return

        # Resolve trigger
        if key in QT_KEY_MAP:
            trigger = QT_KEY_MAP[key]
        elif Qt.Key_A <= key <= Qt.Key_Z:
            trigger = chr(key).lower()
        elif Qt.Key_0 <= key <= Qt.Key_9:
            trigger = chr(key)
        else:
            self.setText('Unsupported key')
            self._valid   = False
            self._trigger = None
            self._set_state('error')
            return

        self._modifiers = mods
        self._trigger   = trigger
        self._valid     = True
        self.setText(('  +  '.join(mods + [trigger])).upper())
        self._set_state('captured')

    def keyReleaseEvent(self, event):
        pass


# ─── Overwrite confirmation dialog ───────────────────────────────────────────

class OverwriteDialog(QDialog):

    def __init__(self, combo_str, existing_cmd, parent=None):
        super(OverwriteDialog, self).__init__(parent)
        self.setWindowTitle('Phoenix — Shortcut Conflict')
        self.setFixedSize(500, 280)
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
        self._build_ui(combo_str, existing_cmd)
        self.setStyleSheet(BASE_STYLE + '''
            QLabel#conflictTitle {{
                font-family: {mono};
                font-size: 16px;
                font-weight: 900;
                letter-spacing: 4px;
                color: #ff6060;
            }}
            QLabel#conflictBody {{
                font-family: {mono};
                font-size: 13px;
                font-weight: 700;
                color: #707080;
                letter-spacing: 1px;
            }}
            QLabel#conflictCombo {{
                font-family: {mono};
                font-size: 20px;
                font-weight: 900;
                letter-spacing: 4px;
                color: #e8a020;
            }}
            QLabel#conflictCmd {{
                font-family: {mono};
                font-size: 14px;
                font-weight: 700;
                letter-spacing: 2px;
                color: #ff6060;
            }}
            QPushButton#overwriteBtn {{
                background: #ff6060;
                border: none;
                border-radius: 6px;
                color: #0c0c12;
                font-family: {mono};
                font-size: 13px;
                font-weight: 900;
                letter-spacing: 3px;
            }}
            QPushButton#overwriteBtn:hover   {{ background: #ff8080; }}
            QPushButton#overwriteBtn:pressed {{ background: #dd3030; }}
        '''.format(mono=MONO))

    def _build_ui(self, combo_str, existing_cmd):
        root = QVBoxLayout(self)
        root.setContentsMargins(30, 26, 30, 26)
        root.setSpacing(8)

        t = QLabel('WARNING  —  SHORTCUT CONFLICT')
        t.setObjectName('conflictTitle')
        root.addWidget(t)

        root.addSpacing(4)

        body1 = QLabel('This shortcut is already assigned to:')
        body1.setObjectName('conflictBody')
        root.addWidget(body1)

        combo_lbl = QLabel(combo_str)
        combo_lbl.setObjectName('conflictCombo')
        root.addWidget(combo_lbl)

        body2 = QLabel('Currently used by:')
        body2.setObjectName('conflictBody')
        root.addWidget(body2)

        cmd_lbl = QLabel(existing_cmd)
        cmd_lbl.setObjectName('conflictCmd')
        cmd_lbl.setWordWrap(True)
        root.addWidget(cmd_lbl)

        root.addSpacing(4)

        body3 = QLabel('Do you want to overwrite it with Phoenix Panel?')
        body3.setObjectName('conflictBody')
        root.addWidget(body3)

        root.addStretch()

        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)

        keep = QPushButton('KEEP EXISTING')
        keep.setObjectName('cancelBtn')
        keep.setFixedHeight(44)
        keep.clicked.connect(self.reject)

        overwrite = QPushButton('OVERWRITE')
        overwrite.setObjectName('overwriteBtn')
        overwrite.setFixedHeight(44)
        overwrite.clicked.connect(self.accept)

        btn_row.addWidget(keep)
        btn_row.addWidget(overwrite)
        root.addLayout(btn_row)


# ─── Main Dialog ──────────────────────────────────────────────────────────────

class AssignShortcutDialog(QDialog):

    def __init__(self, parent=None):
        super(AssignShortcutDialog, self).__init__(parent)
        self.setWindowTitle('Phoenix — Assign Shortcut')
        self.setFixedSize(560, 380)
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
        self._build_ui()
        self.setStyleSheet(BASE_STYLE)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(32, 28, 32, 28)
        root.setSpacing(0)

        title = QLabel('PHOENIX PANEL')
        title.setObjectName('title')
        root.addWidget(title)

        sub = QLabel('Assign a custom shortcut to open the panel')
        sub.setObjectName('sub')
        root.addWidget(sub)

        root.addSpacing(22)

        lbl = QLabel('PRESS YOUR SHORTCUT')
        lbl.setObjectName('fieldLabel')
        root.addWidget(lbl)

        root.addSpacing(6)

        # Hint label — full text, wraps, never truncated
        self.hint_lbl = QLabel(
            'Click the field, then press your combo  —  e.g.  CTRL + SHIFT + SPACE'
        )
        self.hint_lbl.setObjectName('hintLbl')
        self.hint_lbl.setWordWrap(True)
        root.addWidget(self.hint_lbl)

        root.addSpacing(8)

        # Field + clear button row
        row = QHBoxLayout()
        row.setSpacing(8)

        self.hotkey_field = HotkeyField()
        self.hotkey_field.setObjectName('hotkeyField')
        self.hotkey_field.setFixedHeight(58)
        self.hotkey_field.textChanged.connect(
            lambda t: self.hint_lbl.setVisible(not bool(t))
        )

        self.clear_btn = QPushButton('X')
        self.clear_btn.setObjectName('clearBtn')
        self.clear_btn.setFixedSize(58, 58)
        self.clear_btn.clicked.connect(self._on_clear)

        row.addWidget(self.hotkey_field)
        row.addWidget(self.clear_btn)
        root.addLayout(row)

        root.addSpacing(10)

        self.warn_label = QLabel('')
        self.warn_label.setObjectName('warn')
        self.warn_label.setWordWrap(True)
        root.addWidget(self.warn_label)

        root.addStretch()

        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)

        self.cancel_btn = QPushButton('CANCEL')
        self.cancel_btn.setObjectName('cancelBtn')
        self.cancel_btn.setFixedHeight(44)
        self.cancel_btn.clicked.connect(self.reject)

        self.assign_btn = QPushButton('ASSIGN SHORTCUT')
        self.assign_btn.setObjectName('assignBtn')
        self.assign_btn.setFixedHeight(44)
        self.assign_btn.clicked.connect(self._on_assign)

        btn_row.addWidget(self.cancel_btn)
        btn_row.addWidget(self.assign_btn, stretch=2)
        root.addLayout(btn_row)

    def _on_clear(self):
        self.hotkey_field.clear_combo()
        self.warn_label.setText('')
        self.hint_lbl.setVisible(True)

    def _on_assign(self):
        mods, trigger = self.hotkey_field.get_combo()

        if not trigger:
            self.warn_label.setText('No shortcut captured — click the field and press a key combo.')
            return

        self.warn_label.setText('')

        combo_str = ('  +  '.join(mods + [trigger])).upper()

        # ── Conflict check ─────────────────────────────────────────────────
        existing = get_existing_hotkey_name(trigger, mods)

        if existing and existing not in ('OpenPhoenixPanelNameCmd', ''):
            dlg    = OverwriteDialog(combo_str, existing, self)
            result = dlg.exec_() if hasattr(dlg, 'exec_') else dlg.exec()
            if not result:
                self.warn_label.setText('Cancelled — pick a different shortcut.')
                return

        # ── Register ───────────────────────────────────────────────────────
        hotkey_flags = {}
        for m in mods:
            hotkey_flags.update(MAYA_MOD_FLAGS[m])

        runtime_cmd_name = 'OpenPhoenixPanel'

        try:
            cmds.hotkey(keyShortcut=trigger, name='', releaseName='', **hotkey_flags)
        except Exception:
            pass

        if cmds.runTimeCommand(runtime_cmd_name, exists=True):
            cmds.runTimeCommand(runtime_cmd_name, edit=True, delete=True)

        cmds.runTimeCommand(
            runtime_cmd_name,
            annotation='Open Phoenix Panel',
            category='User',
            commandLanguage='python',
            command='import phoenix_panel\nphoenix_panel.open_phoenix_panel()'
        )

        named_cmd = cmds.nameCommand(
            runtime_cmd_name + 'NameCmd',
            annotation='Open Phoenix Panel',
            command=runtime_cmd_name,
            sourceType='mel'
        )

        cmds.hotkey(keyShortcut=trigger, name=named_cmd, **hotkey_flags)

        print('[Phoenix] {} -> open_phoenix_panel() assigned.'.format(combo_str))
        self.accept()


# ─── Entry point ─────────────────────────────────────────────────────────────

def open_assign_shortcut_custom():
    parent = None
    if omui and wrapInstance:
        try:
            ptr    = omui.MQtUtil.mainWindow()
            parent = wrapInstance(int(ptr), QDialog.__bases__[0])
        except Exception:
            pass

    dlg = AssignShortcutDialog(parent)
    dlg.exec_() if hasattr(dlg, 'exec_') else dlg.exec()


open_assign_shortcut_custom()