"""conf 包：业务层运行配置与 LLM 粘合器。

对外暴露：
    load_config_with_llm_profiles —— 读取 conf/config.yaml 并把其中/
    语种 profile 中的 llm_profile 名称展开成完整 LLMConfig。

说明：
    ``dtxml_merge`` 工作流状态已作为内置能力迁入
    :mod:`TiMi_HOK_Game_Translator.workflow.states`，无需在此导入即可被
    语种 profile 的 workflow 列表直接引用。
"""

from ._bootstrap import load_config_with_llm_profiles

__all__ = ["load_config_with_llm_profiles"]
