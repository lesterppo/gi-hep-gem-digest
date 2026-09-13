#!/usr/bin/env python3
"""Push the local Gemini cookies to this repo's GitHub secrets.

Used by the weekly cookie-refresh cron; the digest itself never needs a local
machine, but the Gemini web session cookies do expire (~30 days), so refreshing
them keeps the CI backend on the web (cookie) path instead of the API fallback.

Usage:
    GEMINI_SID=... GEMINI_TS=... python3 refresh_gh_secrets.py owner/repo
    python3 refresh_gh_secrets.py owner/repo          # reads ~/.gemini-cli/auth.json
"""
import json
import os
import subprocess
import sys

AUTH = os.environ.get("GEMINI_AUTH_JSON",
                      os.path.expanduser("~/.gemini-cli/auth.json"))


def main() -> int:
    repo = sys.argv[1] if len(sys.argv) > 1 else ""
    if not repo:
        print("usage: refresh_gh_secrets.py owner/repo")
        return 2
    sid = os.environ.get("GEMINI_SID", "")
    ts = os.environ.get("GEMINI_TS", "")
    if not sid or not ts:
        try:
            with open(AUTH) as f:
                d = json.load(f)
            sid = d.get("__Secure-1PSID", "")
            ts = d.get("__Secure-1PSIDTS", "")
        except FileNotFoundError:
            print(f"no GEMINI_SID/GEMINI_TS env and no {AUTH}")
            return 2
    if not sid or not ts:
        print("cookie values empty — run `python3 gemini.py --init` first")
        return 2
    rc = 0
    for name, val in (("GEMINI_SID", sid), ("GEMINI_TS", ts)):
        p = subprocess.run(["gh", "secret", "set", name, "-R", repo,
                            "--body", val], capture_output=True, text=True)
        print(f"{repo} {name}: {'ok' if p.returncode == 0 else p.stderr[:160]}")
        rc |= p.returncode
    return rc


if __name__ == "__main__":
    sys.exit(main())
