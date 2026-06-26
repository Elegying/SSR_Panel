# SSR_Panel

[![CI](https://github.com/Elegying/SSR_Panel/actions/workflows/ci.yml/badge.svg)](https://github.com/Elegying/SSR_Panel/actions/workflows/ci.yml)


SSR 和 AnyTLS 面板工具统一仓库，一站式管理代理服务端。

## 📦 项目概述

本仓库采用 Git Subtree 方案，将三个相关项目整合为一个 Monorepo，方便统一管理和部署。每个子项目保持独立的 README、脚本和测试。

## 🗂️ 子项目

| 子项目 | 说明 | 主要技术 |
|--------|------|----------|
| `ssr-admin-panel` | SSR 用户流量与账号管理面板 | Python / Shell |
| `anytls-panel` | AnyTLS 多协议节点管理面板 | Shell |
| `ssr-server-optimizer` | 一键优化旧版 Python SSR 服务器 | Shell |

## 🚀 一键部署

### SSR + 管理面板（完整部署）

```bash
curl -fsSL https://raw.githubusercontent.com/Elegying/SSR_Panel/main/ssr-admin-panel/install-all.sh -o install-all.sh && bash install-all.sh
```

### 仅 SSR 管理面板

```bash
curl -fsSL https://raw.githubusercontent.com/Elegying/SSR_Panel/main/ssr-admin-panel/install.sh -o install.sh && bash install.sh
```

### AnyTLS 面板

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/Elegying/SSR_Panel/main/anytls-panel/deploy.sh)
```

### SSR 服务器优化

```bash
curl -fsSL https://raw.githubusercontent.com/Elegying/SSR_Panel/main/ssr-server-optimizer/optimize-ssr.sh | bash
```

## 📁 目录结构

```text
SSR_Panel/
├── ssr-admin-panel/        # SSR 管理面板
│   ├── install.sh          # 单独部署脚本
│   ├── install-all.sh      # 完整部署脚本
│   └── README.md           # 详细说明
├── anytls-panel/           # AnyTLS 面板
│   ├── deploy.sh           # 部署脚本
│   └── README.md           # 详细说明
└── ssr-server-optimizer/   # SSR 服务器优化工具
    ├── optimize-ssr.sh     # 优化脚本
    └── README.md           # 详细说明
```

## ✅ 常用检查

### Python 语法检查

```bash
python -m compileall ssr-admin-panel anytls-panel ssr-server-optimizer
```

### Shell 脚本语法检查

```bash
bash -n ssr-admin-panel/*.sh anytls-panel/*.sh ssr-server-optimizer/*.sh
```

## 📖 使用说明

各子项目的安装部署、配置方法和使用说明，请参阅对应目录下的 README 文件。

## 📄 许可证

MIT License
