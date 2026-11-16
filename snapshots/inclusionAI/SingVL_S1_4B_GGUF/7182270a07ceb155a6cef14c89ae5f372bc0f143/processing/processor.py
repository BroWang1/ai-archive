"""Tokenizer/image preprocessing only: no model loading or device selection."""
import json
import re
from pathlib import Path
import torch
from transformers import AutoProcessor
from .protocol import *

class Processor:
    def __init__(self, model, image_max_pixels=PUBLIC_IMAGE_MAX_PIXELS):
        self.model_path=str(Path(model).resolve())
        cfg=json.loads((Path(model)/'config.json').read_text())
        if cfg.get('jev_prefix_attention_mode')!='prefix_bidir' or cfg.get('jev_gdn_mode')!='causal': raise ValueError('attention contract mismatch')
        self.processor=AutoProcessor.from_pretrained(model,local_files_only=True)
        self.tokenizer=self.processor.tokenizer
        self.choice_ids=cfg['jev_soft_choice']['token_ids']
        self.labels=[self.tokenizer.decode([i],clean_up_tokenization_spaces=False) for i in self.choice_ids]
        if len(set(self.choice_ids))!=256 or any(not re.fullmatch('[A-Z]{2}',s) or self.tokenizer.encode(s,add_special_tokens=False)!=[i] for i,s in zip(self.choice_ids,self.labels)): raise ValueError('invalid 256-label contract')
        ip=self.processor.image_processor
        self.merge_size=ip.merge_size;self.image_factor=ip.patch_size*ip.merge_size
        self.min_pixels=int(cfg['jev_prefix_media']['IMAGE_MIN_TOKEN_NUM'])*self.image_factor**2
        self.image_max_pixels=int(image_max_pixels);self.image_id=cfg['image_token_id'];self.max_text_tokens=65536
        if self.image_max_pixels!=PUBLIC_IMAGE_MAX_PIXELS:raise ValueError('Use the published image budget for protocol compatibility')

    def encode_images(self, images):
            if not images:
                return {}
            prepared = [resize_image(image, self.image_factor, self.min_pixels, self.image_max_pixels) for image in images]
            return dict(self.processor.image_processor(images=prepared, return_tensors="pt", do_resize=False))

    def encode(self, prompt, image_features):
            ids = self.tokenizer.encode(prompt, add_special_tokens=False)
            if image_features:
                grid = image_features["image_grid_thw"]
                if ids.count(self.image_id) != len(grid):
                    raise Unsupported("expanded media tokens do not match the images")
                counts = iter(grid.prod(dim=-1).tolist())
                ids = [part for token in ids for part in (
                    [self.image_id] * (next(counts) // self.merge_size ** 2) if token == self.image_id else [token]
                )]
            limit = VISION_MAX_TOKENS if image_features else self.max_text_tokens
            if len(ids) > limit:
                raise Unsupported(f"maximum model length is {limit} tokens; got {len(ids)}")
            tokens = torch.tensor([ids], dtype=torch.long)
            batch = {"input_ids": tokens, "attention_mask": torch.ones_like(tokens), **image_features}
            if image_features:
                batch["mm_token_type_ids"] = (tokens == self.image_id).to(torch.int32)
            return batch, ids

    def prepare(self, state, questions, images=()):
        if len(images) > 4:
            raise Unsupported("at most four images per request")
        features = self.encode_images(images)
        rgb_images = [resize_image(im, self.image_factor, self.min_pixels, self.image_max_pixels) for im in images]
        prepared = []
        for qid, kind, st, ins, options in questions_for_state(state, questions, len(images)):
            prompt = render(st, ins, options, self.labels)
            batch, ids = self.encode(prompt, features)
            candidate_ids = self.choice_ids[:len(options)]
            raw_ids = self.tokenizer.encode(prompt, add_special_tokens=False)
            for label, tid in zip(self.labels, candidate_ids):
                if self.tokenizer.encode(prompt+label, add_special_tokens=False) != raw_ids+[tid]:
                    raise ValueError("candidate is not one appended token")
            prepared.append({"question_id": qid, "kind": kind, "options": options,
                "criteria": questions[qid].get("criteria"), "prompt": prompt,
                "input_ids": ids, "candidate_token_ids": candidate_ids,
                "image_features": features, "rgb_images": rgb_images, "batch": batch})
        return prepared

    @staticmethod
    def finish(item, candidate_logits):
        return decode_answer(item["kind"], item["options"], candidate_logits, item["criteria"])
