# 原生 UMG 动画读写与无 GPU 预览

独立目录：`F:/Github/Rive-UE-Lite`。固定 UE6：`62d7c1a7125b52b10ee1b714838f515f3563f795`。日期：2026-10-26。

动画功能位于可选 `RiveUmgBlueprintWorker`，沿用 `--with-widget-blueprint`。默认 Rive 目标不链接/打包该 worker。`--with-umg` 的运行宿主和源资产编辑 worker 仍是不同程序；本次没有给运行宿主增加源 Blueprint 编译器。

已完成选定范围的原生资产、播放、截图、部署包与启动验收。总报告为 [summary.json](../artifacts/umg-animation/summary.json)。此前估算保留在 [实现前评估](umg-animation-assessment.md)。

## 实测结果

比较实现前冻结的 worker 与实现后的 worker，采用相同打包器、strip、配置、shader 和字体，包中分别包含同一 UI 的静态/动画版本。下列是**源 Blueprint 编辑 worker**，并非默认 Rive kernel 或 `RiveUmgHost` 的体积。

| 项目 | 实现前 | 实现后 | 增量 |
| --- | ---: | ---: | ---: |
| 完整应用目录，含 manifest 与源 UI 示例 | 566.705 MiB | 566.780 MiB | **78,554 B，76.7 KiB** |
| 实际 tar.gz | 212.285 MiB | 212.321 MiB | **37,998 B，37.1 KiB** |
| strip 后 worker ELF | 393,151,960 B | 393,207,656 B | **55,696 B，54.4 KiB** |
| 示例源 `.uasset` | 19,765 B | 42,659 B | **22,894 B，22.4 KiB** |
| 实际链接模块数 | 394 | 394 | **0 个** |

动画示例包含 Intro（opacity/平移/缩放/旋转）及 Keep（常量 opacity）两个动画。资产增量不是任意工程或每条动画的固定成本。其余声明的 payload 文件完全相同，仅 worker、source `.uasset` 和同长度的 receipt 内容改变；manifest 大小另有 36 B 差异。MovieScene/Tracks/Sequencer 原本已经位于编辑 worker 的链接闭包内。

两核、ext4、llvmpipe，先各预热一次，再交错测量每组 5 次，得到下列中位数：

| 指标 | 原 worker + 静态资产 | 新 worker + 同一静态资产 | 新 worker + 实际动画 |
| --- | ---: | ---: | ---: |
| 进程启动 → worker ready | 2.503 s | 2.424 s | 2.524 s |
| 进程启动 → 首张完整 PNG | 2.736 s | 2.668 s | 2.765 s |
| 含清理的完整进程退出 | 2.975 s | 2.903 s | 2.993 s |
| peak RSS | 739.37 MiB | 743.66 MiB | 745.12 MiB |

原 worker 到实际动画首图的中位数差为 **+28.9 ms**，ready 差 **+20.7 ms**，RSS 差 **+5.75 MiB**。但原版首图范围为 **2.619–2.840 s**，动画版为 **2.625–2.850 s**，范围明显重叠；新 worker 的静态运行也有反向的中位数变化。因此端到端差值尚不足以确定稳定的启动增量，不能把单次结果推广为固定开销或优化收益。

程序内部更直接的计时为：native 系统/owner/manager 初始化中位数 **4.13 ms**，首次动画求值 **0.49 ms**；逐次合计的中位数 **4.56 ms**。它们发生在 asset load 之后；worker ready 指标尚未包含动画加载/播放。

上述结果是 OS cache 可能热的共享 WSL 主机实测，每次使用新 user/Mesa cache，没有执行冷启动或专属云 VM 测量。包体不含主机 Mesa ICD / Linux OS 依赖，其列表保留在部署 manifest 和进程映射记录中。未发现开发目录的库泄漏。

下载：[可部署 worker tar.gz](../package/widget-animation-01.tar.gz)、[带原生动画的源蓝图 ZIP](../artifacts/umg-animation/acceptance-03/WBP_Card-animated.zip)。截图：[起始帧](../artifacts/umg-animation/acceptance-03/11-frame-0.png)、[中间帧](../artifacts/umg-animation/acceptance-03/11-frame-2.png)、[末帧](../artifacts/umg-animation/acceptance-03/11-frame-3.png)。

## 已通过的验收

