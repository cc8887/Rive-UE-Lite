# Rive UE Lite 测量脚本

这些脚本只收集实际证据。没有可执行文件、截图、所选 Vulkan 设备或 UE 对照时，报告保留 `incomplete`，不生成占位成绩。标准输出只打印报告路径和 gate 状态；完整数据保存在 `report.json`。

在 WSL 上仅强制 Lavapipe ICD 时，`/dev/dxg` 仍可能存在。可用独立 mount namespace 隐藏该次进程看到的所有 GPU 设备节点：

```bash
sudo bash scripts/measure_no_gpu.sh -- python3 scripts/measure_vulkan_probe.py \
  --output artifacts/environment/vulkan-cpu-no-gpu-nodes.json
```

该包装器先用 `unshare --mount --fork` 创建新 namespace，并验证其 ID 与原 namespace 不同；随后将 mounts 设为 private，在新 namespace 中用 tmpfs 覆盖 `/dev`，只建常用字符设备与 `/dev/shm`，再降到 uid/gid 1000、移除 capability、设置 no-new-privileges 执行命令。原 WSL 的全局 `/dev` 不变。也可将上述 Python probe 换成 `measure_ue_lite.py` 的完整测量命令。`RIVE_LITE_RUN_UID`、`RIVE_LITE_RUN_GID` 可显式指定目标用户。

已保存的环境 probe 确认进程内 `/dev/dxg`、`/dev/dri` 均不存在，uid 为 1000，能力集合为空，且只枚举 CPU llvmpipe。该 probe 未加载 UE/Rive，也没有渲染或测量 Rive 性能。

在 Linux 上运行（每次使用新的输出目录）：

```bash
python3 scripts/measure_ue_lite.py \
  --executable package/RiveLite \
  --package-dir package \
  --output-dir artifacts/measurement-001 \
  --run-arg=-RenderOffScreen \
  --run-arg=-AllowCPUDevices \
  --run-arg=-Output={output} \
  --receipt build/RiveLite.target \
  --link-map build/RiveLite.rsp \
  --reference artifacts/ue-reference.png \
  --reference-evidence artifacts/reference-evidence.json \
  --repeat 3
```

`--run-arg` 按原顺序组成参数数组，不经过 shell。带 `-` 的参数使用 `--run-arg=-Name=Value`。`{output}` 替换为该次运行的唯一绝对 PNG 路径，`{iteration}` 替换为从 0 开始的序号；具体输出参数名由宿主决定。输出目录必须位于 package 目录之外，且脚本拒绝将已有 PNG 当成新一轮成果。

- `run-000` 记录第一次进程的首图时间，后续运行统计重复启动的中位数。所有轮次都是全新进程；后续轮次可能命中 OS/驱动缓存，不代表进程内暖机渲染时间。
- 每个新输出目录默认新建独立的 `MESA_SHADER_CACHE_DIR`，首个进程标记为 `first_process_fresh_mesa_disk_cache`，后两次复用该目录并单独标记；不刷新或声称 OS page cache 冷启动，也不假定 Mesa cache 一定命中。配对脚本为 reference 与 lite 创建两个互不复用的全新 driver-cache 目录，参考不会提前填充 lite 的首轮 cache。
- 正式计划至少运行两组，每组 `--repeat 3`：默认环境一组；另一个新目录增加 `--cpu-limit 2 --lp-num-threads 2`。报告记录原/有效 CPU affinity、系统可见逻辑 CPU 数和实际传给子进程的 `LP_NUM_THREADS`。第二组只是 WSL 进程限制为 2 个逻辑 CPU 加 Mesa 线程数限制，不是实际 2 核 VM，也不表示独占主机。
- 默认向宿主增加输出目录内的 `-UserDir` 和逐轮 `-abslog`，并列出执行前后 package 内新建/改变/删除的文件。部署压缩包在实际 app 启动前生成；任何仍落进 package 的 Saved/log/cache 单列，避免将运行生成物混成初始部署包。
- 首图时间从启动 `/usr/bin/time` 包装进程到发现完整 PNG 的 IEND，包含启动、渲染、编码和落盘；轮询间隔 10 ms。另存进程完整墙钟及 `/usr/bin/time -v` 的峰值 RSS（KiB）。
- `rive_actual_draw` 单独验证实际 Rive draw。宿主只在 `artboard.draw`、Rive flush、`Graph.Execute`、GPU 完成/readback 和 PNG 保存均成功后输出同一行：`RIVE_LITE_CAPTURE path="<绝对PNG路径>" width=512 height=512 probe_only=0 render_path=UE_RHI_RDG RiveDrawCompleted=1`。测量脚本绑定本轮 PNG 路径和实际尺寸；`probe_only=1` 明确失败，缺少 Rive 完成字段保持 incomplete。清屏 RHI probe 的进程和 PNG 指标仍可保留，但会标 `rive_draw_verified=false`，不能当 Rive 性能或与 UE 的 Rive 画面等价证据。
- 默认从 `/usr/share/vulkan/icd.d/*lvp*.json` 选 Lavapipe，也可用 `--icd` 指定。两个 Vulkan ICD 覆盖变量均设为该文件，并移除 DISPLAY、WAYLAND_DISPLAY。`vulkaninfo --summary` 必须只枚举 CPU 类型，宿主日志还必须明确记录 **selected/using/chosen/active device/adapter** 与 CPU/llvmpipe/lavapipe 设备标识；仅枚举到 CPU 不等于运行时选择了它。
- `.target` receipt 必须包含对应产品；真实 linker response/map 还必须能识别 `Core`、`RHI`、`RenderCore` 模块且没有 `Engine`、`Renderer` 模块。单凭 receipt 的产物列表不能证明单体程序的模块裁剪。保留实际链接命令与构建日志供审查；receipt 的文件名匹配本身不是构建身份认证。
- 包体列出文件总字节、实际 `tar.gz` 字节、ELF 字节及 SHA-256。另列 ELF 的 `ldd` 闭包，以及 Vulkan loader/ICD 和其依赖的去重磁盘字节。外部系统库不会悄悄计作已随包发布；`standalone_bundle` 与依赖范围单列。应用自己 `dlopen` 的库、字体和 shader 数据仍须按宿主包清单核对。

