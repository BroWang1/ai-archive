# -*- coding: utf-8 -*-
"""
思考过程外露检测器（纯检测，无副作用，仅依赖标准库）

用途
----
翻译工具链在拿到模型返回后调用本模块；若判定为「思考过程外露」，
调用方丢弃本次结果并重新请求模型。

设计目标：**宁可漏判，不可误判**
------------------------------------
误判的代价远大于漏判：误判会把正常译文丢掉并重复请求，
而漏判只是少拦一条、可由人工兜底。因此：

1. 分级打分，弱信号单独出现不判定，必须与其他信号叠加；
2. 所有标记都做「源文反查」——若源文本身含该标记（例如游戏文案里
   本来就有 "Note:"、"Final:"），一律不计分；
3. 对易误伤词做了严格约束（详见 `_FALSE_POSITIVE_NOTES`）。

适配模型
--------
混元 Hy-MT2 系 A3B_MoE_RL_* 游戏翻译模型。该系列已知问题：
SFT 语料混入 bad pattern，RL 阶段被放大（reward hack），表现为
「先给出正确译文 → 随后自我点评/反复改写 → 直到 max_tokens 截断」。

实测触发率（5220 条 × 14 语种 = 73080 格）：
    中文源 0.003% ~ 0.016%
    英文源 0.017% ~ 0.019%
    英文源发生率约为中文源的 5 倍。

关键特征：注释块会跟随**目标语言**本地化，而非固定英文。
已覆盖：Note / Nota / Notă / Remarque / Hinweis / Catatan / Not /
        Примечание / ملاحظة / 注 / 주석 / หมายเหตุ / Ghi chú

用法
----
    from think_leak_detector import detect, is_leaked

    r = detect(translation, source_text=src, target_lang='ar')
    if r.leaked:
        logger.warning('思考过程外露，重试: %s', r.describe())
        # 重新请求模型

    # 或极简用法
    if is_leaked(translation, src):
        ...

命令行自检：
    python think_leak_detector.py --selftest
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

__all__ = ['detect', 'is_leaked', 'DetectionResult', 'DetectorConfig']

# ===========================================================================
# 一、判定阈值
# ===========================================================================

# 计分规则：命中项得分累加，总分 >= THRESHOLD_LEAKED 判定为外露。
SCORE_DECISIVE = 100   # 决定性证据，单条即可判定
SCORE_STRONG = 60      # 强证据，单条即可判定
SCORE_MEDIUM = 35      # 中等证据，需与其他证据叠加
SCORE_WEAK = 20        # 弱证据，仅作佐证，两条弱证据不足以判定
THRESHOLD_LEAKED = 60

# 短文本不参与长度比/重复度判断，避免「绿茵宝贝面饰」这类短词误伤
MIN_LEN_FOR_RATIO = 200
MIN_LEN_FOR_REPEAT = 400

# 译文/源文长度比超过该倍数视为异常膨胀。
# 实测各语种正常中位比：中文源 ≈ 1.0~3.5，英文源 ≈ 1.0~1.3，
# 取 6 倍留足余量（阿拉伯语、俄语等天然偏长）。
DEFAULT_RATIO_LIMIT = 6.0

# 各目标语种相对「中文源文」的正常长度比上限（粗粒度，宁松勿紧）
_RATIO_LIMIT_BY_LANG = {
    'en': 8.0, 'vi': 9.0, 'th': 7.0, 'id': 8.0, 'zh-Hant': 3.0,
    'fr': 9.0, 'de': 8.0, 'ru': 8.0, 'ja': 4.0, 'pt-BR': 9.0,
    'ko': 4.0, 'ar': 8.0, 'es': 9.0, 'tr': 8.0,
}
# 英文源（en → 小语种）时，源文已是英文，正常比值接近 1，收紧到 4 倍
_RATIO_LIMIT_EN_PIVOT = 4.0


# ===========================================================================
# 二、规则库
# ===========================================================================
#
# 命名约定：
#   _RE_*  -> 已编译正则
#   每条规则形如 (正则, 得分, 说明)
#
# 注意：凡是可能出现在正常游戏文案中的词，一律不单独使用，
#       必须加位置约束（行首/行尾）或结构约束（Markdown 粗体、括号块）。

# --- A. 决定性证据 ----------------------------------------------------------

# A1. 显式思考标签。任何情况下出现都是泄漏。
_RE_THINK_TAG = re.compile(r'</?think\s*>|</?thinking\s*>|</?reasoning\s*>', re.I)

# A2. 本地化注释块。模型自评时固定写成 `*(Note: ...)` / `*(Catatan: ...)`，
#     Markdown 星号 + 左括号 + 注释词 的组合在正常译文中几乎不可能出现。
_NOTE_WORDS = (
    r'Note|Nota|Notă|Noto|Remarque|Hinweis|Anmerkung|Catatan|Not|Nota Bene|'
    r'Примечание|Прим|ملاحظة|ملحوظة|注|註|注记|注記|주석|참고|หมายเหตุ|Ghi chú|Lưu ý'
)
_RE_NOTE_BLOCK = re.compile(
    r'\*\s*\(\s*(?:' + _NOTE_WORDS + r')\b'      # *(Note  /  * (Catatan
    r'|\(\s*(?:' + _NOTE_WORDS + r')\s*[:：]',   # (Note:  /  (Примечание:
    re.I | re.U,
)

# A3. Markdown 粗体包裹的「最终答案」标题——纯粹的元叙述结构。
_RE_FINAL_HEADER = re.compile(
    r'\*\*\s*(?:Final|Final\s+Answer|Final\s+Translation|Final\s+Version|'
    r'Correct(?:ed)?\s+Translation|Translation|Answer|Output|Result)\b[^*\n]{0,40}\*\*'
    r'|\*\*\s*(?:Note|Correction|Hinweis|Nota|Примечание)\s*[:：]?\s*\*\*',
    re.I,
)

# A4. 输出终止标记。模型"写完了"的自我声明。
_RE_END_MARKER = re.compile(
    r'^\s*(?:\[End\]|\[END\]|End of (?:output|translation|text)\.?|'
    r'<\s*/?\s*end\s*>)\s*$',
    re.M,
)

# A5. 显式自我纠错标题（行首 + 冒号，排除正文中的 "correction" 名词用法）
_RE_CORRECTION_HEADER = re.compile(
    r'^\s*(?:\*+\s*)?(?:Correction|Corrected|Revised|Rewritten|Update)\s*[:：]',
    re.M,
)

_DECISIVE_RULES: List[Tuple[re.Pattern, int, str]] = [
    (_RE_THINK_TAG, SCORE_DECISIVE, '显式思考标签(<think>)'),
    (_RE_NOTE_BLOCK, SCORE_DECISIVE, '本地化注释块(*(Note/Catatan/ملاحظة...))'),
    (_RE_FINAL_HEADER, SCORE_DECISIVE, 'Markdown最终答案标题(**Final**)'),
    (_RE_END_MARKER, SCORE_DECISIVE, '输出终止标记([End]/End of output)'),
    (_RE_CORRECTION_HEADER, SCORE_DECISIVE, '自我纠错标题(Correction:)'),
]

# --- B. 强证据：第一人称元叙述 ----------------------------------------------
#
# 这些短语的主语是"模型自己"，在游戏文案（角色台词、道具描述、UI）中
# 出现的概率极低。但仍做了收紧：
#   * "I'll" 后必须接提交/撰写类动词，排除台词 "I'll go look for quests"
#   * "put" 必须带 "it/that/this"，排除叙事 "I will put an end to this"
#   * "Let me" 后必须接复核类动词，排除台词 "Let me help you"

_RE_FIRST_PERSON_META = re.compile(
    r"\bI(?:'ll| will| am going to| shall)\s+"
    r"(?:just\s+)?(?:go\s+with|stick\s+with|stick\s+to|submit|finalize|"
    r"provide\s+(?:the|that|this|it)|write\s+(?:that|this|it)\b|"
    r"put\s+(?:that|this|it)\b|use\s+(?:that|this|it|the)|"
    r"keep\s+(?:that|this|it)|accept\s+(?:that|this|it)|output\s+(?:that|this|it))\b"
    r"|\bI\s+(?:submit|accept)\s+(?:that|this|it)\b"
    r"|^\s*I\s+submit\.?\s*$"
    r"|\bLet\s+me\s+(?:re-?check|recheck|verify|re-?read|reconsider|re-?examine|"
    r"try\s+again|correct\s+(?:that|this|it)|fix\s+(?:that|this|it)|redo|rewrite)\b",
    re.M,
)

# B1b. "But wait" / "Wait—" 单独出现时可能是角色台词
#      （实测误判："Alright, all set this time. Wait—I... I forgot to lock the door..."），
#      故降为中等证据，必须与其他信号叠加才判定。
_RE_WAIT_HESITATION = re.compile(
    r"(?:^|[.!?;:—\-\n]\s*)But\s+wait\b"
    r"|\bWait\s*[,—–-]\s*(?:the\s+(?:original|source|user)|that'?s\s+not|"
    r"no\s*[,.]|actually|I\s+(?:need|should|must|think))\b",
    re.M | re.I,
)

# B2. 谈论"原文/译文/用户指令"——把翻译任务本身当成话题。
_RE_TASK_TALK = re.compile(
    r"\boriginal\s+(?:text|Chinese|English|sentence|phrase|string)\s+"
    r"(?:says|said|is|was|has|have|uses|reads|seems|appears|contains)\b"
    r"|\bthe\s+(?:translat(?:ion|ed\s+\w+)|output|result)\s+(?:is|should|would|must)\s+"
    r"(?:be|now|correct|final|as)\b"
    r"|\btranslated\s+result\s+is\b"
    r"|\bIf\s+the\s+user\s+(?:intended|meant|wants|wanted|prefers)\b"
    r"|\b(?:per|following|as\s+per)\s+(?:the\s+)?user'?s?\s+instructions?\b"
    r"|\bthe\s+user'?s?\s+(?:instruction|request|requirement)s?\b",
    re.I,
)

# B3. 本地化的「最终版本是：」句式（俄/阿/德/法/西/葡/印尼）
_RE_FINAL_LOCALIZED = re.compile(
    r'^\s*(?:Final|Итог(?:овый)?\s*(?:перевод|вариант)|'
    r'الترجمة\s+النهائية|Endgültige\s+Übersetzung|Traduction\s+finale|'
    r'Traducción\s+final|Tradução\s+final|Terjemahan\s+akhir)\s*[:：]\s*$',
    re.M | re.I,
)

_STRONG_RULES: List[Tuple[re.Pattern, int, str]] = [
    (_RE_FIRST_PERSON_META, SCORE_STRONG, '第一人称元叙述(I\'ll go with/Let me recheck)'),
    (_RE_TASK_TALK, SCORE_STRONG, '谈论原文或用户指令(original text says/user instruction)'),
    (_RE_FINAL_LOCALIZED, SCORE_STRONG, '本地化最终版本标题'),
]

# --- C. 中等证据 ------------------------------------------------------------

# C1. 中文思考词（源自仓库 json_translation_main.py 的 THINKING_KEYWORDS，
#     但**大幅收紧**：原版含"注""即""可能""需要"等单字/常用词，
#     在游戏文案中误报极高，此处只保留元叙述性强的多字组合，
#     且仅在「目标语种非中日繁」时启用）。
_RE_CN_META = re.compile(
    r'原文(?:的意思|中|是指|应该|可能|似乎|有误|写作)'
    r'|译文(?:应该|应为|改为|如下|为[:：])'
    r'|翻译(?:成|为)?(?:如下|结果如下)'
    r'|这里(?:应该|需要|可能)(?:翻译|译|改)'
    r'|(?:最终|最后)(?:的)?(?:译文|翻译|版本|答案)\s*[:：]'
    r'|注意[:：]\s*(?:原文|译文|这里|此处)'
    r'|(?:我|咱们)(?:会|将|应该|需要)(?:使用|采用|保留|改成)'
)

# C2. 译文结尾处的括号说明块（紧贴结尾、以括号包裹、含注释词）
_RE_TRAILING_PAREN_NOTE = re.compile(
    r'[\n\r]\s*[（(][^（()）]{0,20}(?:' + _NOTE_WORDS + r')\b[^（()）]{0,400}[）)]\s*$',
    re.I | re.U,
)

_MEDIUM_RULES: List[Tuple[re.Pattern, int, str]] = [
    (_RE_TRAILING_PAREN_NOTE, SCORE_MEDIUM, '结尾括号注释块'),
    (_RE_WAIT_HESITATION, SCORE_MEDIUM, '犹豫式转折(But wait/Wait—)'),
]

# --- D. 结构性弱证据（长度膨胀、自我重复）在函数内动态计算 ------------------

_FALSE_POSITIVE_NOTES = """
以下词**故意不作为独立判据**，因为实测会误伤正常游戏文案：
  actually   -> "is actually the most distinctive form of drama"
  hmm / Hmm  -> 角色台词拟声词 "Ha hmm... He said your head..."
  the user   -> 技能描述 "the user's damage output is reduced by 30%"
  wait       -> 台词 "wait for me"
  final:     -> 西语/葡语正文 "el efecto final:" / "o efeito final:"
  Note:      -> 原文「注意：」的正常翻译（已由源文反查排除）
  explanation / instruction -> 游戏帮助文案高频词
