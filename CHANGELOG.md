# Changelog

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