- [完整动画回归](../artifacts/umg-animation/acceptance-03/summary.json)：32 个 CLI 场景（含 4 个预期拒绝），48 项检查。原生创建/重载、局部通道修改、其他动画/绑定/图表/变量保留、无效/过期/覆盖拒绝、native bool 未支持轨道的保留与预览拒绝均通过。
- 四个时间点 0 / 0.25 / 0.5 / 1 秒的生成类动画与原生源树动画截图逐像素零差异，使用两次独立 native shader cook 的产物。30/60/120 Hz 的中间帧也完全一致，合计 6 对图。
- 正放、倒放、循环边界、暂停、seek、停止恢复、停止后无迟到属性写入、结束回调不重复，以及同进程重复 10 次 play/stop 清理通过。World 始终为空，原生系统实体和绑定确实求值，无成功进程 error/ensure。
- [原版包](../artifacts/umg-animation/baseline-portable-01/summary.json) 和 [动画包](../artifacts/umg-animation/animated-portable-01/summary.json) 都在开发目录与 GPU 节点隐藏、uid=1000 的 namespace 中正常出图。动画包画面与正式回归中间帧零差异；声明的 payload 未变。
- [启动对照](../artifacts/umg-animation/startup-03/summary.json) 共 18 个独立进程，含 3 个排除的预热。5 对静态截图零差异，动画输出重复一致。Windows → WSL 的新动画 list 与带空格输出路径的 preview 已实际执行，与 Linux 正式帧零差异。
- [默认构建边界](../artifacts/umg-animation/lite-exclusion.json) 仍为 100 个 compile response、21 个链接模块、3 个 UHT 模块，排除 Engine/Renderer/Slate/UMG/UMGEditor/MovieScene 等。恢复原有编译选项后的再次默认构建为 [0 actions](../artifacts/umg-animation/default-noop.console.log)，默认与其他运行目标的源码没有本轮动画改动。

验证默认构建时曾误切换 debug 编译选项，随后已恢复原选项，过程中重新生成了默认 Rive 二进制，因此它的 SHA 与本轮开始时不同。当前默认程序重新进行的 [CPU 渲染回归](../artifacts/umg-animation/default-runtime/summary.json) 与开始前的截图完全一致。没有将这次配置重编算作动画依赖/包体增量；旧 Rive/UMG/Verse 包没有重打或整体重新验收。不能把默认二进制描述成全程 SHA 未变。

## 使用

```bash
sudo bash scripts/build_ui.sh --with-widget-blueprint

python3 scripts/widget_bp.py create --content-dir artifacts/my-ui/Content \
  --asset /Game/UI/WBP_Card --spec fixtures/widget-blueprint/card.json
python3 scripts/widget_bp.py animation create --content-dir artifacts/my-ui/Content \
  --asset /Game/UI/WBP_Card --spec fixtures/widget-blueprint/intro.animation.json
python3 scripts/widget_bp.py animation list --content-dir artifacts/my-ui/Content \
  --asset /Game/UI/WBP_Card
python3 scripts/widget_bp.py animation patch --content-dir artifacts/my-ui/Content \
  --asset /Game/UI/WBP_Card --patch fixtures/widget-blueprint/intro.animation.patch.json
sudo python3 scripts/widget_bp.py preview --content-dir artifacts/my-ui/Content \
  --asset /Game/UI/WBP_Card --animation Intro --time 0.5 \
  --output artifacts/my-ui/intro-half.png
```

Windows 的 `python scripts/widget_bp.py ...` 自动转交给 WSL Ubuntu，不需要 Windows 原生 Editor worker。读取/导入已有源 `.uasset` 后同样可以 `animation list` 和 `animation patch`，不是从 JSON 重建整个 Blueprint。所有写入保持在独立目录；对外部资产先 `import` 复制。

## 资产和播放语义

- 数据是真正嵌入 Widget Blueprint 的 `UWidgetAnimation + UMovieScene`，使用原生 possessable/binding、float track、UMG 2D transform track/channel、Kismet 编译器及 SavePackage。新进程读回源动画和生成类中的 `_INST` 克隆。
- 可写属性：`opacity`、`render_translation`、`render_scale`、`render_angle`；常量或线性插值。颜色、材质、slot 布局、事件轨道等尚未开放写入。
- 创建 schema 参考 `intro.animation.json`；patch schema 只包含 `name` 和 `tracks`。patch **替换指定属性通道的关键帧集合**，保留其他通道、绑定 GUID、section 设置、其他动画和 Blueprint 图表/变量。它不是单个 key 的 JSON Patch。
- 创建使用整数 fps 1–240；用户帧号转换到 240000 ticks/s。末帧关键帧可包含在 `duration_frames`，播放范围按原生 UMG Editor 的约定，exclusive upper = 末帧 tick + 1。已有动画修改沿用原来的 display rate / tick resolution。
- 已有动画仅修改一个可编辑 absolute section 的支持通道；多 section、其他 blend、动态/歧义绑定明确拒绝。未知 native track/section 可描述并原样保留，预览拒绝自动执行不支持的轨道。
- 读取/修改针对当前 Blueprint 本层的动画；跨继承链编辑、动画重命名/删除和引用迁移尚未开放。
- 修改请求先整体校验；native 保存失败、编译错误或 ensure 都由 CLI 判失败并恢复 `.uasset` 备份。`--expected-sha256` 可防止覆盖读取后已变化的资产。