"""


# ===========================================================================
# 三、配置与结果结构
# ===========================================================================

@dataclass
class DetectorConfig:
    """检测器配置。默认值已按「宁漏勿误」调校，一般无需修改。"""
    threshold: int = THRESHOLD_LEAKED
    enable_length_ratio: bool = True
    enable_repetition: bool = True
    enable_cn_meta: bool = True
    ratio_limit: Optional[float] = None       # None -> 按语种自动取
    min_len_for_ratio: int = MIN_LEN_FOR_RATIO
    min_len_for_repeat: int = MIN_LEN_FOR_REPEAT
    # 目标语种为这些时，跳过中文元叙述检测（译文本身就是中日文）
    cn_meta_skip_langs: Tuple[str, ...] = (
        'zh-Hant', 'zh-Hans', 'zh', 'ja', '繁体中文', '日语',
        'Traditional Chinese', 'Japanese',
    )


@dataclass
class Evidence:
    rule: str
    score: int
    sample: str = ''


@dataclass
class DetectionResult:
    leaked: bool
    score: int
    evidences: List[Evidence] = field(default_factory=list)
    length_ratio: Optional[float] = None
    text_len: int = 0
    source_len: int = 0

    @property
    def confidence(self) -> str:
        if self.score >= SCORE_DECISIVE:
            return 'high'
        if self.score >= THRESHOLD_LEAKED:
            return 'medium'
        return 'none'

    @property
    def reasons(self) -> List[str]:
        return [e.rule for e in self.evidences]

    def describe(self) -> str:
        if not self.evidences:
            return '未检出'
        parts = []
        for e in self.evidences:
            s = f'{e.rule}(+{e.score})'
            if e.sample:
                s += f' 样例={e.sample!r}'
            parts.append(s)
        head = f'score={self.score} conf={self.confidence} len={self.text_len}'
        if self.length_ratio is not None:
            head += f' ratio={self.length_ratio:.1f}'
        return head + ' | ' + '; '.join(parts)

    def __bool__(self) -> bool:
        return self.leaked


# ===========================================================================
# 四、内部工具
# ===========================================================================

def _norm(s) -> str:
    if s is None:
        return ''
    if not isinstance(s, str):
        # 容忍 float('nan') / None 等脏数据
        try:
            import math
            if isinstance(s, float) and math.isnan(s):
                return ''
        except Exception:  # pylint: disable=broad-except
            pass
        s = str(s)
    return s


def _strip_markup(s: str) -> str:
    """去掉富文本标签与占位符，避免标签内容干扰长度与重复判断。"""
    s = re.sub(r'<[^<>\n]{0,80}>', '', s)
    s = re.sub(r'\{[^{}\n]{0,80}\}', '', s)
    s = re.sub(r'%[sd]|\\n|_x000D_', ' ', s)
    return s


def _in_source(sample: str, source_norm: str) -> bool:
    """源文反查：若该片段在源文中已存在，则不是模型添加的元叙述。"""
    if not source_norm or not sample:
        return False
    return sample.strip().lower() in source_norm


def _match_rules(text: str, source_norm: str,
                 rules: List[Tuple[re.Pattern, int, str]]) -> List[Evidence]:
    out = []
    for pat, score, name in rules:
        m = pat.search(text)
        if not m:
            continue
        sample = m.group(0).strip()
        if len(sample) > 60:
            sample = sample[:60] + '…'
        if _in_source(sample, source_norm):
            continue
        out.append(Evidence(name, score, sample))
    return out


def _repetition_ratio(text: str, min_len: int = MIN_LEN_FOR_REPEAT) -> float:
    """
    自我重复度：模型反复改写时，同一段落会出现多次。
    返回最长重复片段占全文的比例（0~1）。

    min_len 可下调，用于「源文反查」——源文往往比译文短，
    但只要它自身就是重复文案，译文的重复就是忠实翻译。
    """
    s = re.sub(r'\s+', ' ', text).strip()
    n = len(s)
    if n < min_len:
        return 0.0
    seg_len = max(40, min(240, n // 4))
    best = 0.0
    # 密集采样：按 1/8 文长步进扫描，覆盖「首段不同但正文重复」的情况
    step = max(20, seg_len // 2)
    for start in range(0, max(1, n - seg_len), step):
        seg = s[start:start + seg_len]
        if len(seg) < seg_len:
            break
        cnt = s.count(seg)
        if cnt >= 2:
            best = max(best, (cnt * seg_len) / n)
            if best >= 0.9:
                break
    return best


def _ratio_limit_for(target_lang: Optional[str], src_lang: str,
                     cfg: DetectorConfig) -> float:
    if cfg.ratio_limit is not None:
        return cfg.ratio_limit
    if src_lang == 'en':
        return _RATIO_LIMIT_EN_PIVOT
    if target_lang and target_lang in _RATIO_LIMIT_BY_LANG:
        return _RATIO_LIMIT_BY_LANG[target_lang]
    return DEFAULT_RATIO_LIMIT


def _looks_truncated(text: str) -> bool:
    """被 max_tokens 截断的典型特征：结尾没有任何终止标点。"""
    tail = text.rstrip()
    if len(tail) < MIN_LEN_FOR_RATIO:
        return False
    last = tail[-1]
    if last in '.!?。！？」』"\'）)]】>…·:：;；,，':
        return False
    return unicodedata.category(last)[0] in ('L', 'N')


# ===========================================================================
# 五、主入口
# ===========================================================================

def detect(translation,
           source_text=None,
           target_lang: Optional[str] = None,
           src_lang: str = 'zh',
           config: Optional[DetectorConfig] = None) -> DetectionResult:
    """
    检测译文中是否外露了模型的思考过程。

    Args:
        translation : 模型返回的译文（必填）
        source_text : 本次请求送进去的源文。强烈建议传入——
                      用于「源文反查」，可显著降低误判。
                      英文源（en→小语种）时请传英文源文，而非中文原文。
        target_lang : 目标语种代码，如 'ar' / 'pt-BR'。用于选择长度比阈值
                      及决定是否启用中文元叙述检测。
        src_lang    : 'zh'（中文源）或 'en'（英文源/以英文为轴）。
        config      : 可选，覆盖默认阈值。

    Returns:
        DetectionResult；`result.leaked` 为 True 时建议丢弃并重试。
    """
    cfg = config or DetectorConfig()
    text = _norm(translation)
    source = _norm(source_text)

    res = DetectionResult(leaked=False, score=0, text_len=len(text),
                          source_len=len(source))
    if not text.strip():
        return res

    source_norm = source.lower()
    evidences: List[Evidence] = []

    # --- A/B/C 文本规则 ---
    evidences += _match_rules(text, source_norm, _DECISIVE_RULES)
    evidences += _match_rules(text, source_norm, _STRONG_RULES)
    evidences += _match_rules(text, source_norm, _MEDIUM_RULES)

    # 中文元叙述：仅当目标语种不是中/日时才有意义
    if cfg.enable_cn_meta and (target_lang not in cfg.cn_meta_skip_langs):
        m = _RE_CN_META.search(text)
        if m and not _in_source(m.group(0), source_norm):
            evidences.append(Evidence('中文元叙述', SCORE_STRONG, m.group(0)[:60]))

    # --- D. 结构性证据 ---
    body = _strip_markup(text)
    src_body = _strip_markup(source)

    if cfg.enable_length_ratio and source and len(body) >= cfg.min_len_for_ratio:
        ratio = len(body) / max(len(src_body), 1)
        res.length_ratio = round(ratio, 2)
        limit = _ratio_limit_for(target_lang, src_lang, cfg)
        if ratio >= limit * 2:
            evidences.append(Evidence(
                f'长度异常膨胀(>{limit * 2:.0f}x)', SCORE_STRONG, f'{ratio:.1f}x'))
        elif ratio >= limit:
            evidences.append(Evidence(
                f'长度偏大(>{limit:.0f}x)', SCORE_MEDIUM, f'{ratio:.1f}x'))

    if cfg.enable_repetition and len(body) >= cfg.min_len_for_repeat:
        rep = _repetition_ratio(body)
        # 源文反查：源文本身就是重复文案（游戏里常见的复制粘贴条目）时，
        # 译文跟着重复属于忠实翻译，不计分。
        # 源文通常比译文短，故放宽长度门槛（100 字即可参与反查）。
        src_rep = _repetition_ratio(src_body, min_len=100) if src_body else 0.0
        if src_rep >= 0.25:
            rep = 0.0
        if rep >= 0.5:
            evidences.append(Evidence('大段自我重复', SCORE_STRONG, f'{rep:.0%}'))
        elif rep >= 0.25:
            evidences.append(Evidence('存在自我重复', SCORE_MEDIUM, f'{rep:.0%}'))

    # 截断本身不构成泄漏（长源文正常会被截断），仅在已有其他证据时加权
    if evidences and _looks_truncated(text):
        evidences.append(Evidence('疑似被max_tokens截断', SCORE_WEAK, ''))

    res.evidences = evidences
    res.score = sum(e.score for e in evidences)
    res.leaked = res.score >= cfg.threshold
    return res


def is_leaked(translation, source_text=None, target_lang: Optional[str] = None,
              src_lang: str = 'zh') -> bool:
    """detect() 的布尔简化版。"""
    return detect(translation, source_text, target_lang, src_lang).leaked


# ===========================================================================
# 六、自检用例
# ===========================================================================

# (译文, 源文, 语种, 源语言, 期望是否判定为外露, 说明)
_SELFTEST_CASES = [
    # ---------- 应判定为外露（取自实测）----------
    ('زينة وجه محبوبة كرة القدم  \n*(ملاحظة: النص الأصلي يحتوي على...)',
     '绿茵宝贝面饰', 'ar', 'zh', True, '阿拉伯语本地化注释块'),
    ('Dekorasi Wajah  \n*(Catatan: Terjemahan ini...)',
     'Face Decor', 'id', 'en', True, '印尼语注释块'),
    ('Перевод текста  \n*(Примечание: в последней части...)',
     'Some text', 'ru', 'en', True, '俄语注释块'),
    ('Die Blätter können als Medizin verwendet werden.\n'
     '*(Correction: The original text says "Stealth Radish")\n'
     "I'll just submit that.\n\n**Final Answer:**\nDie Blätter...",
     'The leaves can be used as medicine.', 'de', 'en', True, '德语多重证据'),
    ('Translation here.\n\nI submit.\n\nBut wait, the original text says something else.',
     'Source here.', 'fr', 'en', True, '第一人称元叙述'),    ('<think>let me translate this</think>Bonjour',
     'Hello', 'fr', 'en', True, '显式think标签'),
    ('Some output\n\n[End]\n', 'Some input', 'es', 'en', True, '输出终止标记'),
    ('Texte traduit.\n**Final:**\nTexte traduit.',
     'Translated text.', 'fr', 'en', True, 'Markdown最终答案标题'),

    # ---------- 不应判定（历史误判案例）----------
    ('Ouling theater is actually the most distinctive form of drama in our Dragon Kingdom.',
     '偶灵戏可是我们龙之国最有特色的戏剧形式呢。', 'en', 'zh', False,
     'actually 出现在正文'),
    ('The user\'s damage output is reduced by 30% while the shield is active.',
     '激活期间该单位造成的伤害降低30%。', 'en', 'zh', False,
     'the user 指游戏角色'),
    ('Cuantos más compañeros tengan activado el Modo de Alerta, '
     'mayor será el efecto final:\n\n- Recibes un 10% adicional.',
     'The more teammates have Alert Mode activated, the greater the final effect:'
     '\n\n- You receive an additional 10%.', 'es', 'en', False,
     '西语正文 efecto final:'),
    ('... Ha hmm... He said your head... Aaah hmm, ha... got a pretty hard hit...',
     '就前些天……呣……我刚和那个小嫩枝……啊啦呣……', 'en', 'zh', False,
     'hmm 为拟声词'),
    ('You go gain experience, and I\'ll go look for quests. Let\'s meet up later!',
     '你去历练，我去找任务，晚些时候集合吧！', 'en', 'zh', False,
     "I'll go look 为角色台词"),
    ('Shipment from Fishing Village:\n\nFive cases of fish\n\n'
     'Note: Rebels have been sighted recently.',
     '渔村发往云根镇：\n\n优质梦影鱼 五箱\n\n注意：近期有破门生出没。', 'en', 'zh', False,
     '原文含「注意：」，译文 Note: 属正常翻译'),
    ('Soccer Sweetheart Face Decor', '绿茵宝贝面饰', 'en', 'zh', False, '正常短译文'),
    ('Let me help you with that, traveler.', '让我来帮你吧，旅行者。', 'en', 'zh', False,
     'Let me help 为台词'),
    ('Please wait for the correction to be applied.',
     '请等待修正生效。', 'en', 'zh', False, 'correction 为正文名词'),
    ('Alright, all set this time. Wait—I... I forgot to lock the door...',
     '行，这次都妥了。不对，我......我忘记锁门了......', 'en', 'zh', False,
     'Wait— 为角色台词停顿'),
    ('Tiền tệ kiếm được thông qua Battle Pass. ' * 6,
     '通过战斗通行证赚取的货币。' * 6, 'vi', 'zh', False,
     '源文本身重复，译文跟随重复属忠实翻译'),
    ('큰플라밍고는 유럽, 중동, 아시아에 분포하는 대형 철새이다. ' * 3,
     '大红鹳是一种大型候鸟，遍布于欧洲、中东地区、亚洲。' * 3, 'ko', 'zh', False,
     '正常长文本，比例正常'),
    ('', '源文', 'en', 'zh', False, '空译文'),
    (None, '源文', 'en', 'zh', False, 'None 译文'),
]


def _selftest() -> int:
    passed = failed = 0
    print('=' * 78)
    print('think_leak_detector 自检')
    print('=' * 78)
    for text, src, lang, slang, expect, desc in _SELFTEST_CASES:
        r = detect(text, src, lang, slang)
        ok = (r.leaked == expect)
        flag = 'PASS' if ok else 'FAIL'
        passed, failed = (passed + 1, failed) if ok else (passed, failed + 1)
        print(f'[{flag}] 期望={"外露" if expect else "正常"} '
              f'实际={"外露" if r.leaked else "正常"} | {desc}')
        if not ok or r.evidences:
            print(f'        {r.describe()}')
    print('-' * 78)
    print(f'通过 {passed} / {passed + failed}，失败 {failed}')
    return 0 if failed == 0 else 1


if __name__ == '__main__':
    import sys
    if '--selftest' in sys.argv:
        sys.exit(_selftest())
    print(__doc__)
    print(_FALSE_POSITIVE_NOTES)
    print('运行 python think_leak_detector.py --selftest 执行自检')
