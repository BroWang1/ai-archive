# LQATool 插件

![License](https://img.shields.io/badge/license-Apache%202.0-blue)

## 插件简介

**LQATool** 是一个运行时 Unreal Engine 插件, 面向本地化团队提供语言质量与界面布局的可视化检测能力

### 核心功能

- **Dump**: 导出控件树快照 (JSON), 包含层级、坐标尺寸、样式、文本与本地化 Key, 同时生成前景与背景截图
- **Get Key**: 开启捕获后用鼠标右键点击界面文本, 屏幕提示该文本的内容、源字符串与本地化 Key

> **采集端不翻译**: Dump 记录的是 **游戏当前实际显示的文本** (`textStr`) 和本地化 Key (`TextKey`), 不做任何语言转换, 译文替换发生在还原端 (LQARestore) —— 它按运行时 `-Language` / `-RestoreDirection` 查翻译表后重新渲染, 因此采集一次中文基线, 就能在还原端切换任意目标语言

### 使用方式

- 通过控制台命令 `r.EnableLQATool <0/1> [DelayInSeconds]` 启用或关闭调试面板
- 可选参数 `DelayInSeconds` 用于设置截图与导出流程的延迟执行秒数 (默认为 0, 即立即执行)

### 技术架构

- `ULQAManager` 子系统 (Game Instance Subsystem) 负责初始化调试面板 (`ULQABaseView`)、输入捕获器 (`FLQAInputProcessor`) 以及 Widget 导出功能
- 暴露 `LQADumpViewAdvanced` 等 Blueprint 可调用接口, 便于在编辑器或运行时生成 Widget 快照

### 平台支持

- 支持 Win64、Mac、iOS、Android 平台
- 面向非 Shipping 构建的测试场景

### 插件结构

```text
LQATool/
├── .clang-format                       # UE C++ 代码风格配置
├── LQATool.uplugin                     # 插件清单, 声明模块、版本、平台
├── Resources/                          # 图标与分发资源
└── Source/LQATool/
    ├── LQATool.Build.cs                # 构建脚本
    ├── Public/
    │   ├── LQABase.h                   # 公共宏、日志定义
    │   ├── LQAManager.h                # GameInstanceSubsystem, 对外入口
    │   ├── LQAInputProcessor.h         # GetKey 的右键输入捕获
    │   ├── ToolPanel/LQABaseView.h     # 调试面板 (Dump / GetKey 按钮)
    │   ├── Snapshot/                   # Widget 树节点抽象与构建工具
    │   ├── Utils/                      # 导出、JSON、贴图、通用工具
    │   ├── Validation/                 # 纯 C++ 测试画廊与 LQA.BuildGallery 命令
    │   └── WidgetSlots/
    │       ├── LQAWidgetTypeRegistry.h # Slate 名 + UMG 类 → 控件类型的登记表
    │       ├── WidgetDefines.h         # JSON 字段名与 Slate 类型名常量
    │       ├── Widget2JsonFactory.h    # Widget 转换工厂
    │       ├── Slot2JsonFactory.h      # Slot 转换工厂
    │       ├── Widget/                 # 所有的控件转换实现
    │       └── Slot/                   # 所有的槽转换实现
    └── Private/                        # 对应 Public/ 的实现文件 (.cpp)
```

### 扩展说明

- 插件具备基础控件采集能力, 接入游戏项目中, 需要按需增加自定义控件和 Slot 类型到 `WidgetSlots` 目录下

---

## 接入插件

### 1. 拷贝插件到工程

将 `Plugins/LQATool` 整个目录复制到目标 UE 工程的 `Plugins/` 目录下 (没有则新建):

```text
YourProject/
├── YourProject.uproject
└── Plugins/
    └── LQATool/
        ├── LQATool.uplugin
        ├── Resources/
        └── Source/
```

### 2. 在 .uproject 中启用插件

在 `YourProject.uproject` 的 `Plugins` 数组中声明:

```json
"Plugins": [
    {
        "Name": "LQATool",
        "Enabled": true
    }
]
```

也可以在编辑器中通过 `Edit > Plugins` 搜索 `LQATool` (分类为 Testing) 勾选启用, 然后重启编辑器

### 3. 添加模块依赖 (C++ 调用时)

插件模块为 `Runtime` 类型, 加载阶段 `PostConfigInit`, 会自动随游戏启动, 若需要在项目 C++ 中直接调用 `ULQAManager` 接口, 需在 `YourProject.Build.cs` 中加入模块依赖:

```csharp
PublicDependencyModuleNames.AddRange(new string[]
{
    "Core",
    "CoreUObject",
    "Engine",
    "LQATool"
});
```

### 4. 生成工程并编译

右键 `.uproject` → **Generate Project Files** (Rider 中 Reload/Regenerate 亦可), 编译 `Development Editor` / `Development` 配置, 平台白名单为 `Win64 / Mac / IOS / Android`, 其他平台不会加载

### 5. 运行时打开调试面板

在 Standalone 或打包产物中按 `~` 打开控制台:

```text
r.EnableLQATool 1        // 打开面板
r.EnableLQATool 1 3      // 打开面板, 并让 Dump 延迟 3 秒执行
r.EnableLQATool 0        // 关闭面板
```

也可通过蓝图或 C++ 调用子系统接口:

```cpp
#include "LQAManager.h"

if (ULQAManager* LQAManager = ULQAManager::GetLQAManager(GetGameInstance()))
{
    LQAManager->InitAll();                        // 打开面板
    LQAManager->LQADumpViewAdvanced(true, true);  // 导出快照 (含贴图与 Object 元数据)
}
```

> PIE 模式下 `GetLQAManager` 返回空并提示 `PIE mode is not recommended, please use Standalone mode`, 调试面板请用 **Standalone** 或真机运行

---

## 测试流程 (画廊)

插件自带一个纯 C++ 构造的测试画廊, 覆盖常用 UMG 控件与布局容器, 不依赖任何 WBP 或美术资源, 按下面步骤可以完整走通 Dump 与 GetKey

### 1. 启动运行时

编辑器 **Play → Standalone Game**, 或直接运行打包产物, 按 `~` 打开控制台

### 2. 构造画廊

```text
LQA.BuildGallery             // 控件区 + 布局区
LQA.BuildGallery Widgets     // 仅控件区
LQA.BuildGallery Layout      // 仅布局区
LQA.BuildGallery Bug         // 仅显示性质 BUG 示例区
LQA.BuildGallery All         // 全部: 控件区 + 布局区 + BUG 示例区
```

画廊以 ZOrder 10000 添加到视口并铺满屏幕, 执行后立即可见, BUG 示例区位于画廊最下方, 标题为 `五、显示性质 BUG`, 包含 11 条故意制造的文本溢出 / 截断 / 重叠 / 不可见 / 漏 Key 用例, 用于验证 Dump 与还原对异常 UI 的识别能力

### 3. 打开调试面板

```text
r.EnableLQATool 1
```

屏幕左侧中部出现 `Dump` 与 `GetKey [Off]` 两个按钮, 面板层级高于画廊, 不会被遮挡

### 4. 采集快照

点击 `Dump`, 按钮固定按 `LQADumpViewAdvanced(true, true)` 导出, 完成后在 `<Project>/Saved/LQA/` 下生成一个按时间戳命名的目录:

```text
Saved/LQA/2026_10_18_11_23_18_LQAGalleryWidget_UE5_2147482364/
├── LQA_Snapshot_<WBP名>_<时间戳>.json          # 控件树快照
├── LQA_ScreenShot_<WBP名>_<时间戳>.png         # 含全部 UI (含调试面板)
├── LQA_ScreenShot_<WBP名>_<时间戳>_BG.png      # 无 UI 的纯场景图
└── Textures/                                   # 仅当存在运行时生成的贴图时创建
    └── <MD5(贴图完整名)>.png
```

`<WBP名>` 取自运行时控件名, 画廊为 `LQAGalleryWidget_UE5` (UE4 为 `LQAGalleryWidget_UE4`), 末尾可能带 `_<数字>` 唯一化后缀。Android 的 `Saved` 目录位于 `PersistentDownloadDir` 下, iOS 位于应用沙盒的 `Saved` 目录

### 5. 取文本 Key

1. 点击 `GetKey` 按钮, 按钮变为 `GetKey [On]`
2. 用 **鼠标右键** 点击画廊中的文本 (例如标题 `LQA 验证画廊 (UE5)`)
3. 屏幕上提示 `localization: <当前文本>`, 文本有有效 Key 时同时给出源字符串与本地化 Key
4. 再次点击按钮恢复 `[Off]`, 结束捕获

> 捕获期间右键事件会被插件消费, 不会传给下层控件

### 6. 核对结果

| 检查项 | 期望 |
| --- | --- |
| 顶层字段 | 只有 `uitree` 与 `meta`; `uitree` 只有一个根节点, 名称以 `LQAGalleryWidget_UE5` 开头 |
| `meta.sizeX` / `sizeY` | 与截图像素尺寸一致 (本次示例为 1536 × 864) |
| 文本节点 | `textStr` 为画廊当前文本, `TextKey` 形如 `ST_Gallery,ST_Gallery_TextBlockSample`; 没有 Key 的文本为 `,INVALIDKEY` |
| 控件类型 | 画廊中的 TextBlock、Button、ListView 等都有对应 `WidgetType`, 不应出现 `UNDEFINE` |
| 截图 | 前景含画廊与调试面板, `_BG.png` 只有场景背景 |
| GetKey | 右键点击的文本, 其屏幕提示的 Key 与 JSON 中的 `TextKey` 一致 |

### 7. 还原验证 (可选)

将 Dump 出的 JSON 交给 LQARestore 的本地模式即可查看还原效果, 它会递归扫描 `Saved/LQA/` 下的所有 JSON 文件

### 8. BUG 示例区 (显示性质)

`LQA.BuildGallery Bug` 单独构建, 每行由左标签 + 固定尺寸舞台 (1px 描边) 组成, 行间已有固定上下间距, 画廊内按 BUG-01 ~ BUG-11 顺序显示, 其中 BUG-10 与 BUG-11 相邻, 便于对照漏 Key 与漏译

| 编号 | 缺陷 | 判定点 |
| --- | --- | --- |
| BUG-01 | 单行文本不换行, 横向溢出舞台右边界 | 截图文本越出舞台描边 |
| BUG-02 | 换行后行数超出固定高度, 越出舞台底部 | 截图文本越出舞台描边 |
| BUG-03 | 字号 36 超过舞台高度, 字形越出底边 | `ObjectData` 中 `Font.Size=36`, 截图字形溢出 |
| BUG-04 | 按钮内文本被按钮裁剪 | `textStr` 完整, 截图按钮内只显示前半段 |
| BUG-05 | 行高压缩到 30%, 同节点内行间叠字 | `LineHeightPercentage=0.3`, 截图可判定 |
| BUG-06 | 文本与底色同色 | 节点与 `textStr` 存在, 截图对应区域无字 |
| BUG-07 | 文本被 `ClipToBounds` 硬截断 | `textStr` 完整, 截图尾部缺失 |
| BUG-08 | TileView 条目高度小于行高, 条目重叠 | 相邻条目节点 `corners` 重叠 |
| BUG-09 | TileView 条目宽度小于文本宽度, 文本跨条目溢出 | `textStr` 完整, 截图条目内只显示前半段 |
| BUG-10 | 无 Key, 直接显示原始 Key | `TextKey` 为 `,INVALIDKEY` |
| BUG-11 | 有 Key 但未登记译文 | `F2C` 下 `textStr` 为中文源文 (中文守卫); `C2F` 下查表未命中会变成 `##UnMatched` |

> BUG-10 的文本与 BUG-11 的 Key (`ST_Gallery_Bug_MissingTranslation`) 故意不登记 `LQALocalization`, 不要补录, 否则示例失效

> 采集前请先滚动到画廊底部, 否则 BUG-09~11 落在视口外, 快照中的坐标为负值, 还原图会缺这几条

> `corners` 表示控件分配区域, 不包含文本溢出绘制范围; 溢出、压字、截断等表现以截图为准

---

## 快照 JSON 说明

### 顶层字段

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `uitree` | array | 顶层控件树, 每项为一个 UserWidget 根 (调试面板已被排除) |
| `meta` | object | `version` (取自 `ProjectVersion`, 缺省 `1.0.0.0`)、`device` (`Platform=...&OSVersion=...`)、`sizeX`/`sizeY` (视口像素尺寸, 与截图一致) |

### 节点字段

| 字段 | 说明 |
| --- | --- |
| `WidgetName` | 控件名; `None` 表示无命名的 Slate 内部控件 |
| `WidgetType` | 控件类型标识 (Slate 名); 未登记类型为 `UNDEFINE` |
| `WidgetClass` | 仅 Slate 根类型复用组输出, 如 `SizeBox` / `NamedSlot` / `ComboBoxString` |
| `corners` | 4 个角点, 顺序为 左下 → 左上 → 右上 → 右下, 视口像素, Y 轴向上 |
| `ViewportPos` / `LocalSize` / `BoxSize` | 视口坐标 / Slate 逻辑尺寸 (非像素) / 像素包围盒 |
| `LayerId` | 图层 id, 当前实现恒为 `0`; 未识别节点为 `-1` |
| `Slot` / `SlotType` | 已识别槽的反射属性与槽类型名 (如 `UCanvasPanelSlot`) |
| `ExcludedSlotType` | 源控件的原始槽类名 (无 `U` 前缀), 与 `SlotType` 并存, 供对照排查 |
| `ExcludedWidgetType` | 仅 `UNDEFINE` 节点输出, 为 Slate 原始类型名 |
| `NewWidgetType` | 仅 `UNDEFINE` 且控件名含 `_C_` 时输出 `SObjectWidget` |
| `ParentWidget` | 父路径, 形如 `父##子`; `ChildNodes` 为子节点数组 |
| `ObjectData` | 源 UObject 的反射属性 (`LQADumpViewAdvanced` 第 2 个参数为 true 时输出) |
| `TextureData` | 图片控件的贴图元数据: `name` / `type` / `nameMD5` |
| `textStr` / `SourceString` / `TextKey` | 当前显示文本 / 源字符串 / 本地化键 (`Namespace,Key`; 无键时 `,INVALIDKEY`) |

### 使用时注意

- **单位不同** — `corners`/`BoxSize` 为视口像素, `LocalSize` 为 Slate 逻辑单位, 核对或还原时按 `meta.sizeX / 根节点.LocalSize.x` 归一化, 不要直接混用
- **包含视口外控件** — 采集范围是 Slate 中已排列的控件树, 被裁剪或位于视口外的控件仍会输出; 无子节点的 `UNDEFINE` 节点会被丢弃
- **列表/树控件类型名带模板参数** — 输出为 `ListViewT<ItemType>` / `TileViewT<ItemType>` / `TreeViewT<ItemType>`, 消费端按前缀匹配
- **截图包含调试面板** — `Dump` / `GetKey` 会遮挡左上角; 需要干净截图时以 `_BG.png` 为底, 但它比前景晚 1.2 秒, 动态场景下两者不完全同步
- **JSON 不含时间戳** — 同一界面连续两次 Dump 的 JSON 可以字节级一致, 截图差异来自场景动态或面板状态

---

## 扩展自定义控件与槽

默认只识别引擎内置的 UMG 控件与 Panel Slot: 自定义控件会以 `UNDEFINE` 导出 (若有子节点), 自定义槽会记录在 `ExcludedSlotType` 中, 按下面步骤登记即可纳入 JSON

### 先确认类型名

- **控件类型名** 取自 Slate 层 `SWidget::GetType()` (如 `STextBlock`, 不是 UMG 的 `UTextBlock`)
- **槽类型名** 取自 `UPanelSlot::GetClass()->GetName()` (如 `CanvasPanelSlot`)
- **名称带模板参数** (如 `SComboBox<FName>`) 时登记前缀, 并置 `bPrefixMatch = true`; 此类控件未登记时不会以 `UNDEFINE` 出现, 而是整体消失
- 最省事的确认方式: 先 Dump 一次, 从 `ExcludedWidgetType` / `ExcludedSlotType` 中读取真实类型名

### 新增采集控件 (4 步)

以新增 `SMyText` (对应 `UMyText`) 为例:

1. **新增枚举** — `Public/Snapshot/LQAWidgetNode.h` 的 `ELQAWidgetType` (注释 `项目自定义控件类型可在此处追加` 处):

```cpp
LQA_MyText,
```

2. **登记类型** — `Private/WidgetSlots/LQAWidgetTypeRegistry.cpp` 的 `GetEntries()`:

```cpp
{LQAWidgetNames::LQA_MyText, nullptr, ELQAWidgetType::LQA_MyText},
```

Slate 名常量统一在 `WidgetDefines.h` (声明) 与 `LQAWidgetNode.cpp` (定义) 的 `LQAWidgetNames` 中补一条, 值为 Slate 类型名, 若多个 UMG 控件共用同一个 Slate 根 (如 `SBox`), 每个 UMG 类各登记一条并填 `WidgetClass` 标签, 不保留无约束的同名兜底条目:

```cpp
{LQAWidgetNames::LQA_MyText, UMyText::StaticClass(), ELQAWidgetType::LQA_MyText, TEXT("MyText")},
```

3. **实现转换类** — 复制现有的 `LQA_TextBlock2Json.h/.cpp` 为 `WidgetSlots/Widget/LQA_MyText2Json.h/.cpp`, 改类名为 `FLQA_MyText2Json`, 并在 .cpp 中 include 自定义控件头文件后实现 `ToJson`:

```cpp
void FLQA_MyText2Json::ToJson(const TSharedPtr<FLQAWidgetNode> InWidget,
    const TSharedPtr<FJsonObject> OutJsonObject, TMap<FString, UTexture*>& SharedTextureMap)
{
    if (!InWidget.IsValid()) { return; }
    OutJsonObject->SetStringField(TEXT("WidgetType"), LQAWidgetNames::LQA_MyText.ToString());

    if (const UMyText* MyText = Cast<UMyText>(InWidget->SourceObject.Get()))
    {
        WriteTextEntry_ToJson(OutJsonObject, MyText->GetText());
    }
}
```

4. **工厂注册** — `Private/WidgetSlots/Widget2JsonFactory.cpp` 中 include 新头文件, 并在 `MakeWidgetData()` 的 switch 新增 case:

```cpp
case ELQAWidgetType::LQA_MyText:
    return MakeShareable(new FLQA_MyText2Json());
```

### 新增采集槽 (5 步)

以新增 `UMyPanelSlot` 为例:

1. **定义类型名** — `LQAWidgetNode.cpp` 的 `LQASlotNames` 命名空间, 值为 Slot 类名:

```cpp
const FName LQA_MySlot(TEXT("MyPanelSlot"));
```

2. **新增枚举** — `LQAWidgetNode.h` 的 `ELQASlotType`:

```cpp
LQA_MySlot,
```

3. **注册映射** — `GetSlotType()` 的 `SlotTypeMap`:

```cpp
{LQA_MySlot, ELQASlotType::LQA_MySlot},
```

4. **实现转换类** — 在 `WidgetSlots/Slot/` 下新增 `LQA_MySlot2Json.h/.cpp`, 继承 `FSlot2JsonInterface`:

```cpp
void FLQA_MySlot2Json::ToJson(const TSharedPtr<FLQAWidgetNode> InWidget,
    const TSharedPtr<FJsonObject> OutJsonObject)
{
    if (!InWidget.IsValid() || !InWidget->SourceObject.IsValid()) { return; }
    UWidget* SourceUwg = Cast<UWidget>(InWidget->SourceObject.Get());
    if (!SourceUwg) { return; }

    if (UMyPanelSlot* Slot = Cast<UMyPanelSlot>(SourceUwg->Slot))
    {
        TSharedPtr<FJsonObject> JsonObject = MakeShareable(new FJsonObject);
        if (FLQAJsonUtils::SerializeObjectToJson(JsonObject, Slot))
        {
            OutJsonObject->SetObjectField(TEXT("Slot"), JsonObject);
            OutJsonObject->SetStringField(TEXT("SlotType"), TEXT("UMyPanelSlot"));
        }
    }
}
```

5. **工厂注册** — `Private/WidgetSlots/Slot2JsonFactory.cpp` 中 include 新头文件, 并在 `MakeSlotData()` 的 switch 新增 case:

```cpp
case ELQASlotType::LQA_MySlot:
    return MakeShareable(new FLQA_MySlot2Json());
```

完成后重新生成工程并编译, 漏改的步骤可以这样确认: 新控件仍出现在 `ExcludedWidgetType` 中, 新槽仍出现在 `ExcludedSlotType` 中

---

## 常见问题

| 现象 | 原因与处理 |
| --- | --- |
| `Invalid world for r.EnableLQATool.` | 命令需在有 World 的运行时执行, 不能在编辑器未运行时使用 |
| `Failed to get ULQAManager instance.` | GameInstance 尚未创建或处于 PIE, 改用 Standalone 运行 |
| 命令或按钮无响应 | 确认插件已启用并编译成功, 通过日志分类 `LogLQATool` 过滤排查 |
| `r.EnableLQATool 1` 后看不到按钮 | 按钮位于屏幕左侧中部, 窗口过小或被其他全屏 UI 覆盖时检查布局 |
| 快照节点数与截图可见控件数不一致 | 采集包含被裁剪/视口外的控件, 无子节点的 `UNDEFINE` 节点会被丢弃; 以 `ExcludedWidgetType` / `ExcludedSlotType` 对照排查 |

---

## 代码规范

插件根目录的 `.clang-format` 定义了 UE C++ 代码风格规范

---