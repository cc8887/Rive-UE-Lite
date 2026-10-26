# 原生 UMG 动画支持评估

这是一份实现前的历史评估。当前实现、接口和实测状态见 [UMG 动画实现](umg-animation.md)。

日期：2026-10-26。依据独立原型固定 UE6 `62d7c1a7125b52b10ee1b714838f515f3563f795` 的源码和当前实际链接输入。本轮只做评估，没有实现动画写入、播放器或执行新的动画截图测试。

建议在现有可选 Widget Blueprint worker 中增加原生 `UWidgetAnimation + UMovieScene` 的读取、局部编辑、编译保存和时间点预览。默认 Rive 构建保持不变，沿用 `--with-widget-blueprint`，不需要再增加一个默认启用的动画运行环境。

## 当前缺口

`widget_bp.py` 只暴露控件描述和属性；`DescribeBlueprint` 没有枚举 `UWidgetBlueprint::Animations`、MovieScene 绑定、轨道、section 或关键帧。预览只创建实例、设为 `EWidgetDesignFlags::Designing` 并以 delta=0 调一次 `FWidgetRenderer::DrawWidget`。已有静态预览和蓝图图表保留测试，不构成动画保存/播放/保留证据。

现有编辑 worker 的真实响应文件已经包含 MovieScene、MovieSceneTracks、MovieSceneTools、Sequencer、SequencerCore 和 UMGEditor 的目标文件。应显式声明直接使用的 MovieScene/MovieSceneTracks 依赖，但这不等于再新引入同样规模的模块闭包；无需为编程写入轨道实例化整个 Sequencer 窗口。

## 建议交付范围

| 层次 | 首版内容 | 后续内容 |
| --- | --- | --- |
| 资产读取 | 动画名、内部对象名、时长、display rate/tick resolution、绑定 GUID、轨道/通道/键、插值与完成模式 | 动态绑定、子序列、时间扭曲等完整信息 |
| 资产写入 | 创建动画，修改现有动画的已支持轨道与关键帧；原生编译、SavePackage、重载 | 重命名/删除及跨继承层的引用迁移 |
| 首批属性 | RenderOpacity；RenderTransform 的平移、缩放、旋转 | 颜色、Canvas slot 布局、可见性、材质参数 |
| 时间控制 | 原生播放器，正向、反向、循环、停止/恢复状态；固定时间点与逐帧采样 | 多动画混合、添加/相对混合、权重与复杂 easing |
| 触发 | CLI 直接选择动画播放，不依赖先实现蓝图事件图编辑 | UEFN View Bindings、Verse/UI 交互触发 |

关键数据实际嵌在 Widget Blueprint 的 `.uasset` 内，通常不是新建一个独立 `.uasset` 动画文件。源 Blueprint 的 `Animations` 数组和编译后 `UWidgetBlueprintGeneratedClass::Animations` 必须都验证：编译器会克隆动画并生成 `_INST` 对象，不能把源对象名字直接当作运行时对象路径。

### 原生写入方法

1. 在 Blueprint 下创建 `UWidgetAnimation`，在动画下创建 `UMovieScene`，加入源 `Animations` 数组，设置时长和帧率。引擎自己的 Animation 面板也是这种对象结构。
2. 为目标控件/slot 建立 possessable 和 `FWidgetAnimationBinding`。绑定 GUID、WidgetName、SlotWidgetName 和 root 标志必须匹配；有曲线而没有正确绑定时，动画可能存在但不影响任何控件。
3. 不透明度使用原生 float track/channel；2D 变换使用 UMG 自身的 `UMovieScene2DTransformTrack/Section`，按通道 mask 修改平移、旋转或缩放，避免把没有编辑的轴重置为零/单位值。RenderTransform 位移与 Canvas 布局位置的语义不同，API 不应混用。
4. 关键帧内部使用整数帧与 `FFrameRate` 转换。DisplayRate 和 TickResolution 是不同概念，不能直接把“显示帧数”当作通道存储帧数。首版支持常量/线性，自动三次插值及切线随后单独验证。
5. 完整验证请求后再修改对象。复用现有备份、原生编译保存与失败恢复，不能把动画编辑当作直接修改 JSON 的离线动画模拟器。

