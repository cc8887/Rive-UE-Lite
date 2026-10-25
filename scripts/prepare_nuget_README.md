# 离线恢复 UBT 的 NuGet 依赖

源码、csproj 和版本声明保持原样；仅将准确版本的 nupkg 放进此原型的本地 feed。Windows 可以访问 NuGet CDN，而当前 WSL 的外网连接不可用，所以在 Windows 下载，再让 Linux 重新执行 NuGet restore。

```powershell
python scripts/prepare_nuget_feed.py `
  --central engine/Directory.Packages.props `
  --project engine/Engine/Source/Programs/UnrealBuildTool/UnrealBuildTool.csproj `
  --feed dependencies/nuget-feed `
  --download `
  --report artifacts/setup/ubt-build-local-packages.log
```

该命令遍历项目引用和可静态解析的 props，按中央声明的确切版本准备直接依赖；保存中央声明 SHA-256、下载 URL、包 SHA-256 和字节数。然后在 WSL 中构建：

```bash
NUGET_CERT_REVOCATION_MODE=offline scripts/build_linux.sh ubt \
  --source dependencies/nuget-feed \
  -p:NuGetAudit=false
```

`NuGetAudit=false` 避免在离线构建中查询远程漏洞审计源；`NUGET_CERT_REVOCATION_MODE=offline` 让签名证书吊销检查使用离线模式。这里没有关闭 NuGet 包签名验证。初次尝试即使只设置本地 source，仍在等待远程 80 端口连接；增加上述环境配置后开始正常恢复并输出完整的传递依赖错误。

若 restore 报告还有传递包缺失，可直接消费完整日志，一次处理所有去重后的包：

```powershell
python scripts/prepare_nuget_feed.py `
  --central engine/Directory.Packages.props `
  --from-log artifacts/setup/ubt-build-local-03.log `
  --feed dependencies/nuget-feed `
  --download `
  --report artifacts/setup/ubt-build-local-packages-02.log
```

中央声明中存在的包始终采用该声明的版本；未被中央声明列出的传递包，采用 NuGet 缺失错误明确要求的依赖版本。不会用 feed 内碰巧已有的旧版本替换。未知版本的请求保持 `incomplete`，不猜测包版本。此工具准备 feed，最终依赖选择和编译是否通过仍由原始 Linux MSBuild/NuGet 决定。
