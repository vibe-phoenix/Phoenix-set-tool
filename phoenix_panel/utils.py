# -*- coding: utf-8 -*-
"""Utility helpers for PhoenixPanel (Qt detection, config paths, icons)."""

from __future__ import annotations

import os

# Defer heavy imports until actually needed
_MAYA_IMPORTS_LOADED = False
_QT_IMPORTS_LOADED = False

# Caches
_ICON_CACHE = {}
_MAX_CACHE_SIZE = 200
_MAYA_MAIN_WINDOW = None


def _ensure_maya_imports():
    """Lazy-load Maya imports only when needed."""
    global _MAYA_IMPORTS_LOADED
    if not _MAYA_IMPORTS_LOADED:
        global cmds, omui
        import maya.cmds as cmds_module
        import maya.OpenMayaUI as omui_module
        cmds = cmds_module
        omui = omui_module
        _MAYA_IMPORTS_LOADED = True


def _ensure_qt_imports():
    """Lazy-load Qt imports only when needed."""
    global _QT_IMPORTS_LOADED
    if not _QT_IMPORTS_LOADED:
        global QtWidgets, QtCore, QtGui, shiboken
        try:
            from PySide6 import QtWidgets as qw, QtCore as qc, QtGui as qg
            import shiboken6 as sh
        except ImportError:
            from PySide2 import QtWidgets as qw, QtCore as qc, QtGui as qg
            import shiboken2 as sh
        
        QtWidgets = qw
        QtCore = qc
        QtGui = qg
        shiboken = sh
        _QT_IMPORTS_LOADED = True


def get_maya_main_window():
    """Return Maya main window as QWidget, or None. Cached after first call."""
    global _MAYA_MAIN_WINDOW
    
    if _MAYA_MAIN_WINDOW is not None:
        return _MAYA_MAIN_WINDOW
    
    _ensure_maya_imports()
    _ensure_qt_imports()
    
    ptr = omui.MQtUtil.mainWindow()
    if ptr:
        _MAYA_MAIN_WINDOW = shiboken.wrapInstance(int(ptr), QtWidgets.QWidget)
    return _MAYA_MAIN_WINDOW


def get_config_path():
    """Return path to PhoenixPanel config JSON in userAppDir."""
    _ensure_maya_imports()
    return os.path.join(cmds.internalVar(userAppDir=True), "PhoenixPanel_config.json")


def resolve_maya_icon(icon_name):
    """Try to resolve a Maya icon name/path to a QIcon with aggressive caching.

    Priority:
    - Cache hit (instant)
    - Direct file path
    - Maya/Qt resource (:/)
    - Fallback colored square
    """
    # Check cache FIRST - fastest path
    if icon_name in _ICON_CACHE:
        return _ICON_CACHE[icon_name]
    
    # Clear cache if too large (prevent memory bloat)
    if len(_ICON_CACHE) > _MAX_CACHE_SIZE:
        # Keep 50% most recent entries
        keys = list(_ICON_CACHE.keys())
        for k in keys[:len(keys)//2]:
            del _ICON_CACHE[k]
    
    _ensure_qt_imports()

    if not icon_name:
        return QtGui.QIcon()

    # Direct path (check file existence only if it looks like a path)
    if "/" in icon_name or "\\" in icon_name:
        if os.path.exists(icon_name):
            icon = QtGui.QIcon(icon_name)
            _ICON_CACHE[icon_name] = icon
            return icon

    # Qt resource / Maya icon (most common case)
    qicon = QtGui.QIcon(":/{}".format(icon_name))
    if not qicon.isNull():
        _ICON_CACHE[icon_name] = qicon
        return qicon

    # Fallback colored square (create once, cache forever)
    if "__fallback__" in _ICON_CACHE:
        return _ICON_CACHE["__fallback__"]
    
    pm = QtGui.QPixmap(32, 32)
    pm.fill(QtGui.QColor("#50586B"))
    icon = QtGui.QIcon(pm)
    _ICON_CACHE["__fallback__"] = icon
    _ICON_CACHE[icon_name] = icon
    return icon


def clear_icon_cache():
    """Clear the icon cache. Useful for debugging or manual cleanup."""
    global _ICON_CACHE
    _ICON_CACHE.clear()