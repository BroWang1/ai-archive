"""SystemOne-visible JEV inputs shared by training and inference.

Transport JSON is decoded into one question. Gold fields never enter the
renderer; score values only establish ordinal order in training assets.

Synced from ``inference/runtime_sources/decision_protocol.py`` of the WePM
release so that the MLX runtime renders JEV prompts byte-identically.
"""
import base64
import binascii
import json
import math
from dataclasses import dataclass

INPUT_PROFILE = "systemone_visible_v1"
NOUL_DESCRIPTIONS = ("No / false", "Yes / true")


def state_text(state):
    if isinstance(state, str):
        return state
    if not isinstance(state, dict):
        raise ValueError("state must be an object or string")
    return json.dumps(state, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


@dataclass(frozen=True)
class DecisionInput:
    kind: str
    context: str
    instructions: str
    ids: tuple[str, ...]
    descriptions: tuple[str, ...]

    def __post_init__(self):
        if self.kind not in {"choice", "score", "noul"}:
            raise ValueError("unsupported decision type")
        if not isinstance(self.instructions, str) or not self.instructions.strip():
            raise ValueError("decision instructions must be nonempty")
        if (len(self.ids) < 2 or len(self.ids) != len(self.descriptions)
                or len(set(self.ids)) != len(self.ids)
                or any(not isinstance(x, str) or not x for x in self.ids)
                or any(not isinstance(x, str) or not x.strip() for x in self.descriptions)):
            raise ValueError("invalid decision candidates")


def training_input(sample):
    """Return visible input and source indices aligning the training targets."""
    context = sample["context"]
    if context.get("format") not in {"text", "json"} or not isinstance(context.get("payload"), str):
        raise ValueError("invalid decision context")
    state = json.loads(context["payload"]) if context["format"] == "json" else context["payload"]
    decision = sample["decision"]
    # Platform loaders use the question text when meta.state is None or "".
    # Normalized training assets carry that text in decision.instructions.
    if state is None or state == "":
        state = decision["instructions"]
    options = decision["options"]
    kind = decision["kind"]
    order = tuple(range(len(options)))
    if kind == "score":
        values = [o.get("score_value") for o in options]
        if any(v is not None for v in values):
            if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in values):
                raise ValueError("score scale must be wholly known or wholly ordinal")
            order = tuple(sorted(order, key=lambda i: values[i]))
        ids = tuple(str(i) for i in range(len(options)))
        descriptions = tuple(options[i]["description"] for i in order)
    elif kind == "noul":
        if [o["option_id"] for o in options] != ["false", "true"]:
            raise ValueError("Noul order must be false,true")
        ids, descriptions = ("false", "true"), NOUL_DESCRIPTIONS
    else:
        ids = tuple(o["option_id"] for o in options)
        descriptions = tuple(o["description"] for o in options)
    return DecisionInput(kind, state_text(state), decision["instructions"], ids, descriptions), order


def request_input(request):
    """Decode the documented single-question /systemone protocol, without gold."""
    questions = request.get("questions")
    if not isinstance(questions, dict) or set(questions) != {"q"}:
        raise ValueError("expected exactly questions.q")
    q = questions["q"]
    if not isinstance(q, dict):
        raise ValueError("question must be an object")
    kind = q.get("type")
    if kind == "choice":
        criteria = q.get("criteria")
        if not isinstance(criteria, dict):
            raise ValueError("choice criteria must be an object")
        ids, descriptions = tuple(criteria), tuple(criteria.values())
    elif kind == "score":
        criteria = q.get("criteria")
        if not isinstance(criteria, list):
            raise ValueError("score criteria must be an ordered list")
        ids, descriptions = tuple(str(i) for i in range(len(criteria))), tuple(criteria)
    elif kind == "noul":
        if "criteria" in q:
            raise ValueError("noul has no criteria")
        ids, descriptions = ("false", "true"), NOUL_DESCRIPTIONS
    else:
        raise ValueError("unsupported decision type")
    if "state" not in request:
        raise ValueError("request must include state")
    state = request["state"]
    if state is None or state == "":
        state = q.get("instructions")
    return DecisionInput(kind, state_text(state), q.get("instructions"), ids, descriptions)


def request_images(request):
    images = request.get("images", [])
    if not isinstance(images, list) or len(images) > 8:
        raise ValueError("expected at most eight ordered images")
    result = []
    for image in images:
        if not isinstance(image, str):
            raise ValueError("image must be a base64 data URL")
        header, separator, content = image.partition(",")
        if not separator or not header.startswith("data:image/") or not header.endswith(";base64"):
            raise ValueError("image must be a base64 data URL")
        try:
            blob = base64.b64decode(content, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise ValueError("invalid image base64") from exc
        if not blob:
            raise ValueError("empty image")
        result.append(blob)
    return result


def render_input(value):
    text = ("Evaluate the candidates using the context and instructions.\n"
            f"Context:\n{value.context}\nDecision type: {value.kind}\n"
            f"Instructions:\n{value.instructions}\nCandidates:\n")
    spans = []
    for index, (key, description) in enumerate(zip(value.ids, value.descriptions, strict=True)):
        text += f"{index}: "
        if value.kind == "choice":
            text += "id=" + json.dumps(key, ensure_ascii=False) + " description="
        start = len(text)
        text += json.dumps(description, ensure_ascii=False)
        spans.append((start, len(text)))
        text += "\n"
    return text.rstrip("\n"), spans


def response_from_probabilities(value, probabilities):
    probs = list(probabilities)
    if len(probs) != len(value.ids) or any(isinstance(p, bool) or not isinstance(p, (int, float))
                                          or not math.isfinite(p) or not 0 <= p <= 1 for p in probs):
        raise ValueError("invalid candidate probability vector")
    if not math.isclose(sum(probs), 1., abs_tol=1e-5, rel_tol=0):
        raise ValueError("probabilities must sum to one")
    answer = ({"noul": probs[1]} if value.kind == "noul" else
              {"probabilities": dict(zip(value.ids, probs, strict=True))})
    return {"answers": {"q": answer}}
