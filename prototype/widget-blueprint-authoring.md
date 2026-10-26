# Widget Blueprint 创建、读取与修改入口

轻量 Rive/Verse 渲染入口不包含 UnrealEd/UMGEditor。源 `.uasset` 的创建、编译与保存由独立 `RiveUmgBlueprintWorker` 完成，默认 Rive 的构建和部署包不会加入这些 Editor 依赖。

新增统一入口：`python scripts/widget_bp.py`。Windows 上自动转到 WSL Ubuntu 中的原生 UE worker；Linux 上直接执行，预览通过私有 namespace 隐藏 GPU。该入口目前不代表 Windows 原生编辑器 worker 或完整 UMG Designer 已被交付。

## 先构建

在原型根目录的 WSL Ubuntu 中执行：

```sh
sudo bash scripts/build_ui.sh --with-widget-blueprint
```

`--with-umg` 仍选择原有运行宿主；`--with-widget-blueprint` 单独选择源资产编辑 worker。此 worker 明确依赖 Engine/Renderer/UMGEditor/UnrealEd，不能将它的成本藏进默认 Rive 包。其独立部署依赖闭包尚未打成新的服务器发布包。

## 新建自定义控件布局

以下命令可在 Windows 的 PowerShell 中从 `F:\Github\Rive-UE-Lite` 执行。Linux 预览命令前加 `sudo`；创建/读取/修改本身不需要 GPU。

```powershell
python scripts/widget_bp.py capabilities
python scripts/widget_bp.py create --content-dir artifacts/widget-jobs/demo/Content --asset /Game/UI/WBP_Card --spec fixtures/widget-blueprint/card.json
python scripts/widget_bp.py read --content-dir artifacts/widget-jobs/demo/Content --asset /Game/UI/WBP_Card
python scripts/widget_bp.py patch --content-dir artifacts/widget-jobs/demo/Content --asset /Game/UI/WBP_Card --patch fixtures/widget-blueprint/card.patch.json
python scripts/widget_bp.py preview --content-dir artifacts/widget-jobs/demo/Content --asset /Game/UI/WBP_Card --output artifacts/widget-jobs/demo/preview.png
python scripts/widget_bp.py export --content-dir artifacts/widget-jobs/demo/Content --asset /Game/UI/WBP_Card --output artifacts/widget-jobs/demo/WBP_Card.zip
```

`create` 由描述构造原生 WidgetTree、执行原生 Kismet 编译，再保存未 cook 的 Widget Blueprint。`preview` 重新加载保存的资产，通过真实生成类创建实例并用 Slate/Vulkan 出图；不会用 JSON 重建一棵树冒充读取结果。每次执行都会返回独立 `report_dir`，其中有读取结果 `asset.json`、调用日志和状态。可以用 `--report-dir` 指定一个尚不存在的目录。

## 读取并修改已有蓝图

把实际源 `.uasset` 的副本和依赖放入 job 的 Content 挂载目录，然后按原有 `/Game/...` 包名读取。也可用 `import` 先复制单个资产；它不会修改原项目：

```powershell
python scripts/widget_bp.py import --input F:/MyProject/Content/UI/WBP_Existing.uasset --content-dir artifacts/widget-jobs/existing/Content --asset /Game/UI/WBP_Existing
python scripts/widget_bp.py read --content-dir artifacts/widget-jobs/existing/Content --asset /Game/UI/WBP_Existing
python scripts/widget_bp.py patch --content-dir artifacts/widget-jobs/existing/Content --asset /Game/UI/WBP_Existing --patch artifacts/widget-jobs/existing/patch.json
python scripts/widget_bp.py preview --content-dir artifacts/widget-jobs/existing/Content --asset /Game/UI/WBP_Existing --output artifacts/widget-jobs/existing/after.png
python scripts/widget_bp.py export --content-dir artifacts/widget-jobs/existing/Content --asset /Game/UI/WBP_Existing --output artifacts/widget-jobs/existing/WBP_Existing-edited.zip
```

`--asset` 应保持原始包路径，末段必须与 `.uasset` 的对象名相同；导入不是 UE 资产重命名工具。相关纹理、字体、子蓝图和原生类需另行提供。当前已验证的是固定 UE6 源码版本中的原生控件；缺失自定义类或依赖时不能假设任意工程资产都可运行。

写入路径只能在独立原型内部；原项目只作为导入源。`create/import` 拒绝覆盖已有资产，修改已有资产使用 `patch`。`patch` 会备份、检查完整请求、修改现有原生对象、编译和保存；失败则恢复备份。可将读取结果中的 SHA 通过 `--expected-sha256` 传入，拒绝过期修改。只读操作会检查源资产哈希没有改变。

## 支持的描述和修改范围

创建描述用按父级优先排序的扁平 `widgets` 数组，首个控件为根 CanvasPanel。当前可创建 CanvasPanel、Border、Button、TextBlock、Image；Border/Button 最多一个直接子控件。名称唯一，不可通过描述注入未知原生类。Image/Border 的纹理画刷以及 `texture import/read`、带纹理依赖的 ZIP 交接见 [Texture2D / UMG Image](widget-textures.md)。

