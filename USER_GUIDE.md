# SSR_Panel 运维指南

SSR_Panel 现在包含一个 Web 管理面板和一个服务器优化工具：

- `ssr-admin-panel`：管理 ShadowsocksR 用户、流量、设备统计和服务端优化。
- `ssr-server-optimizer`：优化老版 Python ShadowsocksR 的 TCP、systemd 和运行参数。

AnyTLS/多协议节点管理面板已拆分到独立仓库：[Elegying/AnyTLS_Panel](https://github.com/Elegying/AnyTLS_Panel)。

## 部署前准备

- 推荐使用 CI 已覆盖的 Ubuntu 22.04、Debian 12 或 Rocky Linux 9；同族的较新发行版也会按包管理器自动识别。
- 必须由 `systemd` 作为 PID 1。安装器会自动安装并验证 `sudo`、`curl`、`wget`、`socat`、Python/venv 等运行依赖。
- Web 面板建议放在 Nginx 反向代理和 HTTPS 后面。
- 执行安装脚本前，先确认服务器已有快照或备份。

极简 Debian/Ubuntu 镜像如果没有下载器，先以 root 执行：

```bash
apt-get update && apt-get install -y ca-certificates sudo curl wget
```

RHEL/Rocky/Alma/CentOS Stream 可执行：

```bash
dnf install -y ca-certificates sudo curl wget
```

## 快速部署

### 部署 SSR Admin Panel

如果需要同时安装 SSR 和管理面板：

```bash
curl -fsSL https://raw.githubusercontent.com/Elegying/SSR_Panel/main/ssr-admin-panel/install-all.sh -o install-all.sh
sudo bash install-all.sh
```

如果服务器已安装 SSR，只增加管理面板：

```bash
curl -fsSL https://raw.githubusercontent.com/Elegying/SSR_Panel/main/ssr-admin-panel/install.sh -o install.sh
sudo bash install.sh
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

SSR Admin Panel 安装时会提示设置管理员用户名和密码，配置保存在 `/opt/ssr-admin-panel/config.py`。

完整部署首次创建 SSR 默认用户时，SSR 初始密码会保存到 `/opt/ssr-admin-panel/.initial_ssr_password`，文件仅 root 可读。部署日志默认不直接打印面板密码、SSR 密码或 SSR 链接。

如果忘记 SSR Admin Panel 密码，可在服务器上编辑：

```bash
nano /opt/ssr-admin-panel/config.py
systemctl restart ssr-admin
```

## 常见操作

### 管理 SSR 用户

SSR Admin Panel 支持在 Web 页面中添加、删除、启用、禁用用户，并查看流量与设备统计。命令行仍可使用原 SSR 管理脚本：

```bash
bash /usr/local/shadowsocksr/shadowsocks/mujson_mgr.sh
```

### 更新 SSR Admin Panel

```bash
bash /opt/ssr-admin-panel/update.sh
```

更新由互斥锁保护，会备份应用、venv 和 systemd unit；新服务必须同时通过 systemd 状态与本机 HTTP 健康检查，否则自动恢复。更新默认不修改 SSR 源码或重新执行服务器优化，需要时显式开启：

```bash
SSR_ADMIN_PATCH_SSR_COMPAT=1 \
SSR_ADMIN_APPLY_SERVER_OPTIMIZATION=1 \
bash /opt/ssr-admin-panel/update.sh
```

查看当前版本：

```bash
bash /opt/ssr-admin-panel/update.sh --version
```

## 服务管理

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

- SSR Admin Panel 配置：`/opt/ssr-admin-panel/config.py`。
- SSR 用户文件：`/usr/local/shadowsocksr/mudb.json`。
- 面板服务文件：`/etc/systemd/system/ssr-admin.service`。

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
- 未经校验的 BBR、ServerSpeeder、LotServer 等远程 root 脚本保持默认禁用。

## 排障入口

部署或更新后建议先检查：

```bash
systemctl is-active ssr-admin
systemctl is-active ssr
journalctl -u ssr-admin -n 50 --no-pager
journalctl -u ssr -n 50 --no-pager
```

如果优化脚本执行失败，先查看脚本输出中的备份路径和 `/tmp/ssr-optimizer-sysctl.log`。大多数失败都可以通过自动备份恢复到执行前状态。
