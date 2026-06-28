# SSR_Panel

[![CI](https://github.com/Elegying/SSR_Panel/actions/workflows/ci.yml/badge.svg)](https://github.com/Elegying/SSR_Panel/actions/workflows/ci.yml)

ShadowsocksR / AnyTLS 代理服务端一站式管理面板。三项目合一仓库，支持一键部署、非交互批量安装、Python 虚拟环境隔离、断点续装和部署后健康检查。

---

## 📦 子项目

| 目录 | 用途 | 技术栈 |
|------|------|--------|
| `ssr-admin-panel/` | SSR 用户/流量/设备管理 Web 面板 | Python Flask + Shell |
| `anytls-panel/` | AnyTLS 多协议节点管理面板（支持 Trojan/VMess/VLESS 订阅） | Python Flask + Shell |
| `ssr-server-optimizer/` | SSR 服务器性能与安全一键优化（可独立运行） | Shell |

---

## 🚀 一键部署

### 方式一：完整部署（SSR + 面板 + 服务器优化）

```bash
curl -fsSL https://raw.githubusercontent.com/Elegying/SSR_Panel/main/ssr-admin-panel/install-all.sh -o install-all.sh && bash install-all.sh
```

脚本交互式引导输入管理员用户名、密码和分享域名，执行 7 个步骤：运行环境准备 → 下载项目 → 配置信息 → 安装 SSR → 安装 Python 运行时 → 部署面板服务 → 服务器优化 → 健康检查。

### 方式二：非交互式部署（批量脚本 / CI）

```bash
export SSR_ADMIN_USER="admin"
export SSR_ADMIN_PASS="your-secure-password"
export SSR_SHARE_HOST="your-node.example.com"
bash install-all.sh
```

详情参见 [环境变量配置](#环境变量配置)。

### 方式三：JSON 预置文件部署

```bash
cat > /tmp/ssr-deploy.json << 'JSON'
{
  "admin_user": "admin",
  "admin_pass": "your-secure-password",
  "share_host": "your-node.example.com",
  "port": 5000
}
JSON

SSR_DEPLOY_CONF=/tmp/ssr-deploy.json bash install-all.sh
```

### 仅安装面板（SSR 已存在）

```bash
curl -fsSL https://raw.githubusercontent.com/Elegying/SSR_Panel/main/ssr-admin-panel/install.sh -o install.sh && bash install.sh
```

### AnyTLS 面板

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/Elegying/SSR_Panel/main/anytls-panel/deploy.sh)
```

---

## 🛡️ 兼容性

| 系统 | Python | 状态 |
|------|--------|------|
| CentOS Stream 10 | 3.12 | ✅ |
| Debian 13 (Trixie) | 3.13 | ✅ |
| Ubuntu 24.04 LTS | 3.12 | ✅ |
| Ubuntu 20.04 LTS | 3.8 | ✅ |
| Debian 12 (Bookworm) | 3.11 | ✅ |
| CentOS 7/8 | 3.6+ | ⚠️（需手动升级 Python） |

**Python 版本要求：** ≥ 3.8（Flask 3.0 最低要求）

---

## ⚙️ 环境变量配置

| 变量 | 说明 | 示例 |
|------|------|------|
| `SSR_ADMIN_USER` | 面板管理员用户名 | `admin` |
| `SSR_ADMIN_PASS` | 面板管理员密码 | `your-password` |
| `SSR_SHARE_HOST` | 节点分享域名/IP | `node.example.com` |
| `SSR_PANEL_PORT` | 面板监听端口（默认 5000） | `8080` |
| `SSR_USE_VENV` | 0=强制系统 pip, 1=优先 venv | `1` |
| `SSR_DEPLOY_CONF` | JSON 预置文件路径 | `/tmp/ssr-deploy.json` |
| `SSR_ADMIN_REPO_URL` | 自定义仓库地址 | `https://...` |
| `SSR_ADMIN_UPDATE_REF` | 仓库分支 | `main` |

---

## 📋 v2.0 新特性（2026.06）

| 特性 | 说明 |
|------|------|
| **SSR 直接安装** | 不再通过 50 行管道交互安装 SSR，改为直接下载解压 + mujson_mgr.py 初始化 |
| **断点续装** | 状态文件 `/var/lib/ssr-admin-panel/.install-state` 追踪每步，失败后可从断点恢复 |
| **venv 虚拟环境** | 优先创建 Python venv 隔离安装，失败自动回退系统包 |
| **部署后健康检查** | 部署完成自动检查面板 HTTP 响应、SSR 进程、所有服务状态 |
| **端口冲突检测** | 部署前检测端口占用，自动处理旧实例或提示切换端口 |
| **iptables 统一兼容** | 所有系统自动检测和安装 iptables（ssrmu.sh 依赖） |
| **JSON 配置文件预置** | 支持 `SSR_DEPLOY_CONF` 加载 JSON 预置配置 |

---

## 🔧 部署后管理

```bash
# 重启面板
systemctl restart ssr-admin

# 更新面板
bash /opt/ssr-admin-panel/update.sh

# 卸载面板
bash /opt/ssr-admin-panel/uninstall.sh --yes

# 管理 SSR 用户
bash /opt/ssr-admin-panel/ssrmu.sh

# 查看面板日志
journalctl -u ssr-admin -f

# 查看健康状态
curl -s http://127.0.0.1:5000/
```

---

## 🏗️ 目录结构

```text
SSR_Panel/
├── ssr-admin-panel/              # SSR 管理面板
│   ├── install-all.sh            # 一键部署脚本（v2.0）
│   ├── install.sh                # 仅面板部署
│   ├── update.sh                 # 在线更新
│   ├── uninstall.sh              # 卸载脚本
│   ├── app.py                    # Flask Web 应用
│   ├── requirements.txt          # Python 依赖
│   ├── config.py.example         # 配置文件模板
│   ├── ssrmu.sh                  # SSR 多用户管理 CLI
│   ├── scripts/
│   │   ├── optimize_server.sh    # 服务器优化（7 步）
│   │   ├── patch_ssr_python_compat.py  # SSR Python 3.10+ 兼容
│   │   ├── collect_device_stats.py     # 设备统计采集
│   │   └── run_panel_update.py         # 面板自更新
│   ├── templates/                # HTML 模板
│   └── tests/                    # 测试用例
├── anytls-panel/                 # AnyTLS 面板
│   ├── deploy.sh                 # 一键部署
│   ├── app.py                    # Flask 应用
│   └── templates/                # HTML 模板
└── ssr-server-optimizer/         # SSR 优化工具（独立版）
    └── optimize-ssr.sh
```

---

## ⚠️ 注意事项

1. **必须以 root 权限运行** — 安装脚本需要写入系统目录、配置 systemd 服务
2. **默认监听 0.0.0.0:5000** — 建议部署后配置防火墙或 nginx 反向代理限制访问
3. **SSR 需要 libsodium** — 若使用 chacha20/salsa20 加密需单独安装
4. **Python 3.8 最低版本** — 更旧的系统请先升级 Python
5. **首次部署请修改默认分享密码** — 分享模板中的默认值仅用于测试，请在生产环境更换

---

## 📄 许可证

MIT License
