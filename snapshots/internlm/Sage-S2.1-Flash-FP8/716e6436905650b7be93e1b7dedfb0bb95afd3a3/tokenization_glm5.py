# coding=utf-8
# Copyright 2026 The Intern team and Shanghai AI Lab team. All rights reserved.
"""Sage-S2.1-Flash tokenizer that keeps control-token spellings in content literal.

Shipped inside the model directory and loaded through ``auto_map`` with
``trust_remote_code=True``; no inference-engine change is required. The config
keeps the stock ``tokenizer_class``, so without ``trust_remote_code`` the stock
tokenizer loads (exports keep that, see ``save_pretrained``). The backend
is the stock ``tokenizers.Tokenizer`` (only its normalizer gains two steps), so
inference engines that decode through ``tokenizer._tokenizer`` work unchanged.

Engines render a conversation to a string (``apply_chat_template`` with
``tokenize=False``) and tokenize that string afterwards, so a control-token
spelling inside message content (``<tool_call>``, ``</think>``, ``<|image|>``
...) becomes a real control ID, indistinguishable from template structure.
The training pipeline (xtuner #2208) encodes such spellings as ordinary text
and encodes everything between genuine controls as one BPE run. This class
reproduces that encoding with two small hooks, leaving every tokenizer API to
the stock implementation:

* ``apply_chat_template`` breaks each control-token spelling found in the
  caller's strings (message fields, tools, documents, dict keys included) by
  inserting ``LITERAL_MARK`` after its first character. The template renders
  as usual; the rendered structure is unchanged, and processors scanning the
  text for media placeholders no longer see the broken spellings.
* The backend tokenizer is wrapped. Input containing ``LITERAL_MARK`` is
  encoded by a copy of the original backend whose normalizer removes the mark.
  Added tokens are matched before normalization, so the broken spellings are
  not matched and are encoded with the ordinary BPE of their surrounding run,
  while template-written controls keep their IDs. Truncation, padding,
  post-processing, offsets (in the coordinates of the given string), tensor
  conversion and the other fast-tokenizer features are the backend's own.
  Input without the mark goes to the untouched original backend.

``LITERAL_MARK`` is U+FDD0 U+FDD1 (Unicode noncharacters). A U+FDD0 in the
caller's strings is escaped as U+FDD0 U+FDD2 before marking and restored by
the same normalizer, so every caller string is encoded as written.
"""
from __future__ import annotations

import copy
import inspect
import json
import os
import re

from tokenizers import Tokenizer, normalizers
from transformers import PreTrainedTokenizerFast

STOCK_TOKENIZER_CLASS = 'TokenizersBackend'
STOCK_PROCESSOR_CLASS = 'Glm5NextProcessor'

_RESERVED = '\ufdd0'
LITERAL_MARK = _RESERVED + '\ufdd1'
_ESCAPED_RESERVED = _RESERVED + '\ufdd2'
# Media parts inside an assistant message while its inline reasoning is split.
_MEDIA_SLOT = re.compile(_RESERVED + '\ufdd3(\\d+)' + _RESERVED + '\ufdd3')
_TEMPLATE_MEDIA = {
    'image': '<|begin_of_image|><|image|><|end_of_image|>',
    'image_url': '<|begin_of_image|><|image|><|end_of_image|>',
    'video': '<|begin_of_video|><|video|><|end_of_video|>',
    'video_url': '<|begin_of_video|><|video|><|end_of_video|>',
    'audio': '<|begin_of_audio|><|end_of_audio|>',
    'audio_url': '<|begin_of_audio|><|end_of_audio|>',
    'input_audio': '<|begin_of_audio|><|end_of_audio|>',
}
# The official template infers reasoning from content containing </think>.
_INLINE_REASONING_RULE = "split('</think>')"


def _tool_schemas(tools):
    """Python functions become JSON schemas here (as the parent would do), so
    their docstrings are protected too."""
    if not isinstance(tools, (list, tuple)):
        return tools
    from transformers.utils import get_json_schema
    return [get_json_schema(tool) if inspect.isfunction(tool) else tool for tool in tools]


def _escape(text: str) -> str:
    return text.replace(_RESERVED, _ESCAPED_RESERVED)


def _contains_mark(value) -> bool:
    if isinstance(value, str):
        return _RESERVED in value
    if isinstance(value, (list, tuple)):
        return any(_contains_mark(item) for item in value)
    return False


