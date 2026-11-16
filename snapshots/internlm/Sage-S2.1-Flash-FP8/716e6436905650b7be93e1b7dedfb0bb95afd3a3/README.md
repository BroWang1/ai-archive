# Sage S2.1 Flash

[**Official Website**](https://internlm.github.io/Sage-S2.1-Flash/) · [**Introduction**](#introduction) · [**Model Downloads**](#model-downloads) · [**Evaluation**](#evaluation-results) · [**Deployment**](#deployment) · [**License**](#license)

## Introduction

**Sage S2.1 Flash** is a scientific multimodal model from Shanghai Artificial Intelligence Laboratory designed for research tasks that require multiple rounds of analysis and verification. It combines scientific data understanding with information retrieval, programming, and tool use. It can use specialized software to perform analyses, check results against intermediate outputs and visual feedback, and adjust subsequent steps accordingly.

![Scientific multimodal representation architecture](assets/scientific-multimodal-architecture.png)

Through the unified representation architecture of [**Sage SciPerception**](https://huggingface.co/internlm/Sage-SciPerception), the model supports more than ten types of scientific input, including molecular graphs, crystal structures, and protein sequences and 3D structures. Features from each input type are encoded and projected into a shared representation space for reasoning alongside natural language instructions. These inputs support tasks such as prediction, classification, site localization, quantitative analysis, and structure inference.

## Model Downloads

| Model | Hugging Face | ModelScope |
| --- | --- | --- |
| Sage S2.1 Flash | [Model repository](https://huggingface.co/internlm/Sage-S2.1-Flash) | [Model repository](https://www.modelscope.cn/models/Shanghai_AI_Laboratory/Sage-S2.1-Flash) |
| Sage S2.1 Flash FP8 | [Model repository](https://huggingface.co/internlm/Sage-S2.1-Flash-FP8) | [Model repository](https://www.modelscope.cn/models/Shanghai_AI_Laboratory/Sage-S2.1-Flash-FP8) |

## Evaluation Results

![Sage S2.1 Flash and five baselines on 15 benchmarks](assets/evaluation.png)

### Highlights

Across the 15 benchmarks and six models shown in the chart, Sage S2.1 Flash placed first on four benchmarks and second on seven.

- **Machine learning engineering.** Sage S2.1 Flash placed first on MLE-bench Lite with 90.3, ahead of DeepSeek-V4.1-Flash-1017 at 89.2.
- **Office and professional document processing.** It placed first on OfficeQA Pro, Harvey LAB, and SpreadsheetBench 2, scoring 72.2, 25.0, and 37.1, respectively.
- **Tool use and research execution.** It placed second on AutomationBench, ALE-CLI, BFCL V4, WebArena-Verified, DeepResearch Bench II, JobBench, and OSWorld-Verified.

<table>
  <thead>
    <tr>
      <th scope="col" align="center" valign="middle" style="text-align: center; vertical-align: middle;">Category</th>
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

## Deployment

### Inference with Scientific Projectors

[Sage SciPerception](https://huggingface.co/internlm/Sage-SciPerception) uses scientific encoders and trainable projectors to map scientific data into the language model's input embedding space, where the data can be processed alongside natural language instructions. The resulting representations preserve structural and local information from the original data for tasks such as materials property prediction, sequence classification, site localization, and structure inference.

Download the projector from the model repository and the shared loading scripts from Sage-SciPerception.

```bash
python -m pip install torch safetensors huggingface_hub
hf download internlm/Sage-S2.1-Flash   --include "projectors/sage-s2.1-flash/**" --local-dir ./sage-s2.1-flash
hf download internlm/Sage-SciPerception   load_projector.py modeling_projector.py --local-dir ./sage-s2.1-flash
cd sage-s2.1-flash
```

For a crystal structure task, you can first verify that the projector loads on the CPU.

```python
from load_projector import load_projector

projector, config = load_projector(
    "projectors/sage-s2.1-flash/cif/jarvis", device="cpu"
)
```

To generate a response, the client extracts features according to the relevant scientific input protocol and runs the projector. It combines the projector output with Sage S2.1 Flash's text token embeddings to form the complete prompt sequence, then passes it to the language model. Enable `--enable-prompt-embeds` on the vLLM server and send `prompt_embeds` to `/v1/completions`. Use the tokenizer and text embeddings that match the base model.

Set up the scientific encoders, task-specific scientific readouts, and preprocessing dependencies separately. See `config.json` for each task's input format. The [Sage-SciPerception inference guide](https://huggingface.co/internlm/Sage-SciPerception#inference) provides the full integration workflow and a CIF client example. Replace the example's projector path and base language model with the corresponding versions from this repository.

### Inference for General Tasks

Use the following deployment guides for tasks such as coding, office productivity, security, and computer use.

- [Sage S2.1 Flash Deployment Guide](https://huggingface.co/internlm/Sage-S2.1-Flash/blob/main/deployment_guide.md)
- [Sage S2.1 Flash FP8 Deployment Guide](https://huggingface.co/internlm/Sage-S2.1-Flash-FP8/blob/main/deployment_guide.md)

## License

The code and model weights in this repository are released under the **MIT License**.
