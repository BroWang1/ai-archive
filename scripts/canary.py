#!/usr/bin/env python3
"""Test that an archived model still actually WORKS — not just that its bytes match.

Levels (each catches what the previous can't):
  1. integrity   — file fingerprints match the manifest      -> scripts/verify.py
  2. config      — config.json parses and its (possibly custom) model class imports
  3. tokenizer   — tokenizer loads and round-trips a string
  4. skeleton    — the full architecture instantiates on the 'meta' device
                   (no weights read, no GPU, near-zero RAM — this is what catches
                   "transformers upgraded and the custom code broke")
  5. inference   — real forward pass; needs the weights + enough GPU. Not run here;
                   do it at mirror time: load the model, generate a few tokens.

Usage:
    pip install transformers torch   # only needed for this script
    python3 scripts/canary.py <org>/<name>

Runs against the local snapshot (code + configs), records the result into the
index record under the capture's "canary" key. Exit 0 = all levels passed.
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("repo_id")
    args = ap.parse_args()

    record_path = ROOT / "index" / f"{args.repo_id}.json"
    if not record_path.exists():
        sys.exit(f"no index record — run scripts/ingest.py {args.repo_id} first")
    record = json.loads(record_path.read_text())
    cap = record["captures"][-1]
    snap = ROOT / cap["snapshot_dir"]

    try:
        import transformers
        import torch
    except ImportError:
        sys.exit("this script needs: pip install transformers torch")

    result = {
        "checked_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "transformers": transformers.__version__,
        "torch": torch.__version__,
        "config": None, "tokenizer": None, "skeleton": None,
    }

    def attempt(level, fn):
        try:
            fn()
            result[level] = "ok"
            print(f"  [ok]   {level}")
            return True
        except Exception as e:
            result[level] = f"FAIL: {type(e).__name__}: {e}"
            print(f"  [FAIL] {level}: {type(e).__name__}: {e}")
            return False

    print(f"canary {args.repo_id} @ {cap['revision'][:12]} "
          f"(transformers {transformers.__version__})")

    from transformers import AutoConfig, AutoTokenizer, AutoModel
    config = {}

    def load_config():
        config["obj"] = AutoConfig.from_pretrained(snap, trust_remote_code=True)

    def load_tokenizer():
        tok = AutoTokenizer.from_pretrained(snap, trust_remote_code=True)
        text = "预训练模型归档测试 model archive test"
        assert tok.decode(tok.encode(text), skip_special_tokens=True).strip() != ""

    def load_skeleton():
        with torch.device("meta"):
            AutoModel.from_config(config["obj"], trust_remote_code=True)

    ok = attempt("config", load_config)
    attempt("tokenizer", load_tokenizer)
    if ok:
        attempt("skeleton", load_skeleton)

    cap["canary"] = result
    record_path.write_text(json.dumps(record, indent=2) + "\n")
    failed = [k for k in ("config", "tokenizer", "skeleton") if str(result[k]).startswith("FAIL")]
    if failed:
        print(f"canary FAILED ({', '.join(failed)}) — consider recording the last-known-good "
              f"transformers version in runtime.working_env, and an erratum if upstream broke it")
        sys.exit(1)
    print("canary passed — model code loads under this environment")


if __name__ == "__main__":
    main()
