#!/usr/bin/env python3
"""Batch-capture the top models of every tracked org into the catalog.

Usage: python3 scripts/batch_ingest.py [--per-org 6] [--per-extra-org 3]

Selects each org's most-downloaded repos, skipping repos already captured and
derivative-format repos (quantizations reconstructible from the native
checkpoint). Weight files are manifested only — this stores no weights.
"""
import argparse
import json
import re
import time
import urllib.error
from pathlib import Path

import ingest

ROOT = Path(__file__).resolve().parent.parent
# derivative formats an archiver skips; native FP8 releases don't carry these names
DERIVATIVE = re.compile(r"(GGUF|GGML|AWQ|GPTQ|MLX|ONNX|INT[48]|[48]bit|-FP8$)", re.IGNORECASE)


def top_repos(org, n):
    url = f"https://huggingface.co/api/models?author={org}&sort=downloads&direction=-1&limit=100"
    with ingest.fetch(url) as r:
        models = json.load(r)
    picked = []
    for m in models:
        rid = m["id"]
        name = rid.split("/", 1)[1]
        if DERIVATIVE.search(name):
            continue
        if (ROOT / "index" / f"{rid}.json").exists():
            continue
        if m.get("gated") and org not in ("google", "meta-llama"):
            continue
        picked.append(rid)
        if len(picked) >= n:
            break
    return picked


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-org", type=int, default=6)
    ap.add_argument("--per-extra-org", type=int, default=3)
    args = ap.parse_args()

    cfg = json.loads((ROOT / "config" / "orgs.json").read_text())
    plan = [(o, args.per_org) for o in cfg["orgs"]] + \
           [(o, args.per_extra_org) for o in cfg.get("extra_orgs", [])]

    done, failed = 0, []
    for org, n in plan:
        try:
            repos = top_repos(org, n)
        except Exception as e:
            print(f"?? {org}: listing failed: {e}")
            continue
        for rid in repos:
            try:
                ingest.ingest(rid)
                done += 1
            except urllib.error.HTTPError as e:
                failed.append((rid, e.code))
                print(f"!! {rid}: HTTP {e.code}")
            except Exception as e:
                failed.append((rid, str(e)))
                print(f"!! {rid}: {e}")
            time.sleep(1.5)

    print(f"\nbatch done: {done} new captures, {len(failed)} failures")
    for rid, why in failed:
        print(f"  failed: {rid} ({why})")


if __name__ == "__main__":
    main()
