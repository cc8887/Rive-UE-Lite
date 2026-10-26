# 同项目的可选 UMG 构建方案

状态：构建开关、最小原生 UMG 宿主、独立 shader 对照及测量已经实现。实际接口和验收见 [宿主说明](../Source/RiveUmgHost/README.md) 与 [汇总](../artifacts/umg-optional/summary.json)。下文保留设计背景；独立 worker 仍是后续建议。

## 结论

可以在同一个 `.uproject` 和源码树中，默认只构建 Rive，在显式开启 UMG 后才构建、烘焙、打包其运行依赖。建议一个用户开关选择两个 Target，分别缓存构建结果；启用 UMG 的产物再用运行参数选择 Rive 或 UMG 路径。

这不要求先裁剪原生 UMG 的 Engine/Renderer 依赖，也不需要为这个开关修改引擎核心。UMG 的启动、合成、输入和无 GPU 截图仍是后续实际集成与验收工作。

| 用户选择 | 构建产物 | 可以运行的 UI 路径 | 包体依据 |
| --- | --- | --- | --- |
| 默认，UMG 关闭 | 现有 `RiveRhiLite` | Rive | 当前部署包 51.08 MiB，gzip 16.73 MiB |
| 构建时开启 UMG | 已新增 `RiveUmgHost` | Rive、UMG，及集成后的混合路径 | 本轮实测原始 186.11 MiB / 压缩 70.86 MiB |
| 已开启 UMG 的产物运行时选择 Rive | 仍是 `RiveUmgHost` | Rive | 不会因此变回精简包；Engine 初始化和内存节省不可预先保证 |

上表更新为当前实际应用包数据；系统 CPU Vulkan 驱动和依赖另计，不含 Designer。

## 开关与依赖边界

已实现的构建入口如下（需要 root 私有 mount namespace，实际 UBT 以 uid 1000 运行）：

```sh
sudo bash scripts/build_ui.sh                    # 默认只选择 RiveRhiLite
sudo bash scripts/build_ui.sh --with-umg         # 选择 RiveUmgHost
```

不要在同名 Target 上反复翻转全局 `WITH_ENGINE`，也不要让运行时 INI 决定是否编译 UMG。两个 Target 在相同项目下共享业务源码，但使用独立的中间产物、规则环境、最终程序和包目录。

| 层 | 默认 Rive | 开启 UMG |
| --- | --- | --- |
| Target | `bCompileAgainstEngine=false`、`bUsesSlate=false` | `bCompileAgainstEngine=true`、`bUsesSlate=true`、`bCompileAgainstEditor=false`，使用 Unique 构建环境 |
| 共享模块 | 协议、时间线、Rive RHI/RDG renderer；公共接口不暴露 UWidget/UUserWidget | 复用相同共享源码，按本 Target 的宏与 ABI 编译 |
| 可选模块 | 不进入依赖图、不处理其中的 UHT 类、不编译 | 已新增 `RiveUmgBridge`，拥有 UCLASS、UWidget/Slate 包装、布局与输入适配 |
| 引擎依赖 | 不引入 Engine/Renderer/UMG/Slate 等重依赖 | 加入 UMG、Engine、Renderer、Slate/SlateCore、SlateRHIRenderer 及其原生传递依赖 |
| shader 与资源 | 只用 Lite 自己的 Rive/utility archive 和资源清单 | 对本宿主注册的类型独立 cook，补全 Slate shaders、字体、实际使用的材质与资产 |
| 工具调度 | 不调用 Reference、原生 Engine cooker、UMG 编译/Designer 工具 | 显式调度需要的 cooker；运行已烘焙 WBP 与编译源 WBP 分开配置 |

默认路径不应调用目前会循环构建两个宿主的 `scripts/build_playback_hosts.sh`。原生 UE 独立 cooker 继续作为显式对照/验收任务，不让它成为每次 Lite 开发的前置步骤。

`RIVE_HOST_WITH_UMG` 可作为建议新增的项目局部编译宏，值由 Target 选择派生。Target 到 Build.cs 可使用已有 `AdditionalData`；模块依赖图也使用同一个选择来源。不要仅在 C++ 中包一层 `#if` 却仍在 Build.cs 无条件依赖 UMG，也不要只设置 `bUsesSlate=false` 便认为 Slate 模块不会链接。

桥接模块的反射类型应整体隔离在可选模块中，避免依靠任意自定义 `#if` 包围 UCLASS 声明。共享业务头不要含 UMG 类型、UMG 反射属性或 Engine 资产硬引用，否则轻量构建会再次被依赖拉回。

## 运行时行为

建议新增的统一协议提供编译能力列表，例如 Lite 的 `umg=false`，增强版的 `umg=true`。运行请求可选择 `rive` 或 `umg`；未编入 UMG 的程序收到 UMG 请求时返回清晰的能力缺失错误。

增强版中的 UMG 功能入口、控件树和相关应用资源可以延迟创建。不过，在单体增强版里，Engine/UMG 代码已链接，静态注册和部分引擎启动可能提前发生；运行时未调用 UMG 不等于没有 UMG 包体或完整内存成本。

