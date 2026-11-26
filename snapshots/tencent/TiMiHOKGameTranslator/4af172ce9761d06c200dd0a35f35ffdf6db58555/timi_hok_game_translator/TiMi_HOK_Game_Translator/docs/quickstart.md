# 快速开始 —— 5 分钟端到端跑通（JSON demo）

本教程演示**默认端到端流水线**，全程无需任何外部服务：所有后端都使用
内置 mock，不需要凭据、网络或构建工具。

## 0. 前置要求

- Python **3.8 或更高版本**
- Windows / macOS / Linux 均可

## 1. 安装

```bash
git clone https://github.com/<your-org>/TiMi_HOK_Game_Translator.git
cd TiMi_HOK_Game_Translator

python -m venv .venv
# Linux / macOS
source .venv/bin/activate
# Windows PowerShell
.venv\Scripts\Activate.ps1

pip install -r requirements.txt
```

## 2. 查看最终生效的配置

本仓库在 [`docs/examples/`](./examples/) 下自带了一个开箱即用的 demo 配置
与 5 种格式的样例数据：

```
docs/examples/
├── demo.yaml                     # 全 mock 的 demo 配置
└── data/
    ├── example_game.en.json
    ├── example_game.en.yaml
    ├── example_game.en.xml
    ├── example_game.en.csv
    └── example_game.en.dtxml
```

先看一眼最终生效的配置：

```bash
python main.py config dump --config docs/examples/demo.yaml
```

输出的是一份解析后的 YAML 配置，每个敏感字段都会脱敏成 `***`。
后续排查问题时，这是快速自检的首选命令。

## 3. 运行流水线

```bash
python main.py run --config docs/examples/demo.yaml
```

> 💡 跑过一次之后想从头再来：加 `--fresh`：
> `python main.py run --config docs/examples/demo.yaml --fresh`。

预期输出（节选）：

```
[INFO] TiMi_HOK_Game_Translator: Starting TiMi_HOK_Game_Translator v0.1.0 for project=example_game target=zh-CN
[INFO] TiMi_HOK_Game_Translator.workflow.manager: Entering state 'ingest'
[INFO] TiMi_HOK_Game_Translator.workflow.ingest.pull_vcs_state: Loading source entries from docs/examples/data/example_game.en.json
[INFO] TiMi_HOK_Game_Translator.workflow.manager: Entering state 'translate'
[INFO] TiMi_HOK_Game_Translator.workflow.translate.translate_state: Translating 10 entries into zh-CN via LocalMockLLM
[INFO] TiMi_HOK_Game_Translator.workflow.manager: Entering state 'review'
[INFO] TiMi_HOK_Game_Translator.workflow.manager: Entering state 'merge'
[INFO] TiMi_HOK_Game_Translator.workflow.manager: Entering state 'publish'
[INFO] TiMi_HOK_Game_Translator: Workflow finished with state=finished
```

## 4. 检查结果

运行完成后，查看 workspace 下的产物：

- **`workspace/workflow_state.json`** —— 记录最终工作流状态，CLI 崩溃后据此断点续跑；
- **翻译结果** —— demo 中 mock LLM 会在每条 `target_text` 前加 `[zh-CN]` 前缀，便于一眼
  确认翻译链路通了。

## 5. 下一步

- **切换源文件格式**：把 `demo.yaml` 里 `source.format` 换成 `yaml`、`xml`、`csv`
  或 `dtxml`，`source.path` 指向 `docs/examples/data/` 下对应的样例文件即可。
- **接入真实 VCS**：把 `vcs.type` 改成 `svn` / `git` / `perforce`，凭据通过环境
  变量注入——**永远不要**把它们提交到仓库！详见 [扩展 VCS](./extending_vcs.md)。
- **接入 LLM**：
  ```bash
  pip install openai
  export GAME_TRANS_TOOLCHAIN__LLM__PROVIDER=openai
  export GAME_TRANS_TOOLCHAIN__LLM__API_KEY=sk-...
  python main.py run --config docs/examples/demo.yaml
  ```
- **完整字段参考**：[配置详解](./configuration.md)
- **接入审校平台 / 自定义策略**：[getting_started.md](./getting_started.md)
