# SSR Panel 运维指南

SSR Panel 是一套 ShadowsocksR/AnyTLS 多节点管理面板，包含 AnyTLS Panel 和 SSR Admin Panel 两个后台。

## 快速部署

```bash
git clone https://github.com/Elegying/SSR_Panel.git
cd SSR_Panel
# 部署 AnyTLS 面板
cd anytls-panel && bash deploy.sh
# 或：部署 SSR 管理面板
cd ssr-admin-panel && bash install.sh
```

## 功能概览

### AnyTLS Panel
- **多账户管理**：订阅 URL 导入，自动解析节点
- **流量统计**：记录每账户流量使用量
- **到期提醒**：订阅过期日期显示
- **节点列表**：查看/搜索所有节点
- **Web API**：提供节点查询 HTTP API

### SSR Admin Panel
- **用户管理**：添加/编辑/删除 SSR 用户
- **设备统计**：连接设备数和流量图表
- **服务器优化**：一键 TCP 优化脚本
- **审计日志**：所有操作记录到 `/var/log/ssr-admin-panel/`
- **CSRF 保护**：防跨站请求伪造

## 默认账户

首次部署后自动创建管理员账户：

- 用户名：`admin`
- 密码：随机生成（首次启动时输出到终端）

> ⚠️ 请首次登录后立即修改密码。

## 常见操作

**添加订阅账户（AnyTLS Panel）**
1. 登录面板 → 点击「添加账户」
2. 输入账户名称和订阅 URL
3. 系统自动解析节点并开始流量统计

**同步所有订阅**
```bash
# 手动触发同步（需登录后访问）：
curl -X POST https://your-server/api/sync-all
```

**查看流量统计**
1. 进入账户详情页
2. 查看「已用流量 / 总流量」和到期时间

**修改管理员密码**
- AnyTLS Panel：登录后点击右上角用户菜单 → 修改密码
- SSR Admin Panel：编辑 `config.py` 中的 `ADMIN_PASS`

## 安全建议

1. **部署 Nginx 反向代理 + HTTPS**
2. **修改默认端口号**
3. **定期更新**：`bash update.sh`
4. **备份数据库**：`cp anytls.db /var/backups/`
5. **防火墙限制**：仅允许管理 IP 访问 Web 端口

## 服务器优化

```bash
cd ssr-server-optimizer
bash optimize-ssr.sh
```

该脚本会自动优化 TCP 参数、文件描述符限制、内核参数等。
