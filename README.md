# SSR Admin Panel

🛡️ 一个美观、现代化的 ShadowsocksR 用户管理面板，支持一键部署 SSR + 管理面板

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/Python-3.7+-green.svg)
![Flask](https://img.shields.io/badge/Flask-3.0+-orange.svg)

## ✨ 功能特性

- 📊 **实时监控** - 查看所有用户的流量使用情况
- 📱 **设备统计** - 按账号端口统计当前/近期连接来源数量
- 👤 **用户管理** - 添加、删除、启用/禁用用户
- 🔄 **流量重置** - 一键重置用户流量
- 📈 **数据可视化** - 流量进度条、统计卡片
- 🔍 **搜索过滤** - 按用户名/端口搜索
- 📊 **流量排序** - 按流量使用量一键排序
- 🔐 **登录验证** - 保护管理面板安全
- 📱 **响应式设计** - 完美支持手机访问

---

## 🚀 安装部署

### 方式一：下载后运行（推荐）

```bash
# 下载安装脚本
wget https://raw.githubusercontent.com/Elegying/ssr-admin-panel/main/install-all.sh

# 运行安装
bash install-all.sh
```

### 方式二：一键命令

```bash
curl -fsSL https://raw.githubusercontent.com/Elegying/ssr-admin-panel/main/install-all.sh -o install-all.sh && bash install-all.sh
```

安装过程中会提示：
1. 设置管理面板用户名/密码
2. 自动安装SSR
3. 自动部署管理面板

### 方式三：仅安装管理面板

已安装SSR的服务器，只安装管理面板：

```bash
wget https://raw.githubusercontent.com/Elegying/ssr-admin-panel/main/install.sh && bash install.sh
```

---

## 📋 系统要求

- 操作系统: CentOS 6+ / Debian 8+ / Ubuntu 16.04+
- Python: 3.7+
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
- 重启 `ssr-admin` 服务
- 如果新版本启动失败，自动恢复上一版应用并重启服务

查看当前部署版本：

```bash
bash /opt/ssr-admin-panel/update.sh --version
```

如果你维护的是自己的 GitHub 分支或 fork，也可以临时指定更新源：

```bash
SSR_ADMIN_REPO_URL="https://github.com/your-name/ssr-admin-panel.git" \
SSR_ADMIN_UPDATE_REF="main" \
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
