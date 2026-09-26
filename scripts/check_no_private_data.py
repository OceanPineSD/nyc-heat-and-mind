#!/usr/bin/env python3
"""Private-data guard.

Scope (amendment A1): the files git would publish, i.e. the output of
`git ls-files --cached --others --exclude-standard`. Gitignored files are out
of scope; force-added files are in scope since --cached lists them.

Configuration lives outside the repo (amendment A8.1), in the JSON file named
by the HM_PRIVATE_GUARD_CONFIG environment variable, defaulting to
~/.config/nyc-heat-and-mind/private-guard.json:

    {"private_dir": "/path/to/private/folder", "banned_strings": ["...", ...]}

Exit codes:
  0  no private data found
  1  an in-scope file is byte-identical to a file under private_dir, or its
     path or content contains a banned string (case-insensitive, no exemptions)
  2  config missing, unreadable or malformed (fail closed)

The private folder is only read and hashed; nothing is copied from it.
"""
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ENV = "HM_PRIVATE_GUARD_CONFIG"
DEFAULT_CONFIG = Path.home() / ".config" / "nyc-heat-and-mind" / "private-guard.json"


class ConfigError(Exception):
    pass


def load_config():
    path = Path(os.environ.get(ENV) or DEFAULT_CONFIG).expanduser()
    try:
        cfg = json.loads(path.read_text())
    except (OSError, ValueError) as e:
        raise ConfigError(f"cannot read guard config {path}: {e}") from e
    private = cfg.get("private_dir") if isinstance(cfg, dict) else None
    banned = cfg.get("banned_strings") if isinstance(cfg, dict) else None
    if not isinstance(private, str) or not private:
        raise ConfigError(f"guard config {path}: 'private_dir' must be a non-empty string")
    if not isinstance(banned, list) or not banned or not all(isinstance(s, str) and s for s in banned):
        raise ConfigError(f"guard config {path}: 'banned_strings' must be a non-empty list of non-empty strings")
    return path, Path(private).expanduser(), [s.lower().encode() for s in banned]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def publishable():
    out = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=REPO, capture_output=True, check=True,
    ).stdout
    for rel in sorted(set(out.decode().split("\0")) - {""}):
        p = REPO / rel
        if p.is_file() and not p.is_symlink():
            yield p


def walk(root: Path):
    for dirpath, dirnames, filenames in os.walk(root):
        for name in filenames:
            p = Path(dirpath) / name
            if p.is_file() and not p.is_symlink():
                yield p


def main() -> int:
    try:
        cfg_path, private_dir, banned = load_config()
    except ConfigError as e:
        print(f"ERROR: {e}")
        print(f"Set {ENV} or create {DEFAULT_CONFIG}. Failing closed.")
        return 2

    if not private_dir.is_dir():
        print("FAIL: private folder from guard config not found")
        return 1
    private = {}
    for p in walk(private_dir):
        private.setdefault(sha256(p), []).append(p)
    if not private:
        print("FAIL: private folder from guard config is empty")
        return 1

    problems = []
    n = 0
    for p in publishable():
        n += 1
        rel = p.relative_to(REPO)
        # Messages give the repo path and banned-string index only, so guard
        # output never repeats the private names themselves.
        if sha256(p) in private:
            problems.append(f"hash match: {rel} is byte-identical to a private file")
        path_l = str(rel).lower().encode()
        data = p.read_bytes().lower()
        for i, s in enumerate(banned):
            if s in path_l:
                problems.append(f"banned string #{i} in path {rel}")
            if s in data:
                problems.append(f"banned string #{i} in content of {rel}")

    print(f"config {cfg_path.name}: {len(banned)} banned strings")
    print(f"scanned {n} repo files against {sum(len(v) for v in private.values())} private files")
    if problems:
        for msg in problems:
            print("FAIL:", msg)
        return 1
    print("PASS: no private data found")
    return 0


if __name__ == "__main__":
    sys.exit(main())
