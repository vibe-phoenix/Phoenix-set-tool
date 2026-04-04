# -*- coding: utf-8 -*-
"""
Phoenix Panel Updater
---------------------
1. Fetches the full file list from GitHub
2. Downloads and updates changed/new files only
3. Compares repo file list against local disk — deletes files on disk
   that no longer exist in the repo (with safety checks)
4. Silently reloads the package in Maya

SAFETY RULES for deletion:
  - Only deletes files INSIDE the phoenix_panel subfolder
  - Never deletes the updater script itself
  - Never deletes the manifest file (.update_manifest.json)
  - Never deletes Maya config files (PhoenixPanel_*.json)
  - Backs up every file to a .trash/ folder before deleting
  - If GitHub fetch fails for any reason, deletion step is SKIPPED entirely
    (we never delete based on a partial or failed repo listing)

Usage in Maya Script Editor (Python):
    exec(open(r"C:/path/to/phoenix_panel_updater.py").read())

Or add to userSetup.py for auto-update on every Maya launch.
"""

from __future__ import annotations

import os
import sys
import json
import shutil
import hashlib
import importlib
import ssl
import time
from urllib.request import urlopen, Request

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------

GITHUB_REPO      = "vibe-phoenix/Phoenix-set-tool"
GITHUB_BRANCH    = "main"
GITHUB_SUBFOLDER = "phoenix_panel"

API_URL  = "https://api.github.com/repos/{}/contents/{}?ref={}".format(
    GITHUB_REPO, GITHUB_SUBFOLDER, GITHUB_BRANCH
)
RAW_BASE = "https://raw.githubusercontent.com/{}/{}/{}/".format(
    GITHUB_REPO, GITHUB_BRANCH, GITHUB_SUBFOLDER
)

# Files that must NEVER be deleted regardless of what the repo says
_PROTECTED_SUFFIXES = (".json",)
_PROTECTED_NAMES    = {".update_manifest.json", "phoenix_panel_updater.py"}

# ---------------------------------------------------------------------------
# INSTALL PATH
# ---------------------------------------------------------------------------

def _get_install_path():
    """Resolve the phoenix_panel folder for any Maya version / OneDrive setup."""
    try:
        import maya.cmds as cmds
        scripts_dir = os.path.normpath(cmds.internalVar(userScriptDir=True))
    except Exception:
        home = os.path.expanduser("~")
        try:
            import maya.cmds as cmds
            ver = cmds.about(version=True).split()[0]
        except Exception:
            ver = "2026"
        for base in [
            os.path.join(home, "OneDrive", "Documents"),
            os.path.join(home, "Documents"),
        ]:
            if os.path.isdir(os.path.join(base, "maya")):
                scripts_dir = os.path.join(base, "maya", ver, "scripts")
                break
        else:
            scripts_dir = os.path.join(home, "Documents", "maya", ver, "scripts")

    install_dir = os.path.join(scripts_dir, GITHUB_SUBFOLDER)
    print("PhoenixPanel Updater: install path → {}".format(install_dir))
    return install_dir

# ---------------------------------------------------------------------------
# NETWORK
# ---------------------------------------------------------------------------

def _fetch(url, retries=3):
    """Download URL as text. Retries with unverified SSL as fallback."""
    headers = {
        "User-Agent":    "PhoenixPanelUpdater/1.0",
        "Accept":        "application/vnd.github.v3+json",
        "Cache-Control": "no-cache",
        "Pragma":        "no-cache",
    }
    last_err = None
    for attempt in range(retries):
        ctx = (ssl.create_default_context()
               if attempt == 0
               else ssl._create_unverified_context())
        try:
            req = Request(url, headers=headers)
            with urlopen(req, timeout=20, context=ctx) as r:
                return r.read().decode("utf-8")
        except Exception as e:
            last_err = e
    print("PhoenixPanel Updater: fetch error — {}".format(last_err))
    return None


def _list_repo_files():
    """Return [(filename, raw_url, git_sha), ...] for files in the repo folder.

    Returns None (not empty list) if the network call itself failed — callers
    must treat None as "do not proceed with deletion".
    """
    raw = _fetch(API_URL)
    if raw is None:
        return None          # <-- explicit None = network failure

    try:
        entries = json.loads(raw)
    except Exception as e:
        print("PhoenixPanel Updater: failed to parse GitHub response — {}".format(e))
        return None

    # Sanity check: the API should return a list
    if not isinstance(entries, list):
        print("PhoenixPanel Updater: unexpected GitHub API response (not a list).")
        return None

    result = []
    for entry in entries:
        if entry.get("type") != "file":
            continue
        name = entry.get("name", "")
        if " " in name:      # spaces break raw URLs (e.g. "update it.ini")
            continue
        result.append((name, RAW_BASE + name, entry.get("sha", "")))

    return result            # may be [] if folder is empty but fetch succeeded

