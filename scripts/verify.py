#!/usr/bin/env python3
"""Verify archive contents against the index manifests.

Usage:
    python3 scripts/verify.py --all                  # verify every snapshot
    python3 scripts/verify.py <org>/<name>           # verify one model's snapshots
    python3 scripts/verify.py <org>/<name> --weights-dir /path/to/weights
                                                     # also verify a local weights copy

Exit code 0 = everything matches; 1 = any mismatch or missing file.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_record(record_path, weights_dir=None):
    record = json.loads(record_path.read_text())
    ok, bad = 0, []
    for cap in record["captures"]:
        snap = ROOT / cap["snapshot_dir"]
        for f in cap["files"]:
            if f["kind"] == "snapshot":
                p = snap / f["path"]
                if not p.exists():
                    bad.append((f["path"], "MISSING"))
                elif f["sha256"] and sha256_file(p) != f["sha256"]:
                    bad.append((f["path"], "HASH MISMATCH"))
                else:
                    ok += 1
            elif f["kind"] == "weights" and weights_dir:
                p = Path(weights_dir) / f["path"]
                if not p.exists():
                    bad.append((f["path"], "MISSING (weights)"))
                elif f["sha256"] and sha256_file(p) != f["sha256"]:
                    bad.append((f["path"], "HASH MISMATCH (weights)"))
                else:
                    ok += 1
    status = "OK" if not bad else "FAIL"
    print(f"[{status}] {record['repo_id']}: {ok} verified, {len(bad)} problems")
    for path, why in bad:
        print(f"    {why}: {path}")
    return not bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("repo_id", nargs="?")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--weights-dir")
    args = ap.parse_args()

    if args.all:
        records = sorted((ROOT / "index").rglob("*.json"))
    elif args.repo_id:
        records = [ROOT / "index" / f"{args.repo_id}.json"]
    else:
        ap.error("give a repo id or --all")

    all_ok = True
    for r in records:
        if not r.exists():
            print(f"[FAIL] no record: {r}")
            all_ok = False
            continue
        all_ok &= verify_record(r, args.weights_dir)
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