`reference-evidence.json` 有 `reference`、`prototype` 两个对象。两边都需提供：

```json
{
  "reference": {
    "host_kind": "UE editor",
    "engine_commit": "actual commit",
    "rive_unreal_commit": "actual commit",
    "rive_runtime_commit": "actual commit",
    "fixture_sha256": "actual fixture SHA-256",
    "shader_archive_sha256": "actual shared shader archive SHA-256",
    "width": 512,
    "height": 512,
    "render_path": "UE RHI/RDG",
    "color_space": "the actual transfer function / PNG tagging policy",
    "alpha_mode": "the actual straight / premultiplied convention",
    "sample_count": 1,
    "frame_index": 0,
    "time_seconds": 0,
    "clear_color": [0, 0, 0, 0],
    "png_sha256": "actual reference PNG SHA-256"
  },
  "prototype": {}
}
```

`prototype` 填相同配置与它自己 PNG 的 SHA-256；两张截图的 hash 无需相等。参考宿主可声明 `UE editor`、`UE Engine program`、`UE game`。脚本验证声明字段一致及两个 PNG 的 hash，仍应保留生成两张图片时的 UE 日志和命令，以审查这些声明的来源。

独立像素比较：

```bash
python3 scripts/compare_png.py \
  --reference artifacts/ue-reference.png \
  --actual artifacts/measurement-001/run-000.png \
  --output artifacts/pixel-comparison.json
```

默认要求全图 RGBA8 编码值完全相等，也比较 alpha，且不隐式做 ICC/线性化/预乘转换。PNG 颜色元数据必须一致；双方无标签时明确记为 transfer function 未指定。可显式传 `--channel-tolerance`、`--max-different-fraction`，其数值写入报告。`--mask mask.png` 仅包含 RGB 非零且 alpha 非零的像素，记录掩码 hash、计入/排除像素数；全黑掩码直接失败。非交错 8-bit PNG 由 Python 标准库解码；其他无损 RGBA8 可选 Pillow；16-bit 拒绝有损归一化并标 `incomplete`。

退出码：`0` 全部 passed，`1` 存在 failed，`2` 只有 passed/incomplete。fixture 测试只验证测量逻辑，不充当 Rive 渲染证明：

```bash
python3 -m unittest discover -s tests -p metrics_test.py -v
```

配对 Engine Program 参考与 lite 实测可使用 `measure_pair.py`。默认只生成计划；父任务完成最终 native/host 重编、shader archive 和打包后，明确加 `--execute` 才会启动程序：