def _marked_backend_of(backend: Tokenizer) -> Tokenizer:
    """A separate copy of the stock backend whose normalizer strips LITERAL_MARK
    and restores escaped U+FDD0. Used only for input that contains the mark.

    The stock backend itself is never modified, so the official normalizer
    (None), the saved tokenizer.json and LMDeploy's token profile are unchanged.
    Added tokens are matched before normalization, so a marked spelling is not
    matched and is encoded as ordinary text, while template-written controls
    keep their IDs.
    """
    marked = Tokenizer.from_str(backend.to_str())
    steps = [normalizers.Replace(LITERAL_MARK, ''), normalizers.Replace(_ESCAPED_RESERVED, _RESERVED)]
    base = backend.normalizer
    marked.normalizer = normalizers.Sequence(steps if base is None else steps + [base])
    return marked


class Glm5Tokenizer(PreTrainedTokenizerFast):
    """Stock Sage-S2.1-Flash fast tokenizer with literal-safe chat encoding."""

    # No ``__init__`` override: transformers 5.x rebuilds the backend from bare
    # vocab/merges (dropping the tokenizer.json pre-tokenizer) for subclasses
    # that define one. The backend is wrapped wherever it is assigned instead.
    @property
    def _tokenizer(self):
        return self.__dict__.get('_glm_backend')

    @_tokenizer.setter
    def _tokenizer(self, backend):
        self.__dict__['_glm_backend'] = backend
        self.__dict__.pop('_glm_marked', None)

    def _marked_view(self):
        """Shallow copy of this tokenizer whose backend is the marked copy.

        Only the copy's attributes change; the shared tokenizer is untouched, so
        concurrent calls stay independent.
        """
        marked = self.__dict__.get('_glm_marked')
        if marked is None or marked[0] is not self.__dict__.get('_glm_backend'):
            backend = self.__dict__.get('_glm_backend')
            marked = (backend, _marked_backend_of(backend))
            self.__dict__['_glm_marked'] = marked
        view = copy.copy(self)
        view.__dict__['_glm_backend'] = marked[1]
        return view

    def _encode_plus(self, text, text_pair=None, *args, **kwargs):
        if _contains_mark(text) or _contains_mark(text_pair):
            return super(Glm5Tokenizer, self._marked_view())._encode_plus(text, text_pair, *args, **kwargs)
        return super()._encode_plus(text, text_pair, *args, **kwargs)

    # -- marking ------------------------------------------------------------
    def _spelling_pattern(self):
        vocab = self.get_added_vocab()
        cached = self.__dict__.get('_glm_spelling_pattern')
        if cached is None or cached[0] != len(vocab):
            # Longest first, so a spelling wins over the shorter ones it contains.
            spellings = sorted((s for s in vocab if len(s) > 1), key=len, reverse=True)
            pattern = re.compile('|'.join(map(re.escape, spellings))) if spellings else None
            cached = (len(vocab), pattern)
            self.__dict__['_glm_spelling_pattern'] = cached
        return cached[1]

    def _mark(self, escaped: str) -> str:
        pattern = self._spelling_pattern()
        if pattern is None:
            return escaped
        return pattern.sub(lambda match: match.group()[0] + LITERAL_MARK + match.group()[1:], escaped)

    def _break_text(self, text: str) -> str:
        return self._mark(_escape(text))

    def _break_run(self, texts: list[str], keep=None, offset: int = 0) -> list[str]:
        """Break spellings in texts the template renders back to back, including
        spellings that span two of them.

        ``keep(spelling, position)`` leaves a match unbroken; ``position`` is
        its offset in the escaped visible text, of which this run starts at
        ``offset``.
        """
        if len(texts) == 1 and keep is None:
            return [self._break_text(texts[0])]
        texts = [_escape(text) for text in texts]
        joined = ''.join(texts)
        pattern = self._spelling_pattern()
        cuts = [match.start() + 1 for match in pattern.finditer(joined)
                if keep is None or not keep(match.group(), offset + match.start())] if pattern is not None else []
        broken, start, index = [], 0, 0
        for text in texts:
            end = start + len(text)
            pieces, last = [], start
            while index < len(cuts) and cuts[index] < end:
                pieces += [joined[last:cuts[index]], LITERAL_MARK]
                last = cuts[index]
                index += 1
            pieces.append(joined[last:end])
            broken.append(''.join(pieces))
            start = end
        return broken

    @staticmethod
    def _text_of(item):
        if isinstance(item, str):
            return item
        if isinstance(item, dict) and item.get('type') == 'text' and isinstance(item.get('text'), str):
            return item['text']
        return None

    def _break_list(self, items, keep=None) -> list:
        # Content lists render their text parts concatenated, media as markers.
        broken, run = [], []
        position = 0

        def flush():
            nonlocal position
            texts = self._break_run([self._text_of(item) for item in run], keep, position) if run else []
            position += sum(len(_escape(self._text_of(item))) for item in run)
            for item, text in zip(run, texts):
                if isinstance(item, str):
                    broken.append(text)
                else:
                    broken.append({self._break(key): text if key == 'text' else self._break(value)
                                   for key, value in item.items()})
            run.clear()

        for item in items:
            if self._text_of(item) is not None:
                run.append(item)
            else:
                flush()
                broken.append(self._break(item))
                if isinstance(item, dict):
                    position += len(_TEMPLATE_MEDIA.get(item.get('type'), ''))
        flush()
        return broken

    def _break(self, value):
        if isinstance(value, str):
            return self._break_text(value)
        if isinstance(value, dict):
            return {self._break(key) if isinstance(key, str) else key: self._break(item) for key, item in value.items()}
        if isinstance(value, list):
            return self._break_list(value)
        if isinstance(value, tuple):
            return tuple(self._break_list(value))
        return value

    def _restore(self, escaped: str, media: list[str]) -> str:
        """Break the text between media slots, then put the media markers back."""
        pieces = []
        position = 0
        for match in _MEDIA_SLOT.finditer(escaped):
            pieces.append(self._mark(escaped[position:match.start()]))
            pieces.append(media[int(match.group(1))])
            position = match.end()
        pieces.append(self._mark(escaped[position:]))
        return ''.join(pieces)

    def _split_inline_reasoning(self, message: dict) -> dict | None:
        """Apply the template's inline-reasoning rule before marking.

        For an assistant message without string ``reasoning_content``, the
        official template renders ``content`` and splits it on ``</think>``.
        Marking would hide that spelling from the template, so the same split
        is done here and the parts are passed as ``reasoning_content`` and
        ``content``. Returns None when the rule does not apply.
        """
        if message.get('role') != 'assistant' or isinstance(message.get('reasoning_content'), str):
            return None
        content = message.get('content')
        if isinstance(content, str):
            parts = [content]
        elif isinstance(content, (list, tuple)):
            parts = content
        else:
            return None
        visible = []
        media = []
        for part in parts:
            if isinstance(part, str):
                visible.append(_escape(part))
            elif isinstance(part, dict) and part.get('type') == 'text':
                visible.append(_escape(str(part.get('text', ''))))
            elif isinstance(part, dict) and part.get('type') in _TEMPLATE_MEDIA:
                # Escaped text holds U+FDD0 only as U+FDD0 U+FDD2, so the slot is unambiguous.
                visible.append(f'{_RESERVED}\ufdd3{len(media)}{_RESERVED}\ufdd3')
                media.append(_TEMPLATE_MEDIA[part['type']])
        text = ''.join(visible)
        if '</think>' not in text:
            return None
        split = dict(message)
        split['reasoning_content'] = self._restore(text.split('</think>')[0].split('<think>')[-1], media)
        split['content'] = self._restore(text.split('</think>')[-1], media)
        return split

    def _keep_inline_reasoning_tags(self, message: dict) -> dict | None:
        """Mark an inline-reasoning message without splitting it.

        For renderers that read media items out of ``content`` themselves
        (``ProcessorMixin`` collects images and videos from the content list),
        splitting here would turn the list into strings and lose them. Instead
        the spellings the template's split consumes stay unbroken -- every
        ``</think>`` and each ``<think>`` before the first ``</think>`` -- so
        the template splits exactly as it does for the stock tokenizer, and
        every other spelling is broken. Returns None when the rule does not
        apply.
        """
        if message.get('role') != 'assistant' or isinstance(message.get('reasoning_content'), str):
            return None
        content = message.get('content')
        if isinstance(content, str):
            visible = _escape(content)
        elif isinstance(content, (list, tuple)):
            visible = ''.join(_escape(self._text_of(part)) if self._text_of(part) is not None
                              else _TEMPLATE_MEDIA.get(part.get('type'), '') if isinstance(part, dict) else ''
                              for part in content)
        else:
            return None
        first_close = visible.find('</think>')
        if first_close < 0:
            return None

        def keep(spelling, position):
            return spelling == '</think>' or (spelling == '<think>' and position < first_close)

        kept = {key: self._break(value) for key, value in message.items() if key != 'content'}
        kept['content'] = (self._break_run([content], keep)[0] if isinstance(content, str)
                           else self._break_list(list(content), keep))
        return kept

    def _protect_message(self, message, inline_reasoning: str | None):
        if not isinstance(message, dict):
            return self._break(message)
        if inline_reasoning == 'keep':
            kept = self._keep_inline_reasoning_tags(message)
            return self._break(message) if kept is None else kept
        split = self._split_inline_reasoning(message) if inline_reasoning == 'split' else None
        if split is None:
            return self._break(message)
        return {
            key: (value if key in ('content', 'reasoning_content') else self._break(value))
            for key, value in split.items()
        }

    def _protect_conversation(self, conversation, inline_reasoning: str | None):
        messages = getattr(conversation, 'messages', conversation)
        return [self._protect_message(message, inline_reasoning) for message in messages]

    def _uses_inline_reasoning_rule(self, chat_template) -> bool:
        template = chat_template if chat_template is not None else self.chat_template
        if isinstance(self.chat_template, dict):
            template = self.chat_template.get(template if isinstance(template, str) else 'default', template)
        return isinstance(template, str) and _INLINE_REASONING_RULE in template

    # -- chat template ------------------------------------------------------
    def protect_chat_arguments(self, arguments: dict, chat_template: str | None = None,
                               keep_media_items: bool = False) -> None:
        """Break control-token spellings in the caller strings of bound
        ``apply_chat_template`` arguments, in place.

        Shared with ``Glm5Processor.apply_chat_template``, which renders the
        template itself and only calls this tokenizer to encode the result;
        ``chat_template`` is the template that will actually render, and
        ``keep_media_items`` keeps content lists intact for a caller that
        collects media from them.
        """
        template = chat_template if chat_template is not None else arguments.get('chat_template')
        inline_reasoning = None
        if self._uses_inline_reasoning_rule(template):
            inline_reasoning = 'keep' if keep_media_items else 'split'
        conversation = arguments['conversation']
        is_batch = (isinstance(conversation, (list, tuple)) and len(conversation) > 0
                    and (isinstance(conversation[0], (list, tuple)) or hasattr(conversation[0], 'messages')))
        if is_batch:
            arguments['conversation'] = [self._protect_conversation(chat, inline_reasoning) for chat in conversation]
        elif isinstance(conversation, (list, tuple)) or hasattr(conversation, 'messages'):
            arguments['conversation'] = self._protect_conversation(conversation, inline_reasoning)
        if arguments.get('tools') is not None:
            arguments['tools'] = self._break(_tool_schemas(arguments['tools']))
        if arguments.get('documents') is not None:
            arguments['documents'] = self._break(arguments['documents'])

    def apply_chat_template(self, conversation, *args, **kwargs):
        """Stock ``apply_chat_template`` on literal-safe inputs.

        Every option (tokenize, padding, truncation, return_tensors,
        return_dict, return_assistant_tokens_mask, batched conversations, ...)
        is handled by the parent implementation.
        """
        parent = super().apply_chat_template
        bound = inspect.signature(parent).bind(conversation, *args, **kwargs)
        self.protect_chat_arguments(bound.arguments)
        if (bound.arguments.get('sanitize_control_tokens') and bound.arguments.get('tokenize', True)
                and not bound.arguments.get('return_assistant_tokens_mask')):
            # transformers' own sanitizing (>= 5.20) is redundant once the spellings are broken, and it
            # would encode the template's media placeholders kept by the inline-reasoning split as text.
            # Invalid combinations still reach the parent and raise as stock.
            bound.arguments['sanitize_control_tokens'] = False
        return parent(*bound.args, **bound.kwargs)

    def _set_processor_class(self, processor_class: str):
        super()._set_processor_class(STOCK_PROCESSOR_CLASS if processor_class == 'Glm5Processor' else processor_class)

    def save_pretrained(self, save_directory, legacy_format=None, filename_prefix=None, push_to_hub=False, **kwargs):
        """Stock save, with the stock class named in ``tokenizer_config.json``.

        Like the delivered config, an export then loads this class only through
        ``auto_map`` with ``trust_remote_code=True`` and the stock tokenizer
        without it, instead of failing on an unknown class name.
        """
        files = super().save_pretrained(save_directory, legacy_format=legacy_format,
                                        filename_prefix=filename_prefix, push_to_hub=push_to_hub, **kwargs)
        for path in files or ():
            if os.path.basename(path).endswith('tokenizer_config.json') and os.path.isfile(path):
                with open(path, encoding='utf-8') as f:
                    config = json.load(f)
                config['tokenizer_class'] = STOCK_TOKENIZER_CLASS
                with open(path, 'w', encoding='utf-8') as f:
                    f.write(json.dumps(config, indent=2, sort_keys=True, ensure_ascii=False) + '\n')
        return files
