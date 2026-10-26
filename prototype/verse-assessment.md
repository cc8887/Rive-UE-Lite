# 接入 Verse 的成本评估

本文记录接入前阶段：固定 UE6 源码审计，以及独立的 Verse 编译器前端成本探针。该阶段没有接入完整 VM，其数字不可当作完整运行环境成本。后续已经增加可选 `--with-verse` 的真实 VerseVM worker、UI 出图和功能测试，当前实现与实际成本见 [VerseVM 最小链路](verse-vm.md)；下文保留历史测量范围。

## 目前可以确认的结论

Verse 编译器前端很轻，可以独立于 Engine、CoreUObject、Renderer、RHI 和 Slate 构建。完整 Verse 执行环境是另外一层：需要选 BPVM 或新 VerseVM，并准备代码生成、运行库、框架包和 UI 绑定。不能把前端探针的体积或毫秒数当作完整 Verse 接入成本。

现有两个渲染 Target 的实际定义都是：

```text
WITH_VERSE_BPVM=1
WITH_VERSE_VM=0
WITH_VERSE_COMPILER=0
```

这说明 Blueprint VM 的基础路径已经随 CoreUObject 存在，不代表已经提供可用的完整 Verse 语言环境。单独发现 `VerseVM/` 头文件或 bytecode 生成目录，也不能证明 VM 已启用。

## 新增探针实测

`VerseCoreCostProbe` 和 `VerseFrontendCostProbe` 共享同一个 Main.cpp 和同类 Core 启动流程。后者额外链接 VerseCompiler、uLangCore、uLangJSON 和 VerseProgramHostServices，并调用真实 CProgramBuildManager 的 parser/semantic analyzer。

| 指标 | Core-only | 加入前端 | 增量 |
| --- | ---: | ---: | ---: |
| stripped ELF | 4.92 MiB | 7.33 MiB | **2.40 MiB** |
| 同样 level-9 gzip 的 ELF | 2.10 MiB | 2.95 MiB | **0.85 MiB** |

这是两个实际 ELF 及其压缩结果，不是完整应用部署包；配置、框架、字节码、UI 绑定和系统库不在这组 ELF 容量数字中。组件增量可以作为只嵌入语法/语义校验功能的容量锚点，整合到现有宿主后的最终链接大小仍会有差别。

Linux affinity=2；每种情况 3 个独立进程，每个前端进程重新构造语义项目并检查 10 次变更后的内存源码。每个规模共 30 次检查，未复用已生成 AST 来跳过解析：

| 前端阶段 | 实测 |
| --- | --- |
| 初始化 uLang 和 build manager，不含 UE Core PreInit | 4.57–6.67 ms |
| 单个整数函数，解析 + 语义检查 | 中位数 0.22 ms；范围 0.12–8.44 ms，包含每进程首轮 |
| 1,000 个独立整数函数，解析 + 语义检查 | 中位数 23.19 ms；范围 17.90–43.08 ms |

独立 worker 的通用 UE Core 程序启动本身约 3.3–3.5 秒；两个程序的完整进程中位数约 3.48/3.58 秒，差异被环境/文件缓存波动淹没，不能宣称增加前端让进程启动变快。上面的约 5 ms 是在进程内单独计时的前端初始化阶段，不能直接加到旧首图时间上，称为已经测过的 Verse 首图增量。

探针明确记录 `bytecode_generated=false`、`vm_executed=false`。没有测 stdlib/import-heavy 项目、代码生成、链接字节码、加载实例、事务、执行 UI 逻辑或出图。

## 三种不同的接入成本

### 只加校验/补全前端

主要新增代码为上面的约 2.40 MiB stripped ELF 增量。可以放独立常驻 worker，避免每次改文本都支付通用程序启动成本。这只能完成前端检查，不能驱动 UI。

### BPVM 执行路径

当前 BPVM 基础开关已经打开，因此不应该把已有 CoreUObject/BPVM 全部重复计入增量。但还需 VerseNative、代码生成/加载、所用框架包以及本项目的 Rive/UMG 绑定。

