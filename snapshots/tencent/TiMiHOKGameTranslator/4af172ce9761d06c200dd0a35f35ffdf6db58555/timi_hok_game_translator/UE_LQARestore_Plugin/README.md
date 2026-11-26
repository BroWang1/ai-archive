# LQARestore 插件

![License](https://img.shields.io/badge/license-Apache%202.0-blue)

## 项目简介

LQARestore 是一个虚幻引擎 (Unreal Engine) 工程, 核心功能通过 `LQARestore` 插件实现

### 核心功能

可以读取包含控件信息的 UI 数据 (JSON格式), 动态重构并还原 UI 界面, 支持多语言文本替换, 用于本地化质量保证 (Localization Quality Assurance, LQA) 测试

### 前置依赖: 采集端 LQATool

本插件是 **还原端**, 还原所需的 UI 快照数据 (`LQA_Snapshot_*.json`, 即 dump) 由 **采集端 LQATool** 生成, 两者需配合使用:

| 插件 | 作用 |
| --- | --- |
| LQATool (采集端) | 运行时导出 Widget 树为 JSON 快照 (含布局 / 样式 / 文本) |
| LQARestore (还原端, 本插件) | 读取快照并还原 UI、替换多语言文本 |

> 没有采集端生成的 dump 数据, 还原端无从还原, 接入前请先确保能通过 LQATool 生成 dump 快照 (采集产物位于 `{工程}/Saved/LQA/<时间戳_WBP名>/LQA_Snapshot_*.json`, 采集方式见 LQATool 的 README)

### 仓库组成

#### LQARestore

- **功能**: 还原 UI 在多语言下的实际表现, 以用于 LQA 测试, 保障本地化质量
- **代码规范**: 遵循 UE C++ 代码风格规范 (缩进、命名、反射宏使用等与引擎保持一致)

#### 目录结构

本仓库是一个 UE 插件仓库, 仓库根目录下有一层 `Plugins/` (含还原插件 `LQARestore`), 接入时把该插件目录拷贝到目标工程的 `Plugins/` 下

```
UE_LQARestore_Plugin/                                # 仓库根
├── Plugins/
│   └── LQARestore/                                  # 还原插件 (本仓库主体)
└── README.md

LQARestore/                                          # 插件根目录 (即 Plugins/LQARestore)
├── LQARestore.uplugin                               # 插件描述文件 (依赖 Paper2D)
├── Config/
│   └── LQARestore.ini                               # LQA 还原工具配置 (Host / Authorization)
├── Resources/
│   └── Icon128.png                                  # 插件图标
├── README.md                                        # 插件说明文档
└── Source/
    └── LQARestore/                                  # 插件主模块
        ├── LQARestore.Build.cs                      # 模块构建脚本
        ├── Private/                                 # 私有实现文件
        │   ├── Core/                                # 核心功能模块
        │   │   ├── ConfigManager.cpp                # 配置管理器
        │   │   ├── FileManager.cpp                  # 文件管理器
        │   │   ├── LQAContainerWidget.cpp           # LQA 容器控件
        │   │   ├── LQARestoreManager.cpp            # LQA 还原管理器
        │   │   ├── RestoreWindowProxy.cpp           # 还原窗口代理
        │   │   ├── RestoreWindowUtils.cpp           # 还原窗口工具
        │   │   ├── RootObjWidget.cpp                # 根对象控件
        │   │   └── TaskManager.cpp                  # 任务管理器
        │   ├── Utils/                               # 工具类集合
        │   │   ├── DataConverterUtils.cpp           # 数据转换工具
        │   │   ├── GeometryUtils.cpp                # 几何工具
        │   │   ├── ImageRenderUtils.cpp             # 图像渲染工具
        │   │   ├── JsonUtils.cpp                    # JSON 处理工具
        │   │   ├── SlateBrushUtils.cpp              # Slate 笔刷工具
        │   │   ├── TextureUtils.cpp                 # 纹理工具
        │   │   ├── HttpUtils/                       # HTTP 请求工具
        │   │   │   ├── HttpRequestConfig.cpp        # HTTP 配置 (从插件 Config/ 读取)
        │   │   │   └── HttpRequestHelper.cpp        # HTTP 请求辅助
        │   │   └── TranslationUtils/                # 翻译工具
        │   │       ├── LoaderUtils.cpp              # 翻译加载
        │   │       └── ValidatorUtils.cpp           # 翻译校验
        │   ├── WidgetSlots/                         # 控件/槽位转 JSON 模块
        │   │   ├── Core/                            # 核心转换系统
        │   │   │   ├── RestoreWidget2JsonFactory.cpp  # 还原控件转 JSON 工厂
        │   │   │   ├── Slot2JsonFactory.cpp         # 槽位转 JSON 工厂
        │   │   │   ├── Slot2JsonInterface.cpp       # 槽位转 JSON 接口
        │   │   │   ├── Widget2JsonInterface.cpp     # 控件转 JSON 接口
        │   │   │   └── WidgetDefines.cpp            # 控件定义
        │   │   ├── Slots/                           # 各类槽位实现 (所有的 LQA_*Slot2Json)
        │   │   │   ├── LQA_BorderSlot2Json.cpp
        │   │   │   ├── LQA_CanvasPanelSlot2Json.cpp
        │   │   │   ├── LQA_HorizontalBoxSlot2Json.cpp
        │   │   │   ├── LQA_StackBoxSlot2Json.cpp
        │   │   │   ├── LQA_WindowTitleBarAreaSlot2Json.cpp
        │   │   │   └── ...                          # Button/Grid/Overlay/SafeZone/ScaleBox/WrapBox 等
        │   │   └── Widgets/                         # 各类控件实现 (所有的 LQA_*2Json, 另含 LQA_ListViewEntry)
        │   │       ├── LQA_Button2Json.cpp
        │   │       ├── LQA_TextBlock2Json.cpp
        │   │       ├── LQA_Image2Json.cpp
        │   │       ├── LQA_UserWidget2Json.cpp
        │   │       ├── LQA_ListView2Json.cpp        # 定义 ListView / TileView / TreeView 三个转换器
        │   │       ├── LQA_ListViewEntry.cpp
        │   │       ├── LQA_DynamicEntryBox2Json.cpp
        │   │       ├── LQA_StackBox2Json.cpp
        │   │       ├── LQA_InvalidationBox2Json.cpp
        │   │       ├── LQA_WindowTitleBarArea2Json.cpp
        │   │       ├── LQA_ExpandableArea2Json.cpp
        │   │       ├── LQA_PostBufferUpdate2Json.cpp
        │   │       └── ...                          # RichText/CheckBox/EditableText/ProgressBar 等
        │   ├── WidgetTree/                          # 控件树模块
        │   │   └── LQAWidgetNode.cpp                # LQA 控件节点
        │   ├── LQABase.cpp                          # LQA 基类实现
        │   └── LQARestore.cpp                       # 插件主模块入口
        └── Public/                                  # 公共头文件 (结构与 Private 对应)
            └── [与 Private 目录对应的 .h 文件]
```

### 工作模式

- **本地模式**: 读取本地目录下的多份 JSON 数据文件, 逐个加载并还原 UI 界面
- **远端模式**: 基于任务驱动, 持续从远端获取任务数据, 并还原任务中包含的 UI 数据

该工具帮助 QA 团队快速验证 UI 在不同语言环境下的实际表现, 无需手动切换游戏语言或重新打包

### 扩展说明

插件具备基础控件还原能力, 针对实际游戏项目, 需要按需增加自定义控件和 Slot 类型到 `WidgetSlots` 目录, 参考现有的 `LQA_Button2Json`、`LQA_ButtonSlot2Json` 等实现示例

---

## 接入插件

### 1. 拷贝插件到工程

将 `LQARestore` 插件目录完整拷贝到目标 UE 工程的 `Plugins/` 目录下:

```
YourProject/
└── Plugins/
    └── LQARestore/     # LQA 还原工具插件 (模块名 LQARestore)
```

> 注意: 插件当前仅支持 **Win64** 平台 (见 `LQARestore.uplugin` 的 `SupportedTargetPlatforms`)

### 2. 启用插件与引擎依赖

1. 插件 `LoadingPhase` 为 `Default`、`Type` 为 `Runtime`, 拷贝后通常会被自动识别, 可在编辑器 **Edit → Plugins** 中确认 `LQARestore` 已勾选启用
2. 确认工程启用了插件所需的引擎插件, 重点是 **Paper2D** (`Edit → Plugins → 2D → Paper2D`)
3. 其余所需引擎模块 (`UMG`、`Slate`、`Json`、`HTTP`、`zlib`、`MediaAssets`、`RHI`、`RenderCore` 等) 已在 `LQARestore.Build.cs` 中声明, 无需手动添加

### 3. 重新生成工程并编译

1. 右键 `YourProject.uproject` → **Generate Visual Studio project files**
2. 使用 Rider 或 Visual Studio 打开解决方案, 编译 **Development Editor** 目标
3. 编译成功后启动编辑器, 日志中出现 `LQARestoreManager initializing` 即表示插件已正常加载

### 4. 准备运行所需资源

| 资源 | 路径 | 说明 |
| --- | --- | --- |
| 翻译文件 | `Plugins/LQARestore/LQALocalization/GameLocalizationExport_{lang}.json`、`Text_Translations_{lang}.json` | 多语言文本替换数据，`{lang}` 如 `en`、`ja`、`ko` 等 |

> 译文示例可直接参考 `Plugins/LQARestore/LQALocalization/` 下的 `*_en.json`、`*_ja.json`、`*_ko.json` (仓库已内置英/日/韩三套译文)

### 5. 配置文件 (远端模式必需)

在插件的 `Config/` 目录下创建 `LQARestore.ini`, 填入远端服务地址与鉴权信息:

```ini
[HttpConfig]
Host=xx.xx.xx.xx:xx
Authorization=xxxxxxxxxx
```

> `Host` 无需带 `http://` 前缀, 程序会自动补全; 本地模式可不配置此文件

### 6. 运行与模式说明

`LQARestore` 的核心 `ULQARestoreManager` 是 `UGameInstanceSubsystem`, 会随 GameInstance 启动自动运行 (PIE 或打包运行均可), 延迟约 1 秒后开始工作

- **本地模式 (默认, `JobId=0`)**: 自动递归扫描 `{项目}/Saved/LQA/` 目录下的 JSON 数据文件, **每 25 秒处理一份** (`LocalJobInterval`), 逐个还原 UI, 全部处理完后停止定时器; 直接 PIE 运行即可
- **远端模式 (`JobId` 非 0)**: 通过命令行传入任务参数, 走 HTTP 从远端拉取任务数据

> 模式仅由 `JobId` 决定: 等于 `0` 为本地模式, 非 `0` 为远端模式, 参数均为 `Key=Value` 形式, `-` 前缀可省略, 带空格的路径需加引号

**本地模式示例**

编辑器下直接点 Play 即可, 无需命令行; 打包后运行:

> **关于 `YourProject.exe`**
> 
> 下文命令中的 `YourProject.exe` 只是 **占位示例**, 并非真实文件名, 它 **不会出现在工程根目录** (工程根目录只有 `.uproject`、`Source/`、`Intermediate/` 等开发态文件), 
> 该 exe 仅在对工程执行 **打包 (Package Project)** 后才会生成, 实际名称为你的工程名, 路径类似:
> `<打包输出目录>/Windows/{工程名}/Binaries/Win64/{工程名}.exe`
> 运行时把 `YourProject.exe` 替换为该文件 (如 `UE5Demo.exe`) 即可, 若只是本地测试还原, 无需打包, 直接在编辑器点 Play 更方便

```bash
# 使用默认语言 (LAN_EU_EN)
YourProject.exe

# 指定语言 (决定加载哪份翻译文件)
YourProject.exe -Language=LAN_JP_JP
```

> **本地模式如何指定还原哪一份 Dump 数据?**
> 
> 本地模式不支持通过命令行指定单份数据, 它会 **递归扫描 `{项目}/Saved/LQA/` 下的所有 `*.json` 并逐个还原** (文件名去掉扩展名即作为 `DataId`, 同时用于结果目录命名 `Restore_{DataId}_{语言}`), 
> 若只想还原某一份, 只能通过控制目录内容实现:
> - 只在 `Saved/LQA/` 下保留你要还原的那一份 json
> - 或将其余 json 移出 `Saved/LQA/` 整个目录树 (递归扫描会包含所有子目录)
>
> 注意: `IsCover=true` + `BaseDataId`/`BaseDataFilePath` 是 "基准数据对比" 用途, 会把基准数据插入队列最前, **并非** 用于筛选单个还原目标, 不要混用

**本地模式产物位置**

每还原一份数据, 会在工程 `Saved/` 下生成一个独立结果目录:

```
{项目}/Saved/LQAResult/Restore_{DataId}_{语言}/
├── screenshot.png     # 还原后 UI 的控件截图
└── check_info.json    # 校验信息 (控件角点等)
```

- `{DataId}` 为 `Saved/LQA/` 下 json 文件名去掉扩展名, `{语言}` 为运行时语言 (如 `LAN_EU_EN`)
- 编辑器 PIE 运行时, `{项目}/Saved/` 即工程的 `Saved/` 目录; 打包运行时则是打包产物自身的 `Saved/` 目录
- **本地模式不上传、不清理产物**, 结果会一直保留在本地 (远端模式上传成功后会自动删除该目录)
- 若还原过程涉及背景图, 另会存到 `{项目}/Saved/LQABg/{时间戳}_BG.png`

**端到端快速验证 (采集 → 还原)**

初次接入时, 可按以下最小路径验证整套链路是否打通:

1. **采集**: 在采集端工程 (已接入 LQATool) 中运行目标 UI, 执行 `r.EnableLQATool 1` 导出快照, 确认生成 `{工程}/Saved/LQA/<时间戳_WBP名>/LQA_Snapshot_*.json`
2. **放置数据**: 把采集产物目录 (或其中的 `LQA_Snapshot_*.json`) 拷到还原端工程的 `Saved/LQA/` 下 (可直接拷整个 `<时间戳_WBP名>/` 目录, 本地模式会递归扫描)
3. **还原**: 还原端工程 PIE 运行 (默认 `en`), 等待约 1 秒自动开始还原
4. **核对**: 查看 `Saved/LQAResult/Restore_{DataId}_{语言}/screenshot.png` 与 `check_info.json`, 确认 UI 被还原且文本已替换为目标语言

**远端模式示例**

```bash
# 最小示例
YourProject.exe -JobId=79 -ProjectId=107 -Language=LAN_CHS_CHS

# 回归测试 + 基准数据对比
YourProject.exe -JobId=79 -ProjectId=107 -Language=LAN_CHS_CHS -Regression=1 -IsCover=true -BaseDataId=67890 -BaseDataFilePath="D:/LQA/base_67890.json"
```

**不打包运行远端模式 (编辑器 / PIE / Standalone)**

远端模式不是打包后才能用的功能, `ULQARestoreManager` 作为 `GameInstanceSubsystem`, 只要 GameInstance 启动就会运行, 而模式判定来自 `FCommandLine::Get()` (即当前进程的整条命令行), 因此只要让进程命令行带上 `-JobId=...` 等参数即可, 无需打包

> 前提: `Config/LQARestore.ini` 已配好 `Host` / `Authorization` (远端模式必需), 且已准备好翻译文件

**方式 A: 带参数启动编辑器, 再直接 PIE (推荐, 可断点调试)**

普通 PIE 读取的是 “编辑器主进程” 的命令行, 所以要在 **启动编辑器时** 就把远端参数加上, 退出已开的编辑器, 用命令行启动:

```bash
# UE5 (引擎可执行文件在 <引擎安装目录>/Engine/Binaries/Win64/ 下)
UnrealEditor.exe "D:/Path/To/YourProject.uproject" -JobId=79 -ProjectId=107 -Language=LAN_CHS_CHS

# UE4 同理, 可执行文件名为 UE4Editor.exe
UE4Editor.exe "D:/Path/To/YourProject.uproject" -JobId=79 -ProjectId=107 -Language=LAN_CHS_CHS
```

编辑器会忽略这些它不认识的自定义参数, 但 `FCommandLine::Get()` 会保留它们, 编辑器打开后点 **Play（在编辑器中运行）**, 日志出现 `LQARestoreManager initializing` 且 `IsLocalMode: false` 即表示已进入远端模式

> Rider / Visual Studio 调试: 在运行/调试配置的「程序参数(Program arguments)」里追加 `-JobId=79 -ProjectId=107 -Language=LAN_CHS_CHS`, F5 启动编辑器后 Play 即可带断点调试远端流程

**方式 B: Standalone 独立游戏窗口 + 附加启动参数**

1. **Editor Preferences → Level Editor → Play → Additional Launch Parameters** 填入:
   `-JobId=79 -ProjectId=107 -Language=LAN_CHS_CHS`
2. 以 **Play → New Editor Window (Standalone Game)** 方式运行 (Standalone 会以独立子进程启动, 上述参数会被拼进该子进程命令行)

> 该附加参数仅对 Standalone / Launch 这类独立进程生效, 对同进程 PIE 无效

**方式 C: 以 `-game` 独立进程运行 (无编辑器界面, 最接近打包行为)**

​```bash
UnrealEditor.exe "D:/Path/To/YourProject.uproject" -game -JobId=79 -ProjectId=107 -Language=LAN_CHS_CHS
​```

此方式不打开编辑器界面, 直接以游戏模式启动当前默认地图并运行远端任务, 适合联调验证

> 远端模式必须在插件工程 `Config/LQARestore.ini` 中配好 `Host` 与 `Authorization`, 否则 HTTP 请求无法发出

常用命令行参数:

| 参数 | 说明 | 默认值 |
| --- | --- | --- |
| `JobId` | 远端任务 ID, 非 `0` 时进入远端模式 | `0` |
| `ProjectId` | 项目 ID | `0` |
| `Language` | 目标语言, 如 `LAN_EU_EN`/`LAN_JP_JP`/`LAN_KO_KO`/`LAN_CHS_CHS` | `LAN_EU_EN` |
| `RestoreDirection` | 还原方向: `F2C` 外文→中文 / `C2F` 中文→外文 | `F2C` |
| `Regression` | 回归测试开关 | `0` |
| `IsCover` | 是否启用基准数据对比 | `false` |
| `BaseDataId` / `BaseDataFilePath` | 对比模式的基准数据 | 空 |
| `CreateBug` / `bugId` / `AISign` / `DefaultNums` / `MinID` / `Modules` | 远端平台扩展参数 | 见 `ConfigManager.cpp` |

> **`RestoreDirection` 决定“翻不翻”**:
> - `F2C` (默认): 原文含中文就直接原样输出 (中文守卫不查表), 用于 **中文验证**
> - `C2F`: 把中文原文当作待翻译文本去查翻译表, 用于 **目标语言（英/日/韩…）验证**
>
> **只传 `-Language=LAN_JP_JP` 而方向仍为默认 `F2C` 时, 中文原文会被中文守卫直接返回, 界面还是中文、看不到日语**, 验证目标语言必须同时传 `-RestoreDirection=C2F`
>
> 示例:
> ```bash
> # 中文验证 (不查翻译表, 直接显示采集到的中文原文)
> YourProject.exe
>
> # 日语验证
> YourProject.exe -Language=LAN_JP_JP -RestoreDirection=C2F
>
> # 韩语验证
> YourProject.exe -Language=LAN_KO_KO -RestoreDirection=C2F
> ```

支持的语言枚举详见 `ConfigManager.cpp` 中的 `InitializeLanguageMap()`

### 7. 扩展自定义控件

针对实际游戏项目中的自定义控件, 需在 `Plugins/LQARestore/Source/LQARestore/.../WidgetSlots/` 下新增对应的 `LQA_XxxWidget2Json` / `LQA_XxxSlot2Json` 实现, 可参考现有的 `LQA_Button2Json`、`LQA_ButtonSlot2Json`

---

## 译文接入与自定义

本章说明如何为具体项目准备 / 自定义多语言译文数据, 使还原出的 UI 显示为目标语言文本

### 1. 译文系统工作原理

插件在还原流程启动时 (`LoadTranslationData()`) 按 **当前语言** 加载两份 JSON, 缓存进内存两张表, 供还原每个文本控件时查询:

| 文件 | 内存表 | 查询键 | 典型来源 |
| --- | --- | --- | --- |
| `GameLocalizationExport_{lang}.json` | `AllKeyText` | 文本的 **TextKey** | 由 UE 本地化导出文件转换 |
| `Text_Translations_{lang}.json` | `AllTextKey` | 文本的 **原文(SourceString)** | 由 UE 本地化导出文件转换 |

> **译文 Key 与 json 的来历**:
> - 采集端 (`LQATool`) 导出快照时, 会读取每个文本控件在 **UE 本地化机制下** 的译文 Key (`TextKey`), 一并写入 dump JSON
> - 还原端 (`LQARestore`) 用这个 `TextKey` 从 `GameLocalizationExport_{lang}.json` 匹配译文, 无 Key 命中时再按原文从 `Text_Translations` 匹配
>
> 注意: 这两份 json **并不是 UE 自带本地化工具直接输出的文件**, UE 本地化工具 (Localization Dashboard) 导出的是 `.po` 等本地化文件, 需要接入方编写转换脚本把它们转换成这里的 json 结构

还原文本时调用 `FLoaderUtils::GetTranslateString(TextKey, SourceString)`, **先按 TextKey 查, 再按原文查**, 命中即替换; `TextKey` 为 `,INVALIDKEY`（无 Key）时不做翻译, 直接输出原文

### 2. 存放位置与命名

译文文件统一放在插件根目录下的 `LQALocalization/` (与 `Config/`、`Resources/` 平级):

```
Plugins/
└── LQARestore/
    ├── Config/
    ├── Resources/
    └── LQALocalization/                          # ← 译文目录
        ├── GameLocalizationExport_en.json
        ├── Text_Translations_en.json
        ├── GameLocalizationExport_ja.json
        ├── Text_Translations_ja.json
        ├── GameLocalizationExport_ko.json
        └── Text_Translations_ko.json
```

文件名中的 `{lang}` 是 **PO 语言码**, 由运行时 `-Language` 参数换算而来 (见下表), 默认语言 `LAN_EU_EN` 对应 `en`

### 3. 语言码对照表

`{lang}` 取值由 `ConfigManager::InitializeLanguageMap()` 决定:

| 命令行 `-Language` | `{lang}` (文件名后缀) | 语言 |
| --- | --- | --- |
| `LAN_EU_EN` (默认) | `en` | 英语 |
| `LAN_EU_DE` | `de` | 德语 |
| `LAN_FR_FR` | `fr` | 法语 |
| `LAN_RU_RU` | `ru` | 俄语 |
| `LAN_JP_JP` | `ja` | 日语 |
| `LAN_KO_KO` | `ko` | 韩语 |
| `LAN_CHT_CHT` | `zh-TW` | 繁体中文 |
| `LAN_AR_AR` | `ar` | 阿拉伯语 |
| `LAN_ES_LT` | `es` | 西班牙语 |
| `LAN_PT_BR` | `pt-BR` | 巴西葡萄牙语 |
| `LAN_TR_TR` | `tr` | 土耳其语 |
| `LAN_TH_TH` | `th` | 泰语 |
| `LAN_ID_ID` | `id` | 印尼语 |
| `LAN_CHS_CHS` | `zh` | 简体中文 |

> 未匹配到的语言会回退为 `en`

### 4. 两份文件的格式

**`GameLocalizationExport_{lang}.json`** —— 顶层 key 是 **TextKey**, value 必须是对象且含 `translation` 字段 (其余字段可选, 仅 `translation` 会被读取):

```json
{
    "ST_Menu_Start": {
        "TextKey": "ST_Menu_Start",
        "SourceStr": "Start",
        "translation": "Start Game"
    },
    "ST_Menu_Exit": {
        "TextKey": "ST_Menu_Exit",
        "SourceStr": "Exit",
        "translation": "Exit"
    }
}
```

**`Text_Translations_{lang}.json`** —— 顶层 key 是**原文**, value 直接是译文字符串:

```json
{
    "Hello World": "Hello World (translated)",
    "Settings": "Settings (translated)"
}
```

### 5. 译文匹配规则

还原文本时先按 `TextKey` 的形态分流 (`FWidget2JsonInterface::GetTextFromJson`):

| `TextKey` 形态 | 处理方式 |
| --- | --- |
| `,FORTEST` | 测试标记, 直接输出原文, 不翻译 |
| `,INVALIDKEY` | 无本地化 Key, **直接输出原文** (游戏里本来就是原文, 不查表) |
| 含 `##` | 用完整 `TextKey` 查表 |
| `Namespace,Key` | 取 **逗号右半部分** 作为真正的 Key 查表 |

分流后调用 `FLoaderUtils::GetTranslateString(Key, SourceString)`, 按以下顺序判定, 命中即返回:

1. **`F2C` 方向 + 原文含中文字符 → 原样返回** (中文守卫; `C2F` 方向 **不启用**, 中文会被当作待翻译原文继续查表)
2. 原文仅含数字 / 标点 / 空白 → 原样返回
3. 按 `TextKey` 查 `GameLocalizationExport_{lang}.json` → 命中返回
4. 按原文 `SourceString` 查 `Text_Translations_{lang}.json` → 命中返回
5. 都未命中 → 返回 `##UnMatched`

> - 匹配 **大小写敏感**, key / 原文需完全一致
> - `,INVALIDKEY` 文本 (无 Key) **不会进入查表流程**, 不会输出 `##UnMatched`
> - `##UnMatched` 只表示「有 Key 或可翻译文本, 但两张表都没命中」

### 6. 为具体项目添加自定义译文

1. **确定目标语言**: 根据运行时 `-Language` 参数, 对照上表得到 `{lang}`
2. **准备译文数据**, 二选一:
   - **转换脚本生成 (推荐, 生产用)**: UE 项目通常用 **虚幻自带本地化工具 (Localization Dashboard)** 做本地化, 其导出的是 `.po` 等本地化文件, 不能被本插件直接读取, 需**编写一个 Python 转换脚本**, 把这些导出文件转换成 `GameLocalizationExport_{lang}.json` 与 `Text_Translations_{lang}.json`
   - **手写 (调试 / 小范围验证用)**: 按第 4 节格式手工编写
3. **放入目录**: 将两份文件拷到 `Plugins/LQARestore/LQALocalization/`
4. **多语言**: 每种语言各放一套 `*_{lang}.json`, 运行时按 `-Language` 自动选择加载
5. **编码**: 文件统一用 **UTF-8（无 BOM）**, 避免非 ASCII 文本乱码

> **重点说明: 转换脚本需接入方自己实现**
> 这个转换脚本 **每个项目都不一样** —— 各项目的文本 Key 命名、目录结构、本地化工具配置均不相同, 无法提供一套通用脚本, 
> 接入方需参考本插件 `LQALocalization/` 下的 json 示例自行编写 (通常几十行 Python: 读取 `.po` 的 msgid/msgstr 或平台导出文件, 输出为第 4 节的 json 结构); 此前各接入项目也都是单独为其编写转换脚本的

### 7. 调试与验证

1. 准备一份 dump 放入 `{工程}/Saved/LQA/test.json` (dump 结构复杂, 建议基于已有快照修改文本节点, 不要从零手写)
2. 修改其文本节点以命中不同分支:
   - 命中 Key: `"TextKey": "ST_Menu_Start"`
   - 命中原文: `"SourceString": "Hello World"` (`F2C` 下原文不能是中文, 否则会被中文守卫直接返回; `C2F` 下原文是中文才会去查表)
3. 以目标语言运行: 命令行加 `-Language=LAN_JP_JP -RestoreDirection=C2F` (只加 `-Language` 会因默认 `F2C` 方向而看不到外语)
4. 查看结果: `Saved/LQAResult/Restore_test_{语言}/screenshot.png`, 并在日志中确认出现 `LoadFileToString: .../LQALocalization/...`

### 8. 常见问题排查

| 现象 | 可能原因 |
| --- | --- |
| 文本显示 `##UnMatched` | 有 Key 但两张表都没有对应条目; 大小写不符; 翻译文件未加载 |
| 文本显示 `Invalid/xxx` 这类原文 | `TextKey` 为 `,INVALIDKEY` (无本地化 Key), 属预期行为, 不是漏译 |
| 文本未被翻译 (保持原文) | 方向为 `F2C` 且原文含中文; 或原文仅数字标点 —— 属预期行为 |
| 传了 `-Language` 但界面还是中文 | 方向仍是默认 `F2C`, 中文守卫直接返回原文; 验证目标语言需同时传 `-RestoreDirection=C2F` |
| 日志无 `LoadFileToString` | 文件路径 / 文件名 `{lang}` 后缀不对, 或文件不在插件 `LQALocalization/` 下 |
| 非 ASCII 文本乱码 | 文件未用 UTF-8 保存 |
| 切换语言无变化 | 对应 `*_{lang}.json` 不存在, 或参数未生效 (PIE 需在启动编辑器时带参) |

---

## 扩展还原控件与槽

针对实际游戏项目中的自定义 UI, 适配同学通常要做两件事: **调试还原效果** 与 **新增控件 / 槽的还原实现**

### 新增还原控件 (Widget)

以新增 `UFooWidget` (对应 Slate 类型名 `SFoo`) 为例:

1. **新建实现文件** (参考 `LQA_Button2Json`):
   - 头文件 `Source/LQARestore/Public/WidgetSlots/Widgets/LQA_Foo2Json.h`
   - 源文件 `Source/LQARestore/Private/WidgetSlots/Widgets/LQA_Foo2Json.cpp`

   ```cpp
   // LQA_Foo2Json.h
   #pragma once
   #include "WidgetSlots/Core/Widget2JsonInterface.h"

   class FLQA_Foo2Json : public FWidget2JsonInterface
   {
   public:
       virtual UWidget* FromJson(const TSharedPtr<FJsonObject> JsonData, URestoreWindowProxy* RestoreWindowProxy) override;
       virtual ELQAWidgetType GetType() override;
   };
   ```

   ```cpp
   // LQA_Foo2Json.cpp
   #include "WidgetSlots/Widgets/LQA_Foo2Json.h"
   #include "Components/FooWidget.h"
   #include "WidgetSlots/Core/WidgetDefines.h"
   using namespace LQAWidgetConstants;

   UWidget* FLQA_Foo2Json::FromJson(const TSharedPtr<FJsonObject> JsonData, URestoreWindowProxy* RestoreWindowProxy)
   {
       if (!JsonData.IsValid()) { return nullptr; }
       UFooWidget* NewWidget = nullptr;
       if (JsonData->HasField(CommonObjectKey)) // "ObjectData"
       {
           const TSharedPtr<FJsonObject> ObjectData = JsonData->GetObjectField(CommonObjectKey);
           if (ObjectData.IsValid())
           {
               NewWidget = GetAsObject<UFooWidget>(ObjectData, UFooWidget::StaticClass());
           }
       }
       // 可在此处理纹理 / 文本 / 样式等自定义字段
       return NewWidget;
   }

   ELQAWidgetType FLQA_Foo2Json::GetType() { return ELQAWidgetType::LQA_Foo; }
   ```

2. **声明类型名常量** — `Public/WidgetSlots/Core/WidgetDefines.h` 的 `LQAWidgetNames` 命名空间中 `extern const FName LQA_Foo;`, 并在 `Private/WidgetTree/LQAWidgetNode.cpp` 中定义 `const FName LQA_Foo(TEXT("SFoo"));` (字符串须与该控件对应的 **Slate 类型名** 一致, 可在 `SWidget::GetType()` 处打印确认)

3. **新增枚举值** — `WidgetDefines.h` 的 `ELQAWidgetType` 中加入 `LQA_Foo`; 若该控件需要特殊的尺寸/OCR 后处理, 在 `RestoreWidget2JsonFactory::WidgetFromJson` 对应分支中补充逻辑

4. **登记控件树映射** — `LQAWidgetNode.cpp` 的 `WidgetTypeMap` 中加入 `{LQA_Foo, ELQAWidgetType::LQA_Foo}`

5. **工厂注册 (必需)** — `RestoreWidget2JsonFactory.cpp` 顶部 `#include "WidgetSlots/Widgets/LQA_Foo2Json.h"`, 并在 `MakeWidgetData` 中新增:

   ```cpp
   if (WidgetType == LQAWidgetNames::LQA_Foo)
   {
       return MakeShareable(new FLQA_Foo2Json());
   }
   ```

### 新增还原槽 (Slot)

以新增 `UFooSlot` (dump JSON 中 `SlotType` 为 `"UFooSlot"`) 为例:

1. **新建实现文件** (参考 `LQA_ButtonSlot2Json`):

   ```cpp
   // LQA_FooSlot2Json.h
   #pragma once
   #include "CoreMinimal.h"
   #include "Json.h"
   #include "WidgetSlots/Core/Slot2JsonInterface.h"

   class FLQA_FooSlot2Json : public FSlot2JsonInterface
   {
   public:
       virtual bool FromJson(const TSharedPtr<FJsonObject> JsonData, UPanelSlot* PanelSlot) override;
   };
   ```

   ```cpp
   // LQA_FooSlot2Json.cpp
   #include "WidgetSlots/Slots/LQA_FooSlot2Json.h"
   #include "Components/FooSlot.h"

   bool FLQA_FooSlot2Json::FromJson(const TSharedPtr<FJsonObject> JsonData, UPanelSlot* PanelSlot)
   {
       if (JsonData.IsValid() && JsonData->Values.Num() > 0)
       {
           if (UFooSlot* Slot = Cast<UFooSlot>(PanelSlot))
           {
               bool bResult = SetPanelSlotProperties(JsonData, Slot); // 基类统一反序列化
               Slot->SynchronizeProperties();
               return bResult;
           }
           UE_LOG(LogLQARestoreSlot2Json, Warning, TEXT("Failed to cast PanelSlot to UFooSlot"));
       }
       return false;
   }
   ```

2. **工厂注册 (必需)** — `Slot2JsonFactory.cpp` 顶部 `#include "WidgetSlots/Slots/LQA_FooSlot2Json.h"`, 并在 `MakeSlotData` 中新增 (注意: 工厂会先去掉 `SlotType` 的首字母 `U`, 这里匹配去 `U` 后的名字):

   ```cpp
   if (SlotTypeName == FName(TEXT("FooSlot")))
   {
       return MakeShareable(new FLQA_FooSlot2Json());
   }
   ```

> 槽的还原只要「新建实现 + 工厂分支」两步即可生效; `WidgetDefines.h` 中的 `LQASlotNames` / `ELQASlotType` 为预留项, 当前工厂使用字面量匹配, 非必改, 
> 大多数槽属性 (对齐、边距、锚点、尺寸规则等) 由基类 `SetPanelSlotProperties` 通过 `JsonObjectToUStruct` 自动灌入, 仅当存在无法直接反序列化的特殊字段时才需在 `FromJson` 中手动处理

### 新增后的验证

1. 右键 `.uproject` → Generate project files, 重新编译 Development Editor
2. 准备一份包含新控件 / 槽的 dump json, 放入 `{项目}/Saved/LQA/`, PIE 运行
3. 查看 `Saved/LQAResult/Restore_*/screenshot.png` 与日志, 确认无 `Unknown SlotTypeName` / `Try Restore Xxx Failed` 等告警

---

## 平台交互

> 适用于平台模式 (非本地模式), 四个循环定时器在 `ULQARestoreManager::SetupPlatformTimers()` 中注册, 
> 各自按固定间隔驱动 `TaskManager` 的队列处理与还原流程

### 日志分类对照

| 分类 | 定义位置 | 覆盖模块 |
|------|----------|----------|
| `LogLQARestoreManager` | `LQARestoreManager.cpp` | 主控制器 / 定时器回调 / 还原 / 截图 |
| `LogLQARestoreTask` | `TaskManager.cpp` | 下载/上传队列、重试、解压、JSON 解析 |
| `LogLQARestoreHttp` | `HttpRequestConfig.cpp` | 底层 HTTP 请求、配置加载 |

### 定时器总览

| 定时器 | 间隔 | 回调函数 | 作用 |
|--------|------|----------|------|
| `JobDataTimer` | 150s | `OnGetJobDataTick` | 周期性向平台拉取任务数据 |
| `DownloadTimer` | 3s | `OnDownloadTick` | 处理下载队列 |
| `RestoreTimer` | 10s | `OnRestoreTick` | 处理当前还原项 (建窗/截图/生成结果) |
| `UploadTimer` | 4s | `OnUploadTick` | 处理上传队列 |

### 1. JobDataTimer (拉取任务, 150s)

**调用链**
`OnGetJobDataTick` → `HandlePlatformWorkflow(false)` → `TaskManager::RequestJobData` → `FHttpRequestHelper::GetJobData` → (回调) `OnJobDataSuccess` → 广播 → `Manager::OnJobDataReceived` → `EnqueueDownload`

**日志清单**

| 级别 | 分类 | 日志信息 | 源码位置 | 排查含义 |
|------|------|----------|----------|----------|
| Error | Task | `ConfigManager is null` | `TaskManager::RequestJobData` | 依赖未初始化, 子系统初始化异常 |
| Warning | Task | `JobId is 0, skipping job data request` | `TaskManager::RequestJobData` | JobId 未配置, 不会发起请求 (正常跳过) |
| Log | Http | `GET: {URL}` | `FHttpRequestHelper::CreateRequest` | 确认实际请求 URL 与参数是否正确 |
| Warning | Http | `Request failed` | `FHttpRequestHelper::HandleResponse` | 网络层失败 (连接/超时) |
| Warning | Task | `Job data response is invalid` | `TaskManager::OnJobDataSuccess` | 响应指针无效 |
| Error | Task | `Failed to parse job data response` | `TaskManager::OnJobDataSuccess` | 返回体非合法 JSON |
| Warning | Task | `No data field in job data response` | `TaskManager::OnJobDataSuccess` | JSON 缺少 `data` 字段, 接口协议异常 |
| Log | Task | `Received N job data items` | `TaskManager::OnJobDataSuccess` | 成功解析出的任务数 (0 表示无新任务) |
| Log | Manager | `Received N job data items` | `Manager::OnJobDataReceived` | 去重后加入待处理/下载队列 |

### 2. DownloadTimer (下载队列, 3s)

**调用链**
`OnDownloadTick` → (`CanDownload()` 为真时) `TaskManager::ProcessDownloadQueue` → `FHttpRequestHelper::GetDumpData` → (回调) `OnDownloadSuccess` / `OnDownloadFail` → 广播 → `Manager::OnDumpDataDownloaded`

**日志清单**

| 级别 | 分类 | 日志信息 | 源码位置 | 排查含义 |
|------|------|----------|----------|----------|
| Log | Task | `Dump file already exists: {DataId}` | `ProcessDownloadQueue` | 命中本地缓存, 跳过网络下载 |
| Log | Task | `Downloading dump data: {DataId}` | `ProcessDownloadQueue` | 开始下载, `bIsDownloading` 加锁 |
| Log | Http | `GET: {URL}` | `CreateRequest` | 下载地址 (注意端口 8080→80 替换) |
| Error | Task | `Response is invalid: {DataId}` | `OnDownloadSuccess` | 响应指针无效 |
| Log | Task | `Download response code: {Code}, DataId: {DataId}` | `OnDownloadSuccess` | HTTP 状态码 |
| Error | Task | `HTTP error response: {Code}, Content: {...}` | `OnDownloadSuccess` | 非 2xx, 附带返回体 |
| Log | Task | `Downloaded data size: N bytes` | `OnDownloadSuccess` | 下载字节数 (0 需警惕) |
| Error | Task | `Download data is empty: {DataId}` | `OnDownloadSuccess` | 返回体为空 |
| Log | Task | `Data format check - IsGzip: {Y/N}, First bytes: XX XX` | `OnDownloadSuccess` | gzip 魔数检测结果 |
| Warning | Task | `Data is not gzip compressed, treating as raw JSON` | `OnDownloadSuccess` | 走原始 JSON 兼容分支 |
| Error | Task | `Invalid JSON data (raw): {DataId}, Preview: {...}` | `OnDownloadSuccess` | 原始 JSON 解析失败 |
| Log | Task | `Download success (raw JSON): {DataId}` | `OnDownloadSuccess` | 原始 JSON 分支下载成功 |
| Error | Task | `Failed to decompress gzip data: {DataId}` | `OnDownloadSuccess` | zlib 解压失败 |
| Error | Task | `Invalid JSON data: {DataId}` | `OnDownloadSuccess` | 解压后 JSON 非法 |
| Log | Task | `Download success: {DataId}` | `OnDownloadSuccess` | 下载并落盘成功 |
| Error | Task | `Download failed: {DataId} (Retry: n/3)` | `OnDownloadFail` | 失败重试计数, 达 3 次后放弃并广播失败 |
| Log | Manager | `Dump data downloaded: {DataId}` | `Manager::OnDumpDataDownloaded` | 下载完成回调 |
| Log | Manager | `Base comparison data loaded: {DataId}` | `Manager::OnDumpDataDownloaded` | 基准对比数据加载成功 (对比模式) |

### 3. RestoreTimer (还原流程, 10s)

**调用链**
`OnRestoreTick` → (有待处理项且 `bCanStartRestore`) `ProcessCurrentRestoreItem` → `MakeRestoredWindow` → (延迟) `BuildWindow` → `ScheduleScreenshotAndUpload` → (延迟) 截图 + 生成结果 JSON → `ClearRestoreWindow` → `EnqueueUpload`

**日志清单**

| 级别 | 分类 | 日志信息 | 源码位置 | 排查含义 |
|------|------|----------|----------|----------|
| Log | Manager | `Restoring data ID: {DataId}` | `ProcessCurrentRestoreItem` | dump 文件就绪, 开始还原 |
| Log | Manager | `Waiting for file download: {DataId} (Attempt: n/3)` | `ProcessCurrentRestoreItem` | 文件未就绪, 等待下载, 不推进索引 |
| Warning | Manager | `File not found after 3 attempts, skipping: {Path}` | `ProcessCurrentRestoreItem` | 等待超限, 跳过该项 |
| Error | Manager | `Failed to create RestoreWindowProxy` | `MakeRestoredWindow` | 窗口代理创建失败 |
| Error | Manager | `Failed to build window for: {DataId}` | `MakeRestoredWindow`(lambda) | 窗口内容构建失败, 解锁并推进 |
| Warning | Manager | `Failed to capture screenshot for: {DataId}` | `ScheduleScreenshotAndUpload` | 截图失败 (仍会生成结果 JSON) |
| Log | Manager | `Generating output for: {DataId}` | `ScheduleScreenshotAndUpload` | 生成校验/结果 JSON |
| Log | Manager | `Restore windows cleared, ready for next item` | `ClearRestoreWindow` | 窗口清理完成, 可处理下一项 |

**截图子流程日志 (均为 Manager 分类)**

> 截图有两种取景模式 (`ELQAScreenshotMode`), 默认 `WidgetOnly`, 运行时可通过 `ULQARestoreManager::SetScreenshotMode(...)` 切换:
> - `WidgetOnly` → `CaptureWidgetScreenshot`: 用 `FWidgetRenderer` 离屏渲染根控件 (不带视口背景)
> - `Viewport` → `CaptureViewportScreenshot`: 用 `FSlateApplication::TakeScreenshot` 截游戏视口 (含全部 UI)

**`CaptureWidgetScreenshot` (WidgetOnly 离屏渲染)**

| 级别 | 日志信息 | 排查含义 |
|------|----------|----------|
| Error | `CaptureWidgetScreenshot must run on the game thread` | 非游戏线程调用 |
| Error | `Widget is invalid` | 根控件为空 |
| Error | `Screenshot file path is empty` | 输出路径为空 |
| Error | `Invalid widget size: %fx%f` | 控件尺寸非法 (未完成布局) |
| Error | `Screenshot size is too large: %dx%d` | 尺寸非正或超上限 |
| Error | `Failed to create directory: {Path}` | 输出目录创建失败 |
| Error | `Failed to create render target` | 渲染目标创建失败 |
| Error | `Failed to get render target resource` | 渲染目标资源获取失败 |
| Error | `Failed to read pixels from render target` | 读像素失败 |
| Error | `Pixel count mismatch: RT=%dx%d, Pixels=%d` | 读回像素数量不符 |
| Error | `Failed to compress image to PNG` | PNG 压缩失败 |
| Error | `PNG compression returned empty data` | PNG 压缩结果为空 |
| Error | `Failed to save screenshot to: {Path}` | PNG 落盘失败 |
| Log | `Widget screenshot saved to: {Path} (Size: WxH)` | 截图成功 |

**`CaptureViewportScreenshot` (Viewport 视口截图)**

| 级别 | 日志信息 | 排查含义 |
|------|----------|----------|
| Error | `Failed to get GameViewportClient` | 取游戏视口客户端失败 |
| Error | `Failed to get game viewport widget` | 取视口控件失败 |
| Error | `Failed to create directory: {Path}` | 输出目录创建失败 |
| Error | `Failed to take screenshot of game viewport` | 视口截图失败 |
| Error | `Pixel count mismatch: ViewportWidget=%dx%d, Pixels=%d` | 读回像素数量不符 |
| Error | `Failed to compress image to PNG` | PNG 压缩失败 |
| Error | `PNG compression returned empty data` | PNG 压缩结果为空 |
| Error | `Failed to save screenshot to: {Path}` | PNG 落盘失败 |
| Log | `Screenshot saved to: {Path} (Size: WxH)` | 截图成功 |

### 4. UploadTimer (上传队列, 4s)

**调用链**
`OnUploadTick` → (`CanUpload()` 为真时) `TaskManager::ProcessUploadQueue` → `FHttpRequestHelper::SendRestoreResult` → (回调) `OnUploadSuccess` / `OnUploadFail` → 广播 → `Manager::OnRestoreResultUploaded`

**日志清单**

| 级别 | 分类 | 日志信息 | 源码位置 | 排查含义 |
|------|------|----------|----------|----------|
| Log | Task | `Uploading restore result: {DataId}` | `ProcessUploadQueue` | 开始上传，`bIsUploading` 加锁 |
| Warning | Task | `Result directory not found: {Path}` | `ProcessUploadQueue` | 结果目录缺失, 判为失败 |
| Warning | Task | `No PNG or JSON files found for upload: {DataId}` | `ProcessUploadQueue` | 结果文件不全, 判为失败 |
| Log | Http | `POST: {URL}` | `CreateRequest` | 上传地址 `/api/image/entity` |
| Warning | Http | `Request failed` | `HandleResponse` | 网络层失败 |
| Log | Task | `Upload success: {DataId}` | `OnUploadSuccess` | 上传成功, 成功后清理本地结果目录 |
| Error | Task | `Upload failed: {DataId} (Retry: n/3)` | `OnUploadFail` | 失败重试计数, 达 3 次后放弃 |
| Log | Manager | `Restore result uploaded: {DataId}` | `Manager::OnRestoreResultUploaded` | 上传完成回调 |

### 典型排查路径

- **一直没有新任务**: 查 `JobDataTimer` 链路 → `Received N job data items` (N=0 或无该日志) → 核对 `GET` URL 参数、`JobId is 0`、`No data field`
- **下载卡住不动**: 查 `DownloadTimer` → 是否长期无 `Download success` → 关注 `Download failed (Retry)`、`HTTP error response`、`Failed to decompress`
- **还原项被跳过**: 查 `RestoreTimer` → `File not found after 3 attempts` (下载未跟上) 或 `Failed to build window`
- **结果未回传平台**: 查 `UploadTimer` → `No PNG or JSON files found`、`Result directory not found`、`Upload failed (Retry)`

### 配置加载日志 (启动期, LogLQARestoreHttp)

| 级别 | 日志信息 | 含义 |
|------|----------|------|
| Error | `Plugin 'LQARestore' not found` | 插件未找到 |
| Warning | `Config file not found: {Path}` | `Config/LQARestore.ini` 缺失 |
| Log | `Loaded Host: {Host}` | 平台地址加载成功 |
| Warning | `Host not found in config` | ini 缺少 Host |
| Log | `Loaded Authorization (length: N)` | 鉴权令牌加载成功 |
| Warning | `Authorization not found in config` | ini 缺少 Authorization |

---