#!/usr/bin/env python3
"""Refresh the NotebookLM session jar from a locally signed-in Firefox profile.

Google rejects a cookie set that is not coherent for the host it is sent to
(``accounts.google.com/CookieMismatch``) — a jar that mixes several profiles or
accounts, or that carries ``.google.com.hk`` alongside ``.google.com``, fails
even when the session is valid. So this script builds the jar from ONE Firefox
cookies.sqlite, keeps only the host set NotebookLM actually needs, writes
``~/.notebooklm/profiles/default/storage_state.json`` and verifies it with a
live ``nlm.py notebook list`` RPC before optionally pushing it to GitHub
secrets as ``NLM_STORAGE_STATE_GZ`` (used by the CI digest runs).

Usage:
    python3 nlm_cookie_sync.py                       # refresh + verify
    python3 nlm_cookie_sync.py owner/repo [owner/repo2]
"""
from __future__ import annotations

import base64
import gzip
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from datetime import datetime

HOME = os.path.expanduser("~")
STORAGE = os.path.join(HOME, ".notebooklm", "profiles", "default",
                       "storage_state.json")
NLM = os.environ.get("NOTEBOOKLM_CLI") or os.path.join(HOME, ".hermes",
                                                      "scripts", "nlm.py")

# Firefox profiles, most-likely-signed-into-NotebookLM first.
PROFILES = [
    os.path.join(HOME, "snap/firefox/common/.mozilla/firefox/8npethg8.default",
                 "cookies.sqlite"),
    "/mnt/windows/Users/Peter/AppData/Roaming/Mozilla/Firefox/Profiles/"
    "tv0zh0s7.default-release/cookies.sqlite",
]
# Hosts NotebookLM needs (all end in google.com — never *.google.com.hk).
KEEP_HOSTS = {".google.com", "accounts.google.com", ".notebooklm.google.com",
              "notebooklm.google.com", "www.google.com",
              "myaccount.google.com"}


def log(m: str) -> None:
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {m}", flush=True)


def read_jar(path: str) -> list[dict]:
    tmp = tempfile.mktemp(suffix=".sqlite")
    shutil.copy2(path, tmp)
    for suffix in ("-wal", "-shm"):
        if os.path.exists(path + suffix):
            shutil.copy2(path + suffix, tmp + suffix)
    con = sqlite3.connect(tmp)
    try:
        con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        rows = con.execute(
            "SELECT host,name,value,path,expiry,isSecure,isHttpOnly "
            "FROM moz_cookies WHERE host LIKE '%google.com'").fetchall()
    finally:
        con.close()
        for suffix in ("", "-wal", "-shm"):
            if os.path.exists(tmp + suffix):
                os.unlink(tmp + suffix)
    cookies = []
    for host, name, value, cpath, expiry, secure, http_only in rows:
        if host not in KEEP_HOSTS:
            continue
        try:
            exp = int(expiry or -1)
        except Exception:
            exp = -1
        if exp > 253402300799:      # Firefox stores ms; Playwright wants s
            exp //= 1000
        if exp <= 0:
            exp = -1
        cookies.append({"name": name, "value": value, "domain": host,
                        "path": cpath or "/", "expires": exp,
                        "secure": bool(secure), "httpOnly": bool(http_only),
                        "sameSite": "Lax"})
    return cookies


def verify() -> bool:
    r = subprocess.run([sys.executable, NLM, "notebook", "list"],
                       capture_output=True, text=True, timeout=240)
    if '"s": "ok"' in r.stdout:
        try:
            n = len(json.loads(r.stdout).get("notebooks", []))
        except Exception:
            n = -1
        log(f"NLM RPC OK — {n} notebook(s) reachable")
        return True
    log(f"NLM RPC FAILED: {(r.stdout + r.stderr)[:280]}")
    return False


def main() -> int:
    repos = [a for a in sys.argv[1:] if "/" in a]
    for path in PROFILES:
        if not os.path.exists(path):
            log(f"skip missing profile {path}")
            continue
        try:
            cookies = read_jar(path)
        except Exception as e:  # noqa: BLE001
            log(f"read failed {path}: {type(e).__name__}: {e}")
            continue
        log(f"{os.path.basename(os.path.dirname(path))}: {len(cookies)} cookie(s)")
        if len(cookies) < 10:
            continue
        if os.path.exists(STORAGE):
            shutil.copy2(STORAGE, STORAGE + ".bak")
        os.makedirs(os.path.dirname(STORAGE), exist_ok=True)
        with open(STORAGE, "w") as f:
            json.dump({"cookies": cookies, "origins": []}, f)
        os.chmod(STORAGE, 0o600)
        if verify():
            if repos:
                blob = base64.b64encode(gzip.compress(
                    json.dumps({"cookies": cookies, "origins": []},
                               separators=(",", ":")).encode(), 9)).decode()
                log(f"secret blob {len(blob)} chars")
                rc = 0
                for repo in repos:
                    p = subprocess.run(
                        ["gh", "secret", "set", "NLM_STORAGE_STATE_GZ", "-R",
                         repo, "--body", blob],
                        capture_output=True, text=True)
                    log(f"push {repo}: "
                        f"{'ok' if p.returncode == 0 else p.stderr[:150]}")
                    rc |= p.returncode
                return rc
            return 0
        log("jar did not verify — trying next profile")
    log("no usable NotebookLM jar found")
    return 2


if __name__ == "__main__":
    sys.exit(main())
