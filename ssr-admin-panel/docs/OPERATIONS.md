# SSR Admin Panel 运维手册

这份手册面向生产服务器部署、更新、验证和卸载。所有命令默认以 `root` 身份执行。

## 支持环境

- CI 验证：Ubuntu 22.04、Debian 12、Rocky Linux 9
- 安装识别：Debian/Ubuntu 与 RHEL/Rocky/Alma/CentOS Stream 系的 `apt-get`、`dnf`、`yum`
- CI 验证 Python 3.9 / 3.11 / 3.12；Python 3.6/3.7 仅保留尽力兼容依赖
- systemd 必须作为 PID 1；Docker、未启用 systemd 的 WSL 和 chroot 不支持自动部署
- x86_64 与 aarch64/ARM64 均使用发行版提供的 Python 和 `jq`

安装脚本会先刷新包索引，再一次性安装并验证 CA、`sudo`、`curl`、`wget`、`socat`、Git、Python/venv、systemd、iproute、jq 和防火墙兼容包。未知系统会在复制项目文件之前退出。

## 部署方式

极简 Debian/Ubuntu 如果尚无下载器，先以 root 执行：

```bash
apt-get update && apt-get install -y ca-certificates sudo curl wget
```

Rocky/RHEL 系对应执行：

```bash
dnf install -y ca-certificates sudo curl wget
```

完整安装 SSR + 面板：

```bash
curl -fsSL https://raw.githubusercontent.com/Elegying/SSR_Panel/main/ssr-admin-panel/install-all.sh -o install-all.sh
sudo bash install-all.sh
```

仅安装管理面板：

```bash
curl -fsSL https://raw.githubusercontent.com/Elegying/SSR_Panel/main/ssr-admin-panel/install.sh -o install.sh
sudo bash install.sh
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

安装脚本会自动调用 `/opt/ssr-admin-panel/scripts/optimize_server.sh`。除 systemd、ulimit、sysctl、Fast Open、日志轮转、fail2ban 外，脚本还会默认启用面向 YouTube/Google 卡顿的服务端防护：

- 统一入口承载优化：适用于所有用户通过同一个入口端口（例如 `18899`）连接的部署，持久化 BBR/fq、TFO、`somaxconn`、`tcp_max_syn_backlog`、本地端口范围，以及 SSR systemd 文件句柄/进程数上限。
- IPv6 目标防护：为 `/usr/local/shadowsocksr/mudb.json` 的用户配置写入 `forbidden_ip`，包含 `127.0.0.0/8,::1/128,::/0`。服务器没有真实 IPv6 出口时，SSR 会快速拒绝 IPv6 目标，客户端通常会回落到 IPv4。
- UDP/443 放行：默认清理旧版脚本留下的出站 `udp/443` 拦截，允许 YouTube/Google QUIC/HTTP3 首连成功，避免先失败再回落造成首屏卡顿。确需强制 TCP 回落时，可手动启用拦截。

相关配置会备份为同目录 `.bak-YYYYmmdd-HHMMSS` 文件。运行时规则和持久化配置可用下面的命令检查：

```bash
nft list table inet ssr_filter
grep -R "::/0" /usr/local/shadowsocksr/mudb.json
```

临时关闭 IPv6 目标防护，或强制启用 UDP/443 拦截：

```bash
SSR_BLOCK_IPV6_TARGETS=0 bash /opt/ssr-admin-panel/scripts/optimize_server.sh
SSR_BLOCK_UDP_443=1 bash /opt/ssr-admin-panel/scripts/optimize_server.sh
```

## 更新

```bash
bash /opt/ssr-admin-panel/update.sh
```

指定仓库或分支：

```bash
SSR_ADMIN_REPO_URL="https://github.com/Elegying/SSR_Panel.git" \
SSR_ADMIN_UPDATE_REF="main" \
SSR_ADMIN_REPO_SUBDIR="ssr-admin-panel" \
bash /opt/ssr-admin-panel/update.sh
```

更新脚本使用 `flock` 防止并发执行，保留 `config.py` 和本地文件，并备份应用文件、完整 venv 及相关 systemd unit。任何同步后步骤失败都会触发回滚；重启成功后还必须通过本机 HTTP 健康检查。

为避免面板更新意外修改 SSR 数据、网络规则或内核参数，更新默认不重新应用服务端优化，也不修补 SSR 源码。需要时显式启用：

```bash
SSR_ADMIN_PATCH_SSR_COMPAT=1 \
SSR_ADMIN_APPLY_SERVER_OPTIMIZATION=1 \
bash /opt/ssr-admin-panel/update.sh
```

可通过 `SSR_ADMIN_HEALTH_URL` 覆盖默认健康检查地址 `http://127.0.0.1:5000/login`。

## SSR 来源与可复现性

完整安装默认从 `ToyoDAdoubiBackup/shadowsocksr` 的固定提交 `c4507b7af1fe20a5a6adbb5e3b5a86da9d3a35e8` 获取源码，并把实际 revision 写入 `/usr/local/shadowsocksr/.ssr-upstream-revision`。如需自定义上游，`SSR_UPSTREAM_REF` 仍必须是完整 40 位提交哈希：

```bash
SSR_UPSTREAM_REPO="https://github.com/your-name/shadowsocksr.git" \
SSR_UPSTREAM_REF="0123456789abcdef0123456789abcdef01234567" \
bash /opt/ssr-admin-panel/ssrmu.sh
```

`ssrmu.sh` 的旧版 BBR、ServerSpeeder、LotServer、BT/PT/SPAM 和源码编译入口会下载未经本项目校验的 root 脚本，默认拒绝执行。只有完成独立审计后，才可临时设置 `SSR_ALLOW_UNVERIFIED_DOWNLOADS=1`；生产环境不建议开启。

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

默认路径保持向后兼容；通过环境变量使用自定义目录时，卸载器只接受包含 `.ssr-panel-managed` 标记且不穿越符号链接的目录。安装和更新脚本会自动创建该标记。

## 发布前检查

```bash
python3 -m pip install -r requirements.txt
python3 -m unittest discover -s tests -q
bash -n install.sh install-all.sh update.sh scripts/optimize_server.sh ssrmu.sh uninstall.sh
shellcheck --severity=error install.sh install-all.sh update.sh scripts/optimize_server.sh ssrmu.sh uninstall.sh
```

GitHub Actions 会在 push 和 pull request 时自动运行这些检查。

## 常见排障

- 面板无法启动：执行 `journalctl -u ssr-admin -n 50 --no-pager`。
- 更新失败：执行 `git -C /opt/ssr-admin-panel status --short` 检查本地改动。
- 设备统计服务未运行：先确认 `/usr/local/shadowsocksr/mudb.json` 是否存在。
- 依赖安装失败：确认服务器可访问 PyPI 或配置可用的软件源。