`preview --animation Intro --time 0.5` 创建真正的生成类实例，然后调用 `UUserWidget::PlayAnimation`，通过 UE6 `FWidgetAnimationHandle/FWidgetAnimationState` 和 MovieScene runner 求值。没有用按公式写控件 setter 的模拟器替代动画。

worker 只构造最小 `UGameEngine` owner，不调用 Engine Init、不创建 World/Viewport/PIE。该独立 Program 的 native MovieScene 系统 CDO 是惰性的，必须用公开反射接口构造系统 CDO 才会登记执行依赖；单有实体和成功解析的绑定并不足以播放。注册后使用唯一手动时钟，flush 完成再以 delta=0 绘制。退出前销毁状态，正常 GC 清理 manager/linker 和 Slate delegate。

## 播放控制脚本

```json
{"operations":[
  {"op":"play","loops":0,"restore_state":true},
  {"op":"tick","seconds":0.25,"hz":60},
  {"op":"pause"},
  {"op":"tick","seconds":0.25},
  {"op":"resume"},
  {"op":"seek","time":0.75},
  {"op":"reverse"},
  {"op":"tick","seconds":0.25},
  {"op":"stop"}
]}
```

通过 `preview --animation Intro --playback-script control.json --output ...` 执行。`play` 支持 `time`、`direction=forward/reverse`、`loops`（0 无限）、`restore_state`。`tick` 可按 1–240 Hz 子步推进；seek 要求仍在播放。原生 UE6 Pause 使用 Stopped 状态，因此 worker 的 resume 显式恢复播放状态；停止已暂停的动画会先恢复状态但不推进时间，再调用原生 Stop，使恢复样式也能完成。

metadata 包含每个操作后的 native 时间/状态、控件实际 opacity/transform、解析绑定数量、MovieScene 系统数量、结束回调计数。源关键帧和运行实例的求值属性分开记录。

## 复现验收与测量

```bash
sudo bash scripts/measure_no_gpu.sh -- python3 scripts/verify_widget_bp_animations.py \
  --output-dir artifacts/umg-animation/new-acceptance

python3 scripts/package_widget_worker.py --content-dir artifacts/my-ui/Content \
  --output package/my-widget-worker
sudo bash scripts/isolated_widget_worker.sh -- python3 scripts/verify_widget_worker_package.py \
  --package package/my-widget-worker --animation Intro \
  --output-dir artifacts/my-portable-check
```

包内 `worker.sh` 可直接调用原生程序；也包含 `scripts/widget_bp.py`。应用包包含 strip 后的 worker/receipt 运行依赖、配置、字体/Slate 数据、Editor hash 所需 shader 源文件和预编译 shader archive；不包含引擎 C++ 源码、SDK、UBT 或完整 Editor。CEF 被目标显式禁用，receipt 的 EpicWebHelper 被列为有理由排除的可选项。Linux OS 库、Mesa llvmpipe ICD 和使用 CLI 时的 Python/Bash 属于单独列明的主机前提。

性能脚本 `measure_widget_animation.py` 比较同一静态源资产在原二进制/新二进制下的启动，再比较实际动画资产首图。每组预热 1 次，交错测量 5 次，CPU affinity=2、Mesa 线程=2，每次新 user/Mesa cache。记录进程启动到 ready、完整 PNG、完成和退出，以及 `/usr/bin/time` peak RSS。OS 页缓存可能热，WSL 主机共享，不称冷启动或专属云 VM 基准。

`stage_widget_worker_benchmark.py` 只允许复制到 AGENTS 明确授权的 ext4 临时目录，检查总量不超过 8 GiB；不会覆盖/删除旧 staging。原型保留完整报告。`isolated_widget_worker.sh` 在私有 mount namespace 隐藏开发 engine/vendor/Binaries/Source/SDK/Config，并隐藏 `/dev/dxg` 和 `/dev/dri` 后降权运行，验证真实包能独立出图。

## 验证边界

原生 source WidgetTree + source animation 预览与生成类实例 + `_INST` 动画是两条被测试的 native 路径，使用两个独立执行的 cooker 产物。它们不等于完整 UE Editor 视口，也不等于 UEFN 的 View Bindings/Verse 触发或跨版本 `.uasset` 兼容验收。Rive 嵌入的宿主和原来的 Verse worker 没有新增联动改动。