### 读取和修改已有动画

先读取原来的动画、轨道、section、绑定和关键帧，再按明确目标局部更新；保留未编辑的 GUID、section 设置、其他动画、蓝图图表和成员变量。未知 track 类型标成只读并保留原对象，不要“导出支持字段再重建整段动画”，否则事件、材质轨道、插值切线或绑定信息可能丢失。

事件轨道、动态材质以及会执行项目脚本/访问 World 的轨道不放进首版自动预览白名单。这些数据可以读取/保留，播放语义需要独立验收。

## 首个验证门槛：无 World 的原生求值

这部分存在明确的前置条件，不能把当前静态截图成功直接推成动画可用：

- `UUMGSequenceTickManager::Get()` 把 tick manager 放在 `GEngine` 下；没有 GEngine 时会 ensure，并要求 fallback World。当前 worker 没有显式初始化 GEngine。
- 该快照中 `UUserWidget::PlayAnimation()` 返回 `FWidgetAnimationHandle`，配套 `FWidgetAnimationState`；旧 `UUMGSequencePlayer` 大量接口已弃用。新实现应优先沿用 handle/state。
- 普通 tick manager 在 Editor 中跳过 `IsDesignTime()` 控件；当前预览正处于该模式，需要单独设计动画预览求值路径。
- Play、seek 和 tick 可能只是向 MovieScene runner 排队。`SetCurrentTime()` 本身只更新播放时间，不代表新属性已经求值。必须调用对应原生更新并同步 flush，再进行 layout/paint/readback。

首个探针应尝试为 worker 提供最小的原生 engine owner，例如只构造 `UGameEngine` 对象而不执行游戏初始化、不创建 World/Viewport、不启动 Play/PIE。此方案尚未运行验证。MovieScene linker 本身允许空 outer 并回退到 TransientPackage，说明底层求值并非一概要求 World，但不能因此断言整条 UMG 播放路径已无 World 可用。

如果这一步不成立，再比较最小 preview World 与原生 MovieScene 专用预览上下文的代价；两条路线都应明确标记条件，不通过清除 ensure 或直接注入私有 tick-manager 指针来声称原生路径工作。

## 帧预览与验收

动画预览应有唯一的推进时间入口：在 game thread 显式推进原生动画和同步求值，然后以零 delta 绘制。不要同时推进 Slate 自动 tick、手动播放器和 Paint，避免动画走两遍。

需同时记录源属性和实例的实际求值属性，例如 `rendered_opacity`、`rendered_transform`、当前 qualified frame time 和绑定对象。当前 metadata 主要记录源属性及渲染几何，若只检查源关键帧而不检查实例，无法发现空绑定或未 flush。

验收至少包括：

- 原生创建 Fade + Slide/Scale → 保存 → 新进程重载，动画/绑定/关键帧一致。
- 在关键帧、中间值、末帧、循环边界采样，确认实际属性与画面都变化；测试 30/60/120 Hz 固定步进及端点包含规则。
- 正放、倒放、循环、暂停、停止和 restore-state；检查初始样式恢复、取消后无迟到写入、结束回调不重复。
- 在已有多轨动画中只修改一个通道，其他动画、未知轨道、绑定 GUID、蓝图节点/连线、变量和静态属性保持。
- 重复采样/销毁后没有残留 active state、Slate delegate 或 runner 引用，连续多次执行正常退出。
- 无 GPU llvmpipe 截图与原生 UMG 动画/Sequencer 参考对照。直接按公式手写 setter 的图只能作辅助检查，不能替代原生动画参考。
- 回到目标 UEFN 验证版本兼容和实际触发链；本地 `.uasset` 成功保存不等于 UEFN 已可导入或行为一致。

