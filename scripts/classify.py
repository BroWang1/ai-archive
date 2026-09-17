#!/usr/bin/env python3
"""Classify every captured model's license into a freedom tier.

Usage: python3 scripts/classify.py

Tiers (written to license.freedom on the latest capture, plus redistributable):
  free         MIT/Apache/BSD with the LICENSE file verified in the snapshot —
               use, modify, sell, re-host; nothing owed beyond attribution.
  conditional  Free for normal use but with strings: branding/revenue triggers
               at scale, pass-through use restrictions, or a permissive tag
               with NO license file in the repo (unverifiable).
  restricted   Non-commercial, territory exclusions, or gated EULA.
  unlicensed   No license tag and no file — cannot legally redistribute.

Known special cases are pinned by repo prefix (sourced from reading the actual
LICENSE files); everything else is derived from tag + file presence.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

PERMISSIVE_TAGS = {"apache-2.0", "mit", "bsd-3-clause", "bsd-2-clause", "bsd"}

# repo-prefix overrides where the actual LICENSE text is known to differ from
# what the tag suggests; first match wins
KNOWN = [
    ("moonshotai/Kimi-K3", "conditional",
     "Modified MIT: redistribution allowed; >$20M/yr MaaS revenue requires separate agreement; 'Kimi K3' display >100M MAU"),
    ("moonshotai/Kimi-K2", "conditional",
     "Modified MIT: redistribution allowed; 'Kimi K2' display required >100M MAU or >$20M/mo revenue"),
    ("tencent/Hunyuan", "restricted",
     "Tencent Community License: EXCLUDES EU, UK, South Korea; license required >100M MAU"),
    ("tencent/Hy4", "restricted",
     "Tencent Community License family: territory exclusions apply — check per release"),
    ("Qwen/Qwen3.8-2.4T", "conditional",
     "Qwen License: redistribution allowed; commercial license required above ~$50M annual revenue"),
    ("deepseek-ai/DeepSeek-V3", "conditional",
     "MIT for code; older DeepSeek Model License permits re-hosting but its use restrictions must be passed through"),
]


def classify_record(path):
    rec = json.loads(path.read_text())
    cap = rec["captures"][-1]
    lic = cap["license"]
    tag = (lic.get("tag") or "").lower()
    has_file = bool(lic.get("file"))
    gated = bool(cap.get("gate_terms_sha256"))

    freedom, why = None, ""
    for prefix, tier, note in KNOWN:
        if rec["repo_id"].startswith(prefix):
            freedom, why = tier, note
            break

    if freedom is None:
        if gated:
            freedom, why = "restricted", "Gated repo: access requires accepting the author's terms"
        elif tag in PERMISSIVE_TAGS and has_file:
            freedom, why = "free", f"{tag} with LICENSE file verified in snapshot"
        elif tag in PERMISSIVE_TAGS and not has_file:
            freedom, why = "conditional", f"'{tag}' card tag but NO license file in repo — unverifiable, confirm upstream"
        elif tag in ("", "none", "null"):
            freedom, why = "unlicensed", "No license tag and no file — cannot redistribute"
        else:
            freedom, why = "conditional", f"Custom license ('{tag}') — read before redistributing"

    lic["freedom"] = freedom
    lic["freedom_note"] = why
    if lic.get("redistributable") is None:
        lic["redistributable"] = True if freedom == "free" else (False if freedom == "unlicensed" else None)
    path.write_text(json.dumps(rec, indent=2) + "\n")
    return rec["repo_id"], freedom


def main():
    tally = {}
    for path in sorted((ROOT / "index").rglob("*.json")):
        rid, tier = classify_record(path)
        tally[tier] = tally.get(tier, 0) + 1
        print(f"  {tier:12} {rid}")
    print("\n" + ", ".join(f"{k}: {v}" for k, v in sorted(tally.items())))


if __name__ == "__main__":
    main()
