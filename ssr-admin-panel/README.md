# SSR Admin Panel

🛡️ 一个美观、现代化的 ShadowsocksR 用户管理面板，支持一键部署 SSR + 管理面板

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/Python-3.7+-green.svg)
![Flask](https://img.shields.io/badge/Flask-3.0+-orange.svg)
[GitHub Actions](https://github.com/Elegying/SSR_Panel/actions)

## 📚 运维文档

- [生产部署、更新、卸载与排障手册](docs/OPERATIONS.md)
- 每次 push / pull request 会通过 GitHub Actions 自动运行单元测试和 shell 语法检查。

## ✨ 功能特性

- 📊 **实时监控** - 查看所有用户的流量使用情况
- 📱 **设备统计** - 按账号端口统计当前/近期连接来源数量
- 👤 **用户管理** - 添加、删除、启用/禁用用户
- 🔄 **流量重置** - 一键重置用户流量
- 📈 **数据可视化** - 流量进度条、统计卡片
- 🔍 **搜索过滤** - 按用户名/端口搜索
- 📊 **流量排序** - 按流量使用量一键排序
- 🔐 **登录验证** - 保护管理面板安全
- 🚀 **服务端视频优化** - 一键部署时自动禁止无出口 IPv6 目标，默认放行出站 UDP/443 以保留 YouTube/Google QUIC/HTTP3 首连体验
- 📱 **响应式设计** - 完美支持手机访问

---

## 🚀 安装部署

### 方式一：下载后运行（推荐）

```bash
# 下载安装脚本
wget https://raw.githubusercontent.com/Elegying/SSR_Panel/main/ssr-admin-panel/install-all.sh

# 运行安装
bash install-all.sh
```

### 方式二：一键命令

```bash
curl -fsSL https://raw.githubusercontent.com/Elegying/SSR_Panel/main/ssr-admin-panel/install-all.sh -o install-all.sh && bash install-all.sh
```

安装过程中会提示：
1. 设置管理面板用户名/密码
2. 自动安装SSR
3. 自动部署管理面板
4. 自动应用 SSR 服务端优化（BBR/TFO、IPv6 目标防护、UDP/443 放行、fail2ban）

完整部署首次创建 SSR 默认用户时，初始密码会保存到 `/opt/ssr-admin-panel/.initial_ssr_password`，部署输出默认隐藏密码和 SSR 链接；如确需打印敏感值，可临时设置 `SSR_ADMIN_SHOW_SECRETS=1`。

### 方式三：仅安装管理面板

已安装SSR的服务器，只安装管理面板：

```bash
wget https://raw.githubusercontent.com/Elegying/SSR_Panel/main/ssr-admin-panel/install.sh && bash install.sh
```

---

## 📋 系统要求

- 操作系统: Ubuntu 18.04+ / Debian 10+ / CentOS Stream 或 RHEL 系 8+（需 systemd）
- Python: 3.6+（推荐 3.8+；Python 3.6/3.7 会自动安装兼容版依赖）
- 内存: 512MB+

---

## ⚙️ 配置文件

安装后配置文件位于：`/opt/ssr-admin-panel/config.py`

```python
ADMIN_USER = 'your-username'    # 管理员用户名
ADMIN_PASS = 'your-password'    # 管理员密码
SECRET_KEY = '...'              # Session密钥（自动生成）
MUDB_FILE = '/usr/local/shadowsocksr/mudb.json'  # SSR用户文件
DEVICE_STATS_FILE = '/var/lib/ssr-admin-panel/device-stats.json'  # 设备统计文件
```

修改配置后重启服务：
```bash
systemctl restart ssr-admin
```

---

## 🔧 常用命令

```bash
# 查看面板状态
systemctl status ssr-admin

# 重启面板
systemctl restart ssr-admin

# 查看面板日志
journalctl -u ssr-admin -f

# 更新面板到最新版本
bash /opt/ssr-admin-panel/update.sh

# 管理SSR用户
bash /usr/local/shadowsocksr/shadowsocks/mujson_mgr.sh
```

## 🚀 SSR 服务端优化

`install-all.sh` 和检测到 SSR 的 `install.sh` 会自动调用：

```bash
bash /opt/ssr-admin-panel/scripts/optimize_server.sh
```

该脚本默认会：

- 面向统一入口端口（例如 `18899`）的多用户部署，持久化 BBR/fq、TFO、连接队列、端口范围和 systemd 文件句柄/进程数上限，提升单入口承载能力。
- 为 `mudb.json` 的用户配置写入 `forbidden_ip`，禁止代理 IPv6 目标 `::/0`，避免服务器没有 IPv6 出口时 YouTube/Google 连接反复超时。
- 默认放行服务器出站 `udp/443`，并清理旧版脚本留下的 QUIC 拦截规则，避免浏览器首次连接先失败再回落。
- 保留已有 nftables/fail2ban 表，避免覆盖现有防火墙规则。

如需临时关闭 IPv6 目标防护，或强制启用 UDP/443 拦截让 QUIC 回落到 TCP：

```bash
SSR_BLOCK_IPV6_TARGETS=0 bash /opt/ssr-admin-panel/scripts/optimize_server.sh
SSR_BLOCK_UDP_443=1 bash /opt/ssr-admin-panel/scripts/optimize_server.sh
```

## 🔄 更新机制

项目现在内置了版本文件 `VERSION` 和一键更新脚本 `update.sh`。

线上服务器更新默认只需要执行：

```bash
bash /opt/ssr-admin-panel/update.sh
```

脚本会自动：

- 从 GitHub 拉取最新代码
- 保留现有 `config.py`
- 备份完整旧版应用到 `/opt/ssr-admin-panel/backups/`
- 检测到 SSR 时重新应用服务端优化
- 重启 `ssr-admin` 服务
- 如果新版本启动失败，自动恢复上一版应用并重启服务

查看当前部署版本：

```bash
bash /opt/ssr-admin-panel/update.sh --version
```

如果你维护的是自己的 GitHub 分支或 fork，也可以临时指定更新源：

```bash
SSR_ADMIN_REPO_URL="https://github.com/your-name/SSR_Panel.git" \
SSR_ADMIN_UPDATE_REF="main" \
SSR_ADMIN_REPO_SUBDIR="ssr-admin-panel" \
bash /opt/ssr-admin-panel/update.sh
```

## ✅ 部署验证与排查

推荐部署后执行：

```bash
systemctl is-active ssr-admin
systemctl is-active ssr-device-stats
journalctl -u ssr-admin -n 50 --no-pager
```

本地开发或发版前建议运行：

```bash
python3 -m pip install -r requirements.txt
bash -n install.sh install-all.sh update.sh
python3 -m unittest discover -s tests -q
```

常见问题：

- `Flask 运行时安装失败`：执行 `python3 -m pip show Flask flask-limiter` 检查依赖。
- `项目文件更新失败`：执行 `git -C /opt/ssr-admin-panel status --short` 查看是否有本地改动阻止快进。
- `更新后服务启动失败`：查看 `/opt/ssr-admin-panel/backups/` 中的自动备份和 `journalctl -u ssr-admin -n 50 --no-pager`。

---

## 🌐 访问

安装完成后访问：`http://your-server-ip:5000`

---

## 📝 更新日志

### v1.0.0
- 初始版本
- 用户管理（添加/删除/启用/禁用）
- 流量监控与重置
- 登录验证
- 流量排序功能
- SSR一键部署集成
- 内置SSR安装脚本

---

## 📄 License

MIT License

---

## ☕ 支持

如果觉得有用，请给个 ⭐️ Star 支持一下！