```json
{
  "widgets": [
    {"name":"RootCanvas","type":"CanvasPanel"},
    {"name":"Title","type":"TextBlock","parent":"RootCanvas","text":"My widget","font_size":28,"position":[48,32],"size":[520,48],"color":[1,1,1,1],"is_variable":true}
  ]
}
```

修改请求按现有控件名定位，不创建替代 WidgetTree：

```json
{
  "widgets": [
    {"name":"Title","text":"Edited existing asset","position":[64,40],"size":[500,52],"font_size":26}
  ]
}
```

字段包括 TextBlock 的 `text/font_size`，原生 TextBlock/Border/Button 的 `color`，Border 的 `padding`，Canvas 子控件的 `position/size/alignment`，以及通用的 `enabled/is_variable/visibility/opacity`。颜色为线性 RGBA，padding 为 left/top/right/bottom。未知属性、未知控件和不匹配的 slot 会被拒绝。中文等非 ASCII 文案可保存/读取；字体是否覆盖这些字形仍取决于实际字体资源。

读取返回根控件、完整本层 WidgetTree 的名称/类/父级/受支持属性，以及源蓝图图表、节点、引脚和连线快照、成员变量描述。**当前修改范围是控件属性、Canvas 布局及支持的原生动画通道；没有提供事件图节点/连线改写，也没有提供已有树的新增/删除/重挂接接口。** 修改不会通过重新生成描述丢弃原图。动画的读取、创建、局部修改和预览见 [UMG 动画入口](umg-animation.md)。

## 验证边界

本轮回归入口为 `scripts/verify_widget_bp_authoring.py`，正式结果写入 `artifacts/widget-blueprint-authoring/`。它包含：创建自定义布局、真实源资产读取、修改保存/重载、无 GPU 预览、带非空事件图/连线/成员变量的已有 `.uasset` 导入与保留检查、失败原子性、过期修改/覆盖拒绝及 Unicode 读写。

本轮正式入口回归为 [cli-roundtrip-03](../artifacts/widget-blueprint-authoring/cli-roundtrip-03/summary.json)：17 个 CLI 场景通过，包括预期拒绝的负例。已有资产中的 2 个真实图节点、连线、成员变量 `PreservedCounter=41` 和未编辑控件均保留；源文件哈希不变，修改发生在导入副本上。中文文案保存后可正确读取。Windows → WSL 的新建、已有资产读取、修改和再次读取也已实际执行。

新布局的两组生成类预览与独立 shader cook 的原生源树预览比较均 RGBA 零差异，见 [原生预览对照](../artifacts/widget-blueprint-authoring/native-preview-03/summary.json)。修改本身改变 35,046 个像素，见 [修改前](../artifacts/widget-blueprint-authoring/cli-roundtrip-03/before.png) / [修改后](../artifacts/widget-blueprint-authoring/cli-roundtrip-03/after.png)。可下载 [已修改的已有源蓝图](../artifacts/widget-blueprint-authoring/cli-roundtrip-03/WBP_Existing-edited.zip)，其中仍包含原有事件图与成员变量。完整汇总见 [本轮验收记录](../artifacts/widget-blueprint-authoring/summary.json)。

额外故障恢复测试让原生 `SavePackage` 先成功，再故意使最后的 metadata 写入失败。CLI 检测到原生退出码 8 后恢复备份，源 `.uasset` 的 SHA 完全恢复，见 [保存后故障恢复](../artifacts/widget-blueprint-authoring/post-save-recovery-01/summary.json)。

早期两核测试曾在写出资产后出现退出超时；补齐 Core 的平台配置任务同步入口，并加了分阶段退出记录。最终回归中预期成功的原生进程均成功退出；负例按预期非零退出，超时保护会终止整个 worker 进程组。没有修改引擎或跳过原生编译/保存/错误检查；单次原始挂起没有取得调用栈，最终通过范围以本轮场景为准。

默认路径经 [编译/链接/UHT/包边界检查](../artifacts/widget-blueprint-authoring/lite-exclusion.json) 仍排除 Engine/Renderer/Slate/UMG/UMGEditor/UnrealEd，关闭编辑开关后为 0 actions。验证入口时默认 target 对当前已有的 Main.cpp 做了重新编译，其新 ELF SHA 与历史包不同；本轮没有编辑这些运行源码，也没有重打历史 Rive 包。新默认程序已实际渲染，并与历史包的相同输入 PNG 零差异，见 [默认运行端检查](../artifacts/widget-blueprint-authoring/default-runtime/summary.json)。旧测量中的 SHA/包体声明仍按各自快照理解。

旧的 `artifacts/umg-blueprint/roundtrip-03` 是此前固定 CanvasPanel/Border/TextBlock 样例的验证记录，不替代本轮新入口的验收。完整 Designer、任意项目模块/素材依赖、蓝图图执行语义和 UEFN 资产兼容仍需各自验证。Rive 的既有 RHI/RDG 路径保留，但 Rive 自定义控件嵌入源 Widget Blueprint 不在本轮四种原生控件的验收范围内。
