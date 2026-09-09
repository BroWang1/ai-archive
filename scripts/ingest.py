#!/usr/bin/env python3
"""Capture a model into the archive: index record + everything-but-weights snapshot.

Usage:
    python3 scripts/ingest.py <org>/<name> [--revision <sha>] [--max-file-mb 64]

Stdlib only. Weight files are manifested (size + upstream LFS sha256) but not
downloaded; all other files are downloaded into snapshots/ and hashed locally.
"""
import argparse
import hashlib
import json
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

TOOL = "ingest.py/0.1"
HF = "https://huggingface.co"
ROOT = Path(__file__).resolve().parent.parent
WEIGHT_EXT = {".safetensors", ".bin", ".pt", ".pth", ".gguf", ".h5", ".msgpack", ".ckpt", ".onnx"}
# tokenizer.model / tokenizer.json can be tens of MB but are essential context
ALWAYS_SNAPSHOT = {"tokenizer.json", "tokenizer.model", "vocab.json", "merges.txt"}


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "ai-archive/" + TOOL})
    return urllib.request.urlopen(req, timeout=60)


def api_json(url):
    with fetch(url) as r:
        return json.load(r), dict(r.headers)


def frontmatter(readme_text):
    m = re.match(r"\A---\s*\n(.*?)\n---\s*\n", readme_text, re.DOTALL)
    return m.group(1) if m else None


def classify(path):
    name = path.rsplit("/", 1)[-1]
    if name in ALWAYS_SNAPSHOT:
        return "snapshot"
    if any(path.endswith(ext) for ext in WEIGHT_EXT):
        return "weights"
    return "snapshot"


def ingest(repo_id, revision=None, max_file_mb=64):
    org = repo_id.split("/")[0]
    cfg = json.loads((ROOT / "config" / "orgs.json").read_text())
    orgs = cfg["orgs"] + cfg.get("extra_orgs", [])
    if org not in orgs:
        print(f"warning: {org} is not in config/orgs.json — canonical-org check FAILED. "
              f"Confirm this is not a derivative re-upload before trusting this capture.")

    url = f"{HF}/api/models/{repo_id}?blobs=true"
    if revision:
        url = f"{HF}/api/models/{repo_id}/revision/{revision}?blobs=true"
    meta, headers = api_json(url)
    sha = meta["sha"]
    card = meta.get("cardData") or {}
    captured_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    snap_dir = ROOT / "snapshots" / repo_id / sha
    snap_dir.mkdir(parents=True, exist_ok=True)

    files, total, weight_bytes = [], 0, 0
    license_entry = {"tag": card.get("license"), "file": None, "sha256": None,
                     "redistributable": None, "obligations": []}
    gate_sha = None

    for sib in meta.get("siblings", []):
        path, size = sib["rfilename"], sib.get("size") or 0
        kind = classify(path)
        entry = {"path": path, "size": size, "sha256": None, "kind": kind}
        total += size

        if kind == "weights":
            weight_bytes += size
            lfs = sib.get("lfs") or {}
            entry["sha256"] = lfs.get("oid")  # LFS oid IS the sha256 — free, no download
            files.append(entry)
            continue

        if size > max_file_mb * 1024 * 1024 and path.rsplit("/", 1)[-1] not in ALWAYS_SNAPSHOT:
            entry["kind"] = "skipped-large"
            lfs = sib.get("lfs") or {}
            entry["sha256"] = lfs.get("oid")
            files.append(entry)
            continue

        # download into the snapshot and hash locally
        dest = snap_dir / path
        dest.parent.mkdir(parents=True, exist_ok=True)
        raw_url = f"{HF}/{repo_id}/resolve/{sha}/{path}"
        try:
            with fetch(raw_url) as r:
                data = r.read()
        except urllib.error.HTTPError as e:
            print(f"  ! {path}: HTTP {e.code}, manifested without snapshot")
            entry["kind"] = "gated-no-snapshot" if e.code in (401, 403) else "no-snapshot"
            files.append(entry)
            continue
        dest.write_bytes(data)
        entry["sha256"] = hashlib.sha256(data).hexdigest()
        files.append(entry)

        name = path.rsplit("/", 1)[-1]
        if name.upper().startswith("LICENSE") or name.upper().startswith("LICENCE"):
            license_entry["file"] = path
            license_entry["sha256"] = entry["sha256"]
        if name == "README.md":
            fm = frontmatter(data.decode("utf-8", errors="replace"))
            if fm and "extra_gated" in fm:
                gate_sha = hashlib.sha256(fm.encode()).hexdigest()

    capture = {
        "revision": sha,
        "captured_at": captured_at,
        "provenance": {
            "endpoint": url,
            "tool": TOOL,
            "etag": headers.get("ETag"),
            "last_modified": headers.get("Last-Modified"),
        },
        "license": license_entry,
        "gate_terms_sha256": gate_sha,
        "files": files,
        "total_bytes": total,
        "weight_bytes": weight_bytes,
        "snapshot_dir": str(snap_dir.relative_to(ROOT)) + "/",
        "runtime": {"external_repos": [], "working_env": None},
        "serving": None,
        "mirrors": {"hf": None, "master": None},
    }

    record_path = ROOT / "index" / f"{repo_id}.json"
    if record_path.exists():
        record = json.loads(record_path.read_text())
        existing = [c for c in record["captures"] if c["revision"] == sha]
        if existing:
            print(f"revision {sha[:12]} already captured {existing[0]['captured_at']} — nothing to do")
            return record
        record["captures"].append(capture)
    else:
        record_path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "repo_id": repo_id,
            "canonical_org": org,
            "status": "live",
            "captures": [capture],
            "errata": [],
            "context": {"announcement_urls": [], "tech_report": None, "arxiv": None},
            "notes": "",
        }
    record_path.write_text(json.dumps(record, indent=2) + "\n")

    n_snap = sum(1 for f in files if f["kind"] == "snapshot")
    print(f"captured {repo_id} @ {sha[:12]}")
    print(f"  license tag: {license_entry['tag']}  (file: {license_entry['file'] or 'NONE FOUND'})")
    print(f"  files: {len(files)} total | {n_snap} snapshotted | "
          f"weights manifested: {weight_bytes / 1e9:.1f} GB (not downloaded)")
    print(f"  record: {record_path.relative_to(ROOT)}")
    return record


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("repo_id")
    ap.add_argument("--revision")
    ap.add_argument("--max-file-mb", type=int, default=64)
    args = ap.parse_args()
    try:
        ingest(args.repo_id, args.revision, args.max_file_mb)
    except urllib.error.HTTPError as e:
        sys.exit(f"HTTP {e.code} for {args.repo_id}: "
                 f"{'gated or auth required' if e.code in (401, 403) else 'not found' if e.code == 404 else e.reason}")


if __name__ == "__main__":
    main()
