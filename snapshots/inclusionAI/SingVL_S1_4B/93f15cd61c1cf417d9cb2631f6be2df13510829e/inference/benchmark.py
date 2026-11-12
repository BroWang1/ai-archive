"""Rerun the frozen Decision Index public suites with the release model engine."""
import argparse
from collections import Counter
from contextlib import ExitStack
import fcntl
import gzip
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback

from PIL import Image


COUNTS = {"vision": 12_210, "text": 140_178}
VISION_ROWS_SHA256 = "f5f1cfb5cd92ab48d4d14919dff9c56963f4bbbed483bdd45a4f102dba87c133"
ROOT = Path(__file__).resolve().parent


def rows_for(args, suite):
    if suite == "vision":
        from decision_index.vision.rows import read_rows
        return read_rows(args.data / "vision/vision-rows.jsonl")
    from decision_index.suite.io import Suite
    return Suite(args.data / "text-public-0.3", "0.3").rows(apply_exclusions=True)


def row_id(suite, row):
    return row["id"] if suite == "vision" else row["_evaluation"]["run_id"]


def prepare(args, suites):
    from decision_index.suite.io import Suite, atomic_json, sha256_file
    spec = {
        "model": str(args.model), "data": str(args.data), "kit": str(args.kit),
        "suites": suites, "gpus": args.gpus, "image_max_pixels": args.image_max_pixels,
        "code_sha256": {name: sha256_file(ROOT / name) for name in ("model.py", "benchmark.py")},
        "checkpoint_index_sha256": sha256_file(args.model / "model.safetensors.index.json"),
    }
    path = args.out / "manifest.json"
    if path.exists():
        if json.loads(path.read_text()) != spec:
            raise ValueError("existing run uses a different model, corpus, GPU list or engine")
        return
    for suite in suites:
        if suite == "vision":
            if sha256_file(args.data / "vision/vision-rows.jsonl") != VISION_ROWS_SHA256:
                raise ValueError("Vision input hash differs from the official public suite")
        else:
            verification = Suite(args.data / "text-public-0.3", "0.3").verify()
            if not all(v for k, v in verification.items() if k == "match" or k.endswith("_match")):
                raise ValueError(f"Text suite verification failed: {verification}")
        directory = args.out / suite
        directory.mkdir(exist_ok=True)
        seen = set()
        with ExitStack() as stack:
            handles = [
                stack.enter_context(gzip.open(directory / f"input{i:02}.jsonl.gz", "wt", compresslevel=1))
                for i in range(len(args.gpus))
            ]
            for index, row in enumerate(rows_for(args, suite)):
                identifier = row_id(suite, row)
                if identifier in seen:
                    raise ValueError(f"duplicate {suite} input ID {identifier}")
                seen.add(identifier)
                handles[index % len(handles)].write(json.dumps(row, ensure_ascii=False) + "\n")
        if len(seen) != COUNTS[suite]:
            raise ValueError(f"expected {COUNTS[suite]} {suite} requests, found {len(seen)}")
        print(f"prepared {suite}: {len(seen)}", flush=True)
    atomic_json(path, spec)


def load_images(directory, row):
    images = []
    for filename in row["images"]:
        with Image.open(directory / filename) as image:
            images.append(image.copy())
    return images


def worker(args, suites, index):
    from decision_index.engines.base import validate
    from decision_index.suite.io import atomic_json, read_jsonl
    from model import SingVLS1, Unsupported
    engine = SingVLS1(args.model, image_max_pixels=args.image_max_pixels)
    atomic_json(args.out / f"environment{index:02}.json", {
        **engine.runtime(), "gpu": os.environ.get("CUDA_VISIBLE_DEVICES"), "model": str(args.model),
    })
    for suite in suites:
        directory = args.out / suite
        results = directory / f"result{index:02}.jsonl"
        previous = {}
        if results.exists():
            for record in read_jsonl(results, complete_lines_only=True):
                previous[record["run_id"]] = record
            cleaned = results.with_suffix(".jsonl.tmp")
            with cleaned.open("w") as output:
                for record in previous.values():
                    if record["status"] != "error":
                        output.write(json.dumps(record, ensure_ascii=False) + "\n")
            cleaned.replace(results)
        counts = Counter(r["status"] for r in previous.values() if r["status"] != "error")
        failures = 0
        with results.open("a", buffering=1) as output:
            for row in read_jsonl(directory / f"input{index:02}.jsonl.gz"):
                identifier = row_id(suite, row)
                if previous.get(identifier, {}).get("status") in ("ok", "unsupported"):
                    continue
                record = {**row["_evaluation"], "run_id": identifier}
                started = time.perf_counter()
                try:
                    images = load_images(args.data / "vision", row) if suite == "vision" else []
                    state = "<image>\n" * len(images) if suite == "vision" else row["state"]
                    response, _ = engine.predict(state, row["questions"], images)
                    validate(row["questions"], response)
                    record.update(status="ok", response=response)
                except Unsupported as exc:
                    record.update(status="unsupported", error=str(exc))
                except Exception as exc:
                    record.update(status="error", error=str(exc), exception=type(exc).__name__)
                    traceback.print_exc()
                elapsed = (time.perf_counter() - started) * 1000
                record.update(total_wall_ms=elapsed, model_request_wall_ms=elapsed)
                output.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")
                status = record["status"]
                counts[status] += 1
                failures = failures + 1 if status == "error" else 0
                if sum(counts.values()) % 50 == 0 or status == "error":
                    print(f"{suite} worker {index}: {dict(counts)}", flush=True)
                if failures >= 5 or record.get("exception") in ("OutOfMemoryError", "AcceleratorError"):
                    raise RuntimeError(f"{suite} worker {index} stopped after an inference failure")
        atomic_json(directory / f"complete{index:02}.json", dict(counts))


