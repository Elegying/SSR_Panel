# SSR Admin Panel 运维手册

这份手册面向生产服务器部署、更新、验证和卸载。所有命令默认以 `root` 身份执行。

## 支持环境

- Ubuntu 20.04 / 22.04 / 24.04 / 26.04
- Debian 11 / 12
- Python 3.8+
- systemd

CentOS/RHEL 系脚本仍保留兼容分支，但建议优先在 Ubuntu/Debian 上部署和测试。

## 部署方式

完整安装 SSR + 面板：

```bash
curl -fsSL https://raw.githubusercontent.com/Elegying/ssr-admin-panel/main/install-all.sh -o install-all.sh
bash install-all.sh
```

仅安装管理面板：

```bash
curl -fsSL https://raw.githubusercontent.com/Elegying/ssr-admin-panel/main/install.sh -o install.sh
bash install.sh
```

非交互安装可通过环境变量传入管理员账号：

```bash
SSR_ADMIN_USER="admin" \
SSR_ADMIN_PASS="change-this-password" \
bash install.sh
```

## 部署后验证

```bash
systemctl is-active ssr-admin
journalctl -u ssr-admin -n 50 --no-pager
curl -I http://127.0.0.1:5000/
```

如果服务器已经安装 SSR，再检查：

```bash
systemctl is-active ssr
systemctl is-active ssr-device-stats || true
nft list table inet ssr_filter
```

没有 `/usr/local/shadowsocksr/mudb.json` 时，面板安装会跳过设备统计服务，这是正常行为。

## SSR 服务端网络优化

安装脚本会自动调用 `/opt/ssr-admin-panel/scripts/optimize_server.sh`。除 systemd、ulimit、sysctl、Fast Open、日志轮转、fail2ban 外，脚本还会默认启用两项面向 YouTube/Google 卡顿的服务端防护：

- IPv6 目标防护：为 `/usr/local/shadowsocksr/user-config.json` 和 `/usr/local/shadowsocksr/mudb.json` 写入 `forbidden_ip`，包含 `127.0.0.0/8,::1/128,::/0`。服务器没有真实 IPv6 出口时，SSR 会快速拒绝 IPv6 目标，客户端通常会回落到 IPv4。
- QUIC 回落：写入 `/etc/nftables.d/ssr-filter.nft`，只拦截服务器出站 `udp/443`，不拦截 `tcp/443`。这会促使 YouTube/Google 从 QUIC/HTTP3 回落到 TCP/TLS。

相关配置会备份为同目录 `.bak-YYYYmmdd-HHMMSS` 文件。运行时规则和持久化配置可用下面的命令检查：

```bash
nft list table inet ssr_filter
grep -R "::/0" /usr/local/shadowsocksr/mudb.json /usr/local/shadowsocksr/user-config.json
```

临时关闭某项优化：

```bash
SSR_BLOCK_IPV6_TARGETS=0 bash /opt/ssr-admin-panel/scripts/optimize_server.sh
SSR_BLOCK_UDP_443=0 bash /opt/ssr-admin-panel/scripts/optimize_server.sh
```

## 更新

```bash
bash /opt/ssr-admin-panel/update.sh
```

指定仓库或分支：

```bash
SSR_ADMIN_REPO_URL="https://github.com/Elegying/ssr-admin-panel.git" \
SSR_ADMIN_UPDATE_REF="main" \
bash /opt/ssr-admin-panel/update.sh
```

更新脚本会保留 `config.py`，并在启动失败时尝试回滚到自动备份。

如果服务器存在 `/usr/local/shadowsocksr`，更新脚本也会重新应用 SSR 服务端优化。临时跳过：

```bash
SSR_ADMIN_APPLY_SERVER_OPTIMIZATION=0 bash /opt/ssr-admin-panel/update.sh
```

## 卸载

仅卸载面板和设备统计服务，保留 SSR 本体：

```bash
bash /opt/ssr-admin-panel/uninstall.sh --yes
```

保留面板目录和统计数据，只禁用服务：

```bash
bash /opt/ssr-admin-panel/uninstall.sh --yes --keep-data
```

同时移除 SSR 本体需要显式确认：

```bash
bash /opt/ssr-admin-panel/uninstall.sh --yes --remove-ssr
```

## 发布前检查

```bash
python3 -m pip install -r requirements.txt
python3 -m unittest discover -s tests -q
bash -n install.sh install-all.sh update.sh scripts/optimize_server.sh ssrmu.sh uninstall.sh
```

GitHub Actions 会在 push 和 pull request 时自动运行这些检查。

## 常见排障

- 面板无法启动：执行 `journalctl -u ssr-admin -n 50 --no-pager`。
- 更新失败：执行 `git -C /opt/ssr-admin-panel status --short` 检查本地改动。
- 设备统计服务未运行：先确认 `/usr/local/shadowsocksr/mudb.json` 是否存在。
- 依赖安装失败：确认服务器可访问 PyPI 或配置可用的软件源。