官方 VerseTestScriptCmd 的 Program target 明确设置 `bCompileAgainstEngine=false`，说明完整命令行语言宿主在源码结构上有不引入 Engine/Renderer 的路线。直接启用整套 Solaris 插件则不同：其描述文件声明 GameFeatures 等插件依赖和 Program 白名单，不能等同于最小语言宿主。

运行已编译脚本与在同进程编译源码也不同。CoreUObject、Solaris 和 VerseNative 的 WITH_VERSE_COMPILER 规则通常由 EditorOnlyData/Server 条件决定。现有渲染 Program 不应为了打开编译器就改成 UE Server：云服务器的部署环境不是 UE Server Target，后者会编译掉部分 UMG 绘制路径。编译服务和渲染宿主应分开配置。

本轮没有完成 BPVM 运行库/绑定集成，其新增包体和启动时间仍未测，不能用前端的 2.40 MiB 代替。

### 新 VerseVM

固定源码把新 VM 标为 experimental、target opt-in。`bUseVerseBPVM=false` 会启用另一组 CoreUObject/序列化/GC 条件代码；SetupVerse 引入 libpas，官方 VM 测试 Target 还开启 AutoRTFM 编译器。

新 VM 的启动包括 heap、全局类型、intrinsics、GC 线程及事务状态。进入 VM 要求 FrankenGC，并要求顶层在 game thread 执行。现有 Rive draw 回调位于 render thread，不能直接把 Verse 解释器调用塞进去；应在 game thread/语言 worker 执行，再把数据/命令提交给 Rive/UMG。

源码中的 `verse.ForceCompileFramework` 默认值为 WITH_VERSE_VM。Solaris 的 cooked-package hot-reload 函数也有新 VM server 路径假定框架在启动时已经编译的注释和检查。这不证明所有新 VM 路径都不能预编译，但意味着低延迟方案必须先验证框架缓存/预编译与实际加载路径，不能简单关一个 CVar 就承诺快速启动。

所以开启新 VM 应作为独立 Target/cache 变体；首次可能重建 CoreUObject 及其依赖，不能按“只新增一个小模块”计算。完整 VM 的包体、首图和成功冷构建时间本轮均未测。

## 编译时间应怎样理解

现有 UI 宿主的单 Main.cpp 编译加完整链接基线仍为 Rive 51.32 秒、UMG 177.11 秒。这是此前真实缓存构建结果，本轮二进制未改，也没有测“整合 Verse 后”的 C++ 重链成本。

普通 `.verse` 修改，在接口和既有 native bindings 不变时，可以走语言编译、代码生成与加载，不必触发 C++/UHT 或 Rive shader 重编。前端探针展示了其中一个很小的阶段，但端到端还要加上未测的代码生成/加载/执行成本。变更 native bindings、VNI/UHT 或 VM 全局编译开关仍可能触发 C++ 重建。

如果仍按每次启动一个新渲染进程截图，现有 UE/RHI/字体等首图成本仍然存在；要改善日常编辑响应，编译和渲染都宜常驻，而不能把 23 ms 的语义检查宣称为 23 ms 出图。

## 现阶段建议（2026-10-26：目标明确为 UEFN）

目标明确为 UEFN 后，修正此前仅按现有依赖推荐 BPVM 优先的顺序：独立语言宿主以新 VerseVM 为主线，BPVM 保留为 UEFN 当前路径的兼容对照。这里的“主线”是原型架构建议，不代表 UEFN 已完成新 VM 默认切换，也不代表已经实测新 VM 更小或更快。

