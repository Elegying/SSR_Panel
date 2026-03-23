# SSR Admin Panel

🛡️ 一个美观、现代化的 ShadowsocksR 用户管理面板

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

## 📸 截图

![Dashboard](screenshots/dashboard.png)

## 🚀 一键部署

```bash
curl -fsSL https://raw.githubusercontent.com/Elegying/ssr-admin-panel/main/install.sh | bash
```

## 📋 系统要求

- Python 3.7+
- Flask 3.0+
- 已安装 ShadowsocksR (mudb.json)

## ⚙️ 配置

安装后编辑 `/opt/ssr-admin-panel/app.py` 修改管理员账号：

```python
ADMIN_USER = 'your-username'
ADMIN_PASS = 'your-password'
```

## 🔧 手动安装

```bash
# 克隆项目
git clone https://github.com/Elegying/ssr-admin-panel.git
cd ssr-admin-panel

# 安装依赖
pip3 install -r requirements.txt

# 启动服务
python3 app.py
```

## 📁 项目结构

```
ssr-admin-panel/
├── app.py              # Flask主程序
├── requirements.txt    # Python依赖
├── install.sh          # 一键安装脚本
├── templates/
│   ├── index.html      # 主页面
│   └── login.html      # 登录页面
└── README.md           # 说明文档
```

## 🌐 访问

安装完成后访问：`http://your-server-ip:5000`

## 📝 License

MIT License

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！
