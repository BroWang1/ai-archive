---
license: mit
pipeline_tag: text-generation
---

<p align="center">
    <img src="https://mdn.alipayobjects.com/huamei_qa8qxu/afts/img/A*4QxcQrBlTiAAAAAAQXAAAAgAemJ7AQ/original" width="100" alt="inclusionAI" />
</p>
<p align="center">🤗 <a href="https://huggingface.co/inclusionAI">Hugging Face</a>&nbsp;&nbsp; | &nbsp;&nbsp;🤖 <a href="https://modelscope.cn/organization/inclusionAI">ModelScope</a></p>

# Ling-3.1-flash-base

## Introduction

We introduce **Ling-3.1-flash-base**, the base checkpoint of [Ling-3.1-flash](https://huggingface.co/inclusionAI/Ling-3.1-flash), released to support research and community-driven innovation. With **560B total parameters** and **25B active parameters per token**, the model provides a foundation for continued pretraining, domain adaptation, and post-training research.

Ling-3.1-flash-base shares the same hybrid-linear Mixture-of-Experts (MoE) architecture as Ling-3.1-flash, combining KDA with Gated MLA. As a base checkpoint, it is intended for further training and adaptation.

The model was trained using **FP8**. This release provides the **BF16 base checkpoint** produced after **Warmup-Stable and Merge (WSM)** checkpoint merging. BF16 refers to the precision of the released weights, while FP8 refers to the precision used during training.

## Model Overview

### Key Features

- **Sparse MoE architecture:** 512 routed experts, with 8 routed experts and 1 shared expert activated per token, for a total of 25B active parameters per token.
- **Hybrid linear attention:** 63 KDA layers and 9 Gated MLA layers combine linear attention with Gated MLA at a 7:1 ratio.

### Model Specifications

| Specification | Value |
| --- | --- |
| Model Type | Base checkpoint |
| Architecture | Hybrid-linear MoE |
| Parameter Scale | Total 560B, Activated 25B |
| Transformer Layers | 63 KDA + 9 Gated MLA (7:1) |
| Number of Dense Layers | 4 |
| Number of Routed Experts | 512 |
| Number of Shared Experts | 1 |
| Number of Activated Routed Experts | 8 |
| Attention Heads | 64 |
| Hidden Size | 4096 |
| Expert Intermediate Size | 1280 |
| Dense Intermediate Size | 10240 |
| Vocabulary Size | 157184 |

### Architecture Diagram

![Ling-3.1-flash architecture](https://cdn-uploads.huggingface.co/production/uploads/678143d4ddb1f1ce16daca8e/qwmfVu_K08auI7R_ijbIX.png)

## Base Model Evaluation

We evaluate **Ling-3.1-flash-base** on 47 benchmarks across eight domains: language understanding, knowledge, code, mathematics, reasoning, multilingual capabilities, medical knowledge, and long-context understanding. The results below compare the model with DeepSeek-V4-Pro-Base and MiMo-V2.5-Pro-Base under the shot configurations shown.

**Bold** indicates the highest score in each row; <u>underlining</u> indicates the second-highest distinct score. Tied scores receive the same formatting. EM denotes exact match, and Acc denotes accuracy. Parameter scales are shown as total parameters and active parameters per token (A).

<style>
  .benchmark-wrap { width: 100%; overflow-x: auto; }
  .benchmark-table { border-collapse: collapse; margin: 0 auto; }
  .benchmark-table th, .benchmark-table td {
    padding: 0.55rem 0.8rem;
    text-align: center !important;
    vertical-align: middle;
  }
  .benchmark-table .ling { background-color: #e7f6ff; }
  .benchmark-table thead .ling { color: #1677ff; }
  .benchmark-table thead tr:first-child .ling { border-radius: 28px 28px 0 0; }
  .benchmark-table tbody tr:last-child .ling { border-radius: 0 0 28px 28px; }
  .benchmark-table .section-start > * { border-top: 2px solid #d0d7de; }
  .benchmark-table .table-footnote {
    padding-top: 0.85rem;
    text-align: left !important;
    color: #57606a;
    font-size: 0.9em;
  }
</style>
<div class="benchmark-wrap">
  <table class="benchmark-table" align="center">
    <thead>
      <tr>
        <th rowspan="2" scope="col" align="center">Domain</th>
        <th rowspan="2" scope="col" align="center">Benchmark</th>
        <th rowspan="2" scope="col" align="center">Shot Config</th>
        <th class="ling" scope="col" align="center">Ling-3.1-flash-base</th>
        <th scope="col" align="center">DeepSeek-V4-Pro-Base</th>
        <th scope="col" align="center">MiMo-V2.5-Pro-Base</th>
      </tr>
      <tr>
        <th class="ling" align="center">560B A25B</th>
        <th align="center">1.6T A49B</th>
        <th align="center">1.02T A42B</th>
      </tr>
    </thead>
    <tbody>
      <tr>
        <td class="domain" rowspan="5" align="center">Language Understanding</td>
        <td class="benchmark" align="center">Race-High<sub>(EM)</sub></td>
        <td class="shot" align="center">0-shot</td>
        <td class="ling" align="center"><strong>93.88</strong></td>
        <td align="center">93.37</td>
        <td align="center"><u>93.60</u></td>
      </tr>
      <tr>
        <td class="benchmark" align="center">SquadV2<sub>(Acc)</sub></td>
        <td class="shot" align="center">1-shot</td>
        <td class="ling" align="center"><strong>92.79</strong></td>
        <td align="center">87.70</td>
        <td align="center"><u>88.93</u></td>
      </tr>
      <tr>
        <td class="benchmark" align="center">Belebele<sub>(EM)</sub></td>
        <td class="shot" align="center">0-shot</td>
        <td class="ling" align="center"><strong>94.67</strong></td>
        <td align="center"><u>93.83</u></td>
        <td align="center">92.72</td>
      </tr>
      <tr>
        <td class="benchmark" align="center">C3<sub>(EM)</sub></td>
        <td class="shot" align="center">0-shot</td>
        <td class="ling" align="center"><strong>83.34</strong></td>
        <td align="center"><u>81.64</u></td>
        <td align="center">81.53</td>
      </tr>
      <tr>
        <td class="benchmark" align="center">CCPM<sub>(EM)</sub></td>
        <td class="shot" align="center">0-shot</td>
        <td class="ling" align="center"><u>91.88</u></td>
        <td align="center"><strong>93.31</strong></td>
        <td align="center">90.18</td>
      </tr>
      <tr class="section-start">
        <td class="domain" rowspan="10" align="center">Knowledge</td>
        <td class="benchmark" align="center">ARC-c<sub>(EM)</sub></td>
        <td class="shot" align="center">0-shot</td>
        <td class="ling" align="center"><strong>97.97</strong></td>
        <td align="center">96.61</td>
        <td align="center"><u>96.95</u></td>
      </tr>
      <tr>
        <td class="benchmark" align="center">AGIEval<sub>(Acc)</sub></td>
        <td class="shot" align="center">few-shot(0~5)</td>
        <td class="ling" align="center"><strong>82.59</strong></td>
        <td align="center"><u>81.26</u></td>
        <td align="center">79.90</td>
      </tr>
      <tr>
        <td class="benchmark" align="center">SimpleQA-Verified<sub>(Acc)</sub></td>
        <td class="shot" align="center">5-shot</td>
        <td class="ling" align="center"><strong>52.40</strong></td>
        <td align="center"><u>52.10</u></td>
        <td align="center">32.60</td>
      </tr>
      <tr>
        <td class="benchmark" align="center">C-SimpleQA<sub>(Acc)</sub></td>
        <td class="shot" align="center">5-shot</td>
        <td class="ling" align="center"><u>77.43</u></td>
        <td align="center"><strong>77.60</strong></td>
        <td align="center">70.93</td>
      </tr>
      <tr>
        <td class="benchmark" align="center">AA-Omniscience<sub>(Acc)</sub></td>
        <td class="shot" align="center">3-shot</td>
        <td class="ling" align="center"><u>37.67</u></td>
        <td align="center"><strong>48.16</strong></td>
        <td align="center">36.45</td>
      </tr>
      <tr>
        <td class="benchmark" align="center">MMLU-Pro<sub>(EM)</sub></td>
        <td class="shot" align="center">5-shot</td>
        <td class="ling" align="center"><strong>76.71</strong></td>
        <td align="center"><u>75.28</u></td>
        <td align="center">71.26</td>
      </tr>
      <tr>
        <td class="benchmark" align="center">CEval<sub>(EM)</sub></td>
        <td class="shot" align="center">5-shot</td>
        <td class="ling" align="center"><u>92.36</u></td>
        <td align="center"><strong>93.76</strong></td>
        <td align="center">92.08</td>
      </tr>
      <tr>
        <td class="benchmark" align="center">CMMLU<sub>(EM)</sub></td>
        <td class="shot" align="center">5-shot</td>
        <td class="ling" align="center"><strong>91.60</strong></td>
        <td align="center"><u>90.52</u></td>
        <td align="center">88.33</td>
      </tr>
      <tr>
        <td class="benchmark" align="center">GPQA-Diamond<sub>(EM)</sub></td>
        <td class="shot" align="center">0-shot</td>
        <td class="ling" align="center"><strong>56.57</strong></td>
        <td align="center">52.02</td>
        <td align="center"><u>54.04</u></td>
      </tr>
      <tr>
        <td class="benchmark" align="center">SuperGPQA<sub>(EM)</sub></td>
        <td class="shot" align="center">5-shot</td>
        <td class="ling" align="center"><strong>55.84</strong></td>
        <td align="center"><u>53.19</u></td>
        <td align="center">48.65</td>
      </tr>
      <tr class="section-start">
        <td class="domain" rowspan="7" align="center">Code</td>
        <td class="benchmark" align="center">HumanEval-Plus<sub>(Pass@1)</sub></td>
        <td class="shot" align="center">0-shot</td>
        <td class="ling" align="center"><u>79.88</u></td>
        <td align="center">57.93</td>
        <td align="center"><strong>82.93</strong></td>
      </tr>
      <tr>
        <td class="benchmark" align="center">CruxEval<sub>(Pass@1)</sub></td>
        <td class="shot" align="center">1-shot</td>
        <td class="ling" align="center"><strong>80.50</strong></td>
        <td align="center">69.06</td>
        <td align="center"><u>71.25</u></td>
      </tr>
      <tr>
        <td class="benchmark" align="center">MultiPL-E<sub>(Pass@1)</sub></td>
        <td class="shot" align="center">0-shot</td>
        <td class="ling" align="center"><strong>70.55</strong></td>
        <td align="center">55.94</td>
        <td align="center"><u>64.74</u></td>
      </tr>
      <tr>
        <td class="benchmark" align="center">MBPP-Plus<sub>(Pass@1)</sub></td>
        <td class="shot" align="center">3-shot</td>
        <td class="ling" align="center"><u>76.19</u></td>
        <td align="center">73.81</td>
        <td align="center"><strong>77.51</strong></td>
      </tr>
      <tr>
        <td class="benchmark" align="center">BigCodeBench<sub>(Pass@1)</sub></td>
        <td class="shot" align="center">0-shot</td>
        <td class="ling" align="center"><u>53.60</u></td>
        <td align="center">51.49</td>
        <td align="center"><strong>66.75</strong></td>
      </tr>
      <tr>
        <td class="benchmark" align="center">LCBench<sup>1</sup><sub>(Pass@1)</sub></td>
        <td class="shot" align="center">3-shot</td>
        <td class="ling" align="center"><strong>68.48</strong></td>
        <td align="center">59.14</td>
        <td align="center"><u>67.58</u></td>
      </tr>
      <tr>
        <td class="benchmark" align="center">LCBench-cn<sup>1</sup><sub>(Pass@1)</sub></td>
        <td class="shot" align="center">3-shot</td>
        <td class="ling" align="center"><u>60.83</u></td>
        <td align="center">57.35</td>
        <td align="center"><strong>63.36</strong></td>
      </tr>
      <tr class="section-start">
        <td class="domain" rowspan="6" align="center">Math</td>
        <td class="benchmark" align="center">MATH500<sub>(Acc)</sub></td>
        <td class="shot" align="center">4-shot</td>
        <td class="ling" align="center"><strong>79.40</strong></td>
        <td align="center"><u>68.20</u></td>
        <td align="center">57.20</td>
      </tr>
      <tr>
        <td class="benchmark" align="center">CollegeMath<sub>(Acc)</sub></td>
        <td class="shot" align="center">4-shot</td>
        <td class="ling" align="center"><strong>73.41</strong></td>
        <td align="center">63.15</td>
        <td align="center"><u>66.61</u></td>
      </tr>
      <tr>
        <td class="benchmark" align="center">FinanceReasoning<sub>(Acc)</sub></td>
        <td class="shot" align="center">3-shot</td>
        <td class="ling" align="center"><u>81.76</u></td>
        <td align="center"><strong>82.16</strong></td>
        <td align="center">80.89</td>
      </tr>
      <tr>
        <td class="benchmark" align="center">OlympiadBench<sub>(Acc)</sub></td>
        <td class="shot" align="center">3-shot</td>
        <td class="ling" align="center"><strong>60.24</strong></td>
        <td align="center">46.39</td>
        <td align="center"><u>48.04</u></td>
      </tr>
      <tr>
        <td class="benchmark" align="center">TheoremQA<sub>(Acc)</sub></td>
        <td class="shot" align="center">5-shot</td>
        <td class="ling" align="center"><strong>63.56</strong></td>
        <td align="center"><u>61.92</u></td>
        <td align="center">60.27</td>
      </tr>
      <tr>
        <td class="benchmark" align="center">OmniMath<sub>(Acc)</sub></td>
        <td class="shot" align="center">3-shot</td>
        <td class="ling" align="center"><strong>65.31</strong></td>
        <td align="center">34.89</td>
        <td align="center"><u>40.13</u></td>
      </tr>
      <tr class="section-start">
        <td class="domain" rowspan="5" align="center">Reasoning</td>
        <td class="benchmark" align="center">CommonSenseQA<sub>(EM)</sub></td>
        <td class="shot" align="center">5-shot</td>
        <td class="ling" align="center"><strong>92.22</strong></td>
        <td align="center">86.49</td>
        <td align="center"><u>88.53</u></td>
      </tr>
      <tr>
        <td class="benchmark" align="center">BBH<sub>(EM)</sub></td>
        <td class="shot" align="center">3-shot</td>
        <td class="ling" align="center"><strong>90.25</strong></td>
        <td align="center"><u>89.98</u></td>
        <td align="center">89.80</td>
      </tr>
      <tr>
        <td class="benchmark" align="center">KorBench<sub>(Acc)</sub></td>
        <td class="shot" align="center">3-shot</td>
        <td class="ling" align="center"><strong>54.96</strong></td>
        <td align="center"><u>54.56</u></td>
        <td align="center">53.20</td>
      </tr>
      <tr>
        <td class="benchmark" align="center">AutoLogi<sub>(Acc)</sub></td>
        <td class="shot" align="center">3-shot</td>
        <td class="ling" align="center"><strong>67.13</strong></td>
        <td align="center">64.81</td>
        <td align="center"><u>66.23</u></td>
      </tr>
      <tr>
        <td class="benchmark" align="center">ZebraLogic<sub>(Acc)</sub></td>
        <td class="shot" align="center">1-shot</td>
        <td class="ling" align="center"><strong>30.80</strong></td>
        <td align="center">20.30</td>
        <td align="center"><u>28.90</u></td>
      </tr>
      <tr class="section-start">
        <td class="domain" rowspan="4" align="center">Multilingual</td>
        <td class="benchmark" align="center">mARC<sub>(EM)</sub></td>
        <td class="shot" align="center">0-shot</td>
        <td class="ling" align="center"><strong>92.98</strong></td>
        <td align="center"><u>89.10</u></td>
        <td align="center">88.55</td>
      </tr>
      <tr>
        <td class="benchmark" align="center">MMMLU<sub>(EM)</sub></td>
        <td class="shot" align="center">0-shot</td>
        <td class="ling" align="center"><strong>77.56</strong></td>
        <td align="center"><u>68.81</u></td>
        <td align="center">67.15</td>
      </tr>
      <tr>
        <td class="benchmark" align="center">MultiGSM<sub>(Acc)</sub></td>
        <td class="shot" align="center">4-shot</td>
        <td class="ling" align="center"><strong>87.66</strong></td>
        <td align="center">85.87</td>
        <td align="center"><u>86.33</u></td>
      </tr>
      <tr>
        <td class="benchmark" align="center">HumanEvalXL<sub>(Pass@1)</sub></td>
        <td class="shot" align="center">0-shot</td>
        <td class="ling" align="center"><u>83.25</u></td>
        <td align="center">70.31</td>
        <td align="center"><strong>87.34</strong></td>
      </tr>
      <tr class="section-start">
        <td class="domain" rowspan="3" align="center">Med</td>
        <td class="benchmark" align="center">DiagnosisArena<sub>(EM)</sub></td>
        <td class="shot" align="center">0-shot</td>
        <td class="ling" align="center"><strong>62.20</strong></td>
        <td align="center"><u>55.50</u></td>
        <td align="center">52.70</td>
      </tr>
      <tr>
        <td class="benchmark" align="center">medmcqa<sub>(EM)</sub></td>
        <td class="shot" align="center">5-shot</td>
        <td class="ling" align="center"><u>78.08</u></td>
        <td align="center"><strong>80.33</strong></td>
        <td align="center">77.50</td>
      </tr>
      <tr>
        <td class="benchmark" align="center">medqa<sub>(EM)</sub></td>
        <td class="shot" align="center">5-shot</td>
        <td class="ling" align="center"><strong>87.82</strong></td>
        <td align="center"><u>87.75</u></td>
        <td align="center">85.55</td>
      </tr>
      <tr class="section-start">
        <td class="domain" rowspan="7" align="center">Long-context</td>
        <td class="benchmark" align="center">LongBench<sub>(Acc)</sub></td>
        <td class="shot" align="center">0-shot</td>
        <td class="ling" align="center"><strong>51.90</strong></td>
        <td align="center"><u>17.70</u></td>
        <td align="center">15.66</td>
      </tr>
      <tr>
        <td class="benchmark" align="center">LEval<sub>(Acc)</sub></td>
        <td class="shot" align="center">0-shot</td>
        <td class="ling" align="center"><strong>85.09</strong></td>
        <td align="center">58.34</td>
        <td align="center"><u>61.49</u></td>
      </tr>
      <tr>
        <td class="benchmark" align="center">ruler_16k<sub>(Acc)</sub></td>
        <td class="shot" align="center">1-shot</td>
        <td class="ling" align="center"><u>96.90</u></td>
        <td align="center"><strong>97.00</strong></td>
        <td align="center">90.61</td>
      </tr>
      <tr>
        <td class="benchmark" align="center">ruler_32k<sub>(Acc)</sub></td>
        <td class="shot" align="center">1-shot</td>
        <td class="ling" align="center"><strong>95.87</strong></td>
        <td align="center"><u>95.57</u></td>
        <td align="center">89.10</td>
      </tr>
      <tr>
        <td class="benchmark" align="center">ruler_64k<sub>(Acc)</sub></td>
        <td class="shot" align="center">1-shot</td>
        <td class="ling" align="center"><u>93.81</u></td>
        <td align="center"><strong>95.56</strong></td>
        <td align="center">87.19</td>
      </tr>
      <tr>
        <td class="benchmark" align="center">ruler_128k<sub>(Acc)</sub></td>
        <td class="shot" align="center">1-shot</td>
        <td class="ling" align="center"><u>88.64</u></td>
        <td align="center"><strong>95.06</strong></td>
        <td align="center">85.79</td>
      </tr>
      <tr>
        <td class="benchmark" align="center">ruler_256k<sub>(Acc)</sub></td>
        <td class="shot" align="center">1-shot</td>
        <td class="ling" align="center"><u>86.64</u></td>
        <td align="center"><strong>94.37</strong></td>
        <td align="center">86.00</td>
      </tr>
    </tbody>
    <tfoot>
      <tr>
        <td class="table-footnote" colspan="6" align="left">
          <strong>Note:</strong><br>
          <sup>1</sup> LCBench and LCBench-cn: January 2023–February 2025 (2301-2502).
        </td>
      </tr>
    </tfoot>
  </table>
</div>

## Intended Use

Recommended use cases:

- Continued pretraining.
- Mid-training.
- Supervised fine-tuning for domain adaptation.
- Preference optimization and reinforcement-learning post-training.
- Distillation research.
- Long-context and MoE systems research.

Not recommended as-is for:

- Direct end-user chat deployment.
- Safety-critical applications without additional alignment and evaluation.
- Production use without post-training and task-specific validation.

## Usage

For fine-tuning examples, please refer to our [ling-cookbook](https://github.com/inclusionAI/ling-cookbook/).

## FAQ

For questions or feedback, please open a discussion in the model repository.

## License

This model is released under the **MIT License**.
