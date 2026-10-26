# 可选 VerseVM：最小 UI 链路与实测

日期：2026-10-26。固定 UE6 commit `62d7c1a7125b52b10ee1b714838f515f3563f795`。实现和证据均位于独立原型；没有修改原 UE/Rive 仓库或现有 UE 工程。

## 当前行为

默认 `build_ui.sh` 仍只构建 `RiveRhiLite`。显式 `--with-verse` 增加独立的 `RiveVerseWorker` Program：`WITH_ENGINE=0 / WITH_VERSE_VM=1 / WITH_VERSE_BPVM=0 / WITH_VERSE_COMPILER=1`。Rive 渲染二进制保留原来的 BPVM 基础编译配置，但不链接可用的 Verse 语言运行库、编译器或 worker。两种 CoreUObject/GC 配置不混入同一个进程。

worker 基于本快照的官方 `VerseCmd` 宿主复制、改名并加阶段计时；保留官方源码版权。使用真实 Solaris/uLang 编译、VerseVM codegen、原生标准库、libpas、FrankenGC 和 AutoRTFM，没有把解释器替换成 Python 或模拟 AST 执行。移除这个最小用例不需要的 VerseSpatialMath 依赖。官方宿主的 IO/Yield/Exit API 是本地适配器能力，不代表 UEFN 提供相同接口。

执行链是：

```text
同一份 ui_controller.verse + 本地 worker_main.verse
  → 真实 VerseVM 编译/加载/执行
  → 提交一条 Pressed=true/false UI 命令
  → Python 校验协议并映射到 Rive 的 Press 输入
  → 现有 UE RHI/RDG 渲染宿主
  → CPU Vulkan PNG + 实际状态机元数据
```

这是批处理桥接原型。事件由测试适配器注入；没有实现原生 UI 点击回传、常驻编辑会话、UEFN 玩家对象或 Fortnite 设备模拟。共享控制器没有依赖 worker 专用原生 API；同源代码在 UEFN 中仍需编译和运行验证。

## 构建与运行

从 WSL Ubuntu 的原型根目录执行；构建所需私有 mount namespace 由 root 建立，UBT 降权为 uid 1000：

```sh
# 默认只构建 Rive，不准备 Verse 工具/框架，不构建 worker。
sudo bash scripts/build_ui.sh

# 构建 Rive + 独立 VerseVM worker。
sudo bash scripts/build_ui.sh --with-verse

# 不执行构建的选择检查。
bash scripts/build_ui.sh --plan
bash scripts/build_ui.sh --with-verse --plan

# 当前已打包产物，pressed / idle 各用一份原样共享源码。
sudo bash scripts/check_verse_portable.sh \
  package/verse-ui-02 artifacts/verse-vm/my-pressed-run
sudo bash scripts/check_verse_portable.sh \
  package/verse-ui-02 artifacts/verse-vm/my-idle-run --mode idle
```

输出目录必须是新的目录。部署在真正无 GPU 的 Linux 上时可直接用 `bash package/verse-ui-02/verse-ui.sh --output-dir /absolute/new-directory`，基础镜像需要 Python3、GNU time（`/usr/bin/time`）、系统动态库和 Mesa CPU Vulkan。CPU ICD 与系统库不计入应用压缩包。

`--with-umg --with-verse` 的构建计划可组合选择 UMG 宿主与独立 worker，但本轮 UI 命令桥及部署包只验收 Rive 渲染端，没有验收 Verse → UMG，更没有验收 Verse → UEFN。

## 已通过的运行测试

正式测量为两核 affinity、每状态 3 个独立进程，共 6 次完整链路，使用 llvmpipe。所有渲染端日志确认真实 UE RHI/RDG draw/readback；没有 Engine/Renderer 加入 worker 或默认 Lite 的实际链接输入。

| 用例 | 实际检查 |
| --- | --- |
| 事件与恢复 | 先 Await 挂起，Signal 后状态和计数发生变化；没有重放订阅前的历史信号 |
| 挂起与取消 | race 取消等待任务，defer 恰好执行一次；随后发出的迟到事件不能恢复已取消任务，不能产生迟到写入 |
| 失败回滚 | `<transacts><decides>` 函数先修改两个字段再失败，两个字段均恢复；通过检查后才输出 UI 命令 |
| 故障注入 | 破坏事件赋值、取消清理、失败预期，分别以 11/14/15 拒绝，均没有 UI 命令 |
| Verse 修改 | 修改实际业务函数中的计数增量并更新期望，3 次重新编译并执行新行为；worker、Rive 和 UMG 的二进制 SHA 均不变 |
| UI 可见性 | 按下/空闲图有 5,681 个不同像素，排除“脚本执行了但 UI 没变” |
| 原生 UE 渲染对照 | 两个状态均与 Engine 原生参考宿主 RGBA 零差异，状态机元数据相同；使用分别独立 cook 的 shader archive |
| 部署闭包 | 开发 engine、vendor、Source 和 GPU 设备节点被隐藏，从 /tmp 运行；最终包按下/空闲都通过 |

像素对照证明相同 UI 命令经过现有桥和两种渲染宿主时结果相同；参考端没有执行 UEFN Verse，也没有提供 Fortnite UI 原生服务。

## 实测成本

