# SSR_Panel

[![CI](https://github.com/Elegying/SSR_Panel/actions/workflows/ci.yml/badge.svg)](https://github.com/Elegying/SSR_Panel/actions/workflows/ci.yml)

SSR_Panel 是 SSR、AnyTLS 和服务器优化工具的统一仓库，用于集中维护代理服务端管理面板、订阅节点管理和老版 ShadowsocksR 服务器优化脚本。

本仓库采用 Monorepo 组织方式，每个子项目保留独立 README、部署脚本、依赖文件和测试，方便按需部署，也方便统一 CI 检查。

## 子项目

| 子项目 | 说明 | 主要技术 |
| --- | --- | --- |
| `ssr-admin-panel` | ShadowsocksR 用户、流量、设备统计和服务端优化管理面板 | Python / Flask / Shell |
| `anytls-panel` | 通过订阅导入统一管理 anytls、trojan、vmess、vless、hysteria2、tuic、shadowsocks 等节点 | Python / Flask / Shell |
| `ssr-server-optimizer` | 面向老版 Python ShadowsocksR 的一键性能优化和 systemd 托管脚本 | Shell / Python unittest |

## 快速部署

### SSR + 管理面板完整部署

```bash
curl -fsSL https://raw.githubusercontent.com/Elegying/SSR_Panel/main/ssr-admin-panel/install-all.sh -o install-all.sh
bash install-all.sh
```

### 仅部署 SSR 管理面板

适用于服务器上已安装 ShadowsocksR，只需要增加 Web 管理面板的场景：

```bash
curl -fsSL https://raw.githubusercontent.com/Elegying/SSR_Panel/main/ssr-admin-panel/install.sh -o install.sh
bash install.sh
```

### 部署 AnyTLS 节点管理面板

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/Elegying/SSR_Panel/main/anytls-panel/deploy.sh)
```

也可以指定端口：

```bash
git clone https://github.com/Elegying/SSR_Panel.git
cd SSR_Panel/anytls-panel
bash deploy.sh 9090
```

### 优化老版 SSR 服务器

```bash
curl -fsSL https://raw.githubusercontent.com/Elegying/SSR_Panel/main/ssr-server-optimizer/optimize-ssr.sh | bash
```

正式执行前可先预检：

```bash
bash ssr-server-optimizer/optimize-ssr.sh --check
```

## 目录结构

```text
SSR_Panel/
├── ssr-admin-panel/          # SSR 用户管理面板
│   ├── install.sh            # 仅安装面板
│   ├── install-all.sh        # 安装 SSR + 面板 + 优化
│   ├── update.sh             # 线上更新脚本
│   └── README.md             # 子项目说明
├── anytls-panel/             # AnyTLS/多协议节点管理面板
│   ├── deploy.sh             # 部署脚本
│   ├── requirements.txt      # Python 依赖
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
python -m compileall ssr-admin-panel anytls-panel ssr-server-optimizer
```

Shell 脚本语法检查：

```bash
bash -n ssr-admin-panel/*.sh anytls-panel/*.sh ssr-server-optimizer/*.sh
```

子项目单元测试：

```bash
python -m unittest discover -s anytls-panel/tests -q
python -m unittest discover -s ssr-admin-panel/tests -q
python -m unittest discover -s ssr-server-optimizer/tests -q
```

GitHub Actions 会在 push 和 pull request 时自动运行 CI。

## 运维文档

- `USER_GUIDE.md`：整体部署、常见操作和安全建议。
- `ssr-admin-panel/README.md`：SSR 管理面板安装、配置、更新和排障。
- `anytls-panel/README.md`：AnyTLS/多协议节点面板部署、订阅导入、API 和管理命令。
- `ssr-server-optimizer/README.md`：SSR 优化脚本的预检、执行、回滚和验证。

## 安全建议

- 面板建议部署在 Nginx 反向代理后，并启用 HTTPS。
- 首次部署后立即修改默认管理员密码。
- Web 管理端口应通过防火墙限制访问来源。
- 定期备份数据库、配置文件和 SSR 用户文件。
- 不要在 Issue、日志、截图或命令历史中泄露订阅 URL、密码、服务器 IP、token 或面板凭据。

## 许可证

MIT License
