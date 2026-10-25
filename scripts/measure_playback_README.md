该入口扩展独立 shader cook 和真实动画/状态机对照，不覆盖上一轮静态包体、内存、出图时间报告。

`measure_cook_provenance.py` 直接执行指定 compiler，把此前不存在的 archive、正常退出、完整日志、程序/源码/构建日志 hash 和 source pins 绑定在一次 UUID 执行中。允许 compiler 自己命中其已记录的 shader job cache；不得复制另一边 archive 代替执行。当前通过验证的 Lite cook 记录在 `artifacts/shaders-independent-lite-02/provenance.json`，Engine canonical 记录在 `artifacts/shaders-canonical/full-01/provenance/provenance.json`。两次均为真实独立执行，不能由相同截图或不同输出文件名推断。

实际完整结果在 `artifacts/playback-independent-02/summary.json`：60 次正常退出，30 对 RGBA/alpha 全图精确相同，16 项关键帧内容变化和12项同刻输入效果检查通过。画廊与简洁结果分别为同目录的 `gallery.html`、`review-summary.json`。第一轮 `artifacts/playback-independent-01` 保留真实失败：bankcard 有72399个不同像素；补齐 Lite 离线编译器实际 DXC 身份宏 `COMPILER_DXC=1` 后重新独立 cook、完整重跑，未改 Rive 算法、shader 源或像素门槛。旧编译器与源码快照在 `artifacts/playback/diagnostics/lite-compiler-before-dxc-02`。

`measure_playback_matrix.py` 的两边分别传 `--lite-archive`、`--reference-archive` 和对应的 `--*-cook-provenance`，同时记录 compiler 路径、构建日志及源码 API 路径。相同 archive 字节允许通过，但同一路径/inode、同一执行 UUID、同一执行日志、缺失 cook 或 hash 不符会拒绝。canonical 的覆盖范围取决于真实 cooker；只编译 Rive 和必要 RenderCore utility shaders 时，不能称为完整 UE global map 或 Editor/UMG 验证。

正式 gate 还要求被 hash 绑定的 archive manifest：完整、无 Type 诊断过滤、非 list-only、每个实际 permutation 成功且唯一，计数一致。canonical 必须提供实际 `permutation_ids` 和成功/失败 job 计数；两边 `/Plugin/Rive/` 的 type/permutation 集合须相同。FNULLPS 等过滤 smoke 的正常退出只证明该次诊断执行，不能通过正式 full-domain gate。

默认 `--coverage-profile independent-60-v1` 要求原五静态 fixtures、约定的五播放场景、19动态对照点和6同刻无输入控制，共60次捕获；删减会 incomplete。显式 `--coverage-profile custom-selected` 才允许其他选择，并在报告中明确标为自定义范围。静态分支从 source-state.json 核对 SHA，使用真实 legacy/default-artboard time0 路径；四张要求非透明且至少两种 RGBA 颜色，clip_tests 透明初态单列。

矩阵 manifest 为 JSON：

```json
{
  "schema_version": 1,
  "scenarios": [{
    "id": "trigger-state-machine",
    "fixture": "实际 fixture 的绝对路径或相对 manifest 的路径",
    "playback": {
      "mode": "state_machine",
      "artboard": "main",
      "state_machine": "State Machine 1",
      "fixed_delta": 0.016666666666666666,
      "events": [
        {"time": 0.25, "type": "trigger", "name": "Trigger 1"},
        {"time": 0.75, "type": "trigger", "name": "Trigger 1"}
      ]
    },
    "sample_times": [0, 0.25, 0.5, 0.75, 1],
    "required_changes": [{"from": 0, "to": 0.5}, {"from": 0.5, "to": 1}],
    "event_effect_sample_times": [0.5],
    "require_state_changes_after_events": true
  }]
}
```

上述名字来自 pinned runtime 的 `state_machine_triggers.riv` 单测，仅是场景协议示例；是否可见、是否产生所要求的像素变化，需要真实运行验证。animation 分支改用 `mode: "animation"` 和真实 `animation` 名字，省略 `state_machine`。sample/event 时间必须落在 fixed_delta tick；重名或错类型输入会由真实 helper 拒绝。

每个目标帧启动新进程，从零完整重放全部此前事件。t0 事件后执行一次 dt=0 初始化；随后先 advance(dt) 到该 tick，再应用该时刻事件，并在有事件的正 tick 追加一次 SM advanceAndApply(0) settle。这避免输入被提前一个 delta。metadata 必须提供真实选择 index、driver API 调用数、advanced_time、逐事件时间/tick/值、final inputs 和真实 state_changed/current_animations；不能只记录请求参数。两端 metadata 及每帧编码 RGBA8/alpha 必须精确相同，像素没有掩码和容差。

每个状态机场景还在同一 target_time 运行 no-events control（默认最后一采样，也可显式选 `event_effect_sample_times`）。要求每端有输入图与同刻 control 的像素确实不同，且实际 state_changes/current_animations 至少一项不同，排除仅自动动画随时间变化的假阳性。两个 control 之间继续要求 RGBA 精确一致。

实际运行参数（从独立工程根目录执行；复现时将 `--output-dir` 换成全新目录）：

```bash
sudo bash scripts/measure_no_gpu.sh -- python3 scripts/measure_playback_matrix.py \
  --lite-executable Binaries/Linux/RiveRhiLite \
  --reference-executable Binaries/Linux/RiveUeReference \
  --lite-project-dir "$PWD" --reference-project-dir "$PWD" \
  --lite-archive artifacts/shaders-independent-lite-02/global.bin \
  --lite-cook-provenance artifacts/shaders-independent-lite-02/provenance.json \
  --reference-archive artifacts/shaders-canonical/full-01/global.bin \
  --reference-cook-provenance artifacts/shaders-canonical/full-01/provenance/provenance.json \
  --lite-shader-directory Shaders --reference-shader-directory Shaders \
  --scenario-manifest fixtures/playback/scenarios.json \
  --output-dir artifacts/playback-independent-02 --execute
```

每次使用新的输出目录；省略 `--execute` 只记录 prepared/incomplete 计划。实际执行要求无 `/dev/dxg`、无 `/dev/dri` 的 namespace、单 CPU ICD 枚举与每个真实 capture 选中 CPU 的证据、双方正常退出、Lite 排除 Engine/Renderer、参考明确包含 Engine/Renderer。PNG、playback metadata、scenario、archive、程序和源文件 hash 保留在新报告。记录的过程时间仅为诊断，不能替代之前严格隔离缓存的正式性能数据。

运行完执行以下两个命令，分别生成原图画廊、简洁结果与链接审计：

```bash
python3 scripts/measure_playback_gallery.py --summary artifacts/playback-independent-02/summary.json
python3 scripts/measure_playback_review.py --summary artifacts/playback-independent-02/summary.json
```

画廊直接引用原始 PNG，并排展示每个时间点、输入记录、精确差异及 no-events controls；不读取/修改图像像素，不创建缩略图或拼接图，不改变 JSON gate。审计核验每个 PNG 的原 SHA、全部本地链接，并确认画廊引用的原始 PNG 路径集合与报告完全相同；结果保存在 `gallery-audit.json`。