```bash
sudo bash scripts/measure_no_gpu.sh -- python3 scripts/measure_pair.py \
  --lite-executable package/Engine/Binaries/Linux/RiveRhiLite \
  --lite-package-dir package \
  --reference-executable Binaries/Linux/RiveUeReference \
  --fixture package/fixtures/input.riv \
  --shader-archive package/shaders/global.bin \
  --shader-directory package/Engine/Shaders \
  --output-dir artifacts/paired-measurement-001 \
  --repeat 3
```

执行时，两边采用**同一个文件路径和相同 SHA-256 的 fixture/archive**，相同 shader 映射目录、512×512、RGBA8、透明 clear、contain/center、`Seconds=0`、单采样和无 readback gamma 转换。`--fixture`、`--shader-archive`、`--shader-directory` 必须位于实际 lite 包内；参考工程的 ProjectDir 允许保持源码工程目录，以使用真正的 Engine 配置/数据。若包内空 Shaders 映射目录无法完成 shader bootstrap，需要先补齐真实依赖，不能改成外部源码目录后宣称包体闭包通过。

每个 profile 需使用全新输出目录，且等全部 C++/shader/reference 编译停止后再实测，避免构建进程争用 CPU/内存。`source-provenance.json` 先验证 Git 的 repository toplevel，防止对复制目录错误地取到上级仓库 HEAD；无法读取 Git 时采用相互一致的 source-state、upstream-manifest、native-build-result 记录，并保留各自文件 hash/字段来源。冲突会失败，不猜版本。

`--execute` 先验证参考 receipt/递归 linker inputs 确实包含 Engine、Renderer、RiveUeReferenceRenderer，再捕获参考 PNG 和 `/usr/bin/time` 指标，要求实际 `RIVE_UE_REFERENCE_CAPTURE` 成功标记和 Engine FRenderTarget 路径。随后运行 lite 全部测量，在双方 PNG 真正产生后生成带实际文件 hash 的 `reference-evidence.json`，最后只更新这项捕获后的 provenance gate 并加入参考链接/draw/CPU 证据。缺图、probe、错误参考、缺 shader 或单方启动失败不会被转成 passed。报告同时保留更新前状态与原始日志。

该参考的范围是**真实 UE Engine Program 的 Rive/Engine FRenderTarget/RHI/RDG**，其 `editor_viewport=0`、`umg_composite=0`；不代表 UMG Designer、Slate composite 或完整游戏最终画面。可传 `--utexture-target` 请求真正 UTextureRenderTarget2D 分支，所需 Engine 默认资产必须真实满足，失败仍是失败。

可先单独只读审查包的所有 receipt 源文件和配置，不创建最终包：

```bash
python3 scripts/measure_package_plan.py \
  --receipt Binaries/Linux/RiveRhiLite.target \
  --fixture fixtures/fix_rectangle.riv \
  --output artifacts/environment/package-audit.json
```

审查结果的 `receipt_sources_ready` 仅说明当前 receipt 文件可用；缺 archive 时 `staging_inputs_ready=false`。`planned_source_bytes_before_strip` 是计划输入字节，不是实际部署包大小。

最终实测汇总见 `artifacts/measurements/summary.json`：`default-02` 和 `cpu2-01` 各三次独立进程，所有六张 PNG 均与各自真实 Engine Program 参考逐像素 RGBA 相同。两组均使用独立的新 Mesa 缓存，首轮后缓存目录为 1 个文件、1,310,728 字节；后续允许复用该目录，文件数量/大小不能证明缓存命中率。2 CPU 组是 WSL 进程 affinity 和 `LP_NUM_THREADS=2`，不是独占的双核虚拟机。

`runtime_dependency_inventory` 是必须完成的 gate，包含应用 ELF、系统 Vulkan loader、选定 CPU ICD 及其 `ldd` 闭包。`standalone_bundle=false` 表示需要报告中列出的系统库；完整审计仍可 passed。当前应用包 53,494,161 字节，外部库去重 199,481,112 字节，两者合计 252,975,273 字节；这是当前 Linux 安装的文件字节，不是新系统安装包下载大小。包内备用 Vulkan loader 已计入应用包，不重复算入外部库。

首次报告曾因常规用户 PATH 不含 sbin 而漏查 loader/ICD；已修复工具定位并只补做依赖审计。原报告状态、inventory、hash 以及修复原因保留在 `dependency_inventory_audit_history`，独立原始审计在 `artifacts/measurements/runtime-dependency-audit.json`。`measure_dependency_audit.py` 可在保持原 PNG、计时和 tar.gz 不变的情况下重审；`measure_summary.py` 只汇总已留存的报告，并重新验证所有 PNG 和包 hash，不运行渲染进程。
