"""Send a crystal projector's scientific embeddings to a matching vLLM server.

Input: a CPU-loadable tensor [num_atoms, 64] containing the CHGNet atom states
specified by the cif/jarvis checkpoint. The language-model directory supplies
its tokenizer, config, and sharded safetensors input embedding table.
"""
import argparse
import base64
import io
import json
from pathlib import Path
import sys
import urllib.request

import torch
from safetensors import safe_open

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from load_projector import load_projector

MARKER = "￰SAGE_PAYLOAD￱"


def build_prompt_embeds(projector, config, features, tokenizer, base_model, question):
    """Use the checkpoint's native template and replace its scientific span."""
    with torch.inference_mode():
        scientific = projector(features.float(), torch.arange(len(features)))
    spec = config["prompt"]
    name = spec["names"][0][0]
    messages = [
        {"role": "system", "content": spec["system"]},
        {"role": "user", "content": f"{name}:\n{MARKER}\n\nQuestion: {question}"},
    ]
    prompt = tokenizer.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True, **spec["template_kwargs"]
    )
    before, after = prompt.split(MARKER)
    prefix_ids = tokenizer(before, add_special_tokens=False)["input_ids"]
    suffix_ids = tokenizer(after, add_special_tokens=False)["input_ids"]

    # Text rows must come from the exact embedding table used by the server.
    weight_map = json.loads((base_model / "model.safetensors.index.json").read_text())["weight_map"]
    key = next(name for name in weight_map if name.endswith("embed_tokens.weight"))
    with safe_open(base_model / weight_map[key], framework="pt", device="cpu") as weights:
        table = weights.get_slice(key)
        rows = {index: table[index:index + 1] for index in set(prefix_ids + suffix_ids)}
    prefix = torch.cat([rows[index] for index in prefix_ids])
    suffix = torch.cat([rows[index] for index in suffix_ids])
    return torch.cat([prefix, scientific.to(prefix), suffix]).contiguous()


def complete(api_base, model, prompt_embeds, stop_token_ids, max_tokens):
    """Completions receives the full templated sequence, including text rows."""
    buffer = io.BytesIO()
    torch.save(prompt_embeds.cpu().contiguous(), buffer)
    body = {
        "model": model,
        "prompt_embeds": base64.b64encode(buffer.getvalue()).decode("ascii"),
        "max_tokens": max_tokens,
        "temperature": 0,
        "stop_token_ids": stop_token_ids,
        "skip_special_tokens": False,
    }
    request = urllib.request.Request(
        api_base.rstrip("/") + "/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=600) as response:
        return json.load(response)["choices"][0]["text"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--component", type=Path, required=True)
    parser.add_argument("--base-model", type=Path, required=True)
    parser.add_argument("--features", type=Path, required=True)
    parser.add_argument("--question", default="Predict the formation energy per atom in eV/atom.")
    parser.add_argument("--api-base", default="http://127.0.0.1:8000/v1")
    parser.add_argument("--model", default="sage-sciperception")
    parser.add_argument("--max-tokens", type=int, default=4096)
    args = parser.parse_args()

    projector, config = load_projector(args.component, device="cpu")
    if config["task"] != "cif/jarvis":
        parser.error("This example uses the cif/jarvis input format and unnumbered crystal prompt.")
    features = torch.load(args.features, map_location="cpu", weights_only=True)
    from transformers import AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(args.base_model, local_files_only=True)
    prompt_embeds = build_prompt_embeds(
        projector, config, features, tokenizer, args.base_model, args.question
    )
    language_config = json.loads((args.base_model / "config.json").read_text())
    text_config = language_config.get("text_config", language_config)
    eos = text_config["eos_token_id"]
    stop_ids = eos if isinstance(eos, list) else [eos]
    print(complete(args.api_base, args.model, prompt_embeds, stop_ids, args.max_tokens))


if __name__ == "__main__":
    main()
