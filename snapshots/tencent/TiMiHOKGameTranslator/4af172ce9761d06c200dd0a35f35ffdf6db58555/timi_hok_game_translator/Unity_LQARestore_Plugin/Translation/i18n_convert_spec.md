# 译文接入转换 JSON 规范 (i18n_convert_spec)

> **通用规范**: 定义如何把 "译文总表 (CSV)" 转换为可被还原 / 本地化 / 比对工具消费的 **key→译文** JSON, 任何项目只要有一份 "键 → 多语种译文" 的源表, 都可套用本规范, 
> 本文以 **「某 Unity 项目的译文总表」× `LQARestore` (Unity 还原工程)** 作为 **应用案例**, 规范本身不绑定任何具体项目或引擎

## 1. 适用范围

- **通用目标**: 将 "译文总表" 转换为 "按语种分发的 key→译文 JSON", 供任意消费端在运行时按 key 取译文
- **消费端不限定**: 还原工程、像素比对、TMS 校验、人工核对等只要需要 "按 key 取译文" 的场景均适用
- **不绑定引擎 / 项目**: 键形态、语种集合、目录约定由具体项目决定; 本规范只规定 JSON 的 **结构与查表语义**

## 2. 输入: 译文总表 (CSV)

通用要求:

| 要求 | 说明 |
| ---- | ---- |
| 至少包含 | `键`、`原始文本`、一列或多列 `翻译文本 <语种>` |
| 键唯一 | 同一份表内 "键" 不重复 |
| 键形态 | 由项目决定 (命名键如 `ZSTips`, 或哈希键如 `#FF..#`); 转换时 **原样保留**, 不做格式转换 |
| 译文列 | 每语种一列; 可同时存在 "正式" 与 "在翻" 两版 (如 `en` / `en_tmp`), 转换时取正式列 |

**案例来源 (示例)**: 一份译文总表 CSV (示例约 157 MB), 列:
`键, 源文件, 输出文件, 原始文本, 翻译文本 en, 翻译文本 th, 翻译文本 en_tmp, 翻译文本 th_tmp`
它是该项目的 **译文唯一权威源**, 三类键均已收录

## 3. 输出: 转换 JSON 模板 Schema

顶层为纯数据文件 (规范语义见键类型、查表约定), 仅保留消费端与溯源所需的元信息:

```jsonc
{
  "schemaVersion": "1.0",  // 规范版本, 消费端据此判断兼容性
  "language": "en",  // 本文件语种, 一份一语种
  "source": {  // 来源指向 (仅数据, 不含叙述)
    "project": "<项目名>",
    "file": "<译文总表相对/绝对路径>",
    "translationColumn": "翻译文本 en"  // 本文件 translation 取自总表的哪一列
  },
  "keyTypes": ["stringKey", "hashFF", "hashFB"],  // 本项目声明的键类型集合
  "generatedAt": "…",
  "entries": {  // 核心: 扁平字典, 运行时 O(1) 查找
    "<key>": {
      "keyType": "<type>",
      "source": "<源文件>",
      "original": "<原始文本>",
      "translation": "<目标语言译文>"
    }
  }
}
```

**字段约束**

- `entries` 必须为 **对象(字典)** 非数组; key 即总表 "键" 列 **原样字符串** (含 `#` / `$` 等特殊字符)
- `key` 全局唯一
- `original` 必须保留: 用于构建 "原文→译文" 兜底表
- `original` / `translation` 的 **换行、制表等控制字符必须是真实字符**, 不得是字面转义序列 (如两字符的 `\n`), 若译文总表单元格用字面 `\n` 表示换行, 转换时必须先反转义为真实换行符再写入, 兜底路径按 `original` 与消费端文本做 **精确相等** 匹配, 而消费端 (如 UI dump 抓取的运行时文本) 持有的是真实换行; 转义层级不一致会导致匹配静默失败

## 4. 键类型 (keyTypes)

通用: 本规范 **不预设** 键类型枚举, 由具体项目在 `keyTypes` 中声明, `keyType` 仅用于消费端识别 key 形态, 不参与查表匹配

**案例** 声明三类:

