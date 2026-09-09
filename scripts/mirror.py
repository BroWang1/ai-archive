#!/usr/bin/env python3
"""Mirror a captured model's weights to the archive's Hugging Face org.

Usage:
    export HF_TOKEN=hf_...          # fine-grained token scoped to the archive org
    python3 scripts/mirror.py <org>/<name> --to <archive-org> [--work-dir weights/]

Requires: pip install huggingface_hub  (and hf_xet comes with it).
Set HF_XET_HIGH_PERFORMANCE=1 for faster transfers on fat pipes.

Refuses to run unless the capture's license.redistributable is exactly true —
classify the license in the index record first.

The mirror keeps the upstream name verbatim under the archive org, pins the
upstream revision, is tagged with the upstream SHA, and prepends a provenance
header to the model card. Weights are never modified (byte_identical: true).
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

CARD_HEADER = """\
> **Byte-identical preservation mirror** of [`{repo_id}`](https://huggingface.co/{repo_id})
> at revision [`{rev12}`](https://huggingface.co/{repo_id}/tree/{revision}), archived {date}
> by [ai-archive]. All credit belongs to the original authors. No weights were trained,
> fine-tuned, or numerically altered in any way. The original LICENSE is included verbatim
> and continues to govern this copy. Per-file sha256 manifests: see the ai-archive index.

"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("repo_id")
    ap.add_argument("--to", required=True, help="archive HF org")
    ap.add_argument("--work-dir", default="weights", help="staging dir (gitignored)")
    args = ap.parse_args()

    try:
        from huggingface_hub import HfApi, snapshot_download
    except ImportError:
        sys.exit("pip install huggingface_hub")

    record_path = ROOT / "index" / f"{args.repo_id}.json"
    if not record_path.exists():
        sys.exit(f"no index record — run scripts/ingest.py {args.repo_id} first")
    record = json.loads(record_path.read_text())
    cap = record["captures"][-1]

    if cap["license"]["redistributable"] is not True:
        sys.exit(f"license.redistributable is {cap['license']['redistributable']!r} for the "
                 f"latest capture — classify the license in {record_path} before mirroring. "
                 f"(tag: {cap['license']['tag']!r}, file: {cap['license']['file']!r})")

    revision = cap["revision"]
    name = args.repo_id.split("/", 1)[1]
    target = f"{args.to}/{name}"
    work = Path(args.work_dir) / args.repo_id / revision
    api = HfApi()

    print(f"downloading {args.repo_id} @ {revision[:12]} -> {work}")
    snapshot_download(repo_id=args.repo_id, revision=revision, local_dir=work)

    # provenance header on the card, original preserved below it
    readme = work / "README.md"
    original = readme.read_text() if readme.exists() else ""
    header = CARD_HEADER.format(repo_id=args.repo_id, revision=revision,
                                rev12=revision[:12],
                                date=datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    if "Byte-identical preservation mirror" not in original:
        readme.write_text(header + original)

    print(f"uploading -> {target}")
    api.create_repo(target, repo_type="model", exist_ok=True)
    api.upload_folder(folder_path=work, repo_id=target, repo_type="model",
                      commit_message=f"mirror {args.repo_id}@{revision}")
    api.create_tag(target, tag=f"upstream-{revision[:12]}",
                   tag_message=f"upstream {args.repo_id} revision {revision}", exist_ok=True)

    cap["mirrors"]["hf"] = {
        "repo": target,
        "byte_identical": True,  # only the README header differs, weights untouched
        "upstream_revision": revision,
        "mirrored_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    record_path.write_text(json.dumps(record, indent=2) + "\n")
    print(f"done. verify with: python3 scripts/verify.py {args.repo_id} --weights-dir {work}")


if __name__ == "__main__":
    main()
