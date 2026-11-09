<h1 align="center">书生·元征</h1>
<p align="center"><strong>Sage Sci Perception · 让大模型感知科学数据。</strong></p>
<p align="center">通过投影模块，将晶体、谱图、生物序列与生理信号接入语言模型。</p>
<p align="center"><strong>持续扩展科学模态、任务与语言模型支持。</strong></p>

<p align="center">
  <a href="#已发布权重">下载权重</a> ·
  <a href="#示例展示">示例展示</a> ·
  <a href="#推理使用">推理使用</a> ·
  <a href="#整体框架">整体框架</a> ·
  <a href="https://github.com/InternLM/Sage-SciPerception">GitHub</a> ·
  <a href="https://huggingface.co/internlm/Sage-SciPerception">English</a>
</p>

<p align="center">
  <img src="assets/branding/sage-sciprojector-hero-zh.png" alt="书生·元征：书生探索科学表征。" width="640">
</p>

书生·元征（Sage Sci Perception）将科学表征映射到语言模型的输入空间，使其能够生成自然语言分析和结构化科学答案。你可以用它探索科学工作流与语言模型的连接，包括材料性质预测、生物序列标注、谱图结构识别与信号分类。

projector 按模态、任务与语言模型版本组织。你可以从下表下载已有权重，也可以参考[推理使用说明](#推理使用)，将科学输入接入推理服务。各权重的 `config.json` 记录了对应语言模型和科学输入表示。

## 示例展示

以下为科学输入、参考标注与任务界面的录制展示。各 checkpoint 的生成答案评测见[已发布权重](#已发布权重)。

<table width="100%">
  <tr>
    <td width="50%" align="center">
      <img src="assets/spectra-zh.gif" alt="三谱联合输入、流式解析与预测的分子结构。" width="100%"><br>
      <b>三谱联合 → 分子结构</b><br>
      <sub>红外、拉曼与紫外—可见光谱，配合流式解析和历史预测回放。</sub>
    </td>
    <td width="50%" align="center">
      <img src="assets/protein-zh.gif" alt="蛋白质序列位置与界面参考标注。" width="100%"><br>
      <b>蛋白质界面位点</b><br>
      <sub>序列位置与逐残基界面参考标注。</sub>
    </td>
  </tr>
  <tr>
    <td width="50%" align="center">
      <img src="assets/crystal-zh.gif" alt="晶体几何结构及其形成能参考值。" width="100%"><br>
      <b>晶体结构与形成能</b><br>
      <sub>原子几何结构与材料性质参考值。</sub>
    </td>
    <td width="50%" align="center">
      <img src="assets/rna-iterations-zh.gif" alt="RNA 接入方案实验与评测反馈回放。" width="100%"><br>
      <b>RNA 接入方案迭代</b><br>
      <sub>根据实验反馈修订接入方案。</sub>
    </td>
  </tr>
</table>

## 已发布权重

点击任务名称查看配套文件，或直接下载权重和配置。后续将持续增加科学模态、任务与适配的语言模型版本。

| 榜单 / 任务 | 指标 ↑ | 得分 | 下载 |
|---|---|---:|---|
| [JARVIS-DFT](https://huggingface.co/internlm/Sage-SciPerception/tree/main/projectors/glm-5.3-flash/cif/jarvis)<br>形成能预测 | MAD/MAE | **15.03** | [权重](https://huggingface.co/internlm/Sage-SciPerception/resolve/main/projectors/glm-5.3-flash/cif/jarvis/projector.safetensors?download=true) · [config](https://huggingface.co/internlm/Sage-SciPerception/blob/main/projectors/glm-5.3-flash/cif/jarvis/config.json) |
| [MPBind](https://huggingface.co/internlm/Sage-SciPerception/tree/main/projectors/glm-5.3-flash/protein-seq/mpbind)<br>PPI 界面位点 | 逐蛋白 F1（%） | **61.12** | [权重](https://huggingface.co/internlm/Sage-SciPerception/resolve/main/projectors/glm-5.3-flash/protein-seq/mpbind/projector.safetensors?download=true) · [config](https://huggingface.co/internlm/Sage-SciPerception/blob/main/projectors/glm-5.3-flash/protein-seq/mpbind/config.json) |
| [QM9S](https://huggingface.co/internlm/Sage-SciPerception/tree/main/projectors/glm-5.3-flash/spectra/qm9s)<br>分子结构识别 | Acc@1（%） | **49.75** | [权重](https://huggingface.co/internlm/Sage-SciPerception/resolve/main/projectors/glm-5.3-flash/spectra/qm9s/projector.safetensors?download=true) · [config](https://huggingface.co/internlm/Sage-SciPerception/blob/main/projectors/glm-5.3-flash/spectra/qm9s/config.json) |
| [SciTS PHU01](https://huggingface.co/internlm/Sage-SciPerception/tree/main/projectors/glm-5.3-flash/ecg/phu01)<br>心电分类 | 宏平均 F1（%） | **71.53** | [权重](https://huggingface.co/internlm/Sage-SciPerception/resolve/main/projectors/glm-5.3-flash/ecg/phu01/projector.safetensors?download=true) · [config](https://huggingface.co/internlm/Sage-SciPerception/blob/main/projectors/glm-5.3-flash/ecg/phu01/config.json) |
| [GUE splice](https://huggingface.co/internlm/Sage-SciPerception/tree/main/projectors/glm-5.3-flash/dna/splice)<br>剪接位点分类 | MCC（%） | **87.87** | [权重](https://huggingface.co/internlm/Sage-SciPerception/resolve/main/projectors/glm-5.3-flash/dna/splice/projector.safetensors?download=true) · [config](https://huggingface.co/internlm/Sage-SciPerception/blob/main/projectors/glm-5.3-flash/dna/splice/config.json) |
| [SciTS NEU06](https://huggingface.co/internlm/Sage-SciPerception/tree/main/projectors/glm-5.3-flash/eeg/neu06)<br>睡眠分期 | 宏平均 F1（%） | **72.01** | [权重](https://huggingface.co/internlm/Sage-SciPerception/resolve/main/projectors/glm-5.3-flash/eeg/neu06/projector.safetensors?download=true) · [config](https://huggingface.co/internlm/Sage-SciPerception/blob/main/projectors/glm-5.3-flash/eeg/neu06/config.json) |
| [BEACON ncRNA](https://huggingface.co/internlm/Sage-SciPerception/tree/main/projectors/glm-5.3-flash/rna/ncrna)<br>RNA 家族分类 | 准确率（%） | **97.35** | [权重](https://huggingface.co/internlm/Sage-SciPerception/resolve/main/projectors/glm-5.3-flash/rna/ncrna/projector.safetensors?download=true) · [config](https://huggingface.co/internlm/Sage-SciPerception/blob/main/projectors/glm-5.3-flash/rna/ncrna/config.json) |
| [SimXRD OL](https://huggingface.co/internlm/Sage-SciPerception/tree/main/projectors/glm-5.3-flash/xrd/simxrd)<br>晶系分类 | 准确率（%） | **63.60** | [权重](https://huggingface.co/internlm/Sage-SciPerception/resolve/main/projectors/glm-5.3-flash/xrd/simxrd/projector.safetensors?download=true) · [config](https://huggingface.co/internlm/Sage-SciPerception/blob/main/projectors/glm-5.3-flash/xrd/simxrd/config.json) |
| [ATOM3D PSR](https://huggingface.co/internlm/Sage-SciPerception/tree/main/projectors/glm-5.3-flash/protein-struct/psr)<br>蛋白质结构排序 | Spearman（%） | **35.36** | [权重](https://huggingface.co/internlm/Sage-SciPerception/resolve/main/projectors/glm-5.3-flash/protein-struct/psr/projector.safetensors?download=true) · [config](https://huggingface.co/internlm/Sage-SciPerception/blob/main/projectors/glm-5.3-flash/protein-struct/psr/config.json) |

得分来自各任务选定 checkpoint 的生成答案，不同任务的指标不能直接比较。**MAD/MAE 是越高越好的比值**，不是需要最小化的误差。MPBind 使用 assembly-1 重建评测集及逐蛋白平均 F1；PSR 使用平均 Spearman。各模块分别针对对应任务训练。

## 推理使用

我们的服务路线是：将 projector 输出的科学向量插入语言模型的**完整聊天提示词嵌入**，再通过 `prompt_embeds` 发给 vLLM 的 `/v1/completions`。文本位置使用对应语言模型的输入嵌入表，科学载荷位置使用 projector 的输出。科学特征提取与投影在客户端完成，语言模型服务负责生成答案。

### 1. 准备权重与科学输入

完整的[晶体客户端示例](https://huggingface.co/internlm/Sage-SciPerception/blob/main/examples/vllm_cif.py)包含特征投影、原生 chat template 渲染、文本嵌入读取、科学载荷替换及 HTTP 请求。先下载示例和加载模块，再通过仓库索引选择对应 projector：

```bash
python -m pip install torch safetensors huggingface_hub
python -m pip install --upgrade transformers
hf download internlm/Sage-SciPerception \
  examples/vllm_cif.py load_projector.py modeling_projector.py \
  --local-dir ./sage-sciperception
cd sage-sciperception
python load_projector.py glm-5.3-flash/cif/jarvis --local-dir .
```

下载工具读取根目录的 `config.json` 定位所选 projector，并从同一仓库版本下载其配置和权重。更换任务时，可使用[组件索引](https://huggingface.co/internlm/Sage-SciPerception/blob/main/projectors/glm-5.3-flash/README.md)中对应的 projector ID。

准备 `cif_features.pt`：这是形状为 `[num_atoms, 64]` 的 PyTorch 张量，内容为 `cif/jarvis/config.json` 指定的真实 CHGNet 0.3.0 原子状态，保持原子顺序。本地语言模型目录应与权重 `config.json` 记录的精确版本一致。客户端从该目录读取 tokenizer、配置和分片 safetensors 中的输入嵌入表，无需加载完整语言模型。

### 2. 启动 vLLM 服务

在推理服务环境中，启动支持 `--enable-prompt-embeds` 的 vLLM 服务。张量并行度根据所选模型与设备选择；以下命令以八路并行为例。

```bash
vllm serve /path/to/matching-base-model \
  --served-model-name sage-sciperception \
  --enable-prompt-embeds \
  --tensor-parallel-size 8 \
  --generation-config vllm \
  --max-model-len 8192 \
  --host 127.0.0.1 --port 8000
```

### 3. 生成答案

服务就绪后，在步骤 1 准备的 `sage-sciperception` 目录中运行客户端：

```bash
python examples/vllm_cif.py \
  --component ./projectors/glm-5.3-flash/cif/jarvis \
  --base-model /path/to/matching-base-model \
  --features /path/to/cif_features.pt \
  --api-base http://127.0.0.1:8000/v1 \
  --model sage-sciperception
```

下面是客户端中的传输代码摘录。此时 `prompt_embeds` 已包含原生 system、user 以及 assistant 生成前缀，并在科学载荷位置插入了 projector 向量：

```python
buffer = io.BytesIO()
torch.save(prompt_embeds.cpu().contiguous(), buffer)
body = {
    "model": "sage-sciperception",
    "prompt_embeds": base64.b64encode(buffer.getvalue()).decode("ascii"),
    "max_tokens": 4096,
    "temperature": 0,
}
request = urllib.request.Request(
    "http://127.0.0.1:8000/v1/completions",
    data=json.dumps(body).encode("utf-8"),
    headers={"Content-Type": "application/json"},
)
```

Completions 接口直接消费组装后的完整嵌入。构造请求时沿用 checkpoint 的 system prompt、模板参数及科学输入表示。[组件索引](https://huggingface.co/internlm/Sage-SciPerception/blob/main/projectors/glm-5.3-flash/README.md#scientific-inputs)列出了当前可用输入；晶体示例使用该任务自己的输入格式。服务接口见 [vLLM prompt embeddings 文档](https://docs.vllm.ai/en/v0.32.0/features/prompt_embeds/)。

科学编码器权重和预处理运行脚本是独立依赖。其中 DNA、MPBind 和 ncRNA 所需的任务适配科学模型尚未在此发布。上述推理示例从已准备好的真实科学特征开始。

### 可选：在 CPU 上检查 projector 加载

在同一下载目录中，可以用 CPU 检查 projector 的参数量与输出维度，无需启动语言模型服务：

```python
from load_projector import load_projector

projector, config = load_projector(
    "projectors/glm-5.3-flash/cif/jarvis", device="cpu"
)
print(config["task"])
print(sum(p.numel() for p in projector.parameters()))
print(config["output_dim"])
```

预期输出：

```text
cif/jarvis
4314304
4096
```

更换任务时，将[组件索引](https://huggingface.co/internlm/Sage-SciPerception/blob/main/projectors/glm-5.3-flash/README.md)中的对应 ID 传给同一下载工具。各任务前向所需的输入不同，准备预测时请查看其科学输入说明。

## 整体框架

<p align="center">
  <img src="assets/framework-zh.gif" alt="科学输入经科学表征与可训练投影模块，接入语言模型。" width="100%">
</p>

任务专用 projector 将科学特征映射到语言模型的嵌入维度。在语言映射训练阶段，科学模型和语言模型保持冻结，只训练 projector。部分任务会先对科学模型进行任务适配，或将编码器状态与科学直接读出结合。

## 反馈与后续

如果你正在接入自己的科学流程、缺少配套文件，或希望看到具体示例，可以[提交 GitHub issue](https://github.com/InternLM/Sage-SciPerception/issues/new)，附上任务、科学输入格式和想运行的步骤。发布相关问题也可以在 [HF 社区页](https://huggingface.co/internlm/Sage-SciPerception/discussions)讨论；关注 [InternLM](https://huggingface.co/internlm) 可接收后续更新。

本次发布尚未指定许可证元数据。

## 引用

如果你在研究或项目中使用了书生·元征（Sage-SciPerception），请引用：

```bibtex
@misc{sage_sciperception,
  author       = {{InternLM}},
  title        = {{Sage-SciPerception}},
  note         = {GitHub repository},
  year         = {2026},
  url          = {https://github.com/InternLM/Sage-SciPerception}
}
```