| keyType | 形态 | 含义 |
| ----------- | ----------- | ----------- |
| `stringKey` | `ZSTips`、`ZhanShi`… | UI 文本命名键 (来自 `i18n.txt`) |
| `hashFF` | `#FFxxxxxxxxxxxxxx#` | 客户端侧哈希键 (实测 14 位十六进制; 运行时按 id 取串可能为 64 位, 二者属不同表示形态, 接表前需核对 dump 键与总表键同格式) |
| `hashFB` | `$FBxxxxxxxxxxxxxx$` | 服务端侧哈希键 (实测 14 位十六进制) |

## 5. 消费端接入约定 (通用查表语义)

任何消费端都应遵守以下语义 (与具体实现无关):

1. **查表主路径**: 按待还原文本的 key (命名键或哈希键) 匹配 `entries.key`, 命中则取 `translation` 填充
2. **兜底路径**: 若 key 未命中, 可用 `original` 构建 **原文→译文** 表二次匹配
3. **跳过规则**: 文本含源语言字符 / 纯数字 / 纯标点 / 纯空白 → 不翻译, 直接回原文
4. **未翻译标记**: 主路径与兜底均不命中 → 标记为未翻译 (如标红), 提示待补译

> **实现参考**: 一个典型的还原实现可采用与上述一致的优先级 (含源语言/数字跳过 → Key→译文 → 原文→译文兜底 → 未翻译标记), 可作为参考实现, 但非本规范强制

> **匹配前提**: 兜底路径为 **精确字符串相等**匹配, 要求 `original` 与消费端待匹配文本的转义层级一致 (换行等均为真实控制字符), 生成侧须在写入前完成反转义 (字段约束), 否则会因 `\n`(真实换行) 与字面 `\n`(反斜杠+n) 不等而漏配

## 6. Demo 片段

以下节选自案例产物 `i18n_en.demo.json`, 覆盖三类键:

```json
{
  "ZhanShi": { "keyType": "stringKey", "source": "i18n.txt", "original": "战士", "translation": "Fighter" },
  "#FFDAEEA48050734A#": { "keyType": "hashFF", "source": "Table/LineupTable.xlsx", "original": "示例：阵容推荐说明文本。", "translation": "Sample: lineup recommendation description text." },
  "$FB505CC795D662A5$": { "keyType": "hashFB", "source": "Mail/GlobalMailTable.xlsx", "original": "欢迎来到游戏世界", "translation": "Welcome to the game world" }
}
```

## 7. 应用案例: 某 Unity 项目 × LQARestore

将本规范落到具体项目:

- **源 (译文总表)**: 某项目的译文总表 CSV (示例路径), 三类键均已收录, en/th 译文齐备
- **产物 (符合本规范)**: `LQARestore/Translation/i18n_en.demo.json` (schemaVersion 1.0, en 语种, Demo 仅含 5 条样例)
- **消费端**: `LQARestore` 还原流程 `Core/Runtime/TextNodeBuilder.cs` 的 `ApplyText`; 当前回填原文 (`txt.text = textContent`), 接入时改为先查本表取 `translation`, 未命中回退 `original`/原文
- **目录约定**: 还原工程内新建 `Translation/` 模块, 与 `Core/`、`Entry/`、`Platform/` 平级, 存放各语种转换 JSON 与本文档
- **接入前待验证**: 在游戏内 dump 一个已知节点, 确认其 key (如 `XxxxLocalize.keyHash`, 格式 `#{id:X16}#`) 能与总表 / 本表的 key 同算法同格式匹配; 并确认 UI 文本 (命名键) 在 dump 中以命名键还是哈希形态出现, 这是把查表接到 `ApplyText` 前的唯一阻塞项

## 8. 批量生成与多语种扩展

- **批量生成**: 解析整份译文总表, 按 translationColumn 抽列, 输出为本规范 JSON, 大体量 (百 MB 级) 文件建议预生成、缓存, 避免还原时实时解析, 可参照本规范自行实现转换脚本, 并务必内置字面转义序列反转义 (把单元格里的字面 `\n` / `\r` / `\t` 还原为真实控制字符), 以满足字段约束与匹配前提
- **多语种**: 复制模板, 改 `language` 与 `source.translationColumn` (如 th → `翻译文本 th`), 一份一语种
- **可移植**: 换项目时只需替换 `source` (指向新总表) 与 `keyTypes` (声明新键形态), `entries` 结构与查表语义保持不变
