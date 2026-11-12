"""Run one Sing VL S1 decision request from JSON."""
import argparse
from contextlib import ExitStack
import json
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True, help="local checkpoint directory")
    parser.add_argument("--request", required=True, help="JSON file, or - for stdin")
    parser.add_argument("--image", type=Path, action="append", default=[], help="repeat in prompt order")
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--details", action="store_true", help="include token and logit diagnostics")
    args = parser.parse_args()
    if len(args.image) > 4:
        parser.error("at most four images per request")
    from PIL import Image

    try:
        if args.request == "-":
            request = json.load(sys.stdin)
        else:
            with Path(args.request).open(encoding="utf-8") as source:
                request = json.load(source)
        if not isinstance(request, dict) or set(request) != {"state", "questions"}:
            raise ValueError("request must contain state and questions; supply image files with --image")
        from model import SingVLS1

        with ExitStack() as stack:
            images = [stack.enter_context(Image.open(path)) for path in args.image]
            engine = SingVLS1(args.model, device=args.device)
            response, details = engine.predict(request["state"], request["questions"], images)
    except (OSError, ValueError, Image.DecompressionBombError) as exc:
        parser.error(str(exc))
    if args.details:
        response["evaluation_trace"] = details
    print(json.dumps(response, indent=2, ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    main()
