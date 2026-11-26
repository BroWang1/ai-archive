# LQATool 插件

![Version](https://img.shields.io/badge/version-1.0.0-blue)
![Supported Platforms](https://img.shields.io/badge/platform-Win64%20|%20Mac%20|%20iOS%20|%20Android-lightgrey)
![License](https://img.shields.io/badge/license-Apache%202.0-blue)

---

## 简介

**LQATool** 是由 *IEG互动娱乐事业群/天美工作室群* 开发的一个 Unity 引擎插件, 是本地化 UI 质检流水线的 **上游采集端**: 它在游戏运行时把当前画面的 UI 节点树、文本属性、字体、可见性与截图采集下来, 导出为 **Dump 数据**, 供下游 **LQARestore** 还原端重建画面并对接 **LQA 平台** 做检测, 服务于本地化 UI 质量检查

- **本插件 (LQATool)**: 运行时自动常驻 (无需手动挂载), 通过悬浮 UI 按钮或 F9 热键一键 Dump; 采集时冻结画面同帧输出 `ScreenShot_Full.png` (含文本) 与 `ScreenShot_NoText.png` (无文本背景图), 借助文本 ID 染色图与像素差分判定每个文本是否真正可见, 并遍历场景 Canvas 导出 UI 节点树 JSON (`ui_data_all.json` / `ui_data_text.json`, 含分辨率、语言、屏幕方向、安全区、画质、颜色空间等环境元数据), 输出到 `persistentDataPath/LQATool/UIDump_<时间戳>/`; 另支持长按拾取最近文本节点查看详情, 以及按图层拆分截图等可选调试输出
- **下游 (LQARestore)**: 读取本插件产出的 Dump, 把文本节点树 1:1 重建到还原场景中, 叠加在无文本背景图之上, 截图输出 `Restore.png`, 并导出文本框 `rect_locations.json` 供平台检测使用

---

## 使用说明

### 1. 开启工具

插件随游戏启动自动常驻, 但默认 **不显示**, 两种开启方式任选其一:

| 方式 | 做法 | 生效时机 |
| --- | --- | --- |
| PlayerPrefs 开关 | `PlayerPrefs.SetInt("LQA_ShowDumpAndGetNodeButtons", 1); PlayerPrefs.Save();` | **下次启动游戏** 时生效 (该值只在启动时读取一次), 适合接到 GM 面板 |
| 运行时接口 | `LQATool.Core.LQATool.SetEnable(true);` (传 `false` 关闭) | **立即生效**, 适合接到调试菜单 |

开启后, 屏幕 **左侧垂直居中** 处会出现两个半透明黑底按钮: **`Dump`** 和 **`GetNode[off]`**, 它们始终在所有游戏 UI 的最上层 (Canvas `sortingOrder = 32767`), Dump 截图时会自动隐藏, 不会被截进去

![悬浮按钮](docs/images/usage_tool_buttons.png)

### 2. 一键 Dump (采集当前画面)

#### 2.1 操作步骤

1. 进入要做本地化检查的界面, 等界面动画播完、画面稳定
2. 点击 **`Dump`** 按钮, 或按键盘 **F9** (方便 PC / Editor 使用)
3. Dump 过程中会:
   - 暂停游戏时间 (`Time.timeScale = 0`), 保证几张截图是同一帧
   - 短暂隐藏工具按钮
   - 依次截图、判定文本可见性、导出 JSON
4. 完成后按钮重新出现, 游戏恢复运行, Console 输出:

   ```
   [LQATool][UIDumpService] 转储完成! 路径: <输出目录>
   ```

![Dump 完成日志](docs/images/usage_dump_console.png)

> 防重复触发: 上一次 Dump (包括延时等待阶段) 没结束前, 再点按钮或再按 F9 都会被忽略

#### 2.2 延时 Dump (可选)

有些画面只有在手指按住、鼠标悬停时才会出现 (如 Tips、长按弹窗), 或者手机上需要先关掉 GM 面板, 这时可以设置延时:

```csharp
// 点击 Dump 后等待 N 秒再开始采集 (按真实时间计, 不受 timeScale 影响), 0 表示立即采集 (默认)
PlayerPrefs.SetInt("LQA_DumpDelaySeconds", 3);
PlayerPrefs.Save();
```

触发后 Console 会提示 `[LQATool] Dump 将在 N 秒后开始采集...`, 在这段时间里把画面切到目标状态即可

### 3. 获取 Dump 产物

每次 Dump 都会生成一个带时间戳的独立目录:

```
Application.persistentDataPath/LQATool/UIDump_yyyy_MM_dd_HH_mm_ss/
```

各平台 `persistentDataPath` 的常见位置 (以 Console 日志打印的实际路径为准):

| 平台 | 路径 | 取出方式 |
| --- | --- | --- |
| Windows (Editor / 包体) | `%USERPROFILE%\AppData\LocalLow\<CompanyName>\<ProductName>\` | 直接在资源管理器打开 |
| macOS (Editor / 包体) | `~/Library/Application Support/<CompanyName>/<ProductName>/` | Finder → 前往文件夹 |
| Android | `/storage/emulated/0/Android/data/<包名>/files/` | `adb pull` (见下方) |
| iOS | `<App 沙盒>/Documents/` | Xcode → Devices and Simulators → 下载 App Container; 或开启 `UIFileSharingEnabled` 后用 Finder / iTunes 文件共享导出 |

Android 一次拉取全部 Dump:

```bash
adb pull /storage/emulated/0/Android/data/<包名>/files/LQATool ./LQATool_Dump
```

![输出目录](docs/images/usage_output_folder.png)

### 4. 产物文件说明

| 文件 | 默认是否生成 | 控制开关 | 用途 |
| --- | --- | --- | --- |
| `ScreenShot_Full.png` | 是 | 始终生成 | 完整画面 (含文本), **下游必需** |
| `ScreenShot_NoText.png` | 是 | 始终生成 | 隐藏所有文本 (含 Shadow / Outline、TMP 子网格) 后的背景图, **下游必需** |
| `ui_data_text.json` | 是 | `EmitTextUIDataJson` | 只保留含文本 / 图片的节点及其祖先的 UI 节点树, **下游主要读取它** |
| `ui_data_all.json` | 否 | `EmitFullUIDataJson` | 全量 UI 节点树 (字段与上面相同, 只是不剪枝) |
| `ScreenShot_TextId.png` / `ScreenShot_TextId_Pure.png` | 是 | `EmitTextIdMapDebug` | 文本 ID 染色图, 每个文本一种颜色, 用来人工核对文本足迹 |
| `ScreenShot_VisDebug.png` | 是 | `EmitVisibilityDebug` | 可见性判定结果叠加图 |
| `ScreenShot_Only_<Layer>.png` / `ScreenShot_BG.png` | 否 | `EmitLayerScreenshots` | 按 `UILayerNames` 分层渲染的截图, 纯调试用, 下游不读取 |

#### 4.1 JSON 环境元数据

两份 JSON 的根对象都带有 Dump 那一刻的环境信息, 供还原端复现相同环境:
`sceneName`、`appVersion`、`unityVersion`、`screenWidth` / `screenHeight`、`screenDpi`、`systemLanguage`、`orientation`、`safeArea`、`qualityLevel` / `qualityLevelName`、`colorSpace`、`targetFrameRate`、`activeLayerNames`, 节点树放在 `nodes` 中

![Full vs NoText](docs/images/usage_full_vs_notext.png)

![TextId 染色图](docs/images/usage_textid.png)

#### 4.2 查看可见性判定图 `ScreenShot_VisDebug.png`

在完整截图上, 每个文本的包围盒会按判定结果描上不同颜色的边框:

| 边框颜色 | 判定 | 含义 / 处理建议 |
| --- | --- | --- |
| 绿色 | 可见 | 文本与背景差异明显 |
| 黄色 | 可见 (临界) | 差异像素很少, 建议人工复核 |
| 红色 | 不可见 | 有足迹, 但差异占比低于 `PixelDiffMaskVisibleRatio` (被遮挡 / 没画出来) |
| 紫色 | 不可见 | 足迹被其它文本覆盖 (文字互相重叠) |
| 青色 | 不可见 | 足迹太弱 (小字号 / 细笔画), 可调低 `PureMaskAlphaThreshold` (如 64) |
| 灰色 | 不可见 | 足迹为空 (被裁剪 / 没渲染 / 被非文本图形挡住) |

![可见性判定图](docs/images/usage_visdebug.png)

### 5. 长按拾取文本节点 (GetNode)

用于在游戏里 **现场查看** 某段文字对应的节点路径、文本内容、本地化 Key 等信息, 不需要先 Dump

#### 5.1 操作步骤

1. 点击 **`GetNode[off]`** 按钮, 按钮变成绿色 **`GetNode[on]`**, 表示拾取已开启
2. 在要查看的文字附近 **按住不动 1 秒** (鼠标左键或单指)
3. 按住的位置旁弹出信息面板, 显示 **离按住点最近的文本节点** (按文本矩形中心点距离计算, 只算屏幕内、处于激活状态且内容不为空的 Text / TMP)
4. 再次点击 / 触摸屏幕任意位置, 面板关闭
5. 再点一次 `GetNode[on]` 即可关闭拾取

![GetNode 开启](docs/images/usage_getnode_on.png)

![节点信息面板](docs/images/usage_getnode_panel.png)

#### 5.2 面板字段

| 字段 | 说明 |
| --- | --- |
| `Name` (括号内为主组件类型) | GameObject 名称 |
| `Path` | 节点在 Hierarchy 中的完整路径, 可直接据此在工程里定位 |
| `Text` | 当前显示的文本内容 |
| `KeyHash` | 本地化 Key (需要接入项目, 完成长按详情的适配后才会显示) |
| `AnchoredPosition` / `SizeDelta` | RectTransform 布局信息 |
| `FontStyle` / `FontSize` / `Alignment` / `HorizontalOverflow` / `VerticalOverflow` | **仅 UGUI `Text`** 显示, TMP 文本不显示这几项 |

> 注意: 拾取 **不会拦截** 游戏输入, 如果长按的位置正好在游戏按钮上, 松手时可能触发该按钮的点击, 建议按在文字旁边的空白处 (面板显示的是 "最近" 的节点, 不必精确按在文字上)

---

## 常见问题

**Q: 已经设置 PlayerPrefs 为 1, 但按钮没出现?**
A: 这个值只在游戏启动时读取一次, 需要重启游戏; 或改用 `LQATool.Core.LQATool.SetEnable(true)` 立即开启, 也可以检查 Console 是否有 `[LQATool] 工具已按 PlayerPrefs 配置禁用` 日志

**Q: 开启后 Console 不停报 `InvalidOperationException: You are trying to read Input using the UnityEngine.Input class...`?**
A: 插件的 F9 热键和长按检测用的是旧版 `UnityEngine.Input`, 如果工程的 `Player Settings → Active Input Handling` 只选了 `Input System Package (New)`, 请改成 `Both`

**Q: 按钮点不动?**
A: 插件会在场景里没有 EventSystem 时自动补一个; 如果工程自己的 EventSystem / 输入模块被禁用或拦截了事件, 请检查它的状态, 或者直接用 F9 热键 Dump

**Q: 很多文本被判为不可见 (红 / 青 / 灰框)?**
A: 按 `ScreenShot_VisDebug.png` 的颜色对照表格排查: 青色多就调低 `PureMaskAlphaThreshold`, 红色多但肉眼明显可见就调低 `PixelDiffMaskVisibleRatio` 或 `PixelDiffColorThreshold`

**Q: 截图里有动画残影或文本位置不对?**
A: Dump 时虽然会把 `timeScale` 设为 0, 但用 unscaled time 驱动的动画 / Tween 仍会继续播放, 请等界面动画播完后再 Dump, 必要时配合 `LQA_DumpDelaySeconds` 延时

---

## 接入项目

LQATool 本体与具体游戏工程 **解耦**: 通用 Unity 组件 (Canvas / Text / Image / TMP 等) 已内置支持, 无需改动; 你只需针对本工程做三处适配 —— **配置 UI 图层**、**适配项目专属组件**、**(可选) 调优阈值与输出开关**, 下面按步骤引导

### 1. 安装与启用

1. 将本插件目录放入工程 `Assets/` 下任意位置 (如 `Assets/Plugins/LQATool/` 或 `Assets/LQATool/`) 即可; 脚本会自动编入 `Assembly-CSharp` 参与编译, 无需额外配置
2. 插件通过 `[RuntimeInitializeOnLoadMethod]` 在首个场景加载后 **自动常驻**, 无需手动挂载任何脚本
3. 默认是否显示悬浮按钮由 `PlayerPrefs` 控制, 默认关闭, 启用方式:

   ```csharp
   // 1 = 启用 (显示 Dump / GetNode 悬浮按钮), 0 = 禁用
   PlayerPrefs.SetInt("LQA_ShowDumpAndGetNodeButtons", 1);
   PlayerPrefs.Save();
   ```

   启用后, 运行时点击悬浮按钮或按 **F9** 即可一键 Dump, 产物输出到 `Application.persistentDataPath/LQATool/UIDump_<时间戳>/`

### 2. 配置本工程的 UI 图层

打开 `Config/LQAUILayerConfig.cs`, 把本工程需要单独分层截图的 UI Layer 名添加到 `UILayerNames` 中, 插件会对其中每个 Layer 单独渲染分层截图, 未列入的图层合并为背景图; 列表中不存在的 Layer 名会被自动跳过并打印警告

```csharp
public static readonly List<string> UILayerNames = new List<string>
{
    "UI",
    // 添加你工程里的图层名, 例如:
    // "UI_HUD",
    // "UI_Popup",
};
```

### 3. 适配项目专属组件 (关键步骤)

游戏里常见两类 **项目专属脚本** 需要导出, 供下游 LQARestore / LQA 平台使用:

- **本地化组件**: 导出文本的翻译 Key / Hash, 用于反查原文与译文
- **富文本组件**: 导出描边 / 阴影 / 特效等视觉参数, 供还原端 1:1 复刻

主要适配集中在 `Services/ProjectCustomExtractors.cs`, 通过「**字符串类型名 + 反射读字段**」注册, **不需要** 让插件直接引用你的工程程序集; 若目标类型在当前工程不存在, 会被静默跳过, 不影响其它功能

> 另有一处 (长按拾取详情): 若希望 **长按拾取节点的实时详情面板** 也显示本地化 Key, 还需同步修改两个标注 `Project-Specific` 的代码段 —— `Services/UIDumpService.GetNode.cs` (反射读取并写入该键) 与 `UI/LQAToolUIManager.Display.cs` (读取该键并显示), 把其中的组件名 (`XxxxLocalize`) 与字段名 (`keyHash`) 改成你自己的, ⚠️ 两处键名必须保持一致, 否则详情面板读不到 Key, 该路径独立于主 Dump 流程, 只服务于拾取详情显示

#### 3.1 先查出组件的字段名

你多半不清楚自己组件里字段叫什么 (`keyHash` / `m_Key` / `localizeId` …), 在提取器回调里临时调用 `DumpAllFieldsForDebug`, 运行一次 Dump 即可在 Console 看到该组件的全部字段名、类型与当前值:

```csharp
ComponentExtractors.RegisterByTypeName("你的本地化组件类名", (comp, node) =>
{
    // 临时调试: 打印该组件所有字段 (映射完成后请删除)
    DumpAllFieldsForDebug(comp);          // 只看脚本自身字段
    // DumpAllFieldsForDebug(comp, true); // 连 Unity 基类字段一起看
});
```

#### 3.2 注册本地化组件

把 `RegisterXxxxLocalize` 换成你自己的组件名与字段名, 类型名可用短名 (`Type.Name`) 或带命名空间的全名 (`Type.FullName`, 用于避免重名冲突):

```csharp
private static void RegisterMyLocalize()
{
    ComponentExtractors.RegisterByTypeName("MyLocalizeComponent", (comp, node) =>
    {
        // 用 object 兜底, 兼容 string / int / long 等各种哈希类型
        if (!TryGetFieldValue<object>(comp, "你的Key字段名", out var val) || val == null) return;

        string s = val.ToString();
        if (string.IsNullOrEmpty(s)) return;

        // 写入 ObjectData["MyLocalize"]["keyHash"] = "\"xxxx\""
        // 外层双引号是 JSON 字符串字面量的一部分
        node.AddComponentProperty("MyLocalize", "keyHash", $"\"{s}\"");
    });
}
```

#### 3.3 注册富文本/视觉组件 (可选)

借助 `CustomExtractorHelpers` 提供的类型化写入方法, 导出描边/阴影等参数, 建议优先读运行时的 `Current*` 实际值, 比读原始序列化字段更贴近玩家真正看到的效果:

```csharp
private static void RegisterMyRichText()
{
    ComponentExtractors.RegisterByTypeName("MyNamespace.MyRichText", (comp, node) =>
    {
        const string K = "MyRichText"; // 组件键名, 与下游 JSON 约定一致

        // 枚举: 用基类 Enum 接住, 避免硬引用具体枚举类型
        if (TryGetFieldValue<Enum>(comp, "TextEffectType", out var effectType))
            AddEnum(node, K, "textEffectType", effectType);

        // 颜色 (RGBA)
        if (TryGetFieldValue<Color>(comp, "CurrentOutlineColor", out var outlineColor))
            AddColor(node, K, "outlineColor", outlineColor);

        // Vector2 (像素偏移)
        if (TryGetFieldValue<Vector2>(comp, "CurrentOutlineDistance", out var outlineDistance))
            AddVector2(node, K, "outlineDistance", outlineDistance);
    });
}
```

#### 3.4 挂到注册入口并清理调试代码

在 `RegisterAll` 中登记你的注册方法, 并在确认字段映射正确后删除所有 `DumpAllFieldsForDebug` 调用 (否则每次 Dump 都会反射刷屏):

```csharp
internal static void RegisterAll()
{
    RegisterMyLocalize();
    RegisterMyRichText();
}
```

> 可直接复用的辅助方法 (均在 `CustomExtractorHelpers` 中):
> `TryGetFieldValue<T>(comp, "字段名", out value)` 反射读字段;
> `AddEnum / AddColor / AddVector2(node, 组件键, 属性键, 值)` 类型化写入;
> `node.AddComponentProperty(组件键, 属性键, JSON字面量)` 写任意原始 JSON 值;
> `DumpAllFieldsForDebug(comp)` 开发期打印全部字段
>
> 文本内容本身 (UGUI `Text` 与 TMP) 已由 `Utils/TextLike.cs` 自动适配, **无需** 额外注册; 仅当你的文本组件既不继承 `UnityEngine.UI.Text` 也不继承 `TMP_Text` 时才需扩展该文件

### 4. 阈值与输出开关调优 (可选)

`Config/LQAUILayerConfig.cs` 中的其余参数一般保持默认即可, 按需微调:

| 配置项 | 默认值 | 说明 / 何时调整 |
| --- | --- | --- |
| `PixelDiffMaskVisibleRatio` | `0.10f` | 文本 "可见" 所需的差异像素占比; 误判太多可上调, 漏判可下调 |
| `PixelDiffColorThreshold` | `12` | 单像素颜色差异显著阈值; 值越小越敏感 |
| `PureMaskAlphaThreshold` | `128` | 文本足迹最小 alpha；小字号/细笔画中文误判为不可见时可调低 (如 64) |
| `EmitTextIdMapDebug` | `true` | 是否另存文本 ID 染色图, 便于人工核对足迹 |
| `EmitVisibilityDebug` | `true` | 是否输出可见性判定可视化叠加图 `ScreenShot_VisDebug.png` (颜色含义见使用说明) |
| `EmitFullUIDataJson` | `false` | 是否落盘全量节点树 `ui_data_all.json` |
| `EmitTextUIDataJson` | `true` | 是否落盘文本/图片剪枝版 `ui_data_text.json` |
| `EmitLayerScreenshots` | `false` | 是否落盘分层/背景截图 (纯调试产物, 下游不消费) |

### 5. 验证接入是否成功

运行游戏 → 启用工具 → 按 **F9** 或点击悬浮按钮 Dump, 然后检查输出目录 `Application.persistentDataPath/LQATool/UIDump_<时间戳>/`:

- `ScreenShot_Full.png` (含文本)、`ScreenShot_NoText.png` (无文本背景图) 正常生成;
- `ui_data_text.json` (及按开关生成的 `ui_data_all.json`) 中, 对应节点下 **出现你注册的组件键** (如 `"MyLocalize"`、`"MyRichText"`) 及其属性, 即说明项目专属组件接入成功

---