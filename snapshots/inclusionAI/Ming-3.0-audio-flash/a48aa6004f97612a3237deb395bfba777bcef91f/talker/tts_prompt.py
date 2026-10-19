"""Training-aligned prompt helpers for Ming TTS inference.

The strings and JSON key order in this module are part of the model input
protocol. Keep them in sync with AntOC instead of rebuilding prompts in each
service or test script.
"""

from __future__ import annotations

import json
import itertools
import logging
import re
import threading
from collections import OrderedDict
from pathlib import Path


DEFAULT_TTS_PROMPT = "Please generate speech based on the following description.\n"

_TARGET_LANGUAGE_NAMES = {
    "zh": "Chinese",
    "zh-cn": "Chinese",
    "chinese": "Chinese",
    "en": "English",
    "english": "English",
    "ja": "Japanese",
    "japanese": "Japanese",
    "ko": "Korean",
    "korean": "Korean",
    "de": "German",
    "german": "German",
    "fr": "French",
    "french": "French",
    "es": "Spanish",
    "spanish": "Spanish",
    "yue": "Chinese",
    "zh-yue": "Chinese",
    "cantonese": "Chinese",
}
_NO_TARGET_LANGUAGE_IDS = {
    "zh", "zh-cn", "chinese",
    "en", "en-us", "en-gb", "english",
}
_FASTTEXT_SUPPORTED_LANGUAGE_IDS = {
    "zh", "en", "ja", "ko", "de", "fr", "es",
}
_FASTTEXT_LANGUAGE_ALIASES = {
    "cmn": "zh",
    "lzh": "zh",
    "wuu": "zh",
    "yue": "zh",
}
_FASTTEXT_MODEL = None
_FASTTEXT_MODEL_FILE = Path(__file__).resolve().parent / "data" / "lid.176.ftz"
_FASTTEXT_MODEL_LOCK = threading.Lock()
_FASTTEXT_WARNINGS = set()
_FASTTEXT_WARNING_LOCK = threading.Lock()
_LANGUAGE_SAMPLE_MIN_CHARS = 64
_LANGUAGE_SAMPLE_MAX_CHARS = 512
_LANGUAGE_SAMPLE_MAX_CHUNKS = 16
_LANGUAGE_SAMPLE_ENDINGS = ("。", "！", "？", ".", "!", "?", "\n")
_ZH_FIELDS = ("序号", "说话人", "方言", "风格", "语速", "基频", "音量", "情感")
_EN_FIELDS = ("id", "speaker", "dialect", "style", "speed", "pitch", "volume", "emotion")
_BGM_FIELDS = ("Genre", "Mood", "Instrument", "Theme", "ENV", "SNR")
PARALINGUISTIC_TAGS = (
    "[Breathing]", "[Cough]", "[Sigh]", "[Laughter]",
    "[Surprise-ah]", "[Surprise-oh]", "[Dissatisfaction-hnn]", "[Uhm]",
    "[Confirmation-en]", "[Question-ei]", "[Question-ah]",
    "[Question-en]", "[Question-oh]", "[Question-huh]",
)
PARALINGUISTIC_PLACEHOLDERS = {
    tag: f"MINGPARALINGPLACEHOLDER{chr(ord('A') + index)}"
    for index, tag in enumerate(PARALINGUISTIC_TAGS)
}


def build_tts_prompt(target_language=None):
    """Return our exact user-side prompt; target language is opt-in."""
    if target_language is None or not str(target_language).strip():
        return DEFAULT_TTS_PROMPT
    language = str(target_language).strip()
    language_name = _TARGET_LANGUAGE_NAMES.get(language.lower(), language)
    return DEFAULT_TTS_PROMPT + f"Target language: {language_name}.\n"


def normalize_tts_prompt(prompt):
    """Treat a missing/blank prompt as our canonical generation prompt."""
    if prompt is None or not str(prompt).strip():
        return DEFAULT_TTS_PROMPT
    return str(prompt)


def normalize_instruction(instruction):
    """Blank means no instruction, not an empty assistant EOS prefix."""
    if instruction is None or not str(instruction).strip():
        return None
    return str(instruction).strip()


def validate_text_input(text, *, allow_iterable):
    """Validate text without consuming or stringifying a text iterator.

    The legacy TTS-family path accepts either a complete string or an
    ``Iterable[str]`` and consumes the iterable incrementally.  STYLE keeps
    the legacy complete-string contract.
    """
    if isinstance(text, str):
        if not text:
            raise ValueError("text must not be empty")
        return text
    if not allow_iterable:
        raise TypeError("STYLE text must be a complete string")
    if text is None:
        raise TypeError("text must be a string or an iterable of strings")
    try:
        iter(text)
    except TypeError as error:
        raise TypeError(
            "text must be a string or an iterable of strings") from error
    return text