shader 注册和 archive 加载必须遵守初始化顺序。不能假定当前的单个 `GGlobalShaderMap[Platform]` 可在第一次选择 UMG 时随意覆盖或拼接另一个 archive；增强版应在初始化前装入与其 shader 类型域匹配的完整 archive。两种构建和实际 cook 环境应参与缓存键，资源清单分开。

现有 `RiveLiteRenderer` 和 `RiveUeReferenceRenderer` 含同名渲染类及 Rive shader 类型。新宿主应选择或抽取一个共享 Rive renderer，不要同时链接两个副本。Reference 继续保留为独立对照端。向 UMG 暴露 Rive 时优先做桥接，保留原 RHI/RDG draw/flush 路径，合成像素需另验收。

## 真正运行中的动态扩展

当前两个宿主都是 Monolithic。ModuleManager 在该模式下只能初始化构建时已链接并注册的模块，不会为一个没编入的 UMG 临时加载完整模块库。

改成 Modular 也不能直接混用 `WITH_ENGINE=0` 的 CoreUObject 和 `WITH_ENGINE=1` 的 UMG：源码中 `UObject::GetWorld` 本身就是 `WITH_ENGINE` 条件虚函数，底层 ABI 和初始化条件不同。完整模块化插件需要统一底座的构建配置、依赖、反射、生命周期和 shader 注册；它不是本次最小开关方案。

如果要求主服务保持 Lite 进程、用户首次选 UMG 后无需重启主服务，建议独立 UMG worker：按需取得预编译增强包并启动，或者显式启动构建任务，之后通过同一请求协议路由到对应进程。完成构建、资产与 shader 准备后才能开始处理 UMG 请求；该方案不承诺瞬时启用，也不自动获得进程内纹理共享。

worker 退出可以交还它实际占用的内存；已下载的增强包仍占磁盘。独立增强包也可能重复底层引擎库，不能把两个完整包的差值直接当作可下载增量包的精确大小。

## 编译代价

首次开启 UMG 需要构建其依赖和 `WITH_ENGINE=1` 版本的部分公共模块、UHT 生成内容、shader 与资源。这不是在 Lite ELF 上补一个小模块。成功的完整冷构建耗时仍未测得。

独立 Target 和缓存保留后，在两种产物之间选择不应仅因翻转配置而反复污染同一组中间文件；源码、编译器或配置变化仍会让对应缓存失效。共享源码变动若两端都要发布，就需分别构建两种配置。

之前单个 Main.cpp 增量的历史观察为 Lite 52.41 秒、Engine/UMG 依赖参考端 229.27 秒，主要差异在链接和符号处理；这不是新增 UMG 宿主的计时。固定宿主支持的数据/`.riv` 修改可以不触发 C++ 构建；Widget Blueprint 修改仍有自己的编译/cook 流程。

## 后续最小验收

1. 默认构建的实际依赖图和链接输入排除 Engine、Renderer、UMG、Slate、SlateCore、SlateRHIRenderer、MovieScene、MovieSceneTracks；增强产物单独保存。
2. 默认包不含 UMG 资产和 Slate 内容，默认构建调度不启动 Engine/UMG 工具；已有 Rive 动画/状态机截图回归通过。
3. 增强版分别执行 Rive、原生 UMG 小控件树和 Rive/UMG 合成。无 GPU Linux 上与原生 UE 独立 cook 的对照一致；额外测量包体、RSS、首图时间。
4. Lite 收到 UMG 请求明确拒绝，增强版能力查询与路由正确；构建选择来回切换时不覆盖另一端的程序、archive 或资源。

## 当前源码依据

- [默认精简 Target](../Source/RiveRhiLite.Target.cs) 与 [精简模块依赖](../Source/RiveRhiLite/RiveRhiLite.Build.cs)。
- [现有 Engine 参考 Target](../Source/RiveUeReference.Target.cs)，其 `bUsesSlate=false`，并非完整 UMG 宿主。
- pinned UE source: `Engine/Source/Programs/UnrealBuildTool/Configuration/Rules/TargetRules.cs` (713–718, 1338–1351), `Engine/Source/Programs/UnrealBuildTool/Build/UEBuildTarget.cs` (7551–7554), `Engine/Source/Runtime/CoreUObject/Public/UObject/Object.h` (731–746), `Engine/Source/Runtime/Core/Private/Modules/ModuleManager.cpp` (1207–1267), `Engine/Source/Runtime/UMG/UMG.Build.cs` (9–65), and `Engine/Source/Runtime/Slate/Slate.Build.cs` (51–68).
- [原生 cooker 当前 shader 选择范围](../Source/RiveUeShaderCooker/Private/Main.cpp)：73–89；[当前 Lite archive 初始化](../Source/RiveRhiLite/Private/Main.cpp)：39–55、118–150。
- [此前容量与构建成本评估](../artifacts/umg-assessment/summary.json) 与 [当前 Lite 链接排除证据](../artifacts/playback/lite-linkage-01.json)。
