# Changelog

## v1.0.0 (2026-06-26)

### Security
- anytls-panel: 修复两处 f-string SQL 拼接，改为字段列表白名单
- security_utils.py 加入版本控制

### Added
- GitHub Actions CI 工作流（lint + test）
- LICENSE 文件

### Changed
- 部署入口统一到 SSR_Panel 顶层
