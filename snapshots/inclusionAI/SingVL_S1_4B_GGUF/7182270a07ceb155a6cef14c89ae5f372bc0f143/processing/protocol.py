"""Device-independent request formatting and image resizing."""
import json
import math
import re
from PIL import Image

MODEL_ID = "sing-vl-s1"
TEXT_MAX_TOKENS = 65_536
VISION_MAX_TOKENS = 10_000
PUBLIC_IMAGE_MAX_PIXELS = 1_638_400
INSTRUCTION = "Solve the multiple-choice question and output ONLY the index token of the correct option.\n\n"
ANSWER_PREFIX = "<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n"
IMAGE_SLOT = "<|vision_start|><|image_pad|><|vision_end|>"
TRAILING_IMAGES = re.compile(r"(?:\s*<image>\s*)+$")
CONTROL_MARKER = re.compile(r"<video>|<\|(?:im_|vision_|image_pad|video_pad)")


class Unsupported(ValueError):
    pass

def as_text(value):
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, separators=(",", ":"))

def questions_for_state(state, questions, image_count):
    if not isinstance(questions, dict) or not questions:
        raise ValueError("questions must be a nonempty object")
    state = "" if image_count and state == {} else as_text(state)
    if CONTROL_MARKER.search(state):
        raise Unsupported("state contains a reserved model-control marker")
    if image_count and "<image>" not in state:
        state = "<image>\n" * image_count + state
    if state.count("<image>") != image_count:
        raise Unsupported("the number of <image> placeholders must match the images")
    for question_id, question in questions.items():
        if not isinstance(question, dict):
            raise ValueError("each question must be an object")
        kind = question.get("type")
        if kind not in ("choice", "noul", "score"):
            raise Unsupported("supported question types are choice, noul and score")
        criteria = question.get("criteria")
        if kind == "score":
            if not isinstance(criteria, list) or not 2 <= len(criteria) <= 10:
                raise Unsupported("score criteria must be an ordered array of 2..10 levels")
            criteria = {str(level): description for level, description in enumerate(criteria)}
        if kind == "noul" and (criteria is None or criteria == {}):
            criteria = {"true": "Yes", "false": "No"}
        if not isinstance(criteria, dict) or not 2 <= len(criteria) <= 256:
            raise Unsupported("supports 2..256 options per choice")
        if kind == "noul" and set(criteria) != {"true", "false"}:
            raise Unsupported("noul criteria must be true/false")
        instructions = as_text(question.get("instructions", ""))
        options = {key: key if value is None else as_text(value) for key, value in criteria.items()}
        if CONTROL_MARKER.search(instructions) or any(CONTROL_MARKER.search(value) for value in options.values()):
            raise Unsupported("question contains a reserved model-control marker")
        if "<image>" in instructions:
            raise Unsupported("place image markers in state")
        yield question_id, kind, state, instructions, options

def reference_images(state, options):
    """Resolve option references to images already present in the state."""
    for key, value in options.items():
        if "<image>" not in value:
            continue
        needle = f"({key}) {value}"
        if state.count(needle) != 1:
            raise Unsupported(f"ambiguous image reference for option {key}")
        offset = state.index(needle) + len(f"({key}) ")
        index = state[:offset].count("<image>") + 1
        references = iter(range(index, index + value.count("<image>")))
        options[key] = re.sub(r"<image>", lambda _: f"[Image {next(references)} above]", value)
    indices = iter(range(1, state.count("<image>") + 1))
    return re.sub(r"<image>", lambda _: f"[Image {next(indices)}] <image>", state)

def render(state, instructions, options, labels):
    if any("<image>" in value for value in options.values()):
        state = reference_images(state, options)
    question = state + instructions
    trailing = TRAILING_IMAGES.search(question)
    if trailing and question[:trailing.start()].rstrip():
        question = trailing.group().strip() + "\n" + question[:trailing.start()].rstrip()
    question = question.rstrip()
    if question.endswith("Choices:"):
        question = question[:-len("Choices:")].rstrip()
    lines = "\n".join(f"{label}: {value}" for label, value in zip(labels, options.values()))
    user = (INSTRUCTION + "### Question:\n" + question + "\n\n### Options:\n" + lines).strip()
    return "<|im_start|>user\n" + user.replace("<image>", IMAGE_SLOT) + ANSWER_PREFIX

def resize_image(image, factor, min_pixels, max_pixels):
    if image.mode == "RGBA":
        rgb = Image.new("RGB", image.size, "white")
        rgb.paste(image, mask=image.getchannel("A"))
    else:
        rgb = image.convert("RGB")
    width, height = rgb.size
    if max(width, height) / min(width, height) > 200:
        raise Unsupported("image aspect ratio exceeds 200")
    w, h = (max(factor, round(d / factor) * factor) for d in (width, height))
    if w * h > max_pixels:
        scale = math.sqrt(max_pixels / (width * height))
        w, h = (max(factor, math.floor(d * scale / factor) * factor) for d in (width, height))
    elif w * h < min_pixels:
        scale = math.sqrt(min_pixels / (width * height))
        w, h = (math.ceil(d * scale / factor) * factor for d in (width, height))
    return rgb.resize((w, h), Image.Resampling.BICUBIC)


def decode_answer(kind, options, logits, criteria=None):
    """Logits must follow the prepared candidate token order, not vocabulary order."""
    values = [float(x) for x in logits]
    if len(values) != len(options) or not values or not all(math.isfinite(x) for x in values):
        raise ValueError("candidate logits must be finite and match candidate count")
    peak = max(values)
    weights = [math.exp(x - peak) for x in values]
    total = math.fsum(weights)
    probs = dict(zip(options, (x / total for x in weights)))
    if kind == "choice":
        return {"type": kind, "choice": max(probs, key=probs.get), "probabilities": probs}
    if kind == "noul":
        return {"type": kind, "noul": probs["true"]}
    if kind == "score":
        return {"type": kind, "score": math.fsum(int(k)*v for k,v in probs.items()),
                "probabilities": probs, "legend": dict(zip(probs, criteria))}
    raise Unsupported("unsupported question type")
