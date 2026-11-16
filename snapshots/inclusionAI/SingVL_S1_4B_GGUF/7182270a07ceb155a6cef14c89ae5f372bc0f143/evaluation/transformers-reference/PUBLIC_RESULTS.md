# Sing VL S1 公榜复跑与接口验证

| Panel | 原记录 | 本次 PPU2 复跑 | 差值 |
|---|---:|---:|---:|
| Text | 69.76 | 69.76 | +0.00 |
| Vision | 73.94 | 73.75 | -0.19 |

Text：140,178 条，{'ok': 140178}。Vision：12,210 条，{'ok': 12210}。

## Vision 明细

| 数据集 | Accuracy | Skill |
|---|---:|---:|
| CV-Bench | 87.39 | 79.20 |
| BLINK | 72.53 | 57.47 |
| RealWorldQA | 82.00 | 70.59 |
| CharXiv | 86.28 | 81.70 |
| InfographicVQA | 94.67 | 92.90 |
| Mind2Web | 87.36 | 83.14 |
| Winoground | 93.38 | 86.75 |
| KIE (CORD+FUNSD) | 95.62 | 92.79 |
| Moderation (Hateful Memes) | 72.05 | 44.11 |
| R-Bench-M | 50.23 | 40.26 |
| MMMU-Pro vision | 48.67 | 41.13 |

## Text 明细

| 数据集 | 原始指标 | 原始得分 | Skill |
|---|---|---:|---:|
| BFCL | case exact accuracy | 96.81 | 95.70 |
| ToolRet | nDCG@10 | 67.92 | 62.96 |
| API-Bank | accuracy | 84.45 | 84.15 |
| BANKING77 | macro-F1 | 93.97 | 93.89 |
| CLINC150+OOS | macro-F1 | 96.99 | 96.97 |
| RouterBench | selected quality (quality objective) | 79.84 | 52.73 |
| Home appliance simulator | case exact accuracy | 100.00 | 100.00 |
| SGD/SGD-X | macro-F1 | 8.29 | 0.00 |
| ContractNLI | macro-F1 | 83.95 | 76.78 |
| ANLI | macro-F1 | 78.10 | 67.20 |
| BPoMP | accuracy | 95.30 | 90.92 |
| Humicroedit | accuracy | 67.62 | 35.24 |
| POP909-CL | accuracy | 80.70 | 79.82 |
| cfcolor | accuracy | 69.98 | 44.06 |
| MMLU | accuracy | 82.91 | 77.21 |
| GPQA Diamond | accuracy | 52.04 | 36.05 |
| ARC-Easy | accuracy | 99.07 | 98.76 |
| ARC-Challenge | accuracy | 96.16 | 94.88 |
| WinoGrande | accuracy | 89.90 | 79.80 |
| HellaSwag | accuracy | 96.45 | 95.27 |
| ChessBench | accuracy | 26.92 | 20.40 |
| MuSR | accuracy | 65.82 | 45.66 |
| SATA-Bench | case exact accuracy | 54.12 | 53.51 |
| SimpleBench | accuracy | 50.00 | 40.00 |
| BRIGHT | nDCG@10 | 47.43 | 40.52 |
| Amazon ESCI | macro-F1 | 60.77 | 50.79 |
| ACOS | per-review F1 | 65.07 | 63.95 |
| FinEntity | macro-F1 | 95.23 | 92.98 |
| iSarcasmEval | see separate subtask tracks | None | — |
| VAST | macro-F1 | 79.78 | 69.68 |
| NLI4CT | macro-F1 | 86.41 | 73.56 |
| CRUXEval | accuracy | 77.89 | 64.93 |
| CLadder | accuracy | 94.74 | 89.48 |
| HLE | accuracy | 13.17 | 0.00 |
| Habermas Machine | accuracy | 64.20 | 48.04 |
| GSM8K | accuracy | 73.73 | 68.54 |
| PhishNChips phishing decisions | accuracy | 85.50 | 71.00 |
| MMLU-Pro | accuracy | 68.42 | 64.48 |
| BBH fixed-option tasks | accuracy | 88.60 | 83.48 |
| RAGTruth response-level hallucination | F1 on hallucinated class | 83.71 | 66.22 |
| HoVer claim verification | accuracy | 89.25 | 78.50 |
| When2Call MCQ | accuracy | 90.58 | 87.44 |
| New Yorker caption matching | accuracy | 80.49 | 75.61 |

## 验证范围

- 冻结样本 ID、题目/选项概率与全部实际图像 SHA-256 已核验。
- 原生适配器对照保存的公开输出；HTTP 三种图片编码对照相同预处理图片的原生输出。验证范围和前置缩图带来的预测变化详见 interface_validation.json。
- 空 state、显式 image 标记、Choice/Noul/Score 和声明的非法输入均有验证记录。
- 私榜数据由维护者持有，本次未运行私榜，不能判断私榜成绩是否一致。
- 当前仅准备本地提交包，没有上传模型、结果或创建提交 PR。
- checkpoint 元数据 MAX_PIXELS 为 1,806,336；本次公榜按官方上限 1,638,400 运行。这是已确认的设置差异，不将全部分差归因于它。
- PPU 为共享系统，本次耗时不构成官方 RTX PRO 6000 的延迟准入测量。
