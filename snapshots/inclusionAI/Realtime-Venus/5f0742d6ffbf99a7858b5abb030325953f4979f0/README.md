---
license: apache-2.0
language:
  - en
  - zh
library_name: transformers
pipeline_tag: any-to-any
tags:
  - multimodal
  - audio
  - video
  - speech
  - streaming
  - full-duplex
  - long-video
  - custom-code
---

<p align="center">
  <img src="./assets/venus-logo-white.gif" alt="Realtime-Venus logo" width="180">
</p>

<h1 align="center" style="text-align: center;">Realtime-Venus</h1>

<p align="center" style="text-align: center;"><strong>A full-duplex interaction system with asynchronous delegation</strong></p>

<p align="center" style="text-align: center;"><strong>English</strong> | <a href="https://huggingface.co/inclusionAI/Realtime-Venus/blob/main/README_zh.md">简体中文</a></p>

<p align="center">
<a href="https://realtime-venus.github.io/"><img src="https://img.shields.io/badge/Project_Page-4c9aff.svg?logo=googlechrome&logoColor=white" alt="Project Page"></a>
<a href="https://huggingface.co/inclusionAI/Realtime-Venus"><img src="https://img.shields.io/badge/Hugging_Face-Realtime--Venus-FFD21E.svg?logo=huggingface&logoColor=000" alt="Realtime-Venus on Hugging Face"></a>
<a href="https://www.modelscope.cn/models/inclusionAI/Realtime-Venus"><img src="https://img.shields.io/badge/ModelScope-Realtime--Venus-624AFF.svg?logo=modelscope&logoColor=white" alt="Realtime-Venus on ModelScope"></a>
<a href="https://arxiv.org/abs/2609.13814"><img src="https://img.shields.io/badge/arXiv-2609.13814-b31b1b.svg?logo=arxiv&logoColor=white" alt="arXiv"></a>
<a href="https://github.com/inclusionAI/Realtime-Venus"><img src="https://img.shields.io/badge/GitHub-Realtime--Venus-181717.svg?logo=github&logoColor=white" alt="GitHub"></a>
<a href="https://huggingface.co/inclusionAI/Realtime-Venus/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-Apache_2.0-0b7285.svg?logo=apache&logoColor=white" alt="Apache License 2.0"></a>
</p>

<p align="center">
  <a href="https://arxiv.org/abs/2609.13814">
    <img src="https://arxiv.org/html/2609.13814v1/case.png" alt="Example proactive, delegated, and full-duplex interactions with Realtime-Venus" width="100%">
  </a>
</p>
<p align="center"><em>Realtime-Venus supports proactive audio-visual interaction, asynchronous delegation, and interruption-aware full-duplex dialogue.</em></p>

## 1. 🧭 Overview

