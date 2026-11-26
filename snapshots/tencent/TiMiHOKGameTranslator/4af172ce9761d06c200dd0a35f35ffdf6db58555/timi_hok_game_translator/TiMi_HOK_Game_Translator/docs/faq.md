# 常见问题（FAQ）

## 安装与环境

**Q：安装依赖在 Python 3.7 上失败。**
A：`TiMi_HOK_Game_Translator` 需要 **Python 3.8 或更高版本**。可通过
`pyenv install 3.11.9` 升级（或使用系统包管理器）。

**Q：`pip install -r requirements.txt` 很慢。**
A：启用 wheel 缓存：`pip config set global.cache-dir ~/.cache/pip`。
CI 上使用 `actions/setup-python` 自带的 `cache: pip` 参数
（`.github/workflows/ci.yml` 已经启用）。

## 运行流水线

**Q：CLI 打印 `Workflow finished`，但没有翻译任何内容。**
A：很可能你连着运行了两次。流水线是**可恢复的**：一旦跑到 `finished`，
状态文件（`workspace/workflow_state.json`）就记录它已完成，再次运行会直接返回。
加 `--fresh` 参数即可从头开始，或手动删除该 state 文件。

**Q：如何从某个特定状态恢复？**
A：编辑 `workspace/workflow_state.json`，把 `current_state`
改成你想**重新进入**的状态名，再次运行 CLI。Manager 会在每步执行后
持久化新快照，这一改法是安全的。

**Q：`require_valid` 抱怨 `target_locale`。**
A：框架拒绝在没有目标语种时运行。请通过下列任一方式设置：
`--target-locale zh-CN`、`GAME_TRANS_TOOLCHAIN__TARGET_LOCALE=zh-CN`、
或在 `config.yaml` 中填 `target_locale:` 字段。

## 密钥与敏感信息

**Q：我什么都没加，`scan_secrets` 却在 CI 上失败？**
A：扫描器会同时拦截**内部标识符**（主机名、真实用户名、旧 webhook 等）
和常见密钥模式。请看报错信息，它会给出命中的规则名和行号。
如果确实是误报，请把该文件同时加入 `.gitleaks.toml` 的 `[allowlist]`
以及 `scripts/scan_secrets.py` 中的 `ALLOWLIST_PATHS` 集合。

**Q：`config dump` 里还是能看到我的密码！**
A：仅当你显式加了 `--no-mask` 时才会输出原文，这是为本机调试专用。
不加该参数时，每个敏感字段都会被替换成 `***`。

## VCS

**Q：SVN 客户端每次都提示我信任证书。**
A：`SvnClient` 已经以 `--non-interactive` 方式运行。请在你的工作机上
手动信任一次证书：`svn info <url> --trust-server-cert`，之后 CI 上
就不会再打扰。

**Q：Git 在 CI 上 push 报"authentication required"。**
A：使用短期部署令牌 / SSH 密钥，通过
`GAME_TRANS_TOOLCHAIN__VCS__PASSWORD` 注入。`GitClient` 从不打印其值。

**Q：Perforce 命令卡住不返回。**
A：先在同一 shell 里执行过 `p4 login`。`PerforceClient` 不会自动做 SSO。

## LLM

**Q：如何在不改代码的情况下从 mock 切到 OpenAI？**
A：

```bash
pip install openai
export GAME_TRANS_TOOLCHAIN__LLM__PROVIDER=openai
export GAME_TRANS_TOOLCHAIN__LLM__API_KEY=sk-...
python main.py run --config config.yaml --fresh
```

**Q：翻译结果里 `{value}` 这类占位符被吃掉了。**
A：`OpenAILLM` 的 system prompt 已经要求模型保留占位符，
但没有任何 LLM 能保证 100% 可靠。如果你的 key 中占位符很多，
建议在 `TiMi_HOK_Game_Translator.strategies/` 下加一个"占位符校验"的后置策略。

## 扩展

**Q：私有策略/扩展在哪里发布，团队才能 import？**
A：把它做成独立 PyPI 包（公共或私有源都行）。把 `register_*` 调用
放在包的 `__init__.py`，只需 `import 你的包` 即可完成注册。

## 参与贡献

**Q：我的 PR 至少要兼容哪些 Python 版本？**
A：3.8 – 3.12。CI 矩阵会强制校验。请避免 `list[int]` / `dict[str, X]` /
`X | None` 语法，改用 `typing` 里的 `List[int]` 等。

**Q：我的 PR 里合法的 `Any` 边界被 `mypy` 挡了。**
A：使用带明确错误码和简短说明的
`# type: ignore[error-code]`。**不允许**大段 `# type: ignore`。

其它问题？请开一条打了 `question` 标签的 issue。
