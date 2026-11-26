---
base_model:
- tencent/Hy-MT3-30B-A3B
tags:
- translation
license: apache-2.0
---

<p align="left">
   <a href="https://huggingface.co/tencent/Hy-MT3-30B-A3B-GGUF/blob/main/README.md">English</a>&nbsp;｜&nbsp;中文
</p>
<br>

<p align="center">
 <img src="https://huggingface.co/tencent/Hy-MT3-30B-A3B-GGUF/resolve/main/imgs/logo-zh.png" width="400"/> <br> 
</p>

<div align="center" style="line-height: 1;">


[![HuggingFace](https://img.shields.io/badge/%F0%9F%A4%97%20Hugging%20Face-Tencent%20Hy-ffc107?color=ffc107&logoColor=white)](https://huggingface.co/collections/tencent/hy-mt3)
&nbsp;&nbsp;
[![ModelScope](https://img.shields.io/badge/ModelScope-Tencent%20Hy-624aff)](https://modelscope.cn/collections/Tencent-Hunyuan/Hy-MT3)

</div>

<p align="center">
    🖥️&nbsp;<a href="https://aistudio.tencent.com/chat/HunyuanDefault?from=modelSquare&modelId=hunyuan-translation-pro-chat"><b>官方网站</b></a>&nbsp;&nbsp;|&nbsp;&nbsp;
    💬&nbsp;<a href="https://github.com/Tencent-Hunyuan/Hy-MT3"><b>GitHub</b></a>&nbsp;&nbsp;|&nbsp;&nbsp;
    📚&nbsp;<a href="https://arxiv.org/pdf/2611.27673"><b>Hy-MT3报告</b></a></p>


## 模型介绍


Hy-MT3 是混元多语言翻译模型家族的第三代，涵盖 1.8B、7B 和 30B-A3B（MoE）三种体量，支持语种从 Hy-MT2 的 38 种扩充到 **102 种**。相比 Hy-MT2，Hy-MT3 的翻译**更准确、更完整、更遵循用户约束**：在真实场景数据上，误译样本比例降低 **43%**，漏译 / 增译比例降低 **74%**，指令遵循类错误减少 **40%**。

Hy-MT3-30B-A3B 仅激活 3B 参数，**在所有非思考（快思考）模式的模型中取得最佳综合效果**，超过 Qwen3.8-Max、Kimi-K3.1-Pro、DeepSeek-V4.1-Flash 等旗舰模型，接近 GPT-6.1-Sol、Gemini-4-Argon 等同期最强的闭源思考模型，并超过了推理计算量是自身 **30 倍以上**的模型。轻量级的 Hy-MT3-1.8B 在通用翻译上也超过了讯飞翻译、微软翻译、Qwen-MT-Flash 等商业翻译 API。

在通用翻译之外，Hy-MT3 针对两个产业场景做了优化：
* **游戏本地化**：携手王者荣耀团队，借助优质的游戏垂类数据与专业评测体系，Hy-MT3-30B-A3B 在脱靶率、占位符错误、富文本错误和术语错误等核心指标上全面持平或优于 Gemini 3.1 Pro 等强闭源模型，并可通过开源的游戏翻译工具链 [TiMiHOKGameTranslator](https://github.com/Tencent/TiMiHOKGameTranslator) 无缝接入游戏研发流程。
* **图片翻译**：针对 OCR 级联的图片翻译场景，Hy-MT3 提升了上下文理解与纠错能力，更好地适应 OCR 识别错误，在 VISTA-Bench 上效果达到同尺寸模型最强。

同时，本次我们也开源了基于评分细则（rubric）的翻译自动评估方案 [TransRubric](https://github.com/Tencent-Hunyuan/Hy-MT3/blob/main/TransRubric/README_zh.md)，它在 WMT26 翻译评估赛道测试集上的效果超过其他评估方案，相对人工评估的稳定性更高，准确率也高于大多数专业标注员。

也欢迎大家使用我们发布的腾讯Hy翻译浏览器插件，支持划词翻译、整页翻译和侧边栏文本翻译，下载链接：[Chrome](https://chromewebstore.google.com/detail/tencent-hy-translate-a-pe/plkeongecagdacbbldjkoaijdogfkhof?hl=zh-CN)和[Edge](https://microsoftedge.microsoft.com/addons/detail/npohaablejgdcokflkffadojdconaacm)。

## 新闻

* 2026.11.24  我们在HuggingFace和ModelScope上开源了 **Hy-MT3-1.8B**/**Hy-MT3-7B**/**Hy-MT3-30B-A3B**，并在GitHub上开源了 **TransRubric**
* 2026.5.21  我们在HuggingFace和ModelScope上开源了 **Hy-MT2-1.8B**/**Hy-MT2-7B**/**Hy-MT2-30B-A3B**/**IFMTBench**
* 2025.12.30 我们在HuggingFace和ModelScope开源了 **HY-MT1.5-1.8B**和**HY-MT1.5-7B**
* 2025.9.1 我们在HuggingFace和ModelScope开源了 **Hunyuan-MT-7B**和**Hunyuan-MT-Chimera-7B**。


## 效果
<div align='center'>
<img src="https://huggingface.co/tencent/Hy-MT3-30B-A3B-GGUF/resolve/main/imgs/main_result_zh.png" width = "100%" />
</div>

通用翻译为 FLORES-200、FLORES-200 低资源、WMT26 和普通话⇔少数民族语言四项的平均；WildMTBench-202611 基于最新的真实场景数据构建；IFMTBench 衡量翻译指令遵循能力。通用翻译和 WildMTBench-202611 由 TransRubric 打分。(T) 表示思考模式，其余模型（包括 Hy-MT3）均为非思考模式。

<div align='center'>
<img src="https://huggingface.co/tencent/Hy-MT3-30B-A3B-GGUF/resolve/main/imgs/efficiency_zh.png" width = "90%" />
</div>

上图展示了通用翻译质量与推理计算量的关系。横轴为每个测试样本的预估推理计算量（TFLOPs，对数坐标），约等于 2 × 激活参数量 × 生成 token 数（含思考 token）；纵轴为通用翻译的 TransRubric 平均分。箭头连接同一模型的非思考与思考模式；水平虚线为未公开参数量的闭源模型。Hy-MT3 系列位于左上方的前沿：Hy-MT3-30B-A3B 每个样本的计算量不到 1 TFLOP，却超过了计算量是其 30 倍以上的模型，例如非思考模式下的 Qwen3.8-Max 和 Kimi-K3.1-Pro。

更多的实验效果和分析可以参考我们的[报告](https://arxiv.org/pdf/2611.27673)。

&nbsp;

## 模型链接
| 模型名  | 简介 | 下载链接 |
| ----------- | ----------- |-----------
| Hy-MT3-1.8B  | 混元1.8B翻译模型 |🤗 [Model](https://huggingface.co/tencent/Hy-MT3-1.8B)|
| Hy-MT3-1.8B-FP8 | 混元1.8B翻译模型，fp8量化    | 🤗 [Model](https://huggingface.co/tencent/Hy-MT3-1.8B-FP8)|
| Hy-MT3-1.8B-GGUF | 混元1.8B翻译模型， llama.cpp    | 🤗 [Model](https://huggingface.co/tencent/Hy-MT3-1.8B-GGUF)|
| Hy-MT3-7B | 混元7B翻译模型    | 🤗 [Model](https://huggingface.co/tencent/Hy-MT3-7B)|
| Hy-MT3-7B-FP8 | 混元7B翻译模型，fp8量化     | 🤗 [Model](https://huggingface.co/tencent/Hy-MT3-7B-FP8)|
| Hy-MT3-7B-GGUF | 混元7B翻译模型， llama.cpp    | 🤗 [Model](https://huggingface.co/tencent/Hy-MT3-7B-GGUF)|
| Hy-MT3-30B-A3B | 混元30B-A3B翻译模型    | 🤗 [Model](https://huggingface.co/tencent/Hy-MT3-30B-A3B)|
| Hy-MT3-30B-A3B-FP8 | 混元30B-A3B翻译模型，fp8量化     | 🤗 [Model](https://huggingface.co/tencent/Hy-MT3-30B-A3B-FP8)|
| Hy-MT3-30B-A3B-GGUF | 混元30B-A3B翻译模型， llama.cpp    | 🤗 [Model](https://huggingface.co/tencent/Hy-MT3-30B-A3B-GGUF)|



## Hy-MT3 翻译任务指令示例（中英文对照）

*注意：下面的source_lang和target_lang都使用语言的全称，中文使用中文全称，英文使用英文全称。*

| Type | Chinese prompt | English prompt |
|---|---|---|
| **Default Translation** | 将以下文本翻译为 `{target_lang}`，注意**只需要输出翻译后的结果，不要额外解释**：<br><br>`{source_text}` | Translate the following text into `{target_lang}`. Note that you should **only output the translated result without any additional explanation**:<br><br>`{source_text}` |
| **Terminology** | *参考下面的翻译：*<br>`{text}` 翻译成 `{text}`<br>`{text}` 翻译成 `{text}`<br>`{text}` 翻译成 `{text}`<br>将以下文本翻译为 `{target_lang}`，注意**只需要输出翻译后的结果，不要额外解释**：<br><br>`{source_text}` | *Reference the following translations:*<br>`{text}` translates to `{text}`<br>`{text}` translates to `{text}`<br>`{text}` translates to `{text}`<br><br>Translate the following text into `{target_lang}`. Note that you must **ONLY output the translated result without any additional explanation**:<br><br>`{source_text}` |
| **Style** | 请将以下文本翻译为 `{target_lang}`。<br>注意翻译的风格要严格符合【**`{target_style}`**】<br><br>`{source_text}` | Please translate the following text into `{target_lang}`. Note that the translation style must strictly conform to [**`{target_style}`**]:<br><br>`{source_text}` |
| **Personalization** | *【待翻译文本】*<br>`{source_text}`<br><br>*【翻译任务】*<br>1、**`{user_preferences}`**<br>2、**`{user_preferences}`**<br>3、……<br>4、将【待翻译文本】翻译为 `{target_lang}`。 | *[Source Text]*<br>`{source_text}`<br><br>*[Translation Tasks]*<br>1. **`{user_preferences}`**<br>2. **`{user_preferences}`**<br>3. ...<br>4. Translate the [Source Text] into `{target_lang}`. |
| **Delimiters** | 请将以下文本准确翻译为 `{target_lang}`。<br>你必须在译文中**保留等量的分隔符，绝对不可遗漏、转义或翻译该符号，并注意分隔符的位置**。<br><br>`{source_text}` | Please accurately translate the following text into `{target_lang}`.<br>You must **retain the exact same number of delimiters in the translation. Strictly do not omit, escape, or translate these symbols, and pay close attention to their placement**.<br><br>`{source_text}` |
| **Structured Data 1** | *# 任务目标*<br>将下方 `{source_text}` 中的 `{format_type}` 格式数据翻译为 `{target_lang}`。<br><br>*# 严格约束*<br>1. **结构锁定**：绝对保持原有的 `{format_type}` 数据结构、缩进和层级完全不变。<br>2. **选择性翻译**：仅翻译面向用户展示的可见文本内容。<br>3. **禁止修改**：**严禁**翻译或更改任何代码标签、键名 (Key)、变量占位符（如 `{{var}}`、`${var}`、`%s`、`%d` 等）或代码属性。<br><br>*# 数据输入*<br>`{source_text}` | *### Task*<br>Translate the user-facing text within the following `{format_type}` data into `{target_lang}`.<br><br>*### Strict Rules*<br>1. **Structure Preservation:** You MUST preserve the original `{format_type}` data structure, nesting, hierarchy, and indentation exactly as they are.<br>2. **Selective Translation:** Translate ONLY the visible, user-facing text content/values.<br>3. **Strict Non-Translation:** NEVER translate or alter code tags, keys, properties, object names, or variable placeholders. Leave them exactly in their original English/code form.<br><br>*### Source Data*<br>`{source_text}` |
| **Structured Data 2** | *【背景信息】*<br>`{background_text}`<br><br>请结合背景信息将以下文本翻译为 `{target_lang}`。<br><br>*【待翻译文本】*<br>`{source_text}` | *[Background Information]*<br>`{background_text}`<br><br>Please translate the following text into `{target_lang}`, taking the provided background information into consideration.<br><br>*[Source Text]*<br>`{source_text}` |

---

## 推理和部署

对于1.8B和7B，我们推荐使用下面这组参数进行推理。注意，我们的模型没有默认 system_prompt。

```json

{
  "temperature": 0.7,
  "top_p": 0.6,
  "top_k": 20,
  "repetition_penalty": 1.05,
  "max_tokens": 4096
}
```

对于30B-A3B，我们推荐使用下面这组参数进行推理。注意，我们的模型没有默认 system_prompt。

```json

{
  "temperature": 0.7,
  "top_p": 1.0,
  "top_k": -1,
  "repetition_penalty": 1.0,
  "max_tokens": 4096
}
```


### transformers

transformers>=5.6.0

```python
from transformers import AutoModelForCausalLM, AutoTokenizer
import torch

model_path = "tencent/Hy-MT3-30B-A3B"

# Load tokenizer
tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)

# Load model
model = AutoModelForCausalLM.from_pretrained(
    model_path,
    dtype=torch.bfloat16,
    device_map="auto",
    trust_remote_code=True,
)

model.eval()

# Example inference
prompt = "将以下文本翻译成英语,注意只需要输出翻译后的结果,不要额外解释:\n\n今天天气真好。"
messages = [{"role": "user", "content": prompt}]
inputs = tokenizer.apply_chat_template(messages, add_generation_prompt=True, return_tensors="pt").to(model.device)

with torch.no_grad():
    outputs = model.generate(
        **inputs,
        max_new_tokens=4096,
    )
response = tokenizer.decode(outputs[0][inputs["input_ids"].shape[-1]:], skip_special_tokens=True)
print(response)
```

### vllm

Build vLLM from source:
```bash
uv venv --python 3.12 --seed --managed-python
source .venv/bin/activate
git clone https://github.com/vllm-project/vllm.git
cd vllm
uv pip install --editable . --torch-backend=auto
```

Start the vLLM server:

```bash
vllm serve tencent/Hy-MT3-30B-A3B --tensor-parallel-size 1
```

### sglang

Build SGLang from source:
```bash
git clone https://github.com/sgl-project/sglang
cd sglang
pip3 install pip --upgrade
pip3 install "transformers>=5.6.0"
pip3 install -e "python"
```

Launch SGLang server:

```bash
python3 -m sglang.launch_server --model tencent/Hy-MT3-30B-A3B --tp 1
```


### llama_cpp
#### Clone llama.cpp

```bash
git clone https://github.com/ggml-org/llama.cpp.git
```

#### Enter the llama.cpp folder

```bash
cd llama.cpp
```

#### Build llama.cpp

```bash
cmake -B build
cmake --build build --config Release
```

#### Run a completion example

```bash
./build/bin/llama-completion \
  --model model.gguf  \
  -p "Translate the following segment into Chinese, without additional explanation：Hello" \
  --jinja \
  -ngl 0 \
  -n 64 -st 
```

#### Run the llama.cpp benchmark

```bash
./build/bin/llama-bench -m model_zoo/model.gguf  -ngl 0
```


## 模型训练
Hy-MT3提供了完整的模型训练流程，支持全量微调和 LoRA 微调，同时支持 DeepSpeed ZeRO 多种配置以及 LLaMA-Factory 集成。

详细的训练文档请参考：[模型训练指南](https://github.com/Tencent-Hunyuan/Hy-MT3/blob/main/train/README_CN.md)

## TransRubric

[TransRubric](https://github.com/Tencent-Hunyuan/Hy-MT3/blob/main/TransRubric/README_zh.md) 是一套基于评分细则（rubric）的大模型裁判评估方案，用于细粒度、可解释地评估翻译质量。给定原文、候选译文、翻译指令以及（可选的）参考译文，TransRubric 裁判对照样本专属的评分细则检查候选译文，标出每个问题及其错误类型和严重程度，并给出 0–100 分的单点分数。

* 在 WMT26 翻译质量自动评估赛道的 Task 2 上，TransRubric 的句子级 PDP（0.744）和 Avg Corr（0.832）均为最高，超过官方排名第一的提交系统。
* 与 10 位英语专业标注员在 651 条中英译文上对比：TransRubric 10 次打分之间的单条样本标准差平均仅 3.31 分，而人工标注员之间为 15.57 分；其 Pairwise 准确率（59.91%）高于 10 位标注员中的 7 位。

我们开源了 FLORES-200（33 个语种及 64 个低资源语种）、WMT26 GenMT 和 HardMTBench 上的样本专属评分细则，以及评分细则构建提示词和翻译裁判提示词，详见 [TransRubric](https://github.com/Tencent-Hunyuan/Hy-MT3/blob/main/TransRubric/README_zh.md)。

## 量化工具

我们提供了 [AngelSlim](https://github.com/tencent/AngelSlim)——一套易用、全面、高效的大模型压缩工具包，涵盖常用量化算法、低比特量化和投机采样等能力。


## 支持的语种

Hy-MT3 共支持 102 个语种，包括 Hy-MT2 已支持的 38 个语种和 64 个新增语种。

### Hy-MT2 已支持的语种（33 种）

| Language | Abbr. | Chinese Name | Language | Abbr. | Chinese Name | Language | Abbr. | Chinese Name |
|---|---|---|---|---|---|---|---|---|
| Chinese | `zh` | 中文 | Italian | `it` | 意大利语 | Khmer | `km` | 高棉语 |
| English | `en` | 英语 | German | `de` | 德语 | Burmese | `my` | 缅甸语 |
| French | `fr` | 法语 | Vietnamese | `vi` | 越南语 | Persian | `fa` | 波斯语 |
| Portuguese | `pt` | 葡萄牙语 | Malay | `ms` | 马来语 | Gujarati | `gu` | 古吉拉特语 |
| Spanish | `es` | 西班牙语 | Indonesian | `id` | 印尼语 | Urdu | `ur` | 乌尔都语 |
| Japanese | `ja` | 日语 | Filipino | `tl` | 菲律宾语 | Telugu | `te` | 泰卢固语 |
| Turkish | `tr` | 土耳其语 | Hindi | `hi` | 印地语 | Marathi | `mr` | 马拉地语 |
| Russian | `ru` | 俄语 | Traditional Chinese | `zh-TR` | 繁体中文 | Hebrew | `he` | 希伯来语 |
| Arabic | `ar` | 阿拉伯语 | Polish | `pl` | 波兰语 | Bengali | `bn` | 孟加拉语 |
| Korean | `ko` | 韩语 | Czech | `cs` | 捷克语 | Tamil | `ta` | 泰米尔语 |
| Thai | `th` | 泰语 | Dutch | `nl` | 荷兰语 | Ukrainian | `uk` | 乌克兰语 |

### Hy-MT2 已支持的少数民族语言和方言（5 种）

| Language | Abbr. | Chinese Name | Language | Abbr. | Chinese Name | Language | Abbr. | Chinese Name |
|---|---|---|---|---|---|---|---|---|
| Tibetan | `bo` | 藏语 | Traditional Mongolian | `mn` | 传统蒙古语 | Cantonese | `yue` | 粤语 |
| Arabic Kazakh | `kk` | 阿拉伯字母哈萨克语 | Uyghur | `ug` | 维吾尔语 |  |  |  |

### Hy-MT3 新增语种（64 种）

| Language | Abbr. | Chinese Name | Language | Abbr. | Chinese Name | Language | Abbr. | Chinese Name |
|---|---|---|---|---|---|---|---|---|
| Greek | `el` | 希腊语 | Welsh | `cy` | 威尔士语 | Sinhala | `si` | 僧伽罗语 |
| Romanian | `ro` | 罗马尼亚语 | Catalan | `ca` | 加泰罗尼亚语 | Punjabi | `pa` | 旁遮普语 |
| Hungarian | `hu` | 匈牙利语 | Galician | `gl` | 加利西亚语 | Sindhi | `sd` | 信德语 |
| Bulgarian | `bg` | 保加利亚语 | Basque | `eu` | 巴斯克语 | Assamese | `as` | 阿萨姆语 |
| Serbian | `sr` | 塞尔维亚语 | Afrikaans | `af` | 南非荷兰语 | Odia | `or` | 奥里亚语 |
| Croatian | `hr` | 克罗地亚语 | Luxembourgish | `lb` | 卢森堡语 | Kannada | `kn` | 卡纳达语 |
| Slovak | `sk` | 斯洛伐克语 | Maltese | `mt` | 马耳他语 | Malayalam | `ml` | 马拉雅拉姆语 |
| Slovenian | `sl` | 斯洛文尼亚语 | Esperanto | `eo` | 世界语 | Sanskrit | `sa` | 梵语 |
| Albanian | `sq` | 阿尔巴尼亚语 | Yiddish | `yi` | 意第绪语 | Lao | `lo` | 老挝语 |
| Macedonian | `mk` | 马其顿语 | Armenian | `hy` | 亚美尼亚语 | Javanese | `jv` | 爪哇语 |
| Belarusian | `be` | 白俄罗斯语 | Georgian | `ka` | 格鲁吉亚语 | Sundanese | `su` | 巽他语 |
| Lithuanian | `lt` | 立陶宛语 | Azerbaijani | `az` | 阿塞拜疆语 | Cebuano | `ceb` | 宿务语 |
| Latvian | `lv` | 拉脱维亚语 | Uzbek | `uz` | 乌兹别克语 | Waray | `war` | 瓦瑞语 |
| Estonian | `et` | 爱沙尼亚语 | Kyrgyz | `ky` | 吉尔吉斯语 | Swahili | `sw` | 斯瓦希里语 |
| Finnish | `fi` | 芬兰语 | Turkmen | `tk` | 土库曼语 | Amharic | `am` | 阿姆哈拉语 |
| Swedish | `sv` | 瑞典语 | Tajik | `tg` | 塔吉克语 | Somali | `so` | 索马里语 |
| Danish | `da` | 丹麦语 | Tatar | `tt` | 鞑靼语 | Malagasy | `mg` | 马达加斯加语 |
| Norwegian | `nb` | 挪威语 | Bashkir | `ba` | 巴什基尔语 | Haitian Creole | `ht` | 海地克里奥尔语 |
| Norwegian Nynorsk | `nn` | 新挪威语 | Kurdish | `ku` | 库尔德语 | Cyrillic Kazakh | `kk-Cyrl` | 西里尔哈萨克语 |
| Icelandic | `is` | 冰岛语 | Central Kurdish | `ckb` | 中库尔德语 | Cyrillic Mongolian | `mn-Cyrl` | 西里尔蒙古语 |
| Irish | `ga` | 爱尔兰语 | Pashto | `ps` | 普什图语 |  |  |  |
| Scottish Gaelic | `gd` | 苏格兰盖尔语 | Nepali | `ne` | 尼泊尔语 |  |  |  |


## 引用 Hy-MT3

```bibtex
@misc{zheng2026hymt3accuraterobust,
      title={Hy-MT3: More Accurate, Robust and Practical Multilingual Translation Models in the Wild}, 
      author={Mao Zheng and Zheng Li and Fangxu Liu and Tao Chen and Bingxin Qu and Bo Lv and Mingrui Sun and Hongyu Li and Hong Huang and Jinlong Song and Decheng Wu and Guanghua Yu},
      year={2026},
      eprint={2611.27673},
      archivePrefix={arXiv},
      primaryClass={cs.CL},
      url={https://arxiv.org/abs/2611.27673}, 
} 
```

## 联系我们
如果你想给我们的研发和产品团队留言，欢迎联系我们腾讯混元LLM团队。你可以通过邮件（hunyuan_opensource@tencent.com）联系我们。
