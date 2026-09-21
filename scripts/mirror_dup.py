#!/usr/bin/env python3
"""Server-side mirror of every redistributable captured model into the archive org.

Usage:
    .venv/bin/python scripts/mirror_dup.py --to AIArchiveInfo [--only org/name]

Flow per model (no local staging, no bandwidth):
  1. skip unless license.redistributable is True and not already mirrored
  2. if upstream HEAD moved since capture, re-ingest first (capture-first)
  3. `hf repos duplicate` (server-side, seconds)
  4. verify every weight file's size+sha256 on the mirror against the manifest
  5. provenance header inserted AFTER the card frontmatter; tag upstream-<sha12>
  6. record mirrors.hf in the index
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HF_CLI = shutil.which("hf") or str(ROOT / ".venv" / "bin" / "hf")
sys.path.insert(0, str(ROOT / "scripts"))
import ingest  # noqa: E402

HEADER = ("> **Byte-identical preservation mirror** of [`{rid}`](https://huggingface.co/{rid}) "
          "at revision [`{rev12}`](https://huggingface.co/{rid}/tree/{rev}), archived {date} by "
          "AIArchive. All credit belongs to the original authors. No weights were trained, "
          "fine-tuned, or altered in any way. The original license ({tag}) is included verbatim "
          "and continues to govern this copy.\n\n")


def api(url):
    with ingest.fetch(url) as r:
        return json.load(r)


def blobs(rid):
    d = api(f"https://huggingface.co/api/models/{rid}?blobs=true")
    return d["sha"], {s["rfilename"]: (s.get("size"), (s.get("lfs") or {}).get("oid"))
                      for s in d["siblings"]}


def mirror_one(record_path, to_org, hf_api):
    rec = json.loads(record_path.read_text())
    rid = rec["repo_id"]
    cap = rec["captures"][-1]
    if cap["license"].get("redistributable") is not True:
        return "skip-license"
    if (cap.get("mirrors") or {}).get("hf"):
        return "skip-done"

    up_sha, up = blobs(rid)
    if up_sha != cap["revision"]:
        print(f"  upstream moved ({cap['revision'][:12]} -> {up_sha[:12]}), re-capturing")
        ingest.ingest(rid)
        rec = json.loads(record_path.read_text())
        cap = rec["captures"][-1]

    name = rid.split("/", 1)[1]
    target = f"{to_org}/{name}"
    for attempt in range(3):
        r = subprocess.run([HF_CLI, "repos", "duplicate", rid, target,
                            "--public"], capture_output=True, text=True)
        if r.returncode == 0 or "already" in r.stderr.lower():
            break
        if "429" in r.stderr and attempt < 2:
            print(f"  rate-limited, waiting 90s (attempt {attempt + 1})")
            time.sleep(90)
            continue
        print(f"  duplicate failed: {r.stderr.strip()[:200]}")
        return "fail-duplicate"

    _, mi = blobs(target)
    manifest = {f["path"]: (f["size"], f["sha256"]) for f in cap["files"] if f["kind"] == "weights"}
    bad = [p for p, sv in manifest.items() if mi.get(p) != sv]
    if bad:
        print(f"  VERIFY FAILED: {len(bad)} mismatched files, e.g. {bad[0]}")
        return "fail-verify"

    snap_readme = ROOT / cap["snapshot_dir"] / "README.md"
    text = snap_readme.read_text() if snap_readme.exists() else ""
    header = HEADER.format(rid=rid, rev=cap["revision"], rev12=cap["revision"][:12],
                           date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                           tag=cap["license"].get("tag") or "see LICENSE")
    m = re.match(r"(\A---\s*\n.*?\n---\s*\n)(.*)", text, re.DOTALL)
    stamped = (m.group(1) + "\n" + header + m.group(2)) if m else (header + text)
    tmp = ROOT / ".venv" / "mirror_readme.tmp"
    tmp.write_text(stamped)
    hf_api.upload_file(path_or_fileobj=str(tmp), path_in_repo="README.md", repo_id=target,
                       commit_message=f"provenance: mirror of {rid}@{cap['revision']}")
    try:
        hf_api.create_tag(target, tag=f"upstream-{cap['revision'][:12]}",
                          tag_message=f"upstream {rid} revision {cap['revision']}")
    except Exception:
        pass

    cap["mirrors"]["hf"] = {"repo": target, "byte_identical": True,
                            "upstream_revision": cap["revision"],
                            "verified_files": len(manifest),
                            "mirrored_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    record_path.write_text(json.dumps(rec, indent=2) + "\n")
    return "ok"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--to", required=True)
    ap.add_argument("--only")
    ap.add_argument("--pause", type=int, default=30,
                    help="seconds between models; raise to ride out duplication quotas")
    ap.add_argument("--budget-tb", type=float, default=11.5,
                    help="stop before org storage would exceed this many TB")
    args = ap.parse_args()
    from huggingface_hub import HfApi
    hf_api = HfApi()

    if args.only:
        records = [ROOT / "index" / f"{args.only}.json"]
        used_tb = 0.0
    else:
        # smallest-first maximizes models preserved within the storage budget
        pend, used_tb = [], 0.0
        for p in sorted((ROOT / "index").rglob("*.json")):
            r = json.loads(p.read_text())
            cap = r["captures"][-1]
            tb = cap["weight_bytes"] / 1e12
            if (cap.get("mirrors") or {}).get("hf"):
                used_tb += tb
            elif cap["license"].get("redistributable") is True:
                pend.append((tb, p))
        pend.sort(key=lambda x: x[0])
        records = [p for _, p in pend]
        print(f"queue: {len(records)} models, org currently ~{used_tb:.2f} TB, budget {args.budget_tb} TB")

    tally = {}
    consecutive_quota_fails = 0
    for p in records:
        rec = json.loads(p.read_text())
        rid = rec["repo_id"]
        tb = rec["captures"][-1]["weight_bytes"] / 1e12
        if not args.only and used_tb + tb > args.budget_tb:
            tally["skip-storage"] = tally.get("skip-storage", 0) + 1
            continue
        print(f"{rid}")
        try:
            res = mirror_one(p, args.to, hf_api)
        except Exception as e:
            print(f"  error: {type(e).__name__}: {e}")
            res = "error"
        tally[res] = tally.get(res, 0) + 1
        print(f"  -> {res}", flush=True)
        if res == "ok":
            used_tb += tb
            consecutive_quota_fails = 0
            time.sleep(args.pause)
        elif res == "fail-duplicate":
            consecutive_quota_fails += 1
            if consecutive_quota_fails >= 3:
                print("3 consecutive duplication failures — quota wall; stopping (resumable)", flush=True)
                break
            time.sleep(args.pause)
    print("\n" + ", ".join(f"{k}: {v}" for k, v in sorted(tally.items())))


if __name__ == "__main__":
    main()