def _warn_fasttext_once(key, message, *args):
    """Avoid emitting the same language-detection warning per request."""
    with _FASTTEXT_WARNING_LOCK:
        if key in _FASTTEXT_WARNINGS:
            return
        _FASTTEXT_WARNINGS.add(key)
    logging.warning(message, *args)


def _get_fasttext_model():
    """Lazily load the bundled FastText LID model once per process."""
    global _FASTTEXT_MODEL

    model_path = str(_FASTTEXT_MODEL_FILE)

    with _FASTTEXT_MODEL_LOCK:
        if _FASTTEXT_MODEL is not None:
            return _FASTTEXT_MODEL
        try:
            import fasttext
            model = fasttext.load_model(model_path)
        except Exception as error:
            _warn_fasttext_once(
                ("load-error", model_path),
                "Failed to load FastText LID model from %s; Target language "
                "auto-detection is skipped: %s",
                model_path,
                error,
            )
            return None
        _FASTTEXT_MODEL = model
        logging.info("FastText LID model loaded from %s", model_path)
        return model


def detect_language_id(text, *, model=None):
    """Detect one supported request-level language with FastText.

    The original text is never normalized or mutated. Only the bounded sample
    passed to FastText has whitespace collapsed because ``predict`` accepts a
    single line.
    """
    if not isinstance(text, str):
        raise TypeError("language detection text must be a string")
    sample = " ".join(text.split())[:_LANGUAGE_SAMPLE_MAX_CHARS]
    if not sample:
        return None
    model = model if model is not None else _get_fasttext_model()
    if model is None:
        return None
    try:
        # FastText's batch API avoids the NumPy 2 scalar conversion in 0.9.2.
        batch_labels, _probabilities = model.predict([sample], k=1)
        labels = batch_labels[0]
        if not labels:
            return None
        language_id = str(labels[0]).removeprefix("__label__").lower()
        language_id = _FASTTEXT_LANGUAGE_ALIASES.get(
            language_id, language_id)
    except Exception as error:
        _warn_fasttext_once(
            ("predict-error", type(error).__name__, str(error)),
            "FastText language detection failed; Target language auto-"
            "detection is skipped: %s",
            error,
        )
        return None
    if language_id not in _FASTTEXT_SUPPORTED_LANGUAGE_IDS:
        _warn_fasttext_once(
            ("unsupported-label", language_id),
            "FastText detected unsupported language %s; Target language is "
            "not added",
            language_id,
        )
        return None
    return language_id


def detect_text_language_once(text, *, detector=None):
    """Detect language once and preserve a string or streaming text input.

    For an iterator, only a bounded prefix is consumed. Every consumed chunk
    is replayed exactly once before the untouched remainder of the iterator.
    """
    detector = detector or detect_language_id
    if isinstance(text, str):
        return detector(text), text

    iterator = iter(text)
    buffered_chunks = []
    sample_chunks = []
    sample_chars = 0
    meaningful_chars = 0
    for _ in range(_LANGUAGE_SAMPLE_MAX_CHUNKS):
        try:
            chunk = next(iterator)
        except StopIteration:
            break
        if not isinstance(chunk, str):
            raise TypeError("text iterable must yield strings")
        buffered_chunks.append(chunk)
        if chunk:
            remaining = _LANGUAGE_SAMPLE_MAX_CHARS - sample_chars
            if remaining > 0:
                sample_chunks.append(chunk[:remaining])
                sample_chars += len(chunk[:remaining])
                meaningful_chars += len("".join(chunk[:remaining].split()))
        stripped = chunk.rstrip()
        if sample_chars >= _LANGUAGE_SAMPLE_MAX_CHARS:
            break
        if (meaningful_chars >= _LANGUAGE_SAMPLE_MIN_CHARS
                or (stripped and stripped.endswith(
                    _LANGUAGE_SAMPLE_ENDINGS))):
            break

    language_id = detector("".join(sample_chunks))
    return language_id, itertools.chain(buffered_chunks, iterator)


def resolve_request_language(text, *, language, taskname, detector=None):
    """Resolve one language ID for a complete generation request.

    Dialect control deliberately has no Target language ID. Other tasks use
    an explicit ID when supplied, otherwise FastText detects once from the
    complete string or a bounded prefix of a text iterator.
    """
    if str(taskname).strip().upper() == "DIALECT":
        if language is not None:
            logging.warning(
                "DIALECT ignores language=%r and never adds a Target "
                "language ID",
                language,
            )
        return None, text
    if language is not None:
        return language, text
    return detect_text_language_once(text, detector=detector)


def target_language_from_prompt(prompt):
    """Read the optional Target language line from a legacy-style prompt."""
    match = re.search(
        r"(?im)^\s*Target language:\s*([^\n.]+)\.?\s*$",
        str(prompt or ""),
    )
    return match.group(1).strip() if match else None