| 项目 | 实测 |
| --- | ---: |
| 原 Rive 应用包 | 51.08 MiB；tar.gz 16.74 MiB |
| Rive + VerseVM worker 应用包 | **98.70 MiB；tar.gz 34.96 MiB** |
| 增量部署量 | **47.62 MiB；压缩包增加约 18.21 MiB** |
| worker ELF | 46.83 MiB，不含 debug/sym、SDK 或 VNI 构建工具 |
| worker 就绪（含 Core 初始化、框架/脚本编译加载） | 中位数 **2.926 秒**，从 worker main 计时 |
| 框架/脚本编译与加载阶段 | 中位数 **355.8 毫秒** |
| 整个 worker 进程 | 中位数 **3.131 秒**，含进程启动和退出 |
| Verse → UI 首张完整 PNG | 中位数 **4.764 秒**；范围 **4.578–4.985 秒** |
| worker 峰值 RSS | **85.2–87.3 MiB** |
| Rive 渲染进程峰值 RSS | **228.2–234.6 MiB** |
| 修改 `.verse` 后的新 worker 编译/执行周期 | 中位数 **3.130 秒**，不运行 C++/UHT/shader 编译 |
| worker 单 C++ 文件实际增量编译、完整链接 | **60.67 秒**，直接调用缓存 target；一次 Compile、一次 Link |
| 完整 `build_ui.sh --with-verse` 入口的同类单 C++ 文件增量 | **124.11 秒**，含源码/依赖校验和默认 Rive target 检查；worker UBT 阶段 55.00 秒 |

完整入口存在显著的准备/校验开销，见 [入口级增量报告](../artifacts/verse-vm/cpp-wrapper-incremental-01/report.json)。依赖已准备且只修改 worker C++ 时，可直接运行 `sudo bash scripts/build_linux_cached.sh RiveVerseWorker`。60.67 秒与 124.11 秒是两次单次观察，不应把差值视作稳定常数；前者不能冒充入口总耗时。

运行测量为独立进程，OS 文件缓存可能已热；不是清空整机缓存的冷启动。C++ 构建为本机 Ryzen 9950X / WSL2、Linux Development、最多 12 个并行动作，缓存已存在，正常 Link 包含符号处理和 strip。没有独立的成功冷构建计时。首次排错的失败构建不能拼接成冷构建基准。

当前桥在 worker 退出后才启动渲染端，首图指标包含这两段顺序执行。两段 RSS 分开测量，不能当成一个常驻双进程编辑器的总内存实测。

包体按首次部署归档计量；验证后产生的 Python bytecode cache 和引擎配置 manifest 属于运行时缓存，另在机器汇总中列出，没有把它们冒充构建产物或可选语言依赖。

## 未通过：同进程二次代码加载

一次显式实验在同一 Solaris IDE/VM 内第二次 `BuildAll` 生成并加载代码，触发原生 AsyncLoading2 的 `LoaderImport` 断言，涉及重新替换框架包。保留了 [失败调用栈](../artifacts/verse-vm/incremental-probe-01.log)。没有删除断言、改 GC 标志或修补引擎包加载器来绕过。

该实验入口已从交付 worker 移除。当前每次 Verse 修改采用新 worker，因此上面的 `.verse` 数据是“修改后的重新编译和执行”，不是在存活 VM 里保留状态的增量编译或热重载。这个限制不妨碍已测的批处理链路，但常驻编辑器/低延迟交互还需要后续工作。

## 需要回到 UEFN 对照

- 本地配置使用固定源码中的 `LatestUnstable` 语言版本；必须按目标 UEFN 版本匹配语言、UploadedAtFNVersion、API digest 和 native bindings，再验证同一份控制器源码。
- 分别在目标 UEFN 的 BPVM 会话和新 VerseVM 测试会话跑事件顺序、挂起取消、失败回滚；本地通过不代表目标版本语义已经一致。
- 接入真实玩家 UI、设备事件、时钟/Sleep、生命周期、持久化和联机复制。当前测试是合成事件与本地任务队列，未覆盖这些宿主服务。
- 验证 UEFN 支持的 widget 路径和截图，包括 Rive 自定义控件是否可导入；不能从 UE 插件可运行推断 UEFN 可用。
- 单独测试 UEFN Verse Reload/Live Edit。没有交付这些能力，也没有测试 UEFN 编译产物可直接在 Linux worker 中加载。
- 验证不同代码规模、长时间运行、GC 压力、错误恢复、计时器和性能。当前只有最小控制器、单帧截图和有界功能测试。

## 证据与复现

- [本轮汇总](../artifacts/verse-vm/summary.json)、[实际默认/worker 依赖与包边界](../artifacts/verse-vm/boundary-01.json)
- [正式运行报告](../artifacts/verse-vm/runtime-02/report.json)、[最终部署包测量](../artifacts/verse-vm/package-02/report.json)
- [按下图](../artifacts/verse-vm/runtime-02/pressed-0/output.png)、[空闲图](../artifacts/verse-vm/runtime-02/idle-0/output.png)、[原生 UE 按下图](../artifacts/verse-vm/runtime-02/native-pressed/output.png)
- [最终包按下验证](../artifacts/verse-vm/portable-02/report.json)、[最终包空闲验证](../artifacts/verse-vm/portable-idle-02/report.json)
- [直接 target 增量编译](../artifacts/verse-vm/cpp-incremental-01/report.json)、[完整入口增量编译](../artifacts/verse-vm/cpp-wrapper-incremental-01/report.json)
- [固定源码与依赖来源](../artifacts/verse-vm/source-provenance.json)、[工具/框架依赖哈希](../artifacts/verse-vm/compiler-dependencies.json)

```sh
python3 scripts/package_verse_ui.py --output package/my-verse-ui \
  --report-dir artifacts/verse-vm/my-package
sudo bash scripts/measure_no_gpu.sh -- python3 scripts/measure_verse_vm.py \
  --package package/my-verse-ui --output-dir artifacts/verse-vm/my-runtime
sudo python3 scripts/measure_ui_incremental.py --verse-worker \
  --via-ui-build --output-dir artifacts/verse-vm/my-cpp-incremental
python3 scripts/audit_verse_boundary.py --verse-package package/my-verse-ui \
  --output artifacts/verse-vm/my-boundary.json
```