def collect(args, suite):
    from decision_index.suite.io import Suite, atomic_json, read_jsonl, sha256_file
    directory = args.out / suite
    final = directory / "final"
    final.mkdir(exist_ok=True)
    result = final / "results.jsonl"
    temporary = final / "results.jsonl.tmp"
    seen, counts = set(), Counter()
    with temporary.open("w") as output:
        for index in range(len(args.gpus)):
            expected = {row_id(suite, row) for row in read_jsonl(directory / f"input{index:02}.jsonl.gz")}
            actual = set()
            for row in read_jsonl(directory / f"result{index:02}.jsonl"):
                identifier = row["run_id"]
                if identifier in seen or identifier not in expected:
                    raise ValueError(f"duplicate or unexpected {suite} result {identifier}")
                seen.add(identifier)
                actual.add(identifier)
                counts[row["status"]] += 1
                output.write(json.dumps(row, ensure_ascii=False) + "\n")
            if actual != expected:
                raise ValueError(f"incomplete {suite} shard {index}")
    temporary.replace(result)
    if suite == "vision":
        from decision_index.vision.score import score_run
        score = score_run(args.data / "vision/vision-rows.jsonl", result, final)
        index = score["public_vision_index"]
    else:
        from decision_index.pipeline import score_run
        score = score_run(Suite(args.data / "text-public-0.3", "0.3"), result, "sing-vl-s1", final)
        index = score["decision_index"]
    summary = {
        "ids_exact": len(seen) == COUNTS[suite], "counts": dict(counts),
        "index": index, "scorer_complete": score["complete"], "results_sha256": sha256_file(result),
    }
    atomic_json(final / "completion.json", summary)
    print(f"{suite}: {json.dumps(summary)}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--kit", type=Path, required=True, help="Decision Index kit source directory")
    parser.add_argument("--data", type=Path, required=True, help="parent of vision and text-public-0.3")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--gpus", required=True, help="comma-separated visible physical GPU IDs")
    parser.add_argument("--suite", choices=("all", "vision", "text"), default="all")
    parser.add_argument("--image-max-pixels", type=int, default=1_638_400)
    parser.add_argument("--worker", type=int, help=argparse.SUPPRESS)
    args = parser.parse_args()
    args.gpus = args.gpus.split(",")
    if len(set(args.gpus)) != len(args.gpus) or not all(gpu.isdecimal() for gpu in args.gpus):
        parser.error("--gpus must contain unique numeric device IDs")
    sys.path.insert(0, str(args.kit))
    suites = ["vision", "text"] if args.suite == "all" else [args.suite]
    if args.worker is not None:
        worker(args, suites, args.worker)
        return
    args.out.mkdir(parents=True, exist_ok=True)
    with (args.out / "run.lock").open("a") as lock, ExitStack() as stack:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        prepare(args, suites)
        for suite in suites:
            for marker in (args.out / suite).glob("complete*.json"):
                marker.unlink()
        children = []
        try:
            for index, gpu in enumerate(args.gpus):
                log = stack.enter_context((args.out / f"worker{index:02}.log").open("a"))
                env = dict(os.environ, CUDA_VISIBLE_DEVICES=gpu)
                children.append(subprocess.Popen(
                    [sys.executable, "-u", str(Path(__file__).resolve()), *sys.argv[1:], "--worker", str(index)],
                    stdout=log, stderr=subprocess.STDOUT, env=env,
                ))
            for suite in suites:
                directory = args.out / suite
                while not all((directory / f"complete{i:02}.json").is_file() for i in range(len(children))):
                    failed = [(i, p.returncode) for i, p in enumerate(children) if p.poll() not in (None, 0)]
                    if failed:
                        raise RuntimeError(f"public evaluation worker failures: {failed}")
                    time.sleep(5)
                collect(args, suite)
            if any(child.wait() for child in children):
                raise RuntimeError("public evaluation worker exited unsuccessfully")
        finally:
            for child in children:
                if child.poll() is None:
                    child.terminate()
            for child in children:
                child.wait()


if __name__ == "__main__":
    main()
