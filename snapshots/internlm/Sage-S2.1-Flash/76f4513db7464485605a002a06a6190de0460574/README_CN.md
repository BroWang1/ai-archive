# Sage S2.1 Flash

**书生 S2.1 Flash 科学多模态大模型**

[**官网**](https://internlm.github.io/Sage-S2.1-Flash/) · [**模型介绍**](#模型介绍) · [**模型下载**](#模型下载) · [**评估结果**](#评估结果) · [**部署方式**](#部署方式) · [**许可证**](#许可证)

## 模型介绍

**Sage S2.1 Flash（书生 S2.1 Flash）**是上海人工智能实验室推出的科学多模态大模型，面向需要多轮分析与反复验证的科研任务。模型将科学数据理解与检索、编程和工具调用相结合，可使用专业软件开展分析，并依据中间结果和视觉反馈核验结果、调整后续步骤。

![书生 S2.1 Flash 科学多模态架构图](assets/scientific-multimodal-architecture-cn.png)

借助[**书生·元征**](https://huggingface.co/internlm/Sage-SciPerception)**（Sage SciPerception）**的统一表征架构，模型支持十余类科学输入，涵盖分子图、晶体结构、蛋白质序列与三维结构等。各类数据经特征编码与投影后映射到共享表征空间，与自然语言指令共同参与推理，为预测、分类、位点定位、定量分析和结构推断等任务提供输入基础。

## 模型下载

| 模型 | Hugging Face | ModelScope |
| --- | --- | --- |
| Sage S2.1 Flash | [模型仓库](https://huggingface.co/internlm/Sage-S2.1-Flash) | [模型仓库](https://www.modelscope.cn/models/Shanghai_AI_Laboratory/Sage-S2.1-Flash) |
| Sage S2.1 Flash FP8 | [模型仓库](https://huggingface.co/internlm/Sage-S2.1-Flash-FP8) | [模型仓库](https://www.modelscope.cn/models/Shanghai_AI_Laboratory/Sage-S2.1-Flash-FP8) |

## 评估结果

![书生 S2.1 Flash 与五款基线模型在 15 项基准上的评测结果](assets/evaluation.png)

### 重点结果

在评测图选取的 **15 项基准、6 款模型** 的比较中，Sage S2.1 Flash 取得 **4 项第一、7 项第二**。这一排名仅适用于该图的基准和模型集合。

- **机器学习工程：** MLE-bench Lite 得分 **90.3**，位列第一，高于第二名 DeepSeek-V4.1-Flash-1017 的 89.2。
- **办公与专业文档处理：** OfficeQA Pro、Harvey LAB 和 SpreadsheetBench 2 分别取得 **72.2、25.0 和 37.1**，均位列第一。
- **工具使用与科研执行：** AutomationBench、ALE-CLI、BFCL V4、WebArena-Verified、DeepResearch Bench II、JobBench 和 OSWorld-Verified 位列第二。

<table>
  <thead>
    <tr>
      <th scope="col" align="center" valign="middle" style="text-align: center; vertical-align: middle;">类别</th>
      <th scope="col">Benchmark</th>
      <th scope="col">Sage S2.1 Flash</th>
      <th scope="col">GLM-5.3-Flash</th>
      <th scope="col">DeepSeek-V4.1-Flash-1017</th>
      <th scope="col">Qwen3.8-Max</th>
      <th scope="col">GPT-5.6 Sol</th>
      <th scope="col">Claude Opus 5</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td rowspan="4" align="center" valign="middle" style="text-align: center; vertical-align: middle;">Agentic Coding</td>
      <td>Terminal-Bench 2.1</td>
      <td>87.9</td>
      <td>84.3</td>
      <td>87.6</td>
      <td>89.6</td>
      <td>86.2</td>
      <td><strong>90.2</strong></td>
    </tr>
    <tr>
      <td>DeepSWE</td>
      <td>67.9</td>
      <td>63.7</td>
      <td><strong>73.9</strong></td>
      <td>67.0</td>
      <td>70.6</td>
      <td>72.6</td>
    </tr>
    <tr>
      <td>NL2Repo-Bench</td>
      <td>57.2</td>
      <td>53.0</td>
      <td>62.7</td>
      <td>63.2</td>
      <td>60.7</td>
      <td><strong>79.9</strong></td>
    </tr>
    <tr>
      <td>SWE-bench Pro</td>
      <td>60.6</td>
      <td>60.3</td>
      <td>61.8</td>
      <td>65.3</td>
      <td>59.8</td>
      <td><strong>76.5</strong></td>
    </tr>
    <tr>
      <td rowspan="6" align="center" valign="middle" style="text-align: center; vertical-align: middle;">Productivity</td>
      <td>SpreadsheetBench 2</td>
      <td><strong>37.1</strong></td>
      <td>32.4</td>
      <td>35.8</td>
      <td>34.9</td>
      <td>32.7</td>
      <td>33.6</td>
    </tr>
    <tr>
      <td>ALE-CLI</td>
      <td>32.4</td>
      <td>28.1</td>
      <td><strong>35.4</strong></td>
      <td>24.8</td>
      <td>28.6</td>
      <td>29.5</td>
    </tr>
    <tr>
      <td>APEX-Agents</td>
      <td>61.7</td>
      <td>50.8</td>
      <td><strong>69.2</strong></td>
      <td>66.3</td>
      <td>55.4</td>
      <td>61.3</td>
    </tr>
    <tr>
      <td>GDPval</td>
      <td>78.0</td>
      <td>67.7</td>
      <td>77.6</td>
      <td>79.6</td>
      <td>69.6</td>
      <td><strong>80.0</strong></td>
    </tr>
    <tr>
      <td>Workspace-Bench-Lite</td>
      <td>67.1</td>
      <td>65.1</td>
      <td>66.8</td>
      <td>67.4</td>
      <td>57.4</td>
      <td><strong>68.1</strong></td>
    </tr>
    <tr>
      <td>Workspace-Bench</td>
      <td>61.7</td>
      <td>59.7</td>
      <td>63.0</td>
      <td><strong>63.9</strong></td>
      <td>50.9</td>
      <td>62.0</td>
    </tr>
    <tr>
      <td rowspan="7" align="center" valign="middle" style="text-align: center; vertical-align: middle;">Tool Use</td>
      <td>OfficeQA Pro</td>
      <td><strong>72.2</strong></td>
      <td>64.7</td>
      <td>69.7</td>
      <td>66.2</td>
      <td>66.4</td>
      <td>67.2</td>
    </tr>
    <tr>
      <td>Harvey LAB</td>
      <td><strong>25.0</strong></td>
      <td>20.0</td>
      <td>11.7</td>
      <td>24.2</td>
      <td>5.0</td>
      <td>22.7</td>
    </tr>
    <tr>
      <td>AutomationBench</td>
      <td>56.7</td>
      <td>48.3</td>
      <td><strong>57.8</strong></td>
      <td>49.7</td>
      <td>45.7</td>
      <td>49.4</td>
    </tr>
    <tr>
      <td>BFCL V4</td>
      <td>75.5</td>
      <td>71.7</td>
      <td>71.4</td>
      <td>66.8</td>
      <td>68.8</td>
      <td><strong>80.6</strong></td>
    </tr>
    <tr>
      <td>JobBench</td>
      <td>58.8</td>
      <td>56.5</td>
      <td>58.5</td>
      <td>52.7</td>
      <td>45.4</td>
      <td><strong>68.0</strong></td>
    </tr>
    <tr>
      <td>SkillsBench</td>
      <td>62.3</td>
      <td>58.3</td>
      <td>52.8</td>
      <td><strong>66.7</strong></td>
      <td>62.5</td>
      <td>63.7</td>
    </tr>
    <tr>
      <td>τ³-bench Banking</td>
      <td>45.4</td>
      <td>39.2</td>
      <td>47.4</td>
      <td><strong>55.2</strong></td>
      <td>46.9</td>
      <td>48.7</td>
    </tr>
    <tr>
      <td rowspan="4" align="center" valign="middle" style="text-align: center; vertical-align: middle;">ML Engineering</td>
      <td>MLE-bench Lite</td>
      <td><strong>90.3</strong></td>
      <td>84.3</td>
      <td>89.2</td>
      <td>82.2</td>
      <td>80.7</td>
      <td>88.0</td>
    </tr>
    <tr>
      <td>PostTrainBench</td>
      <td><strong>39.2</strong></td>
      <td>36.8</td>
      <td>–</td>
      <td>–</td>
      <td>31.0</td>
      <td>35.7</td>
    </tr>
    <tr>
      <td>PaperBench</td>
      <td>88.0</td>
      <td>83.0</td>
      <td>88.6</td>
      <td><strong>95.1</strong></td>
      <td>94.3</td>
      <td>86.9</td>
    </tr>
    <tr>
      <td>MLS-Bench</td>
      <td>42.0</td>
      <td>39.9</td>
      <td>44.3</td>
      <td>41.0</td>
      <td>46.2</td>
      <td><strong>49.8</strong></td>
    </tr>
    <tr>
      <td rowspan="1" align="center" valign="middle" style="text-align: center; vertical-align: middle;">Deep Research</td>
      <td>DeepResearch Bench II</td>
      <td>54.2</td>
      <td>51.9</td>
      <td><strong>55.1</strong></td>
      <td>49.2</td>
      <td>50.7</td>
      <td>54.1</td>
    </tr>
    <tr>
      <td rowspan="4" align="center" valign="middle" style="text-align: center; vertical-align: middle;">Search</td>
      <td>DeepSearchQA</td>
      <td>94.4</td>
      <td>92.6</td>
      <td><strong>95.3</strong></td>
      <td>–</td>
      <td>93.2</td>
      <td>–</td>
    </tr>
    <tr>
      <td>BrowseComp-VL</td>
      <td>60.5</td>
      <td><strong>61.0</strong></td>
      <td>60.6</td>
      <td>–</td>
      <td>–</td>
      <td>–</td>
    </tr>
    <tr>
      <td>WideSearch</td>
      <td>81.5</td>
      <td>77.2</td>
      <td><strong>86.3</strong></td>
      <td>81.9</td>
      <td>83.3</td>
      <td>84.0</td>
    </tr>
    <tr>
      <td>BrowseComp</td>
      <td>91.2</td>
      <td>88.3</td>
      <td><strong>93.8</strong></td>
      <td>–</td>
      <td>92.2</td>
      <td>90.8</td>
    </tr>
    <tr>
      <td rowspan="7" align="center" valign="middle" style="text-align: center; vertical-align: middle;">Vision</td>
      <td>OSWorld v2.1</td>
      <td>69.3</td>
      <td>66.4</td>
      <td>70.1</td>
      <td>66.4</td>
      <td>70.4</td>
      <td><strong>74.0</strong></td>
    </tr>
    <tr>
      <td>OSWorld-Verified</td>
      <td>85.2</td>
      <td>83.5</td>
      <td>78.5</td>
      <td>84.3</td>
      <td>82.2</td>
      <td><strong>86.4</strong></td>
    </tr>
    <tr>
      <td>WebArena-Verified</td>
      <td>67.6</td>
      <td>65.0</td>
      <td>60.7</td>
      <td>64.9</td>
      <td>66.6</td>
      <td><strong>69.1</strong></td>
    </tr>
    <tr>
      <td>Vision2Web</td>
      <td>78.0</td>
      <td>75.8</td>
      <td>–</td>
      <td>75.2</td>
      <td>73.5</td>
      <td><strong>80.2</strong></td>
    </tr>
    <tr>
      <td>WeaveBench</td>
      <td>68.4</td>
      <td>60.9</td>
      <td>–</td>
      <td>71.9</td>
      <td>79.6</td>
      <td><strong>86.4</strong></td>
    </tr>
    <tr>
      <td>OSWorld-G</td>
      <td>84.8</td>
      <td>83.7</td>
      <td>61.4</td>
      <td><strong>88.6</strong></td>
      <td>77.7</td>
      <td>76.8</td>
    </tr>
    <tr>
      <td>BabyVision</td>
      <td>75.8</td>
      <td>51.3</td>
      <td>58.0</td>
      <td><strong>83.8</strong></td>
      <td>80.7</td>
      <td>63.1</td>
    </tr>
  </tbody>
</table>

## 部署方式

### 使用科学 Projector进行推理部署

[书生·元征（Sage SciPerception）](https://huggingface.co/internlm/Sage-SciPerception)通过科学编码器与可训练 projector，将科学数据映射到语言模型的输入嵌入空间，与自然语言指令共同参与推理。科学表征保留原始数据的结构和局部信息，为材料性质预测、序列分类、位点定位与结构推断等任务提供输入。

下载本仓库的 projector，并从 Sage-SciPerception 获取通用加载脚本：

```bash
python -m pip install torch safetensors huggingface_hub
hf download internlm/Sage-S2.1-Flash   --include "projectors/sage-s2.1-flash/**" --local-dir ./sage-s2.1-flash
hf download internlm/Sage-SciPerception   load_projector.py modeling_projector.py --local-dir ./sage-s2.1-flash
cd sage-s2.1-flash
```

以晶体结构任务为例，可先在 CPU 上检查加载：

```python
from load_projector import load_projector

projector, config = load_projector(
    "projectors/sage-s2.1-flash/cif/jarvis", device="cpu"
)
```

生成时，客户端按对应科学输入协议提取特征并执行 projector，将输出与 Sage S2.1 Flash 的文字 token embedding 组合为完整提示序列，再交给语言模型生成。vLLM 服务需开启 --enable-prompt-embeds，通过 /v1/completions 接收 prompt_embeds，并使用匹配底座的 tokenizer 与文字 embedding。

科学编码器、任务适配的科学读出及预处理依赖需另行准备；各任务的输入格式以 config.json 为准。完整接入流程与 CIF 客户端示例见 [Sage-SciPerception 推理指南](https://huggingface.co/internlm/Sage-SciPerception#inference)，示例中的 projector 路径与语言底座需替换为本仓库对应版本。

### 非科学任务的推理部署

针对非科学任务(如code编程、通用办公、安全攻防，computer use等)的使用，可以参考下面链接进行部署

<https://huggingface.co/internlm/Sage-S2.1-Flash/blob/main/deployment_guide.md>

<https://huggingface.co/internlm/Sage-S2.1-Flash-FP8/blob/main/deployment_guide.md>

## 许可证

The code and model weights in this repository are released under the [**MIT License**](https://huggingface.co/internlm/Atria-Dawn/tree/main/LICENSE).
