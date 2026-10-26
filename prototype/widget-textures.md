# Texture2D 与 UMG Image

统一 CLI 增加 `widget texture import/read`。PNG/JPEG 通过 UE ImageWrapper 解码，保存成带源数据的
原生、未 cooked 的 `UTexture2D .uasset`；蓝图使用原生 `UImage`/`UBorder` 的 Slate Brush 引用它。
预览沿用 UE `FWidgetRenderer → SlateRHIRenderer → VulkanRHI`。运行端没有引入 Pillow 或另一套图片渲染器。

```bash
./rive-tool --workspace /data/ui-demo widget texture import \
  --asset /Game/Textures/T_Logo --input /data/logo.png --filter nearest
./rive-tool --workspace /data/ui-demo widget texture read --asset /Game/Textures/T_Logo
./rive-tool --workspace /data/ui-demo widget create \
  --asset /Game/UI/WBP_Logo --spec /data/logo-widget.json
./rive-tool --workspace /data/ui-demo widget preview \
  --asset /Game/UI/WBP_Logo --output renders/logo.png
```

`logo-widget.json`：

```json
{
  "widgets": [
    {"name":"RootCanvas","type":"CanvasPanel"},
    {"name":"Logo","type":"Image","parent":"RootCanvas",
     "position":[32,32],"size":[128,128],"color":[1,1,1,1],
     "brush":{"texture":"/Game/Textures/T_Logo","draw_as":"Image"}}
  ]
}
```

对已有 `.uasset`，`read` 会返回 Image/Border 的 brush 和直接纹理依赖；`patch` 修改原对象，
编译后保存，并保留未修改的控件、图表、变量与动画。已有 WidgetTree 的增删/重挂接仍不在接口范围内。

```json
{
  "widgets": [
    {"name":"Logo","brush":{"texture":"/Game/Textures/T_Logo",
      "image_size":[64,64],"tint":[1,0.8,0.8,1]},"opacity":0.9}
  ]
}
```

`brush` 适用于 Image 和 Border，支持局部更新；未提供的字段保留原值：

| 属性 | 值 |
|---|---|
| `texture` | `/Game/...` 或 `/Engine/...` 的 Texture2D 包名/完整对象路径；`null` 清除资源引用 |
| `image_size` | 正数 `[width,height]`，单维最多 4096；绑定新纹理时默认采用源图大小 |
| `tint` | 线性 `[r,g,b,a]`，各分量 0..1 |
| `draw_as` | `Image`、`Box`、`Border`、`NoDrawType` |
| `margin` | 九宫格切分 `[left,top,right,bottom]`，各分量 0..1 |
| `tiling` | `NoTile`、`Horizontal`、`Vertical`、`Both` |

Image 的 `color` 使用原生 `SetColorAndOpacity`，与 brush tint 相乘。Border 的 `color` 修改 brush tint，
保留其纹理、切分和其他画刷信息。清除 `texture` 后仍遵循原生空 brush 的绘制行为；完全禁用绘制可设置
`draw_as: "NoDrawType"`。支持的原生 opacity/transform 动画同样可以绑定 Image。

图片导入归一为 BGRA8、默认 UI 无压缩设置、单 mip、NeverStream；`--compression default` 可选择原生平台纹理压缩。
默认 sRGB，`--linear` 按线性纹理采样，
`--filter nearest|linear` 选择最近点或双线性过滤。输入限制为 PNG/JPEG、1..4096 像素、文件最多 64 MiB。
也可导入同版本的单文件原生 Texture2D `.uasset`，此时保留原有设置。替换现有纹理必须显式声明：

```bash
./rive-tool --workspace /data/ui-demo widget texture import \
  --asset /Game/Textures/T_Logo --input /data/new-logo.png \
  --replace --expected-sha256 <上次读取的文件哈希>
```

重导入保持纹理包名与对象名；引用它的蓝图无需重写。失败时恢复备份，新建失败会清理本次产生的资产。
带 sidecar 的既有纹理替换暂未验收，因此拒绝修改。

导出 ZIP 现在包含蓝图、Image/Border/Button style brush 直接引用的 `/Game/` Texture2D 及其 sidecar，
并附 `assets.json` 文件哈希清单。相同版本工具可原路径重导入此 ZIP：

```bash
./rive-tool --workspace /data/ui-demo widget export \
  --asset /Game/UI/WBP_Logo --output exports/logo.zip
./rive-tool --workspace /data/another-demo widget import \
  --asset /Game/UI/WBP_Logo --input /data/ui-demo/exports/logo.zip
```

直接导入一个外部 Widget `.uasset` 时，先用 `texture import --input T_Logo.uasset` 将依赖纹理放到
相同 `/Game/...` 路径，再导入蓝图；缺失的原生依赖会被报错。ZIP 不会覆盖目标已有资产，也不执行资源重命名。
`/Engine/` 依赖在清单中列出，接收端需具备对应资产。

当前依赖收集针对上述直接 brush Texture2D，不等同于任意 UE 项目的完整迁移闭包。UI Material、RenderTarget、
TextureCube、视频、图集/Sprite、软引用异步加载、插件自定义控件，以及 UEFN 接收端兼容性尚未验收。
原有此类 brush 的未修改字段保留，不能据此宣称它们已支持创建或正确预览。

实现仅在可选 Widget worker 与 CLI 中；默认 Rive 构建仍不包含 Image/Texture 编辑能力。构建入口保持
`bash scripts/build_ui.sh --with-widget-blueprint`，完整交付仍为同一个 all-tools 包。