# ---------------------------------------------------------------------------
# MANIFEST
# ---------------------------------------------------------------------------

def _sha256(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _manifest_path(d):
    return os.path.join(d, ".update_manifest.json")


def _load_manifest(d):
    try:
        with open(_manifest_path(d), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_manifest(d, m):
    try:
        os.makedirs(d, exist_ok=True)
        with open(_manifest_path(d), "w", encoding="utf-8") as f:
            json.dump(m, f, indent=2)
    except Exception:
        pass


def _read_local(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return None


def _write_file(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

# ---------------------------------------------------------------------------
# SAFE DELETION
# ---------------------------------------------------------------------------

def _is_protected(filename):
    """Return True if this file must never be deleted."""
    if filename in _PROTECTED_NAMES:
        return True
    if any(filename.endswith(s) for s in _PROTECTED_SUFFIXES):
        return True
    return False


def _backup_and_delete(install_dir, filename):
    """Move file to .trash/<timestamp>/ before deleting so it can be recovered.

    Returns True on success, False if anything went wrong (file is kept).
    """
    src = os.path.join(install_dir, filename)
    if not os.path.isfile(src):
        return True  # already gone, nothing to do

    # Create timestamped trash folder inside install_dir
    trash_dir = os.path.join(install_dir, ".trash",
                             time.strftime("%Y%m%d_%H%M%S"))
    try:
        os.makedirs(trash_dir, exist_ok=True)
        dst = os.path.join(trash_dir, filename)
        shutil.move(src, dst)
        return True
    except Exception as e:
        print("PhoenixPanel Updater: could not move {} to trash — {}  (file kept)".format(
            filename, e))
        return False


def _find_deletable_local_files(install_dir, repo_filenames_set):
    """Return list of filenames that are on disk but not in the repo.

    Only looks at FILES directly inside install_dir — never recurses into
    any subdirectory (so __pycache__, .trash, etc. are always left alone).
    Skips protected files and hidden files (starting with '.').
    """
    deletable = []
    try:
        for entry in os.scandir(install_dir):
            # NEVER touch subdirectories — __pycache__, .trash, etc.
            if not entry.is_file(follow_symlinks=False):
                continue
            name = entry.name
            if name.startswith("."):
                continue          # skip hidden files / manifest
            if _is_protected(name):
                continue          # skip .json, updater script, etc.
            if name not in repo_filenames_set:
                deletable.append(name)
    except Exception as e:
        print("PhoenixPanel Updater: could not scan local folder — {}".format(e))
    return deletable

# ---------------------------------------------------------------------------
# SILENT RELOAD
# ---------------------------------------------------------------------------

def _silent_reload():
    pkg = "phoenix_panel"
    try:
        import phoenix_panel.launcher as _l
        if _l._WINDOW_INSTANCE is not None:
            try:
                _l._WINDOW_INSTANCE.close()
                _l._WINDOW_INSTANCE.deleteLater()
            except Exception:
                pass
            _l._WINDOW_INSTANCE = None
    except Exception:
        pass

    for mod in ["utils", "widgets", "shelf_picker", "settings", "core", "launcher"]:
        full = "{}.{}".format(pkg, mod)
        if full in sys.modules:
            try:
                importlib.reload(sys.modules[full])
            except Exception as e:
                print("PhoenixPanel Updater: reload {} — {}".format(full, e))

    if pkg in sys.modules:
        try:
            importlib.reload(sys.modules[pkg])
        except Exception:
            pass

    try:
        import phoenix_panel.core as _c
        _c._SHELF_PICKER = None
        _c._SETTINGS     = None
    except Exception:
        pass

    try:
        import phoenix_panel.utils as _u
        _u.clear_icon_cache()
        _u._MAYA_MAIN_WINDOW = None
    except Exception:
        pass

# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def update_phoenix_panel(force=False):
    """Sync local phoenix_panel folder with GitHub.

    Steps:
      1. Fetch repo file list  (abort everything if this fails)
      2. Download / update changed files
      3. Delete local files not present in repo  (skipped if step 1 was partial)

    Args:
        force: Re-download every file regardless of hash.
    """
    install_dir = _get_install_path()
    manifest    = _load_manifest(install_dir)

    # ── STEP 1: Get authoritative file list from GitHub ──────────────────
    repo_files = _list_repo_files()

    if repo_files is None:
        # Network failure — do NOT touch any local files
        print("PhoenixPanel Updater: ABORTED — could not reach GitHub. "
              "No files were changed or deleted.")
        return False

    if not repo_files:
        print("PhoenixPanel Updater: WARNING — GitHub returned an empty folder. "
              "Skipping update and deletion to be safe.")
        return False

    print("PhoenixPanel Updater: found {} file(s) in repo — {}".format(
        len(repo_files), ", ".join(n for n, _, _ in repo_files)
    ))

    repo_names = {name for name, _, _ in repo_files}  # set for O(1) lookup

    # ── STEP 2: Download / update ─────────────────────────────────────────
    updated = []
    skipped = []
    failed  = []

    for filename, url, git_sha in repo_files:
        local_path   = os.path.join(install_dir, filename)
        manifest_key = filename + ":git_sha"

        # Fast path via git SHA (no download needed)
        if not force and manifest.get(manifest_key) == git_sha and git_sha:
            skipped.append(filename)
            continue

        remote_content = _fetch(url)
        if remote_content is None:
            failed.append(filename)
            continue

        remote_hash = _sha256(remote_content)

        # Skip if content hash matches manifest
        if not force and manifest.get(filename) == remote_hash:
            manifest[manifest_key] = git_sha
            skipped.append(filename)
            continue

        # Skip if actual local file matches remote content
        if not force:
            local_content = _read_local(local_path)
            if local_content is not None and _sha256(local_content) == remote_hash:
                manifest[filename]     = remote_hash
                manifest[manifest_key] = git_sha
                skipped.append(filename)
                continue

        # Write updated / new file
        try:
            _write_file(local_path, remote_content)
            manifest[filename]     = remote_hash
            manifest[manifest_key] = git_sha
            updated.append(filename)
        except Exception as e:
            print("PhoenixPanel Updater: write error {} — {}".format(filename, e))
            failed.append(filename)

    # ── STEP 3: Delete local files absent from repo ───────────────────────
    # Only run if NO downloads failed (a partial failure means our repo list
    # might be incomplete, so we must not delete based on it).
    deleted        = []
    delete_skipped = []

    if failed:
        print("PhoenixPanel Updater: Skipping deletion step because {} "
              "file(s) failed to download — repo list may be incomplete.".format(
              len(failed)))
    else:
        deletable = _find_deletable_local_files(install_dir, repo_names)
        for filename in deletable:
            if _backup_and_delete(install_dir, filename):
                deleted.append(filename)
                # Remove from manifest too
                manifest.pop(filename, None)
                manifest.pop(filename + ":git_sha", None)
            else:
                delete_skipped.append(filename)

    _save_manifest(install_dir, manifest)

    # ── REPORT ────────────────────────────────────────────────────────────
    anything_changed = bool(updated or deleted)

    print("")
    print("=" * 54)
    print("  PhoenixPanel Updater — Sync Report")
    print("  Repo files : {}".format(len(repo_files)))
    print("  Updated    : {} {}".format(
        len(updated), ("— " + ", ".join(updated)) if updated else "(none)"))
    print("  Unchanged  : {}".format(len(skipped)))
    print("  Deleted    : {} {}".format(
        len(deleted), ("— " + ", ".join(deleted)) if deleted else "(none)"))
    if delete_skipped:
        print("  Del failed : {} (backed up but kept) — {}".format(
            len(delete_skipped), ", ".join(delete_skipped)))
    if failed:
        print("  Fetch fail : {} — {}".format(len(failed), ", ".join(failed)))
    print("=" * 54)

    if anything_changed:
        _silent_reload()
        print("PhoenixPanel Updater: package reloaded silently.")
    else:
        print("PhoenixPanel Updater: already up to date.")

    if deleted:
        print("PhoenixPanel Updater: NOTE — deleted files were backed up to "
              "{}/.trash/".format(install_dir))

    return anything_changed


# Run immediately when exec()'d or imported
update_phoenix_panel()