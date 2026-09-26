#!/usr/bin/env python3
"""Mutation test for check_no_private_data.py. Prints a markdown result table.

Default mode uses synthetic fixtures only (amendment A8.1): a temp dir as the
fake private folder holding one generated file, a temp config pointed to by
HM_PRIVATE_GUARD_CONFIG, and a made-up marker string.

--real runs the same table against the real guard config (HM_PRIVATE_GUARD_CONFIG
or the default path). The sample file, banned string and folder name are all
read from that config at run time, so no private name appears in this file.

M1/M2/M4/M5 temporarily place the sample file inside the repo and delete it
right after the check (amendment A2); M3 temporarily edits README.md and
restores it; M5 force-adds the file to the index and unstages it afterwards;
M7 writes a temporary untracked file and deletes it.
"""
import json
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
GUARD = REPO / "scripts" / "check_no_private_data.py"
ENV = "HM_PRIVATE_GUARD_CONFIG"
DEFAULT_CONFIG = Path.home() / ".config" / "nyc-heat-and-mind" / "private-guard.json"


def run(config: Path) -> int:
    env = {**os.environ, ENV: str(config)}
    return subprocess.run([sys.executable, str(GUARD)], env=env, capture_output=True).returncode


def git(*args):
    subprocess.run(["git", *args], cwd=REPO, check=True, capture_output=True)


def with_copy(config: Path, sample: Path, dst: Path, force_add=False) -> int:
    shutil.copyfile(sample, dst)
    try:
        if force_add:
            git("add", "-f", str(dst.relative_to(REPO)))
        return run(config)
    finally:
        if force_add:
            git("rm", "--cached", "-q", str(dst.relative_to(REPO)))
        dst.unlink()


def with_text(config: Path, dst: Path, text: str) -> int:
    dst.write_text(text)
    try:
        return run(config)
    finally:
        dst.unlink()


def table(config: Path, sample: Path, marker: str, folder: str) -> int:
    rows = []
    rows.append(("M0", "clean repo", 0, run(config)))

    code = with_copy(config, sample, REPO / "web" / "public" / "data" / "m1_sample.bin")
    rows.append(("M1", "private sample file copied into web/public/data/", 1, code))

    code = with_copy(config, sample, REPO / "pipeline" / "renamed_sample.txt")
    rows.append(("M2", "same file renamed to pipeline/renamed_sample.txt", 1, code))

    readme = REPO / "README.md"
    original = readme.read_bytes()
    readme.write_bytes(original + f"\nData also from {marker.upper()}.\n".encode())
    try:
        code = run(config)
    finally:
        readme.write_bytes(original)
    rows.append(("M3", "README line containing a banned string (upper-cased)", 1, code))

    code = with_copy(config, sample, REPO / "data" / "raw" / "m4_sample.bin")
    rows.append(("M4", "same file in data/raw/ (gitignored)", 0, code))

    code = with_copy(config, sample, REPO / "data" / "raw" / "m5_sample.bin", force_add=True)
    rows.append(("M5", "same file in data/raw/, git add -f", 1, code))

    code = run(config.parent / "no-such-config.json")
    rows.append(("M6", "config missing", 2, code))

    code = with_text(config, REPO / "pipeline" / "m7_note.txt", f"see {folder}\n")
    rows.append(("M7", "untracked pipeline/m7_note.txt naming one private folder", 1, code))

    print("| Case | Mutation | Expected | Exit | Result |")
    print("|---|---|---|---|---|")
    names = {0: "PASS (0)", 1: "FAIL (1)", 2: "CONFIG ERROR (2)"}
    for case, what, exp, code in rows:
        print(f"| {case} | {what} | {names[exp]} | {code} | {'ok' if code == exp else 'DEFECT'} |")
    return 0 if all(code == exp for _, _, exp, code in rows) else 1


def synthetic() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        marker = f"zq-marker-{secrets.token_hex(4)}"
        folder = f"zq-folder-{secrets.token_hex(4)}"
        private = tmp / "private"
        (private / folder).mkdir(parents=True)
        sample = private / folder / "generated.bin"
        sample.write_bytes(secrets.token_bytes(4096))
        config = tmp / "guard.json"
        config.write_text(json.dumps({"private_dir": str(private), "banned_strings": [marker, folder]}))
        print("Mode: synthetic fixtures")
        return table(config, sample, marker, folder)


def real() -> int:
    config = Path(os.environ.get(ENV) or DEFAULT_CONFIG).expanduser()
    cfg = json.loads(config.read_text())
    private = Path(cfg["private_dir"]).expanduser()
    banned = cfg["banned_strings"]
    sample = min((p for p in private.rglob("*") if p.is_file() and not p.is_symlink()),
                 key=lambda p: (p.stat().st_size, str(p)))
    folders = sorted(p.name for p in private.iterdir() if p.is_dir() and p.name in banned)
    if not folders:
        print("config lists no private folder names")
        return 1
    print("Mode: real guard config")
    return table(config.resolve(), sample, banned[0], folders[0])


if __name__ == "__main__":
    sys.exit(real() if "--real" in sys.argv[1:] else synthetic())