def append_optional_target_language(prompt, language=None):
    """Append a non-Chinese/English target language to an existing prompt.

    ``language`` is an optional Ming 3.0 interface parameter. Chinese,
    English and ``None`` deliberately preserve the caller's prompt
    byte-for-byte; blank strings are invalid. ``language`` is the only
    supported source of a Target language line; callers must not preassemble
    one in ``prompt``.
    """
    prompt = normalize_tts_prompt(prompt)
    existing = target_language_from_prompt(prompt)
    if existing is not None:
        raise ValueError(
            "prompt must not contain Target language; pass it through the "
            "language argument")
    if language is None:
        return prompt
    value = str(language).strip()
    if not value:
        raise ValueError("language must be None or a non-empty language ID")
    key = value.lower().replace("_", "-")
    if key in {"none", "null"}:
        raise ValueError(
            "language='none' is not a disable switch; pass None to enable "
            "automatic language detection")
    if key in _NO_TARGET_LANGUAGE_IDS:
        return prompt

    language_name = _TARGET_LANGUAGE_NAMES.get(key, value)
    separator = "" if prompt.endswith("\n") else "\n"
    return prompt + separator + f"Target language: {language_name}.\n"


def preserve_multilingual_text(language_id):
    """Return true when target text must bypass Chinese/English TN.

    ``TalkerTN`` treats any CJK ideograph as Chinese. Japanese containing
    kanji would therefore lose its kana. AntOC's multilingual path passes the
    target text to ``tts_job`` unchanged, so explicit non-zh/en languages must
    follow the same route here.
    """
    if language_id is None or not str(language_id).strip():
        return False
    language = str(language_id).strip().lower().replace("_", "-")
    return language not in {
        "zh", "zh-cn", "chinese", "en", "english",
    }


def contains_paralinguistic_tag(text):
    """Whether text must bypass TN to preserve NVBench placeholders."""
    value = str(text or "")
    return any(tag in value for tag in PARALINGUISTIC_TAGS)


def protect_paralinguistic_tags(text):
    """Replace supported tags with TN-safe sentinels."""
    value = str(text or "")
    for tag, placeholder in PARALINGUISTIC_PLACEHOLDERS.items():
        if tag not in value:
            continue
        if placeholder in value:
            raise ValueError(
                f"text contains reserved paralinguistic placeholder: "
                f"{placeholder}")
        value = value.replace(tag, placeholder)
    return value


def restore_paralinguistic_tags(text):
    """Restore exact bracketed tags after TN."""
    value = str(text or "")
    for tag, placeholder in PARALINGUISTIC_PLACEHOLDERS.items():
        value = value.replace(placeholder, tag)
    return value


def build_structured_instruction(
    *, dialect=None, style=None, speed=None, pitch=None, volume=None,
    emotion=None, ip=None, schema="zh",
):
    """Build the ordered assistant-side caption consumed during SFT."""
    schema = str(schema).strip().lower()
    values = (1, "speaker_1", dialect, style, speed, pitch, volume, emotion)
    if schema in {"zh", "chinese"}:
        fields, ip_key = _ZH_FIELDS, "IP"
    elif schema in {"en", "english"}:
        fields, ip_key = _EN_FIELDS, "ip"
    else:
        raise ValueError(f"Unsupported structured instruction schema: {schema!r}")

    item = OrderedDict(zip(fields, values))
    item["BGM"] = OrderedDict((key, None) for key in _BGM_FIELDS)
    item[ip_key] = ip
    payload = OrderedDict((("audio_sequence", [item]),))
    return json.dumps(payload, ensure_ascii=False)


def build_task_instruction(task, *, schema=None, **controls):
    """Build a task caption while preventing unrelated controls from leaking."""
    task = str(task).strip().upper()
    allowed = {
        "BASIC": {"speed", "pitch", "volume"},
        "DIALECT": {"dialect"},
        "EMOTION": {"emotion"},
        "VOICE_DESIGN": {"style"},
        "STYLE": {"style"},
        "IP": {"ip"},
    }
    if task not in allowed:
        raise ValueError(f"Unsupported TTS control task: {task!r}")
    unknown = set(controls) - allowed[task]
    if unknown:
        raise ValueError(f"{task} does not accept control fields: {sorted(unknown)!r}")
    if schema is None:
        schema = "en" if task == "DIALECT" else "zh"
    return build_structured_instruction(schema=schema, **controls)


__all__ = [
    "DEFAULT_TTS_PROMPT", "PARALINGUISTIC_PLACEHOLDERS",
    "PARALINGUISTIC_TAGS",
    "append_optional_target_language", "contains_paralinguistic_tag",
    "build_task_instruction",
    "build_tts_prompt", "build_structured_instruction",
    "detect_language_id", "detect_text_language_once",
    "normalize_instruction", "normalize_tts_prompt",
    "preserve_multilingual_text", "protect_paralinguistic_tags",
    "resolve_request_language",
    "restore_paralinguistic_tags", "target_language_from_prompt",
    "validate_text_input",
]
