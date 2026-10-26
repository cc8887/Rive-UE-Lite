# 统一命令行工具包

整包包含 Rive、原生 UMG/Rive 宿主、VerseVM，以及 Widget Blueprint/UMG 动画编辑 worker。
解压一个 Linux x86_64 包，通过同一个 `rive-tool` 操作。相同文件按内容去重，组件保留各自的
原生路径、shader archive 和运行依赖。主机需要 Python 3.11+、Bash、GNU time、系统库和 Mesa CPU Vulkan ICD。

```bash
./rive-tool doctor
./rive-tool capabilities
./rive-tool widget capabilities
./rive-tool widget create --help
./rive-tool --workspace /data/ui-demo init
./rive-tool --workspace /data/ui-demo start
./rive-tool --workspace /data/ui-demo status
```

`start` 只启动轻量 Python 协调服务。UE worker 在对应命令执行时启动，完成后退出；这不是常驻 UE
编辑器、热加载 UObject 会话或 UEFN 模拟器。未显式 start 时，首个实际操作会自动启动协调服务。
同一工作区串行执行原生操作，status 始终可查；忙时新操作或 stop 返回退出码 75。
每个工作区有独立 Content、任务记录和服务实例，多个 agent 可使用不同工作区。

所有业务命令 stdout 返回一个 JSON 对象。`ok`、`exit_code`、`job_id`、`data` 和 `report` 可供 agent
解析；原生 UE 输出进入任务日志。失败返回非零退出码。命令内部的相对路径以工作区为基准，绝对输入
路径也可读取；输出和资产修改限制在选定工作区。对已有外部蓝图先 import，避免直接覆盖原始资产。

```bash
# Rive 和原生 UMG/Rive 复合界面
./rive-tool --workspace /data/ui-demo render --input examples/bankcard.riv --output renders/rive.png
./rive-tool --workspace /data/ui-demo render --ui umg --input examples/bankcard.riv --output renders/umg.png

# 创建、读取、修改真实源 .uasset
./rive-tool --workspace /data/ui-demo widget create --asset /Game/UI/WBP_Card --spec examples/widget/card.json
./rive-tool --workspace /data/ui-demo widget read --asset /Game/UI/WBP_Card
./rive-tool --workspace /data/ui-demo widget patch --asset /Game/UI/WBP_Card --patch examples/widget/card.patch.json
./rive-tool --workspace /data/ui-demo widget import --asset /Game/UI/WBP_Existing --input /assets/WBP_Existing.uasset
./rive-tool --workspace /data/ui-demo widget export --asset /Game/UI/WBP_Card --output exports/card.zip

# 原生 Texture2D 与 Image/Border 画刷；创建描述支持 type: Image
./rive-tool --workspace /data/ui-demo widget texture import --asset /Game/Textures/T_Logo --input /assets/logo.png
./rive-tool --workspace /data/ui-demo widget texture read --asset /Game/Textures/T_Logo
# export ZIP 包含直接 brush 纹理依赖，import 可将它们一同放到新工作区
./rive-tool --workspace /data/ui-copy widget import --asset /Game/UI/WBP_Card --input /data/ui-demo/exports/card.zip

# UMG 动画读写和原生播放预览
./rive-tool --workspace /data/ui-demo widget animation create --asset /Game/UI/WBP_Card --spec examples/widget/intro.animation.json
./rive-tool --workspace /data/ui-demo widget animation list --asset /Game/UI/WBP_Card
./rive-tool --workspace /data/ui-demo widget animation patch --asset /Game/UI/WBP_Card --patch examples/widget/intro.animation.patch.json
./rive-tool --workspace /data/ui-demo widget preview --asset /Game/UI/WBP_Card --animation Intro --time 0.5 --output renders/intro.png

# 编译运行 Verse，以及共享控制器驱动 UI
./rive-tool --workspace /data/ui-demo verse run --source examples/verse/hello.verse
./rive-tool --workspace /data/ui-demo verse test
./rive-tool --workspace /data/ui-demo verse ui --mode pressed --output renders/verse-rive.png
./rive-tool --workspace /data/ui-demo verse ui --ui umg --mode idle --output renders/verse-umg.png

./rive-tool --workspace /data/ui-demo jobs
./rive-tool --workspace /data/ui-demo jobs --id <job_id>
./rive-tool --workspace /data/ui-demo jobs --id <job_id> --logs --lines 80
./rive-tool --workspace /data/ui-demo stop
```

`verse run` 的入口是 `Main(Args:[]string, Env:[string]string)<suspends>:void`，`--args` 传入脚本参数。
`verse ui` 使用当前独立桥接协议，将共享控制器的 Pressed 布尔命令转换成 Rive 状态机输入；选择 UMG 时
渲染嵌入 Rive 的原生 UMG 界面。它不提供任意 UMG 控件的 Verse 绑定或 Fortnite device API。

支持读取已有蓝图节点/连线及变量，现有写接口覆盖控件属性与已支持的动画通道；任意图表编辑、复杂
动画轨道和 UEFN 资产兼容范围见 capabilities 及原编辑工具文档。普通用户可直接进行 CPU Vulkan
预览；正式无 GPU 验收另在私有 namespace 隐藏 GPU 和开发目录，并核对实际 llvmpipe 设备和截图。

Image/Border 的 `brush` 支持原生 Texture2D、tint、image_size、九宫格 margin、draw_as、tiling 局部修改。
纹理导入默认 sRGB，可选 `--linear` 和 `--filter nearest|linear`；替换要求 `--replace`，可用
`--expected-sha256` 拒绝过期编辑。详细 schema 与原生资产交接范围见源码文档 `prototype/widget-textures.md`。

Windows 使用同包的 `rive-tool.ps1`，它转交给 WSL Ubuntu 执行整套 Linux 工具。它不是原生 Windows
全功能构建。macOS 完整 SDK、Metal 构建和运行仍未验证。

开发者仍可默认只构建 Rive。整套工具需显式执行：

```bash
sudo bash scripts/build_ui.sh --all-tools
python3 scripts/package_toolkit.py --output package/toolkit-all
```

打包输入是各原生目标的已生成 package-manifest；可通过 `--rive-package`、`--umg-package`、
`--verse-package`、`--widget-package` 指定。`--stage-only` 用于先运行验收；提交冻结后可用
`--refresh-cli --stage-only` 刷新入口与文档，再用 `--archive-existing` 验证哈希并归档。
`doctor --verify` 对解压包的全部声明文件核对 SHA-256。体积和启动指标须以实际整包验收报告为准。
