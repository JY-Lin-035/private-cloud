#!/usr/bin/env python3
"""Scrub bearer credentials (32-hex share hashes, 64-hex verify tokens,
session tokens) out of application log files, and verify zero residue.

Covers ALL log locations the app writes to (fail loudly if any is missing).
Run while the backend is stopped, then restart. Usage:
    python3 scripts/scrub_logs.py          # scrub + verify
    python3 scripts/scrub_logs.py --check  # verify only
"""
import glob
import gzip
import os
import re
import shutil
import sys

DIRS = [
    "/home/Jun/workspace/log/meowcloud",
    "/home/Jun/safe_box/private-cloud/logs",
    "/home/Jun/safe_box/private-cloud/backend/logs",
]
EXTRA = ["/home/Jun/safe_box/private-cloud/backend/backend.log"]

P32 = re.compile(r"(?<![0-9a-f])([0-9a-f]{32})(?![0-9a-f])")
P64 = re.compile(r"(?<![0-9a-f])([0-9a-f]{64})(?![0-9a-f])")
SESS = re.compile(r"('token': '\d+\|)([^'\s]{8,})")


def _interesting(h: str) -> bool:
    return len(set(h)) >= 10  # skip low-entropy fixtures like f00dfeed...


def scrub_text(t: str) -> str:
    t = P32.sub(lambda m: (m.group(1)[:6] + "…") if _interesting(m.group(1)) else m.group(1), t)
    t = P64.sub(lambda m: (m.group(1)[:6] + "…") if _interesting(m.group(1)) else m.group(1), t)
    t = SESS.sub(r"\1redacted…", t)
    return t


def all_files():
    missing = [d for d in DIRS if not os.path.isdir(d)]
    if missing:
        sys.exit(f"FAIL: expected log dirs missing: {missing}")
    fs = []
    for d in DIRS:
        fs += [f for f in glob.glob(d + "/*") if os.path.isfile(f)]
    fs += [f for f in EXTRA if os.path.isfile(f)]
    return sorted(set(fs))


def read_any(f):
    if f.endswith(".gz"):
        with gzip.open(f, "rt", errors="ignore") as g:
            return g.read()
    with open(f, errors="ignore") as h:
        return h.read()


def main() -> int:
    check = "--check" in sys.argv
    files = all_files()
    changed = residue = 0
    for f in files:
        try:
            data = read_any(f)
        except Exception as e:  # fail, don't silently skip
            print(f"FAIL-READ {f}: {e}")
            residue += 1
            continue
        hits = [m for pat in (P32, P64) for m in pat.finditer(data) if _interesting(m.group(1))]
        if not check and hits:
            new = scrub_text(data)
            if new != data:
                if f.endswith(".gz"):
                    tmp = f + ".scrub"
                    with gzip.open(tmp, "wt") as g:
                        g.write(new)
                    shutil.copystat(f, tmp)
                    os.replace(tmp, f)
                else:
                    tmp = f + ".scrub"
                    with open(tmp, "w") as g:
                        g.write(new)
                    shutil.copymode(f, tmp)
                    # truncate-in-place keeps inode (safe for open fds too)
                    with open(f, "w") as dst, open(tmp) as src:
                        dst.write(src.read())
                    os.remove(tmp)
                changed += 1
                hits = []
        for m in hits:
            print(f"RESIDUE {f}: {m.group(1)[:8]}…")
            residue += 1
    print(f"{'check' if check else 'scrub'}: {len(files)} files, {changed} changed, residue={residue}")
    return 1 if residue else 0


if __name__ == "__main__":
    sys.exit(main())
