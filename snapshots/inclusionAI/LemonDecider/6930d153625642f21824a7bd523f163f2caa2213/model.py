"""Standalone local decision inference (not an AIStudio Maya canvas component).

Inside the exported checkpoint this file can be run directly with --checkpoint .
The actual HF architecture lives in modeling_autojev.py/configuration_autojev.py.
"""
import argparse
import json
from pathlib import Path
import torch
from transformers import AutoModel, AutoProcessor

if Path(__file__).with_name('decision_utils.py').is_file():
    from decision_utils import predict_batch, answer_codes
else:
    from modeling.decision_utils import predict_batch, answer_codes


def load_model(checkpoint, device='cuda:0'):
    torch.set_num_threads(8)
    if torch.cuda.is_available():
        torch.backends.cuda.enable_cudnn_sdp(False)
    model = AutoModel.from_pretrained(str(checkpoint), trust_remote_code=True,
        local_files_only=True, dtype=torch.bfloat16, device_map=device,
        attn_implementation='sdpa').eval()
    processor = AutoProcessor.from_pretrained(str(checkpoint), local_files_only=True, trust_remote_code=True)
    processor.tokenizer.padding_side = 'left'
    codes, ids = answer_codes(processor.tokenizer)
    if codes != model.config.codes or ids != model.config.token_ids:
        raise ValueError('Checkpoint code/tokenizer mapping mismatch')
    return model, processor


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--checkpoint', default=str(Path(__file__).resolve().parent))
    parser.add_argument('--device', default='cuda:0')
    parser.add_argument('--input', help='JSON file containing a list of decision inputs')
    args = parser.parse_args()
    model, processor = load_model(args.checkpoint, args.device)
    rows = json.loads(Path(args.input).read_text()) if args.input else [{
        'state': '我想申请退款。', 'question': {'type': 'choice', 'instructions': '判断主要诉求',
        'criteria': {'refund': '退款相关', 'delivery': '物流相关', 'account': '账户相关'}}}]
    print(json.dumps(predict_batch(model, processor, rows), ensure_ascii=False, indent=2))