Epic 的 [UEFN 42.40 官方发布说明](https://dev.epicgames.com/documentation/fortnite/42-40-fortnite-ecosystem-updates-and-release-notes?lang=en-US)（2026-10-15）明确说明：Session 菜单可选择新 VerseVM 服务器来测试岛屿；该模式尚不支持 Verse Reload，Live Edit 也尚未完整支持，当前只有 BPVM 会通过 Live Edit 向服务器传送 Verse 属性。因此，要对照今天的 UEFN 编辑迭代体验，仍需保留 BPVM 会话验证；不能用新 VM 测试结果代替全部既有会话行为。

本地固定源码提供 `VerseCmd` 和 `VerseTestScriptCmdVM` 两种无 Engine 的新 VM Program 路线。编译器 `SBuildParams::EWhichVM` 明确区分两个后端。现有渲染 Target 的 `WITH_VERSE_BPVM=1` 仅说明这些自定义 Target 的配置，不能据此判定所有 UEFN/Fortnite 版本采用哪种 VM。前端可共用，执行产物应按 VM、引擎版本、语言版本和 native API 版本分别缓存；本轮没有证明两个 VM 的字节码/包可以互换。

保留默认 Rive 的构建与包边界。后续已实现 `--with-verse` 显式构建独立 VerseVM worker/Target；`--verse-backend=bpvm` 仍只是候选方案，没有实现。不要在同一个已链接的渲染二进制里热切换 CoreUObject/GC 的 VM 编译配置。语言 worker 向渲染宿主提交 UI 数据/命令，VM 的 game-thread 入口条件在 worker 内仍须满足。

UEFN 兼容目标应先限定为“同份 Verse 业务源码，通过对应 native API 适配在两端运行”。[官方 UI 文档](https://dev.epicgames.com/documentation/en-us/fortnite/ingame-user-interfaces-in-unreal-editor-for-fortnite)将 Verse 交互和 UMG 界面设计作为相互配合的两层，UI 按玩家关联；因此只有 VM 和标准库不足以运行实际 UEFN UI。需要按目标 UEFN 版本补上所用 player/UI API、事件和调度行为，再回到真实 UEFN 会话对照。此前 UE 原生截图一致不构成 UEFN 验收，也没有证明自定义 Rive UWidget 能直接装进 UEFN。

下一步最小验收：同份 Verse 源码完成点击事件、状态变量、挂起/恢复与取消、失败上下文回滚，并驱动同一组 UI 状态；在本地新 VM、UEFN BPVM 会话及 UEFN 新 VM 测试会话中比较事件轨迹和最终状态。UI 布局/像素对照另在 UEFN 实际支持的 widget 路径中完成。Fortnite 的设备、玩家和联机原生服务未实现时要标明缺失，不能靠空桩把整个 UEFN 工程标成可运行。

在完整链路测出之前，可以确定前端是数 MiB 级组件，而不能可靠给出“完整 Verse 会增加 X MiB / Y 秒”。若采用独立 worker，渲染应用自身可保持目前包体级别；整机总部署量还要增加该 worker 的实际包，不能把这部分计成零。

## 复现与证据

```sh
sudo bash scripts/build_linux_cached.sh VerseCoreCostProbe \
  -Log="$PWD/artifacts/verse-assessment/core-build-new.log"
sudo bash scripts/build_linux_cached.sh VerseFrontendCostProbe \
  -Log="$PWD/artifacts/verse-assessment/frontend-build-new.log"
python3 scripts/measure_verse_frontend.py \
  --output-dir artifacts/verse-assessment/frontend-metrics-new
```

- [结构化评估](../artifacts/verse-assessment/assessment.json)、[实际前端测量](../artifacts/verse-assessment/frontend-metrics-01/report.json)
- [Core/前端共同宿主](../Source/VerseCostProbe/Private/Main.cpp)、[模块规则](../Source/VerseCostProbe/VerseCostProbe.Build.cs)
- [原生插件源码快照及哈希](../artifacts/verse-assessment/source-snapshots/manifest.json)，来自同一个固定 UE commit，不写入原 UE 工程
- [VM 源码说明](../engine/Engine/Source/Runtime/CoreUObject/Public/VerseVM/README.md)、[CoreUObject 构建规则](../engine/Engine/Source/Runtime/CoreUObject/CoreUObject.Build.cs)、[编译器规则](../engine/Engine/Source/Runtime/VerseCompiler/VerseCompiler.Build.cs)
- [官方无 Engine 测试宿主](../engine/Engine/Source/Programs/VerseTestScriptCmd/VerseTestScriptCmd.Target.cs)、[新 VM 变体](../engine/Engine/Source/Programs/VerseTestScriptCmd/VerseTestScriptCmdVM.Target.cs)
- [VM 进入条件](../engine/Engine/Source/Runtime/CoreUObject/Public/VerseVM/Inline/VVMEnterVMInline.h)、[框架编译开关](../engine/Engine/Source/Runtime/CoreUObject/Private/VerseVM/VVMCVars.cpp)
