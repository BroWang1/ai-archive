# GenFirst model release manifest

All paths below are relative to the root of this model release. These are the
checkpoints used for the paper results, not the later validation runs.

## VAE bundles

- `vae/e2e-f8d4/`: ImageNet f8d4 VAE initialized from SD-VAE.
- `vae/e2e-f16d32/`: decoder-finetuned f16d32 VAE used by the ImageNet-256
  class-conditional results.
- `vae/e2e-f16d32-nodecft/`: pre-decoder-finetune f16d32 VAE used by the
  ImageNet-512 results.
- `vae/e2e-flux-vae-sit-imagenet-s2/`: T2I variant A VAE (FLUX.1 init).
- `vae/e2e-flux-vae-mmdit-l2-t2i-s2/`: T2I variant B VAE (FLUX.1 init).
- `vae/qwenvit-siglip-b256-s2/`: Qwen3-VL ViT + ViT decoder VAE shaped with
  E2E + SigLIP supervision (Table 9).
- `vae/qwenvit-nlltrunk-s2/`: Qwen3-VL ViT + ViT decoder VAE shaped with
  E2E + VLM-NLL supervision (Table 9).
- `vae/e2e-joint-gan-l2-330k/`: Jointly E2E-shaped FLUX.1 image VAE + Cola text
  VAE (Table 10).
- `vae/e2e-vae-flux2-sitxl2-auxkl2p5e8-s3-20k/`: 32-channel f8d32 E2E FLUX.2 VAE
  (three-stage aspect-ratio-bucketed E2E + decoder finetune).

Every VAE directory contains:

- `<name>.pt`: directly loadable VAE state dict.
- `<name>-latents-stats.pt`: required latent normalization statistics.
- `<name>-discriminator-ckpt.pt`: only needed to resume end-to-end training.

In addition:

- `vae/e2e-joint-gan-l2-330k/` includes `e2e-joint-gan-l2-330k-text-vae.pt`
  (standalone E2E-reshaped Cola text VAE state dict).
- `vae/e2e-vae-flux2-sitxl2-auxkl2p5e8-s3-20k/` includes:
  - `e2e-vae-flux2-sitxl2-auxkl2p5e8-s3-20k.safetensors` and `diffusion_pytorch_model.safetensors`:
    diffusers-compatible safetensors weights.
  - `config.json` and `vae_params.json`: diffusers configuration and explicit per-channel
    `scaling_factor` and `shift_factor`:
    - `--vae_pth=vae/e2e-vae-flux2-sitxl2-auxkl2p5e8-s3-20k/e2e-vae-flux2-sitxl2-auxkl2p5e8-s3-20k.safetensors`
    - `--model.vae.scaling_factor=[0.887221,0.886926,0.887096,0.881914,0.886901,0.887307,0.886685,0.886833,0.886540,0.886646,0.887031,0.887073,0.887381,0.886768,0.887299,0.885674,0.886466,0.886795,0.886979,0.886519,0.886949,0.886949,0.887036,0.886828,0.887344,0.887004,0.886816,0.886799,0.887354,0.887523,0.887012,0.886643]`
    - `--model.vae.shift_factor=[-0.000623,0.000143,0.000282,0.001599,-0.001093,-0.000477,0.000855,-0.000830,-0.000883,0.001076,-0.000417,0.000200,0.000626,-0.000649,-0.000137,0.001453,-0.000816,-0.000307,-0.000290,0.000662,0.000484,0.000993,0.000574,-0.000139,-0.000914,0.000578,-0.000691,-0.000323,0.000619,-0.000606,-0.000372,0.000437]`
  - `e2e-vae-flux2-sitxl2-auxkl2p5e8-s3-20k-stage2-bn-latents-stats.pt`: Stage-2 70k SiT EMA BatchNorm statistics.

Keep each VAE and its latent statistics together.

## Class-conditional priors

ImageNet-256, paired with `vae/e2e-f16d32/`:

