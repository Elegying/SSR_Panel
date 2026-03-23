# SSR Admin Panel

🛡️ 一个美观、现代化的 ShadowsocksR 用户管理面板，支持一键部署 SSR + 管理面板

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/Python-3.7+-green.svg)
![Flask](https://img.shields.io/badge/Flask-3.0+-orange.svg)

## ✨ 功能特性

- 📊 **实时监控** - 查看所有用户的流量使用情况
- 👤 **用户管理** - 添加、删除、启用/禁用用户
- 🔄 **流量重置** - 一键重置用户流量
- 📈 **数据可视化** - 流量进度条、统计卡片
- 🔍 **搜索过滤** - 按用户名/端口搜索
- 📊 **流量排序** - 按流量使用量一键排序
- 🔐 **登录验证** - 保护管理面板安全
- 📱 **响应式设计** - 完美支持手机访问

---

## 🚀 一键部署（推荐）

### 方式一：SSR + 管理面板 同时安装

**全新服务器，一条命令安装 SSR 和管理面板：**

```bash
curl -fsSL https://raw.githubusercontent.com/Elegying/ssr-admin-panel/main/install-all.sh | bash
```

安装过程中会提示：
1. 设置管理面板用户名/密码
2. 自动安装SSR
3. 自动部署管理面板

### 方式二：仅安装管理面板

**已安装SSR的服务器，只安装管理面板：**

```bash
curl -fsSL https://raw.githubusercontent.com/Elegying/ssr-admin-panel/main/install.sh | bash
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
```

修改配置后重启服务：
```bash
systemctl restart ssr-admin
```

---

## 📁 项目结构

```
ssr-admin-panel/
├── app.py              # Flask主程序
├── config.py.example   # 配置文件示例
├── requirements.txt    # Python依赖
├── install.sh          # 单独安装面板
├── install-all.sh      # SSR+面板一键安装
├── ssrmu.sh            # SSR安装脚本（内置）
├── templates/
│   ├── index.html      # 主页面
│   └── login.html      # 登录页面
└── README.md           # 说明文档
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

# 管理SSR用户
bash /usr/local/shadowsocksr/shadowsocks/mujson_mgr.sh
```

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

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

---

## ☕ 支持

如果觉得有用，请给个 ⭐️ Star 支持一下！
