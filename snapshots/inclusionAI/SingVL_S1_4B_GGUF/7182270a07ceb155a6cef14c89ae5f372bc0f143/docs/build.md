# Build the llama.cpp CPU backend

The reference backend targets Linux x86_64 and uses the upstream llama.cpp library at commit `f3b407ca1bfeeecebf9e9ef19fcd6eed565bd70a`. Run the following commands from the `SingVL-4B-GGUF` repository root.

## Dependencies

Use an existing Python 3.12 environment with compatible PyTorch and torchvision builds. The recorded CPU environment used PyTorch 2.9.0 and torchvision 0.24.0. Install the Python dependencies into the environment selected for this model.

```bash
python -m pip install -r examples/llama_cpp/requirements.txt
python validation/validate_processing.py
```

The compiler dependencies are Git, CMake, a C++17 compiler and Python development headers. On Ubuntu or Debian they can be installed with the following command.

```bash
sudo apt-get install -y build-essential cmake git python3-dev
```

For a CPU environment that still needs PyTorch, the recorded package versions can be installed with the following command.

```bash
python -m pip install torch==2.9.0 torchvision==0.24.0 \
  --index-url https://download.pytorch.org/whl/cpu
```

## Build

```bash
git clone https://github.com/ggml-org/llama.cpp.git third_party/llama.cpp
git -C third_party/llama.cpp checkout f3b407ca1bfeeecebf9e9ef19fcd6eed565bd70a

cmake -S third_party/llama.cpp -B build/llama \
  -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=ON \
  -DGGML_CUDA=OFF -DGGML_NATIVE=OFF \
  -DLLAMA_BUILD_TESTS=OFF -DLLAMA_BUILD_EXAMPLES=OFF \
  -DLLAMA_BUILD_APP=OFF -DLLAMA_BUILD_UI=OFF \
  -DLLAMA_USE_PREBUILT_UI=OFF -DLLAMA_OPENSSL=OFF
cmake --build build/llama --target llama mtmd --parallel 8

python examples/llama_cpp/build.py \
  --source third_party/llama.cpp --build build/llama
python validation/validate_backend.py --variant q8_0
```

Adjust `--parallel` to the available build memory. The adapter is compiled against `libllama`, `libmtmd`, `libggml` and `libggml-base`. Its RPATH refers to the local build directory, so rebuild the adapter after moving the compiled library directory. `JEV_RUNNER_LIBRARY` can select a separately compiled adapter library.

## Runtime settings

| Variable | Purpose | Default |
|---|---|---|
| `JEV_GGUF_MODEL` | Decoder GGUF path | Required |
| `JEV_GGUF_MMPROJ` | Vision projector GGUF path | Required |
| `JEV_CPU_CONTEXT` | Full input capacity, including image tokens | 4096 |
| `JEV_CPU_THREADS` | Inference threads | 8 |
| `JEV_RUNNER_LIBRARY` | External adapter library | `examples/llama_cpp/libjev_runner.so` |

The reference context is 4096 tokens. Larger contexts require additional memory and their validation remains pending. The adapter uses `n_gpu_layers=0` and `use_gpu=false`. GPU or PPU backends require their own build settings and validation.

## Attention and readout

The GGUF metadata declares `qwen35.attention.causal=false`. Full-attention layers process the complete input bidirectionally and GDN layers retain causal recurrence. The adapter verifies non-causal attention during initialization, clears KV and recurrent state for each question, and submits the entire text and image input in one `llama_process` call. Batch and microbatch capacities cover that complete input.

The last valid input position supplies the logits for the configured candidate token IDs. `processing/protocol.py` normalizes those candidate logits and maps the answers back to the supplied keys. Image ordering, image-token expansion and M-RoPE coordinates follow the shared processor configuration.

## Validation

`validate_processing.py` checks token IDs, image grids and probability postprocessing against the recorded BF16, Q8_0 and Q4_K_M references. `validate_backend.py` loads the selected GGUF variant and compares fresh answers, probabilities, token IDs, image grids and position coordinates with its reference. The default probability tolerance is `1e-5`.

```bash
python validation/validate_processing.py
python validation/validate_backend.py --variant bf16
python validation/validate_backend.py --variant q8_0
python validation/validate_backend.py --variant q4_k_m
```

The stored validation covers 9 examples and 11 questions. Quantized variants retain the recorded BF16 top-1 answers on those examples, while probabilities and continuous scores vary. Full GGUF Decision Index runs remain pending.
