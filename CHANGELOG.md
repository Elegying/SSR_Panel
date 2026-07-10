# Changelog

## v1.3.0 (2026-07-10)

### Security
- SSR 安装源码固定到提交 `c4507b7af1fe20a5a6adbb5e3b5a86da9d3a35e8` 并核对实际 Git revision；服务脚本改为仓库内模板，不再下载远程 init 脚本。
- 未经校验的 BBR、ServerSpeeder、LotServer、BT/PT/SPAM 和源码编译脚本默认禁用；卸载器会在任何副作用前校验服务名、删除路径、符号链接和托管标记。
- 安装和更新拒绝越界项目子目录及目标路径任一层的符号链接，避免 root 文件同步逃逸到部署范围外。
- `mudb.json` 写操作增加进程锁和原子替换；JSON 损坏时拒绝覆盖，避免并发添加用户或异常写入造成数据丢失。

### Added
- 安装前自动刷新 apt/dnf/yum 索引，安装并验证 `sudo`、`curl`、`socat`、CA、Python、venv、systemd、iptables 等完整基础环境。
- 更新流程增加互斥锁、应用/venv/systemd unit 完整备份、全阶段错误捕获、自动回滚和本机 HTTP 健康检查。
- CI 增加 Python 3.9/3.11/3.12、Ubuntu 22.04、Debian 12、Rocky Linux 9、ShellCheck 与依赖安全审计。

### Fixed
- 修复两个优化器误启用单端口底层入口，统一以 `/usr/local/shadowsocksr/server.py m` 启动读取 `mudb.json` 的多用户服务。
- systemd 接管 SSR 时禁用旧 SysV 自启动，面板也只调用唯一的 systemd 管理入口，避免重复进程。
- 完整卸载 SSR 时同步移除托管的旧 SysV 脚本和 `mudb.json` 对应的 IPv4/IPv6 防火墙端口规则。
- ARM64 等非 x86_64 系统不再误用 `jq-linux32`，统一链接发行版提供的 `jq`。
- 安装器不再强制覆盖服务器时区；firewalld 和 iptables/nft 兼容层均可配置幂等端口规则。
- 安装和更新覆盖源码时保留本地文件；完整安装会验证 SSR 入口、配置和 `mudb.json`，不再只凭目录存在判断成功。

### Changed
- 面板更新默认不修改 SSR 源码或重新运行服务器优化；需要时分别显式设置 `SSR_ADMIN_PATCH_SSR_COMPAT=1`、`SSR_ADMIN_APPLY_SERVER_OPTIMIZATION=1`。
- Python 依赖只安装到面板 venv，移除对 venv 不可见的系统 Flask 包回退。

- ssr-admin-panel: `optimize_server.sh` 默认放行服务器出站 UDP/443，并清理旧版部署留下的 QUIC 拦截规则；如需强制 TCP 回落，可显式设置 `SSR_BLOCK_UDP_443=1`。
- anytls-panel: 拆分到独立仓库 https://github.com/Elegying/AnyTLS_Panel，SSR_Panel 仅保留 SSR 管理面板和服务器优化工具。
- ssr-admin-panel: 修复更新脚本复制 `venv/lib64` 失败、内置优化脚本 `--check` 误执行、默认 SSR 密码固定、敏感配置权限过宽和优化摘要端口误报问题。

## v1.0.1 (2026-06-26)

### Fixed
- install.sh / install-all.sh: 修复 Debian 12+ (PEP 668) 下 pip 安装 waitress/flask 等依赖失败的问题，添加 `--break-system-packages` 参数
- optimize_server.sh: 修复 `setup_fail2ban()` 缺少 Debian/Ubuntu 的 `apt-get install fail2ban` 路径，导致未安装 fail2ban 就写配置文件报错退出
- anytls-panel: 流量上报 API 增加 Bearer token / `X-API-Token` 鉴权，避免匿名写入流量数据

### Changed
- anytls-panel: 部署脚本会生成并保留 `.traffic_api_token`
- anytls-panel: `traffic_collector.sh` 上报流量时需要配置 `API_TOKEN`

## v1.0.0 (2026-06-26)

### Security
- anytls-panel: 修复两处 f-string SQL 拼接，改为字段列表白名单
- security_utils.py 加入版本控制

### Added
- GitHub Actions CI 工作流（lint + test）
- LICENSE 文件

### Changed
- 部署入口统一到 SSR_Panel 顶层