- `class-conditional/imagenet256/eit-imagenet256-weak-20ep.pt`: weak model
  required for the paper's autoguidance evaluation.
- `class-conditional/imagenet256/eit-imagenet256-80ep.pt`
- `class-conditional/imagenet256/eit-imagenet256-480ep.pt`
- `class-conditional/imagenet256/eit-imagenet256-800ep.pt`

ImageNet-512, paired with `vae/e2e-f16d32-nodecft/`:

- `class-conditional/imagenet512/eit-imagenet512-80ep.pt`
- `class-conditional/imagenet512/eit-imagenet512-400ep.pt`

These prior checkpoints are directly accepted by
`Prior_only/generate.py --ckpt` and `Prior_only/scripts/eval_fid.sh` through its
`CKPT` override. Do not convert or strip them.

## Text-to-image priors

- `text-to-image/variant-a/eit-t2i-variant-a-512.pt`, paired with
  `vae/e2e-flux-vae-sit-imagenet-s2/`.
- `text-to-image/variant-b/eit-t2i-variant-b-512.pt`, paired with
  `vae/e2e-flux-vae-mmdit-l2-t2i-s2/`.

These checkpoints are directly accepted by `Prior_only/infer_t2i.py` and the
GenEval/DPG generation scripts. Pass the matching VAE, latent statistics and
`--text-encoder-name openai/clip-vit-large-patch14`; no checkpoint conversion
is required.

## Shared visual latents (generation + understanding, Table 9)

- `shared-latents/siglip/eit-qwenvit-siglip-t2i-512.pt`, paired with
  `vae/qwenvit-siglip-b256-s2/` (`0.90` GenEval, `83.76` DPG-Bench, `79.25%` IN1K linear probe).
- `shared-latents/vlm-nll/eit-qwenvit-vlm-nll-t2i-512.pt`, paired with
  `vae/qwenvit-nlltrunk-s2/` (`0.89` GenEval, `83.49` DPG-Bench, `81.69%` IN1K linear probe).

Directly accepted by `Prior_only/infer_t2i.py` and `Prior_only/gen_for_bench.py`
with `--vae-arch qwenvit --vae-vit-path Qwen/Qwen3-VL-2B-Instruct`.

## Unified text-image modeling (`JointMMDiT-XL/2`, Table 10)

- `unified-text-image/e2e-joint/eit-joint-e2e-text-e2e-img-512-sft.pt`: Phase-3
  512x512 SFT checkpoint for text-to-image (`86.57` GenEval, `72.68` DPG-Bench).
- `unified-text-image/e2e-joint/eit-joint-e2e-text-e2e-img-512.pt`: Phase-2
  512x512 checkpoint before SFT for image-to-text COCO captioning (`33.28` CIDEr,
  `57.97` CLIPScore).
- Both pair with `vae/e2e-joint-gan-l2-330k/` (`--image-vae-ckpt vae/e2e-joint-gan-l2-330k/e2e-joint-gan-l2-330k.pt`;
  the reshaped text VAE weights are already embedded inside `ckpt["text_vae"]`).

## Checkpoint formats produced by the repository

- `train_prior_only.py`, `train_t2i_frozen.py`, and `train_joint_frozen.py` save
  final checkpoints in direct evaluation format.
- Class-conditional `train_e2e.py` checkpoints can be used directly by the
  top-level `generate.py`; all `train_e2e.py`, `train_e2e_vae.py`, and
  `train_decoder_ft.py` checkpoints can be evaluated directly for reconstruction.
  Before using either checkpoint's VAE with a separate prior, run
  `Prior_only/scripts/run_prior_only_pipeline.sh extract` (or `save_joint_vae_weights.py`
  for `train_joint_e2e.py`), which produces a standalone VAE bundle.
- A downloaded VAE bundle is already extracted and must not be extracted again.

Weights are released under CC BY-NC 4.0. See the repository's
`MODEL_CARD.md`, `NOTICE`, and documentation for complete terms and commands.