验收入口：`scripts/verify_widget_bp_textures.py`。它检查原生源纹理保存/重载、PNG 透明度、sRGB/linear
像素区别、局部 brush 修改、纹理重导入、依赖 ZIP 交接、错误原子性、Image 动画，以及独立 shader cook
的原生源树截图对照。实际构建、截图和包体验收结果另附在本目录对应记录中。

2026-10-27 验证结果记录在 [验收汇总](widget-textures-validation.json)：源入口 22 个场景通过，
实际 TAR 解压后的统一 CLI 也通过相同 22 个场景；后者在 GPU、开发 Engine/vendor/Source、SDK 和
Runtime 源码缓存都被隐藏的 namespace 中执行。四组独立 shader archive 的原生源树参考截图 RGBA
零差异，源码程序与实际归档程序的五组截图也全部零差异。Windows PowerShell → WSL 路径额外验证了
带空格路径的图片导入、蓝图创建、读取和 CPU 预览。此次图片像素验收覆盖 8-bit RGBA PNG（包括透明度
与非二次幂尺寸 64×37）和 JPEG；未据此扩展到 HDR/高位深、视频或 UI Material。

原有蓝图编辑的 17 个场景、原生动画回归及 31 项脚本测试通过。另有两项真实故障注入：原生纹理已经
成功保存后，使最终 metadata 写入失败；覆盖操作恢复原文件 SHA，新建操作清理新资产。

后续按实际部署文件重新测量，体积结论以 [运行文件与依赖验证](widget-textures-runtime-validation.json)
为准。以下均为未压缩文件的实际字节，不使用归档压缩率推算：

| 实测项 | 旧版 | 新版 | 变化 |
|---|---:|---:|---:|
| 编辑 worker ELF | 393,207,656 B | 393,293,656 B | +86,000 B（83.98 KiB） |
| 新增四个 NVTT 动态库 | 0 B | 559,048 B | +545.95 KiB |
| 原生程序与动态库合计增量 | — | — | +645,048 B（629.93 KiB） |
| 整套部署文件按内容/硬链接去重，含清单 | 764.1882 MiB | 764.8052 MiB | +647,006 B（631.84 KiB） |
| 本次 ext4 实际分配空间 | 769.6602 MiB | 770.3047 MiB | +660 KiB |
| 编辑 worker 实际链接模块 | 394 | 397 | +3 |
| 默认 Rive 实际链接模块 | 21 | 21 | 无 Engine/Renderer/Slate/UMG/纹理编辑模块 |

四个新增库分别为 `libnvcore.so` 309,824 B、`libnvimage.so` 133,704 B、`libnvmath.so` 26,320 B、
`libnvtt.so` 89,200 B。主程序新增的直接 ELF 依赖是 `libnvtt.so`，其余三个由它传递引入。
实际 `/proc/<pid>/maps` 确认四个库在旧版没有映射，在新版的无图片场景也全部加载，不能仅删除文件。
其他原生库、预编译 shader、编辑器 shader 源文件、配置、字体/内容均无字节变化；Rive、UMG 宿主、
Verse 三个运行组件无变化。全工具文件增量还包含 CLI、示例与清单，ext4 分配空间则受块大小影响。

新增 UE 模块是 `TextureBuild`、`TextureFormatUncompressed`、`TextureFormatDXT`；新增原生动态库为
`libnvcore.so`、`libnvimage.so`、`libnvmath.so`、`libnvtt.so`。`DerivedDataCache` 增加了直接依赖声明，
但在旧 worker 中已经链接，因此不算新增模块。DDC 使用每个任务自己的本地目录，不依赖 Zen 服务。
完整交付仍是一个包、一个 CLI。默认 Rive 复查为 0 个编译动作。

以上实测对应本地验证快照 [rive-toolkit-textures-01.tar.gz](../package/rive-toolkit-textures-01.tar.gz)，SHA-256 为
`555a2f04be75c4b1bc46376e9b7838c20c410627467c20a68ffb84fd9781689f`；验收 JSON 中的本地快照字段保留其原始状态。
对外统一交付见 [preview.5 release](https://github.com/cc8887/Rive-UE-Lite/releases/tag/v0.1.0-preview.5)，
发布包另附冻结源码提交、最终解压校验与运行记录。发布时只刷新 CLI、文档和清单，原生程序及依赖采用同一已验证字节。
本轮构建包含新增模块的首次编译，共 6 个动作、125.84 秒，不属于稳态增量编译对照。

实际运行另做了配对：相同旧蓝图和相同输入分别运行旧、新程序，每类排除一次预热，再交错运行三次，
限制 2 个 CPU、2 个 Mesa 线程，隐藏 GPU、开发源码和 SDK。三个相同输入的截图均 RGBA 零差异。

| 共享 WSL 实测中位数 | 旧版、同一界面 | 新版、同一界面 | 差值 |
|---|---:|---:|---:|
| worker ready | 2.646 s | 3.188 s | +0.542 s |
| 首张完整 PNG | 2.902 s | 3.766 s | +0.864 s |
| ready 时 RSS | 691.86 MiB | 696.68 MiB | +4.82 MiB |
| 进程峰值 RSS | 744.47 MiB | 756.67 MiB | +12.20 MiB |

额外的四纹理与 Image 动画场景首图为 3.450 s、峰值 RSS 777.41 MiB；它与旧场景不同，不作为
代码自身的增量开销。时间样本范围、全部命令、进程映射与测量原始数据见
[配对运行报告](../artifacts/widget-textures/runtime-benchmark-01/summary.json)。这是本机共享 WSL 的
三次样本，OS 缓存可能已热，每次使用新的用户/Mesa/DDC 目录，不能解释为冷启动或云端专机性能。
