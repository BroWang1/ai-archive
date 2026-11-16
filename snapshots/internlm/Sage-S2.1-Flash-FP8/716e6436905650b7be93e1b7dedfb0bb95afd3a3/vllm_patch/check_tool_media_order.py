# coding=utf-8
# Copyright 2026 The Intern team and Shanghai AI Lab team. All rights reserved.
"""vLLM HfRenderer.render_messages (the server's chat path) on tool results with images:
image order fed to the multimodal processor vs the template's placeholder order (CPU, no
weights; image sizes identify the order).

    python vllm_patch/check_tool_media_order.py <Sage-S2.1-Flash model dir>

Run it before and after applying the patch: stock vLLM 0.33.0 prints BAD for the reversed
cases, the patched one OK for all.
"""
import base64
import io
import json
import sys

from PIL import Image

import vllm
from vllm.config import ModelConfig, ParallelConfig
from vllm.multimodal import MULTIMODAL_REGISTRY
from vllm.multimodal.processing.context import TimingContext
from vllm.multimodal.processing.inputs import ProcessorInputs
from vllm.renderers.params import ChatParams
import types

from vllm.renderers.hf import HfRenderer
from vllm.tokenizers.registry import cached_tokenizer_from_config

MODEL = sys.argv[1]
SIDES = {0: 224, 1: 252, 2: 280, 3: 308}


def url(k):
    buf = io.BytesIO()
    Image.new('RGB', (SIDES[k], SIDES[k]), (40 * k, 0, 0)).save(buf, format='PNG')
    return {'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode()}}


def calls(*ids):
    return {'role': 'assistant', 'content': '', 'tool_calls': [
        {'id': i, 'type': 'function', 'function': {'name': 'get_weather', 'arguments': '{"city": "x"}'}} for i in ids]}


def tool(i, *parts, key='tool_call_id'):
    return {'role': 'tool', key: i, 'content': list(parts)}


TEXT = lambda t: {'type': 'text', 'text': t}  # noqa: E731
TOOLS = [{'type': 'function', 'function': {'name': 'get_weather', 'parameters': {
    'type': 'object', 'properties': {'city': {'type': 'string'}}}}}]
USER = {'role': 'user', 'content': [url(0), TEXT('maps?')]}
CASES = {
    'reversed': ([USER, calls('c1', 'c2'), tool('c2', url(1), TEXT('R2')), tool('c1', url(2), TEXT('R1'))], [0, 2, 1]),
    'in_order': ([USER, calls('c1', 'c2'), tool('c1', url(1), TEXT('R1')), tool('c2', url(2), TEXT('R2'))], [0, 1, 2]),
    'three_reversed': ([USER, calls('a', 'b', 'c'), tool('c', url(3)), tool('b', url(2)), tool('a', url(1))], [0, 1, 2, 3]),
    'unknown_id_kept': ([USER, calls('c1', 'c2'), tool('c2', url(1)), tool('zz', url(2))], [0, 1, 2]),
    'duplicate_id_kept': ([USER, calls('c1', 'c2'), tool('c2', url(1)), tool('c2', url(2))], [0, 1, 2]),
    'no_tool_calls_kept': ([USER, {'role': 'assistant', 'content': 'ok'}, tool('c2', url(1)), tool('c1', url(2))], [0, 1, 2]),
    'text_only_results': ([USER, calls('c1', 'c2'), {'role': 'tool', 'tool_call_id': 'c2', 'content': 'R2'},
                           {'role': 'tool', 'tool_call_id': 'c1', 'content': 'R1'}], [0]),
}


def order(grids):
    side = {round(s / 28) * 2: k for k, s in SIDES.items()}
    return [side.get(int(g[1]), '?') for g in grids]


config = ModelConfig(model=MODEL, tokenizer=MODEL, trust_remote_code=True, max_model_len=8192)
class _Config(types.SimpleNamespace):
    """VllmConfig stand-in (no device on this box): unset ``xxx_config`` fields get the default
    instance of vllm.config.XxxConfig."""

    def __getattr__(self, name):
        import vllm.config as vc

        cls = getattr(vc, ''.join(part.capitalize() for part in name.split('_')), None)
        if cls is None:
            raise AttributeError(name)
        value = cls()
        setattr(self, name, value)
        return value


renderer = HfRenderer(_Config(model_config=config, renderer_num_workers=1, mm_ipc_gpu_memory_gb=0,
                              parallel_config=ParallelConfig()),
                      cached_tokenizer_from_config(config))
mm = MULTIMODAL_REGISTRY.create_processor(config)
patched = hasattr(sys.modules['vllm.renderers.hf'], '_glm5_next_tool_media_order')
print('vllm', vllm.__version__, 'patched' if patched else 'stock', type(renderer).__name__)
for name, (messages, expected) in CASES.items():
    params = ChatParams(chat_template_kwargs={'tools': TOOLS, 'add_generation_prompt': True})
    _, prompt = renderer.render_messages(json.loads(json.dumps(messages)), params)
    items = mm.data_parser.parse_mm_data(prompt['multi_modal_data'])
    out = mm.apply(ProcessorInputs(prompt=prompt['prompt_token_ids'], mm_data_items=items), TimingContext())
    got = order(out['mm_kwargs'].get_data()['image_grid_thw'])
    print(f"{'OK ' if got == expected else 'BAD'} {name:20s} placeholder order {expected} images fed {got}")