## 拟议接口（尚未实现）

```text
widget_bp.py animation list   --content-dir ... --asset /Game/UI/WBP_Card
widget_bp.py animation create --content-dir ... --asset ... --spec intro.animation.json
widget_bp.py animation patch  --content-dir ... --asset ... --patch intro.patch.json
widget_bp.py preview --content-dir ... --asset ... --animation Intro --time 0.5 --output frame.png
```

外部描述建议以用户帧率的整数帧为主要定位：

```json
{
  "name": "Intro",
  "fps": 60,
  "duration_frames": 60,
  "tracks": [
    {"widget": "Title", "property": "opacity", "interpolation": "linear",
     "keys": [{"frame": 0, "value": 0}, {"frame": 30, "value": 1}]},
    {"widget": "Title", "property": "render_translation", "interpolation": "linear",
     "keys": [{"frame": 0, "value": [0, 24]}, {"frame": 30, "value": [0, 0]}]}
  ]
}
```

## 工作量与成本

这是源码评估，不是已经测出的性能承诺。按一名熟悉 UE C++ 的工程师估计，首版约 **3–5 人日**：资产读取/创建/保存约 1–2 日；无 World 求值、原生逐帧截图和回归约 2–3 日。先给最小 engine owner/播放器探针半天到一天的验证窗口；若该路径必须引入 preview World，重新估算范围。

- 默认 Rive：设计上不增加动画依赖；实现后仍需重复依赖/包审计。
- 编辑 worker：MovieScene、Tracks、Sequencer 已在链接闭包内，预计主要增加接口/序列化/控制代码和资产数据；没有实测新增 MiB，不能把当前约 569 MiB 的 ELF 数字当作新增量或完整部署包。
- 日常修改动画键：应只进行原生资产编辑、蓝图编译保存和播放预览，不触发 C++ 或 shader 重编。新增 C++ 动画接口首次仍需编译/链接 worker。
- 淡入和普通 2D 变换预期复用现有 Slate 渲染路径；材质参数、特殊效果或新的目标平台应另验 shader/素材闭包。
- 启动/RSS/出图：初始化 engine owner、动画 manager/linker 后必须重新测。当前静态截图指标不能代替动画指标，批量采样也不能直接宣传为实时 FPS。

## 来源

- [原生动画创建](../engine/Engine/Source/Editor/UMGEditor/Private/TabFactory/AnimationTabSummoner.cpp)、[蓝图动画编译与克隆](../engine/Engine/Source/Editor/UMGEditor/Private/WidgetBlueprintCompiler.cpp)
- [WidgetAnimation](../engine/Engine/Source/Runtime/UMG/Public/Animation/WidgetAnimation.h)、[绑定结构](../engine/Engine/Source/Runtime/UMG/Public/Animation/WidgetAnimationBinding.h)
- [新动画状态](../engine/Engine/Source/Runtime/UMG/Public/Animation/WidgetAnimationState.h)、[状态实现](../engine/Engine/Source/Runtime/UMG/Private/Animation/WidgetAnimationState.cpp)、[tick manager](../engine/Engine/Source/Runtime/UMG/Private/Animation/UMGSequenceTickManager.cpp)
- [2D 变换 section](../engine/Engine/Source/Runtime/UMG/Public/Animation/MovieScene2DTransformSection.h)、[当前静态预览](../Source/RiveUmgBlueprintWorker/Private/BlueprintCapture.inl)
- [源码/现有链接输入审计](../artifacts/umg-animation-assessment/source-audit.json)
- Epic [UEFN UI Widget Editor](https://dev.epicgames.com/documentation/en-us/fortnite/ui-widget-editor-in-unreal-editor-for-fortnite) 与 [Animating UI](https://dev.epicgames.com/documentation/fortnite/aninmating-ui-in-unreal-editor-for-fortnite)。官方支持 UMG Sequencer 及 View Binding 触发流程；具体能力需按目标版本及接口另行验证。
