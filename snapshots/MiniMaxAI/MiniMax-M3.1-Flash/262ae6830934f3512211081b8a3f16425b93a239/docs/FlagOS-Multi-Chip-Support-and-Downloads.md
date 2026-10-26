### Multi-Chip Deployment with FlagOS

MiniMax-M3.1-Flash supports multi-chip deployment through FlagOS. The FlagOS community provides **W8A8 quantized versions** for platforms from **nine chip vendors**. The corresponding model repositories provide access to weights, deployment code, and container image instructions.

#### About FlagOS

The FlagOS Open Source Community was jointly established by the Beijing Academy of Artificial Intelligence (BAAI), research institutions, chip manufacturers, system vendors, and algorithm and software organizations. It develops a unified, open-source system software stack for diverse AI chips.

FlagOS includes the FlagGems operator library, FlagTree AI compiler, FlagScale parallel training and inference framework, and FlagCX communication library. These projects connect the model, system, and chip layers, helping developers reuse model code and software components while reducing migration and maintenance costs. For inference deployment, vLLM-plugin-FL and SGLang-plugin-FL extend hardware support while preserving the original framework interfaces and usage patterns.

Website: [flagos.io](https://flagos.io/) | Community: [GitHub](https://github.com/flagos-ai) / [GitCode](https://gitcode.com/flagos-ai)

#### Multi-Chip Support and Downloads

FlagRelease is the FlagOS team's platform for model migration, adaptation, and release across AI chips. MiniMax-M3.1-Flash is adapted for platforms from **nine vendors: T-Head, NVIDIA, MetaX, Hygon, Huawei Ascend, Moore Threads, Iluvatar, Kunlunxin, and Tsingmicro**, with W8A8 versions provided across these platforms.

FlagOS converts and requantizes the model's original QAT NVFP4 weights into W8A8 deployment versions, providing a common quantization format across supported chips. The table below lists the model repositories. NVIDIA, Huawei Ascend, Kunlunxin, and T-Head (Zhenwu) use Express versions, named `MiniMax-M3.1-Flash-W8A8-<platform>-FlagOS-Express`; the other platforms use `MiniMax-M3.1-Flash-W8A8-<platform>-FlagOS`.

| Chip Vendor / Platform | ModelScope | Hugging Face |
| --- | --- | --- |
| T-Head (Zhenwu) | [Model repository](https://modelscope.cn/models/FlagRelease/MiniMax-M3.1-Flash-W8A8-zhenwu-FlagOS-Express) | [Model repository](https://huggingface.co/FlagRelease/MiniMax-M3.1-Flash-W8A8-zhenwu-FlagOS-Express) |
| NVIDIA | [Model repository](https://modelscope.cn/models/FlagRelease/MiniMax-M3.1-Flash-W8A8-nvidia-FlagOS-Express) | [Model repository](https://huggingface.co/FlagRelease/MiniMax-M3.1-Flash-W8A8-nvidia-FlagOS-Express) |
| MetaX | [Model repository](https://modelscope.cn/models/FlagRelease/MiniMax-M3.1-Flash-W8A8-metax-FlagOS) | [Model repository](https://huggingface.co/FlagRelease/MiniMax-M3.1-Flash-W8A8-metax-FlagOS) |
| Hygon | [Model repository](https://modelscope.cn/models/FlagRelease/MiniMax-M3.1-Flash-W8A8-hygon-FlagOS) | [Model repository](https://huggingface.co/FlagRelease/MiniMax-M3.1-Flash-W8A8-hygon-FlagOS) |
| Huawei Ascend | [Model repository](https://modelscope.cn/models/FlagRelease/MiniMax-M3.1-Flash-W8A8-ascend-FlagOS-Express) | [Model repository](https://huggingface.co/FlagRelease/MiniMax-M3.1-Flash-W8A8-ascend-FlagOS-Express) |
| Moore Threads | [Model repository](https://modelscope.cn/models/FlagRelease/MiniMax-M3.1-Flash-W8A8-mthreads-FlagOS) | [Model repository](https://huggingface.co/FlagRelease/MiniMax-M3.1-Flash-W8A8-mthreads-FlagOS) |
| Iluvatar | [Model repository](https://modelscope.cn/models/FlagRelease/MiniMax-M3.1-Flash-W8A8-iluvatar-FlagOS) | [Model repository](https://huggingface.co/FlagRelease/MiniMax-M3.1-Flash-W8A8-iluvatar-FlagOS) |
| Kunlunxin | [Model repository](https://modelscope.cn/models/FlagRelease/MiniMax-M3.1-Flash-W8A8-kunlunxin-FlagOS-Express) | [Model repository](https://huggingface.co/FlagRelease/MiniMax-M3.1-Flash-W8A8-kunlunxin-FlagOS-Express) |
| Tsingmicro | [Model repository](https://modelscope.cn/models/FlagRelease/MiniMax-M3.1-Flash-W8A8-tsingmicro-FlagOS) | [Model repository](https://huggingface.co/FlagRelease/MiniMax-M3.1-Flash-W8A8-tsingmicro-FlagOS) |

#### Installation and Usage

##### Option 1: Use a FlagRelease Image (Recommended)

FlagRelease provides deployment environments for the supported platforms:

1. Select your target chip platform from the table above and open the corresponding model repository.
2. Follow the model card to prepare the host drivers and runtime, download the model weights, pull and start the container image, and configure device mappings and model directory mounts.
3. Start the inference service or run the examples inside the container using the commands in the model card. Refer to that card for accelerator count, memory requirements, parallelism, model paths, framework versions, and startup parameters.

##### Option 2: Install from Source

MiniMax-M3.1-Flash supports deployment through vLLM-plugin-FL and SGLang-plugin-FL. Refer to the corresponding model card for framework versions, plugin branches, and model-specific dependencies.

Official developer guides:

- **vLLM-plugin-FL**: [GitHub](https://github.com/flagos-ai/vllm-plugin-FL/blob/main/README.md) / [GitCode](https://gitcode.com/flagos-ai/vllm-plugin-FL/blob/main/README.md)
- **SGLang-plugin-FL**: [GitHub](https://github.com/flagos-ai/sglang-plugin-FL/blob/main/README.md) / [GitCode](https://gitcode.com/flagos-ai/sglang-plugin-FL/blob/main/README.md)

The following example installs the base components used for the **T-Head platform** in this adaptation: **vLLM v0.24.0, vllm-plugin-FL v0.3.0, and FlagGems v5.4.0**. First prepare the chip drivers, runtime, compatible PyTorch build, and build dependencies as described in the model card. Apply any model-specific patches and additional configuration required by that card.

```bash
# 1. Install vLLM v0.24.0 (T-Head example)
git clone --branch v0.24.0 https://github.com/vllm-project/vllm.git
cd vllm
VLLM_TARGET_DEVICE=empty python -m pip install -v --no-build-isolation --no-deps .
cd ..

# 2. Install vllm-plugin-FL v0.3.0
git clone --branch v0.3.0 https://github.com/flagos-ai/vllm-plugin-FL.git
cd vllm-plugin-FL
python -m pip install --no-build-isolation -e .
cd ..

# 3. Install FlagGems v5.4.0
python -m pip install scikit-build-core==0.11 pybind11 ninja cmake
git clone --branch v5.4.0 https://github.com/flagos-ai/FlagGems.git
cd FlagGems
python -m pip install --no-build-isolation -e .
cd ..
```

Install the [FlagTree unified compiler](https://github.com/flagos-ai/FlagTree) and [FlagCX communication library](https://github.com/flagos-ai/FlagCX) as required by your platform, and complete the environment and communication configuration described in the model card. For CUDA/HIP environments that use PyTorch's CUDA dispatch key, refer to the plugin installation guide for native extension build instructions.

##### Run Inference

The following text generation example uses **MiniMax-M3.1-Flash W8A8 Express** on T-Head with `tensor_parallel_size=8`. Run it in a configured vLLM-plugin-FL environment or the corresponding container, on hardware that meets the model card's requirements. Accelerator counts and parallelism settings for other platforms are specified in their model cards.

Save the code as `inference.py`:

```python
from vllm import LLM, SamplingParams


if __name__ == "__main__":
    prompts = ["Please introduce MiniMax-M3.1-Flash."]
    sampling_params = SamplingParams(max_tokens=512, temperature=0.0)

    llm = LLM(
        model="FlagRelease/MiniMax-M3.1-Flash-W8A8-zhenwu-FlagOS-Express",
        tensor_parallel_size=8,
        trust_remote_code=True,
    )

    outputs = llm.generate(prompts, sampling_params)
    for output in outputs:
        print(f"Prompt: {output.prompt!r}")
        print(f"Generated: {output.outputs[0].text!r}")
```

```bash
VLLM_PLUGINS=fl python inference.py
```

To use local weights, replace `model` with the downloaded model directory. When changing chip platforms, select the corresponding repository from the table and adjust `tensor_parallel_size`, `max_model_len`, `max_num_batched_tokens`, and `max_num_seqs` according to its model card. Refer to the platform's model card for online serving, chat templates, multimodal inputs, DSpark speculative decoding, and `reasoning_effort` configuration.
