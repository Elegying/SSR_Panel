# SSR_Panel 运维指南

SSR_Panel 包含两类 Web 面板和一个服务器优化工具：

- `ssr-admin-panel`：管理 ShadowsocksR 用户、流量、设备统计和服务端优化。
- `anytls-panel`：通过订阅导入统一管理多协议节点账号。
- `ssr-server-optimizer`：优化老版 Python ShadowsocksR 的 TCP、systemd 和运行参数。

## 部署前准备

- 推荐使用 Ubuntu 20.04+ 或 Debian 10+。
- 服务器需要 `systemd`、`curl`、`bash`、`python3`。
- Web 面板建议放在 Nginx 反向代理和 HTTPS 后面。
- 执行安装脚本前，先确认服务器已有快照或备份。

## 快速部署

### 部署 AnyTLS Panel

```bash
git clone https://github.com/Elegying/SSR_Panel.git
cd SSR_Panel/anytls-panel
bash deploy.sh
```

指定端口：

```bash
bash deploy.sh 9090
```

### 部署 SSR Admin Panel

如果需要同时安装 SSR 和管理面板：

```bash
curl -fsSL https://raw.githubusercontent.com/Elegying/SSR_Panel/main/ssr-admin-panel/install-all.sh -o install-all.sh
bash install-all.sh
```

如果服务器已安装 SSR，只增加管理面板：

```bash
curl -fsSL https://raw.githubusercontent.com/Elegying/SSR_Panel/main/ssr-admin-panel/install.sh -o install.sh
bash install.sh
```

### 仅执行 SSR 优化

```bash
curl -fsSL https://raw.githubusercontent.com/Elegying/SSR_Panel/main/ssr-server-optimizer/optimize-ssr.sh | bash
```

正式执行前可先预检：

```bash
bash optimize-ssr.sh --check
```

## 默认账户和密码

首次部署后会创建管理员账户。不同子项目的账号来源略有差异：

- `anytls-panel`：部署脚本会创建管理员账号，首次登录后应立即修改密码。
- `ssr-admin-panel`：安装时会提示设置管理员用户名和密码，配置保存在 `/opt/ssr-admin-panel/config.py`。

如果忘记 SSR Admin Panel 密码，可在服务器上编辑：

```bash
nano /opt/ssr-admin-panel/config.py
systemctl restart ssr-admin
```

## 常见操作

### 添加 AnyTLS 订阅账号

1. 登录 AnyTLS Panel。
2. 进入「账号管理」。
3. 点击「导入订阅」。
4. 填写账号名称和订阅 URL。
5. 保存后执行同步，面板会自动解析节点、流量和到期时间。

### 同步所有订阅

```bash
curl -X POST https://your-server/api/sync-all
```

生产环境建议通过登录后的面板按钮操作，避免把管理接口暴露给公网脚本。

### 配置流量上报 token

AnyTLS Panel 的流量上报接口需要独立 API token。部署脚本会生成并保存到面板目录的 `.traffic_api_token`：

```bash
cat /opt/anytls-panel/.traffic_api_token
```

节点侧 `traffic_collector.sh` 需要配置：

```bash
PANEL_URL="https://your-panel.example"
PASSWORD="节点密码"
API_TOKEN="上面文件里的 token"
```

### 管理 SSR 用户

SSR Admin Panel 支持在 Web 页面中添加、删除、启用、禁用用户，并查看流量与设备统计。命令行仍可使用原 SSR 管理脚本：

```bash
bash /usr/local/shadowsocksr/shadowsocks/mujson_mgr.sh
```

### 更新 SSR Admin Panel

```bash
bash /opt/ssr-admin-panel/update.sh
```

查看当前版本：

```bash
bash /opt/ssr-admin-panel/update.sh --version
```

## 服务管理

AnyTLS Panel：

```bash
systemctl status anytls-panel
systemctl restart anytls-panel
journalctl -u anytls-panel -f
```

SSR Admin Panel：

```bash
systemctl status ssr-admin
systemctl restart ssr-admin
journalctl -u ssr-admin -f
```

SSR 服务：

```bash
systemctl status ssr --no-pager
journalctl -u ssr -n 50 --no-pager
```

## 备份建议

建议至少备份以下文件：

- AnyTLS Panel 数据库：`anytls-panel/anytls.db` 或部署目录中的数据库文件。
- SSR Admin Panel 配置：`/opt/ssr-admin-panel/config.py`。
- SSR 用户文件：`/usr/local/shadowsocksr/mudb.json`。
- 面板服务文件：`/etc/systemd/system/anytls-panel.service`、`/etc/systemd/system/ssr-admin.service`。

示例：

```bash
mkdir -p /var/backups/ssr-panel
cp /opt/ssr-admin-panel/config.py /var/backups/ssr-panel/
cp /usr/local/shadowsocksr/mudb.json /var/backups/ssr-panel/
```

## 安全检查清单

- 已启用 HTTPS。
- 已修改默认密码。
- 面板端口只允许可信 IP 访问。
- 服务器防火墙没有暴露不必要端口。
- 日志、截图和工单中没有订阅 URL、密码、token、服务器 IP 或面板凭据。
- 定期执行更新脚本并保留最近一次可恢复备份。

## 排障入口

部署或更新后建议先检查：

```bash
systemctl is-active anytls-panel
systemctl is-active ssr-admin
systemctl is-active ssr
journalctl -u anytls-panel -n 50 --no-pager
journalctl -u ssr-admin -n 50 --no-pager
journalctl -u ssr -n 50 --no-pager
```

如果优化脚本执行失败，先查看脚本输出中的备份路径和 `/tmp/ssr-optimizer-sysctl.log`。大多数失败都可以通过自动备份恢复到执行前状态。
