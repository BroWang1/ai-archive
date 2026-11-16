# coding=utf-8
# Copyright 2026 The Intern team and Shanghai AI Lab team. All rights reserved.
"""Sage-S2.1-Flash processor whose ``apply_chat_template`` keeps control-token
spellings in content literal, as ``Glm5Tokenizer.apply_chat_template`` does.

``ProcessorMixin.apply_chat_template`` renders the chat template itself and then
only calls ``self.tokenizer`` to encode the rendered prompt, so the protection
in ``Glm5Tokenizer.apply_chat_template`` never runs on that path: a
``<tool_call>`` or ``</think>`` typed in a message became a control ID, and a
literal ``<|image|>`` was counted as a media placeholder.

This class breaks the spellings in the caller's strings before the parent
renders, with the tokenizer's own marking (same rules, same marker). Everything
after that is the stock processor: the broken spellings are invisible to the
placeholder expansion, and the tokenizer encodes them as ordinary text and
drops the marker. Loaded through ``auto_map`` in ``processor_config.json``
with ``trust_remote_code=True``; requires the ``Glm5Tokenizer`` of
``tokenization_glm5.py`` as its tokenizer. The config keeps the stock
``processor_class``, so without ``trust_remote_code`` the stock processor loads
(exports keep that, see ``to_dict``).

The parent also collects images and videos on its own, message by message from
the top level of each ``content`` list, while the template renders a block of
tool results in the preceding assistant's ``tool_calls`` order (its
``can_sort`` rule) and reads media inside aggregated ``{"id": ..., "output":
[...]}`` results. Reordered results paired their placeholders with the wrong
media, and an aggregated result raised ``KeyError: 'type'``. Before the parent
runs, each tool block is therefore laid out the way the template emits it: one
message per result, in ``tool_calls`` order when ``can_sort`` holds. The
template renders that layout byte for byte as the original, and the parent's
collection order becomes the placeholder order (the rule of xtuner's
``sort_tool_messages`` / ``glm53_media_messages`` in Sage-S2.1-Flash training).
"""
from __future__ import annotations

import inspect
from collections.abc import Mapping

try:
    from transformers.models.glm5_next.processing_glm5_next import Glm5NextProcessor
except ImportError as exc:  # transformers < 5.17.0 has no glm5_next
    raise ImportError('Glm5Processor needs transformers >= 5.17.0 (Glm5NextProcessor); the official files '
                      'load no processor on this version either. The tokenizer works from 5.14.1') from exc


def _id_of(obj) -> str:
    """The template's ``id_of``: ``tool_call_id``, else ``id``, rendered as text."""
    if not isinstance(obj, Mapping):
        return ''
    for key in ('tool_call_id', 'id'):
        if obj.get(key):
            return str(obj[key])
    return ''


def _is_list_of_outputs(message) -> bool:
    """The template's ``is_list_of_outputs``: the first content item has an ``output`` key."""
    content = message.get('content')
    return isinstance(content, list) and bool(content) and isinstance(content[0], Mapping) and 'output' in content[0]


def _split_results(message) -> list | None:
    """One tool message per result of ``message``, rendered by the template exactly as the
    aggregated entry it comes from; ``None`` when a result would not render the same."""
    if not _is_list_of_outputs(message):
        return [message]
    results = []
    for entry in message['content']:
        result = {'role': 'tool'}
        if isinstance(entry, Mapping):
            result.update({key: entry[key] for key in ('tool_call_id', 'id') if key in entry})
            # A missing output renders empty, as the template's undefined ``entry.output`` does.
            result['content'] = entry['output'] if 'output' in entry else ''
        else:
            result['content'] = ''
        if _is_list_of_outputs(result):
            return None
        results.append(result)
    return results


def _sort_order(previous, results) -> list | None:
    """``tool_calls`` ids the template orders a block's ``results`` by (its ``can_sort``
    rule; ``previous`` is the message before the block), or ``None`` when it keeps the
    message order."""
    calls = previous.get('tool_calls') if previous is not None and previous.get('role') == 'assistant' else None
    if not calls:
        return None
    result_ids = [_id_of(result) for result in results]
    call_ids = [_id_of(call) for call in calls]
    if (not all(result_ids) or len(set(result_ids)) != len(result_ids) or not all(call_ids)
            or len(set(call_ids)) != len(call_ids) or not set(result_ids) <= set(call_ids)):
        return None
    return call_ids


def _results_in_rendered_order(conversation):
    """``conversation`` with every block of tool messages laid out as the template emits it:
    one message per result, in ``tool_calls`` order when ``can_sort`` holds. Unchanged when it
    is not a list of messages or a result cannot be laid out without changing the render."""
    if not isinstance(conversation, list) or not all(isinstance(m, Mapping) for m in conversation):
        return conversation
    split = []
    for message in conversation:
        results = _split_results(message) if message.get('role') == 'tool' else [message]
        if results is None:
            return conversation
        split.append(results)
    out, index = [], 0
    while index < len(conversation):
        if conversation[index].get('role') != 'tool':
            out.append(conversation[index])
            index += 1
            continue
        end = index
        while end + 1 < len(conversation) and conversation[end + 1].get('role') == 'tool':
            end += 1
        results = [result for message in split[index:end + 1] for result in message]
        order = _sort_order(conversation[index - 1] if index else None, results)
        if order is not None:
            position = {call_id: i for i, call_id in enumerate(order)}
            results.sort(key=lambda result: position[_id_of(result)])
        out.extend(results)
        index = end + 1
    return out


class Glm5Processor(Glm5NextProcessor):
    """Stock Sage-S2.1-Flash processor with literal-safe ``apply_chat_template``."""

    def _rendering_template(self, chat_template):
        """The template the parent will render, resolved the way it resolves it."""
        if chat_template is None:
            if isinstance(self.chat_template, dict):
                return self.chat_template.get('default')
            return self.chat_template
        if isinstance(self.chat_template, dict) and chat_template in self.chat_template:
            return self.chat_template[chat_template]
        return chat_template

    def apply_chat_template(self, conversation, *args, **kwargs):
        """Stock ``apply_chat_template`` on literal-safe inputs; every option is
        handled by the parent implementation."""
        protect = getattr(self.tokenizer, 'protect_chat_arguments', None)
        if protect is None:
            raise TypeError(f'Glm5Processor needs the Glm5Tokenizer of tokenization_glm5.py, '
                            f'got {type(self.tokenizer).__name__}; load with trust_remote_code=True')
        parent = super().apply_chat_template
        bound = inspect.signature(parent).bind(conversation, *args, **kwargs)
        template = self._rendering_template(bound.arguments.get('chat_template'))
        if isinstance(template, str) and 'is_list_of_outputs' in template and 'can_sort' in template:
            # The Sage-S2.1-Flash template's tool-block rules; a custom template renders as given.
            conversation = bound.arguments['conversation']
            if isinstance(conversation, list) and conversation and isinstance(conversation[0], list):
                bound.arguments['conversation'] = [_results_in_rendered_order(c) for c in conversation]
            else:
                bound.arguments['conversation'] = _results_in_rendered_order(conversation)
        protect(bound.arguments, chat_template=template, keep_media_items=True)
        return parent(*bound.args, **bound.kwargs)

    def to_dict(self):
        output = super().to_dict()
        output['processor_class'] = 'Glm5NextProcessor'
        return output