This repository hosts two checkpoints of the
[Realtime-Venus](https://realtime-venus.github.io/) system:

- **Realtime-Venus-Omni** (`Realtime-Venus-Omni/`): the 9B audio-visual
  interaction model. It continuously watches and listens, decides whether and
  when to respond, and generates text and speech on a shared causal timeline.
  Adapted from MiniCPM-o 4.5, it supports proactive interaction, semantic
  interruption handling, and training-free long-video memory.
- **Realtime-Venus-Audio** (`Realtime-Venus-Audio/`): the audio-focused
  checkpoint on the same streaming backbone, for audio understanding and
  audio-driven conversation with text or speech output.

Both directories contain model weights and custom Hugging Face Transformers
code. The asynchronous Realtime-Venus-Harness and its external tool
integrations live in the
[GitHub repository](https://github.com/inclusionAI/Realtime-Venus).

## 2. ✨ Highlights

- **Native full-duplex conversation:** keeps perceiving while speaking and
  distinguishes backchannels, interruptions, corrections, and redirections.
- **Omni-Proactive interaction:** continuously processes temporally aligned
  video and audio, and initiates a response when an event warrants it — without
  waiting for a user prompt.
- **Delegation:** emits in-stream `<delegate>` requests on the shared causal
  timeline and consumes asynchronous backend results the same way, so external
  tasks never block the ongoing conversation. (Executing requests requires the
  Realtime-Venus-Harness runtime, available in the
  [GitHub repository](https://github.com/inclusionAI/Realtime-Venus).)
- **Training-free long-video Memory:** archives visually informative moments,
  retrieves query-relevant and non-redundant evidence, and reassembles the
  corresponding audio-visual context — no additional training required.
- **Text and speech output:** generates response text together with native
  speech through the bundled Token2wav resources and a reference voice.

## 3. 📋 Model Details

| Item | Realtime-Venus-Omni | Realtime-Venus-Audio |
| --- | --- | --- |
| Parameters | 9B | 9B |
| Base architecture | MiniCPM-o 4.5 / Omni-Flow | MiniCPM-o 4.5 / Omni-Flow |
| Visual encoder | SigLIP2 | not used at inference |
| Audio encoder | Whisper-Medium | Whisper-Medium |
| Language backbone | Qwen3-8B | Qwen3-8B |
| Speech generation | Discrete S3 speech tokens with a streaming flow-matching decoder | same decoder, enabled in full-duplex mode |
| Inputs | Video/images, audio, and text | Audio and text |
| Outputs | Text and optional speech waveform | Text and speech waveform |
| Context length | 40,960 tokens | 40,960 tokens |
| Weight dtype | BF16 | BF16 |

## 4. 📊 Evaluation

All values are reported in the
[Realtime-Venus technical report](https://arxiv.org/abs/2609.13814).

<p align="center"><img src="assets/paper-understanding.svg" width="100%" alt="Radar charts comparing video understanding for Omni and audio understanding for Audio" /><br /><sub>Figure 1. Video and audio understanding results from the <a href="https://arxiv.org/html/2609.13814v1#S0.F1">paper</a>.</sub></p>

<p align="center"><img src="assets/paper-duplex.svg" width="100%" alt="Full-duplex benchmark comparisons for interruption handling and continuation under different types of overlapping speech" /><br /><sub>Figure 2. Full-duplex interaction results from the <a href="https://arxiv.org/html/2609.13814v1#S0.F2">paper</a>.</sub></p>

## 5. 🗂️ Repository Layout

```text
.
├── Realtime-Venus-Omni/          # Audio-visual full-duplex checkpoint
│   ├── model-*.safetensors       # Sharded model weights
│   ├── config.json, *.py         # Model config and custom Transformers code
│   ├── realtime_venus_omni_memory.py  # Public Memory entry point
│   ├── memory_adapter/           # Chat and Duplex Memory runtime
│   ├── assets/                   # Reference voice, Token2wav, demo videos
│   └── requirements.txt
├── Realtime-Venus-Audio/         # Audio-focused checkpoint
│   ├── model-*.safetensors       # Sharded model weights
│   ├── config.json, *.py         # Model config and custom Transformers code
│   └── assets/                   # Reference voice, Token2wav, demo audio
├── assets/                      # Brand resources (logo)
├── config.yaml                  # Model names and download directory mapping
├── download_models.py           # Unified Omni / Audio / all downloader
├── README.md
├── README_zh.md
└── LICENSE
```

The examples below write generated media to `output/`. Use a new filename or a
new output directory when repeating an experiment.

## 6. 🛠️ Installation

Running the inference examples requires Python 3.10, CUDA, and FFmpeg. First,
install the download dependencies and fetch the unified downloader from this
Hugging Face repository:

```bash
python -m pip install 'huggingface_hub>=0.34' 'PyYAML>=6.0'
hf download inclusionAI/Realtime-Venus download_models.py --local-dir .
```

Then choose the models to download:

| `--model` | Download |
| --- | --- |
| `omni` | Realtime-Venus-Omni for audio-visual interaction |
| `audio` | Realtime-Venus-Audio for audio understanding and conversation |
| `all` | Both models |

For example, download both models into the current directory:

```bash
python download_models.py --model all --local-dir .
```

Use `--model omni` or `--model audio` to download only the model you need.
The downloader reads this repository's root `config.yaml` and downloads each
selected model's complete directory, including weights, custom code, and
assets. It saves a download manifest and uses the Hugging Face Hub's standard
progress display and cache. Each download uses one repository revision.

Install the inference dependencies after downloading. For Omni or `all`:

```bash
python -m pip install -r Realtime-Venus-Omni/requirements.txt
```

Audio uses the same published dependency list; it does not have a separate
`requirements.txt`. If you downloaded only Audio, fetch that small file first
without downloading the Omni weights:

```bash
hf download inclusionAI/Realtime-Venus Realtime-Venus-Omni/requirements.txt --local-dir .
python -m pip install -r Realtime-Venus-Omni/requirements.txt
```

To download from Python instead, run this once from the directory containing
`download_models.py`. It uses the same downloader as the command above:

```python
from download_models import download_models

paths = download_models(model="omni", local_dir=".")  # "omni", "audio", or "all"
model_dir = paths["omni"]  # pathlib.Path; use paths["audio"] for Audio
```

The inference examples below load the downloaded local model directories. Run
them from the same directory; all asset and output paths are relative to it.

As an independent alternative, the ModelScope CLI (installed separately) can
download the entire mirror repository:

```bash
modelscope download --model inclusionAI/Realtime-Venus --local_dir .
```

This mirror command is separate from the Hugging Face downloader above.

## 7. 🎙️ Realtime-Venus-Omni Usages

Runnable standalone versions of these examples live in the
[Omni cookbook](https://github.com/inclusionAI/Realtime-Venus/tree/main/frontend/Realtime-Venus-Omni)
on GitHub.

### 7.1 🧱 Model Initialization

The examples below share the following model initialization; run each
example in a fresh Python process.
Chat and Duplex automatically load the default reference voice.

<details>
<summary>Click to show Omni model loading code.</summary>

```python
from pathlib import Path

import torch
from transformers import AutoModel, set_seed

Path("output").mkdir(exist_ok=True)
set_seed(42)
print("Loading model ...")
model = AutoModel.from_pretrained(
    "./Realtime-Venus-Omni",  # or an absolute path to the sub-directory
    trust_remote_code=True,
    local_files_only=True,
    attn_implementation="sdpa",
    torch_dtype=torch.bfloat16,
)
model.eval().cuda()
print("Model loaded.")
```

</details>

### 7.2 🔊 Duplex Omni Mode

`model = model.as_duplex()` switches the model to full-duplex streaming:
`prepare()` initializes the session, then each second of input is handled by
one `streaming_prefill()` + `streaming_generate()` pair, and `as_simplex()`
switches back to offline mode. Set `MAX_NUM_FRAMES` before importing
`minicpmo.utils`, otherwise videos longer than 64 seconds are truncated to the
default frame cap.

Subtitle font note: Duplex examples burn the response text into the output
video through FFmpeg/libass, which resolves fonts via fontconfig. Rendering
non-Latin responses (e.g. Chinese) requires a CJK-capable font on the system,
otherwise those glyphs show up as empty boxes. On any Linux distribution,
install one without root and refresh the font cache:

```bash
mkdir -p ~/.local/share/fonts
curl --fail --location --retry 3 \
  --output ~/.local/share/fonts/NotoSansCJKsc-Regular.otf \
  https://raw.githubusercontent.com/notofonts/noto-cjk/main/Sans/OTF/SimplifiedChinese/NotoSansCJKsc-Regular.otf
fc-cache -f
```

Package-manager equivalents: `apt install -y fonts-noto-cjk` (Debian/Ubuntu) or
`yum install -y cjkuni-ukai-fonts cjkuni-uming-fonts` (RHEL/Alibaba Cloud Linux).
No code changes are needed.

#### 7.2.1 Duplex Chat

Stream the demo video second by second and inject text questions at the seconds
given by `question_times` (paired with `questions`). The model listens
continuously and speaks when it answers.

<details>
<summary>Click to show the Duplex Chat code.</summary>

```python
import os

os.environ["MAX_NUM_FRAMES"] = "100000"

from minicpmo.utils import get_video_frame_audio_segments, generate_duplex_video

model = model.as_duplex()  # switch to full-duplex streaming
model.prepare()

video_path = "Realtime-Venus-Omni/assets/sample_1_real.mp4"
# each question is injected at the corresponding second
question_times = [60, 128]
questions = [
    "What do you see in the video so far?",
    "What is the color of the cooler labeled PRIME near the team bench?",
]
question_plan = dict(zip(question_times, questions))
print(f"Extracting per-second audio and frames from {video_path} ...")
frames, audios, _ = get_video_frame_audio_segments(
    video_path, stack_frames=1, use_ffmpeg=True, adjust_audio_length=True
)
print(f"Streaming {len(audios)} seconds; questions are injected at {question_times}.")
results, output_audio = [], []
for second, (frame, audio) in enumerate(zip(frames, audios), start=1):
    model.streaming_prefill(
        audio_waveform=audio,
        frame_list=[frame] if frame is not None else None,
        text_list=[question_plan[second]] if second in question_plan else None,
    )
    result = model.streaming_generate()
    print(
        f"[{second}/{len(audios)}]",
        "listen..." if result["is_listen"] else f"speak> {result['text']}",
        flush=True,
    )
    results.append({"chunk_idx": second - 1, **result})
    if result["audio_waveform"] is not None:
        output_audio.append((second - 1, result["audio_waveform"]))

model = model.as_simplex()
print("Muxing the spoken responses into the output video ...")
generate_duplex_video(
    video_path=video_path,
    output_video_path="output/duplex_chat.mp4",
    results_log=results,
    timed_output_audio=output_audio,
)
```

</details>

#### 7.2.2 Speech-In Duplex Chat

Same as above, except the question is spoken and already mixed into the video's
audio track (at ~3 s, asking for an alert when the water boils), so no text is
injected — the model must hear it.

<details>
<summary>Click to show the Speech-In Duplex Chat code.</summary>

```python
import os

os.environ["MAX_NUM_FRAMES"] = "100000"

from minicpmo.utils import get_video_frame_audio_segments, generate_duplex_video

model = model.as_duplex()  # switch to full-duplex streaming
model.prepare()

video_path = "Realtime-Venus-Omni/assets/speech_in.mp4"
print(f"Extracting per-second audio and frames from {video_path} ...")
frames, audios, _ = get_video_frame_audio_segments(
    video_path, stack_frames=1, use_ffmpeg=True, adjust_audio_length=True
)
print(f"Streaming {len(audios)} seconds; the spoken question is already in the audio track.")
results, output_audio = [], []
for second, (frame, audio) in enumerate(zip(frames, audios), start=1):
    model.streaming_prefill(
        audio_waveform=audio,
        frame_list=[frame] if frame is not None else None,
    )
    result = model.streaming_generate()
    print(
        f"[{second}/{len(audios)}]",
        "listen..." if result["is_listen"] else result["text"],
        flush=True,
    )
    results.append({"chunk_idx": second - 1, **result})
    if result["audio_waveform"] is not None:
        output_audio.append((second - 1, result["audio_waveform"]))

model = model.as_simplex()
print("Muxing the spoken responses into the output video ...")
generate_duplex_video(
    video_path=video_path,
    output_video_path="output/duplex_speech_in_chat.mp4",
    results_log=results,
    timed_output_audio=output_audio,
)
```

</details>

#### 7.2.3 Memory Duplex Chat

`model.use_memory(memory_minutes=40)` enables the long-video Memory before
entering duplex mode.

<details>
<summary>Click to show the Memory Duplex Chat code.</summary>

```python
import os

os.environ["MAX_NUM_FRAMES"] = "100000"

from minicpmo.utils import get_video_frame_audio_segments, generate_duplex_video

model.use_memory(memory_minutes=40)  # enable long-video memory
model = model.as_duplex()  # switch to full-duplex streaming
model.prepare()

video_path = "Realtime-Venus-Omni/assets/sample_1_real.mp4"
question = "What is the color of the cooler labeled PRIME near the team bench?"
print(f"Extracting per-second audio and frames from {video_path} ...")
frames, audios, _ = get_video_frame_audio_segments(
    video_path, stack_frames=1, use_ffmpeg=True, adjust_audio_length=True
)
print(f"Streaming {len(audios)} seconds; the text question is injected at second 128.")
results, output_audio = [], []
for second, (frame, audio) in enumerate(zip(frames, audios), start=1):
    model.streaming_prefill(
        audio_waveform=audio,
        frame_list=[frame] if frame is not None else None,
        text_list=[question] if second == 128 else None,
    )
    result = model.streaming_generate()
    print(
        f"[{second}/{len(audios)}]",
        "listen..." if result["is_listen"] else f"speak> {result['text']}",
        flush=True,
    )
    results.append({"chunk_idx": second - 1, **result})
    if result["audio_waveform"] is not None:
        output_audio.append((second - 1, result["audio_waveform"]))

model = model.as_simplex()
print("Muxing the spoken responses into the output video ...")
generate_duplex_video(
    video_path=video_path,
    output_video_path="output/duplex_memory_chat.mp4",
    results_log=results,
    timed_output_audio=output_audio,
)
```

</details>

### 7.3 💬 Half-Duplex Omni Mode

`model.chat(...)` answers one turn at a time over the whole video.
`model.init_tts()` enables speech output.

#### 7.3.1 Offline Chat

Sampled frames, per-second audio, and the question go into a single `chat()`
call. The 128-frame cap (`MAX_NUM_FRAMES`) limits the visual load, while
`max_inp_length=32768` sets the input-token budget. Full audio is still
retained, so very long videos can exceed that budget even with frame sampling.

<details>
<summary>Click to show the Offline Chat code.</summary>

```python
import os

os.environ.setdefault("MAX_NUM_FRAMES", "128")

from minicpmo.utils import get_video_frame_audio_segments

model.init_tts()  # enable speech output

video_path = "Realtime-Venus-Omni/assets/sample_1_real.mp4"
question = "What is the color of the cooler labeled PRIME near the team bench?"
print(f"Extracting audio and frames from {video_path} ...")
frames, audios, _ = get_video_frame_audio_segments(
    video_path, stack_frames=1
)
content = []
for frame, audio in zip(frames, audios):
    if frame is not None:
        content.append(frame)
    content.append(audio)
content.append(question)

print("Running chat inference ...")
response = model.chat(
    msgs=[{"role": "user", "content": content}],
    max_new_tokens=4096,
    max_inp_length=32768,
    do_sample=True,
    temperature=0.7,
    use_image_id=False,
    max_slice_nums=1,
    use_tts_template=True,
    enable_thinking=False,
    omni_mode=True,
    generate_audio=True,
    output_audio_path="output/offline_chat.wav",
)
print(response)
```

</details>

#### 7.3.2 Memory Offline Chat

`model.use_memory()` enables Memory before the chat call; retrieval selects up
to 96 historical frames plus 4 recent frames, each with ±1 s of audio.

<details>
<summary>Click to show the Memory Offline Chat code.</summary>

```python
import os

os.environ["MAX_NUM_FRAMES"] = "100000"

from minicpmo.utils import get_video_frame_audio_segments

model.use_memory()  # enable long-video memory
model.init_tts()  # enable speech output

video_path = "Realtime-Venus-Omni/assets/sample_1_real.mp4"
question = "What is the color of the cooler labeled PRIME near the team bench?"
print(f"Extracting audio and frames from {video_path} ...")
frames, audios, _ = get_video_frame_audio_segments(
    video_path, stack_frames=1, use_ffmpeg=True, adjust_audio_length=True
)
content = []
for frame, audio in zip(frames, audios):
    if frame is not None:
        content.append(frame)
    content.append(audio)
content.append(question)

print("Running chat inference ...")
response = model.chat(
    msgs=[{"role": "user", "content": content}],
    max_new_tokens=4096,
    max_inp_length=32768,
    do_sample=True,
    temperature=0.7,
    use_image_id=False,
    max_slice_nums=1,
    use_tts_template=True,
    enable_thinking=False,
    omni_mode=True,
    generate_audio=True,
    output_audio_path="output/offline_memory_chat.wav",
)
print(response)
```

</details>

## 8. 🎧 Realtime-Venus-Audio Usages

Runnable standalone versions of these examples live in the
[Audio cookbook](https://github.com/inclusionAI/Realtime-Venus/tree/main/frontend/Realtime-Venus-Audio)
on GitHub.

The Audio checkpoint runs audio-only inference in two ways: turn-based
`model.chat` (text response) and the full-duplex streaming API (spoken
response). Inputs are decoded as 16 kHz mono audio from any audio or video
file.

### 8.1 🧱 Model Initialization

Speech output is enabled with `init_tts=True` so the same `model` serves both
examples; use `init_tts=False` for text-only chat to load faster.

<details>
<summary>Click to show Audio model loading code.</summary>

```python
from pathlib import Path

import torch
from transformers import AutoModel, AutoTokenizer, set_seed

Path("output").mkdir(exist_ok=True)
set_seed(42)
print("Loading model ...")
tokenizer = AutoTokenizer.from_pretrained(
    "./Realtime-Venus-Audio", trust_remote_code=True, local_files_only=True,
    fix_mistral_regex=True,
)
model = AutoModel.from_pretrained(
    "./Realtime-Venus-Audio",
    trust_remote_code=True,
    local_files_only=True,
    attn_implementation="sdpa",
    torch_dtype=torch.bfloat16,
    init_vision=False,  # audio-only usage
    init_audio=True,
    init_tts=True,      # speech output; set False for text-only chat
).eval().cuda()
print("Model loaded.")
```

</details>

### 8.2 💭 Offline Chat

One deterministic turn over the full audio input: the audio (plus an optional
text instruction) goes into a single `model.chat()` call.

<details>
<summary>Click to show the Offline Chat code.</summary>

```python
import librosa

print("Loading audio ...")
audio, _ = librosa.load(
    "Realtime-Venus-Audio/assets/case_offline.wav", sr=16000, mono=True
)
msgs = [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": [audio, "What is the speaker asking about?"]},
]

print("Running chat inference ...")
answer = model.chat(
    msgs=msgs,
    tokenizer=tokenizer,
    do_sample=False,
    max_new_tokens=2048,
    enable_thinking=False,
    use_tts_template=True,
    generate_audio=False,
)
print(answer)
```

</details>

### 8.3 🎙️ Duplex Chat

`model.as_duplex(generate_audio=True)` switches to full-duplex streaming:
audio is fed second by second, the model listens continuously and speaks when
it answers. The example appends 10 s of trailing silence so the model can
finish its response after the input ends, and writes the generated speech to
`output/audio_full_duplex.wav`.

<details>
<summary>Click to show the Duplex Chat code.</summary>

```python
import librosa
import numpy as np
import soundfile as sf

duplex = model.as_duplex(generate_audio=True)  # full-duplex with speech output
duplex.prepare(prompt_wav_path="Realtime-Venus-Audio/assets/HT_ref_audio.wav")

audio, _ = librosa.load(
    "Realtime-Venus-Audio/assets/case_duplex.wav", sr=16000, mono=True
)
audio = np.concatenate([audio, np.zeros(10 * 16000, dtype=np.float32)])

chunk_samples = int(duplex.CHUNK_MS * duplex.SAMPLE_RATE / 1000)
total_chunks = max(1, (len(audio) + chunk_samples - 1) // chunk_samples)
timed_audio = []
for chunk_index in range(total_chunks):
    chunk = audio[chunk_index * chunk_samples:(chunk_index + 1) * chunk_samples]
    if len(chunk) < chunk_samples:
        chunk = np.pad(chunk, (0, chunk_samples - len(chunk)))
    duplex.streaming_prefill(audio_waveform=chunk)
    result = duplex.streaming_generate(
        max_new_speak_tokens_per_chunk=20,
        decode_mode="sampling",
        temperature=0.7,
        top_k=20,
        top_p=0.8,
        listen_prob_scale=1.0,
    )
    state = "listen" if result["is_listen"] else f"speak> {result['text']}"
    print(f"[{chunk_index + 1}/{total_chunks}] {state}", flush=True)
    if result["audio_waveform"] is not None and not result["is_listen"]:
        timed_audio.append((chunk_index, result["audio_waveform"]))

# stitch the generated speech on its original timeline (24 kHz)
sample_rate = 24000
total_samples = max(
    t * sample_rate + len(np.asarray(w, dtype=np.float32).squeeze())
    for t, w in timed_audio
)
output = np.zeros(total_samples, dtype=np.float32)
for t, waveform in timed_audio:
    w = np.asarray(waveform, dtype=np.float32).squeeze()
    output[t * sample_rate: t * sample_rate + len(w)] += w
sf.write("output/audio_full_duplex.wav", np.clip(output, -1.0, 1.0), sample_rate)
print("Saved generated speech to output/audio_full_duplex.wav")
```

</details>

## 9. 📝 Citation

If you find Realtime-Venus useful, please cite the technical report:

```bibtex
@article{zhao2026realtime,
  title={{Realtime-Venus}: A full-duplex interaction system with asynchronous delegation},
  author={{Venus Team(Ant Group), Tsinghua University}},
  journal={arXiv preprint arXiv:2609.13814},
  year={2026}
}
```

## 10. 📄 License

This repository includes an [Apache License 2.0](./LICENSE). Please also review
the licenses and acceptable-use terms of the upstream model, third-party
libraries, and any data used with this checkpoint.
