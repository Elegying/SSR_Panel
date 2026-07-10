# SSR_Panel

[![CI](https://github.com/Elegying/SSR_Panel/actions/workflows/ci.yml/badge.svg)](https://github.com/Elegying/SSR_Panel/actions/workflows/ci.yml)

SSR_Panel 是 SSR 管理面板和服务器优化工具的统一仓库，用于集中维护 ShadowsocksR 服务端管理面板和老版 ShadowsocksR 服务器优化脚本。

本仓库采用 Monorepo 组织方式，每个子项目保留独立 README、部署脚本、依赖文件和测试，方便按需部署，也方便统一 CI 检查。

## 子项目

| 子项目 | 说明 | 主要技术 |
| --- | --- | --- |
| `ssr-admin-panel` | ShadowsocksR 用户、流量、设备统计和服务端优化管理面板 | Python / Flask / Shell |
| `ssr-server-optimizer` | 面向老版 Python ShadowsocksR 的一键性能优化和 systemd 托管脚本 | Shell / Python unittest |

AnyTLS/多协议节点管理面板已拆分到 [Elegying/AnyTLS_Panel](https://github.com/Elegying/AnyTLS_Panel) 独立维护。

## 快速部署

安装脚本会在复制项目或创建 Python 环境前，自动刷新软件源并安装 `sudo`、`curl`、`wget`、`socat`、CA 证书、Python/venv、systemd 等依赖。服务器如果连下载器都没有，先以 root 执行：

```bash
# Debian / Ubuntu
apt-get update && apt-get install -y ca-certificates sudo curl wget

# Rocky / AlmaLinux / RHEL / CentOS Stream
dnf install -y ca-certificates sudo curl wget
```

安装器要求真正由 systemd 作为 PID 1 管理；Docker、未启用 systemd 的 WSL 和 chroot 会在写入系统前停止并说明原因。

### SSR + 管理面板完整部署

```bash
curl -fsSL https://raw.githubusercontent.com/Elegying/SSR_Panel/main/ssr-admin-panel/install-all.sh -o install-all.sh
sudo bash install-all.sh
```

### 仅部署 SSR 管理面板

适用于服务器上已安装 ShadowsocksR，只需要增加 Web 管理面板的场景：

```bash
curl -fsSL https://raw.githubusercontent.com/Elegying/SSR_Panel/main/ssr-admin-panel/install.sh -o install.sh
sudo bash install.sh
```

### 优化老版 SSR 服务器

```bash
curl -fsSL https://raw.githubusercontent.com/Elegying/SSR_Panel/main/ssr-server-optimizer/optimize-ssr.sh -o optimize-ssr.sh
sudo bash optimize-ssr.sh --check
sudo bash optimize-ssr.sh
```

如果没有 `curl` 但已有 `wget`，可将下载命令替换为：

```bash
wget -O install-all.sh https://raw.githubusercontent.com/Elegying/SSR_Panel/main/ssr-admin-panel/install-all.sh
```

## 支持与验证矩阵

| 范围 | 状态 |
| --- | --- |
| Ubuntu 22.04、Debian 12、Rocky Linux 9 | CI 容器持续验证 |
| Debian/Ubuntu 与 RHEL/Rocky/Alma/CentOS Stream 系 | 安装器按 `apt-get`、`dnf`、`yum` 自动识别 |
| Python 3.9、3.11、3.12 | CI 持续验证 |
| x86_64、aarch64/ARM64 | 使用系统 Python 与系统 `jq`，不再选择 x86 专用二进制 |
| Python 3.6/3.7 | 保留兼容依赖分支，但已 EOL，属于尽力兼容 |

未知发行版不会再默认当作 Debian 执行。OpenRC、SysV-only 和非 systemd 容器不在自动部署范围内。

## 目录结构

```text
SSR_Panel/
├── ssr-admin-panel/          # SSR 用户管理面板
│   ├── install.sh            # 仅安装面板
│   ├── install-all.sh        # 安装 SSR + 面板 + 优化
│   ├── update.sh             # 线上更新脚本
│   └── README.md             # 子项目说明
├── ssr-server-optimizer/     # SSR 服务器优化工具
│   ├── optimize-ssr.sh       # 优化脚本
│   └── README.md             # 子项目说明
├── USER_GUIDE.md             # 运维使用指南
└── CHANGELOG.md              # 更新记录
```

## 本地开发和检查

Python 语法检查：

```bash
python -m compileall ssr-admin-panel ssr-server-optimizer
```

Shell 脚本语法检查：

```bash
bash -n ssr-admin-panel/*.sh ssr-admin-panel/scripts/*.sh ssr-server-optimizer/*.sh
```

子项目单元测试：

```bash
python -m unittest discover -s ssr-admin-panel/tests -q
python -m unittest discover -s ssr-server-optimizer/tests -q
```

GitHub Actions 会在 push 和 pull request 时自动运行 CI。
根工作流还会执行 ShellCheck、Python 依赖审计，以及 Ubuntu/Debian/Rocky 的容器冒烟测试。

## 运维文档

- `USER_GUIDE.md`：整体部署、常见操作和安全建议。
- `ssr-admin-panel/README.md`：SSR 管理面板安装、配置、更新和排障。
- `ssr-server-optimizer/README.md`：SSR 优化脚本的预检、执行、回滚和验证。
- [Elegying/AnyTLS_Panel](https://github.com/Elegying/AnyTLS_Panel)：AnyTLS/多协议节点面板部署、订阅导入、API 和管理命令。

## 安全建议

- 面板建议部署在 Nginx 反向代理后，并启用 HTTPS。
- 首次部署后确认管理员密码，并妥善保存 `/opt/ssr-admin-panel/.initial_ssr_password` 中的 SSR 初始密码。
- Web 管理端口应通过防火墙限制访问来源。
- 定期备份数据库、配置文件和 SSR 用户文件。
- 不要在 Issue、日志、截图或命令历史中泄露订阅 URL、密码、服务器 IP、token 或面板凭据。
- 完整安装默认使用固定 SSR 上游提交；`ssrmu.sh` 中未经校验的远程 root 脚本默认禁用。

## 许可证

MIT License
