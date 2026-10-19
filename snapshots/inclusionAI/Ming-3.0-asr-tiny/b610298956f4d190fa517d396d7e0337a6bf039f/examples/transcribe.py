"""Transcribe local audio with the aligned Ming 3.0 ASR Tiny model."""
import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
from asr_request import (
    context_chunk_frames, decode_transcript, prepare_asr_request,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True, help="Complete checkpoint directory or model ID")
    parser.add_argument("--audio", type=Path, required=True)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--attention", choices=("sdpa", "eager"), default="sdpa")
    parser.add_argument("--max-new-tokens", type=int, default=256)
    parser.add_argument("--prompt", default=None)
    parser.add_argument("--language-hint", choices=("zh", "en"),
                        help="Optional known-language prefix; omit when language is unknown")
    parser.add_argument("--audio-chunk-frames", type=int,
                        help="Mel frames per audio encoder chunk; 6000 supports up to 60-second chunks")
    parser.add_argument("--context-chunks", action="store_true",
                        help="Context ASR: 3000 frames up to 30 s, else 6000")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not args.audio.is_file():
        parser.error(f"Audio file does not exist: {args.audio}")
    if args.max_new_tokens < 1:
        parser.error("--max-new-tokens must be positive")
    if args.audio_chunk_frames is not None and args.audio_chunk_frames < 1:
        parser.error("--audio-chunk-frames must be positive")
    if args.context_chunks and args.audio_chunk_frames is not None:
        parser.error("Use either --context-chunks or --audio-chunk-frames")

    import soundfile as sf
    import torch
    from transformers import AutoModelForCausalLM, AutoProcessor

    if not args.device.startswith("cuda") or not torch.cuda.is_available():
        parser.error("The supported inference path requires a CUDA GPU")
    processor = AutoProcessor.from_pretrained(args.model, trust_remote_code=True)
    model = AutoModelForCausalLM.from_pretrained(
        args.model, trust_remote_code=True, dtype=torch.bfloat16,
        device_map=args.device, attn_implementation=args.attention,
    ).eval()
    waveform, rate = sf.read(args.audio, dtype="float32", always_2d=True)
    audio_chunk_frames = (context_chunk_frames(len(waveform) / rate)
                          if args.context_chunks else args.audio_chunk_frames)
    if audio_chunk_frames is not None:
        model.config.audio_config.chunk_frames = audio_chunk_frames
    inputs = prepare_asr_request(
        processor, (waveform.T, rate), prompt=args.prompt,
        language_hint=args.language_hint, audio_chunk_frames=audio_chunk_frames,
    ).to(model.device)
    eos = getattr(model.config, "text_config", model.config).eos_token_id
    with torch.inference_mode():
        output = model.generate(
            **inputs, max_new_tokens=args.max_new_tokens, do_sample=False,
            eos_token_id=eos, pad_token_id=eos, no_repeat_ngram_size=10,
        )
    generated = output[0, inputs.input_ids.shape[1]:]
    transcript = decode_transcript(processor.tokenizer, generated.tolist())
    print(transcript)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps({
            "audio": str(args.audio), "model": args.model, "text": transcript,
            "language_hint": args.language_hint,
            "audio_chunk_frames": audio_chunk_frames,
            "generated_token_ids": generated.tolist(), "max_new_tokens": args.max_new_tokens,
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
