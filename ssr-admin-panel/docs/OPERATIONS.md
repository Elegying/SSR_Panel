# SSR Admin Panel 运维手册

这份手册面向生产服务器部署、更新、验证和卸载。所有命令默认以 `root` 身份执行。

## 支持环境

- x86_64 容器冒烟：Ubuntu 22.04、Debian 12、Rocky Linux 9，仅覆盖依赖安装、测试套件和 Shell 语法，不包含真实 systemd 部署
- 安装识别：Debian/Ubuntu 与 RHEL/Rocky/Alma/CentOS Stream 系的 `apt-get`、`dnf`、`yum`
- CI 验证 Python 3.9 / 3.11 / 3.12；Python 3.6/3.7 仅保留尽力兼容依赖
- systemd 必须作为 PID 1；Docker、未启用 systemd 的 WSL 和 chroot 不支持自动部署
- x86_64 与 aarch64/ARM64 均使用发行版提供的 Python 和 `jq`；ARM64 未在 CI 实机验证

安装脚本会先刷新包索引，再一次性安装并验证 CA、`sudo`、`curl`、`wget`、`socat`、Git、Python/venv、systemd、iproute、jq 和防火墙兼容包。未知系统会在复制项目文件之前退出。

Debian/Ubuntu 刚重装后，`apt-daily`、`unattended-upgrades` 或 cloud-init 可能正在占用 dpkg。安装和更新脚本会使用 apt 原生锁机制等待最多 300 秒，并对网络/软件源错误重试 3 次，不会删除任何锁文件。慢速镜像可按需延长等待：

```bash
SSR_ADMIN_APT_LOCK_TIMEOUT=600 \
SSR_ADMIN_PACKAGE_INSTALL_RETRIES=3 \
bash install-all.sh
```

若等待后仍失败，应先用错误中显示的 PID 检查合法进程；不要手工删除 `/var/lib/dpkg/lock*`。

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

安装器只把 PBKDF2-SHA256 哈希写入 `config.py`。旧版本的 `ADMIN_PASS` 会在更新时自动迁移，原密码保持不变。

面板和设备统计以无登录 shell 的 `ssr-panel` 用户运行。源码目录由 root 持有；SSR 启停、防火墙同步、`mudb.json` 提交和面板更新只能通过固定提权助手执行。当前仍监听 `0.0.0.0:5000`，原有 `http://服务器IP:5000` 访问方式不变。

## 部署后验证

```bash
systemctl is-active ssr-admin
systemctl show ssr-admin -p User -p Group --value
journalctl -u ssr-admin -n 50 --no-pager
curl -I http://127.0.0.1:5000/
sudo -l -U ssr-panel
```

`systemctl show` 应显示 `ssr-panel`；`sudo -l` 只能列出 admin-helper 的固定动作，不应出现通配符或任意 shell。

如果服务器已经安装 SSR，再检查：

```bash
systemctl is-active ssr
systemctl is-active ssr-device-stats || true
nft list table inet ssr_filter
```

没有 `/usr/local/shadowsocksr/mudb.json` 时，面板安装会跳过设备统计服务，这是正常行为。

## 导入 mudb.json 与开放 SSR 端口

部署会安装 `/usr/local/libexec/ssr-panel/sync-firewall.py`，并在 SSR 每次启动前同步本机防火墙。同步范围包括 `mudb.json` 中所有有效用户端口，以及 `/etc/default/ssr-panel-firewall` 的附加端口；附加端口默认包含单端口多用户入口 `18899`：

```bash
# Managed by SSR_Panel
SSR_EXTRA_PORTS=18899
```

导入自己的配置后执行：

```bash
install -m 600 /root/mudb.json /usr/local/shadowsocksr/mudb.json
# helper 会校正 root:ssr-panel / 0640 权限并同步端口
/usr/local/libexec/ssr-panel/admin-helper firewall-sync
systemctl restart ssr ssr-device-stats
systemctl is-active ssr
cat /var/lib/ssr-panel-firewall/managed-ports.json
ss -lntup | grep ':18899' || true
```

需要额外入口时可写成 `SSR_EXTRA_PORTS="18899,24444"`，然后重启 SSR。面板新增或删除用户时也会即时同步。规则对 firewalld 或 iptables 的 TCP/UDP、IPv4/IPv6 后端幂等执行，并在端口退出配置后移除项目管理的旧规则。

本机防火墙放行不等于 SSR 已监听：`ss` 没有显示 `18899` 时，应检查导入配置本身。云厂商安全组不受本项目控制，还必须在云控制台单独放行 `18899/TCP` 和 `18899/UDP`。

## SSR 服务端网络优化

安装脚本会自动调用 `/opt/ssr-admin-panel/scripts/optimize_server.sh`。除 systemd、ulimit、sysctl、Fast Open、日志轮转、fail2ban 外，脚本还会默认启用面向 YouTube/Google 卡顿的服务端防护：

- 统一入口承载优化：适用于所有用户通过同一个入口端口（例如 `18899`）连接的部署，持久化 BBR/fq、TFO、`somaxconn`、`tcp_max_syn_backlog`、本地端口范围，以及 SSR systemd 文件句柄/进程数上限。
- 入站端口同步：默认放行 `18899/TCP+UDP`，并在 SSR 启动前根据 `mudb.json` 和附加端口配置同步 firewalld 或 iptables。
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

从 v1.3.1 或更早版本首次升级到低权限安全版时，建议直接运行远端的新版更新器，使源码同步和服务降权在同一事务中完成：

```bash
curl -fsSL https://raw.githubusercontent.com/Elegying/SSR_Panel/main/ssr-admin-panel/update.sh -o /tmp/ssr-panel-update.sh
bash /tmp/ssr-panel-update.sh main
rm -f /tmp/ssr-panel-update.sh
```

如果使用旧面板内的在线更新，旧更新器第一次只会同步新源码。新面板会继续显示“需要完成安全迁移”，再次执行更新后才会迁移密码、安装 helper 并把服务切换到 `ssr-panel`；这不是更新失败。

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

### 使用正式发布包回滚

GitHub Release 提供 `SSR_Panel-v1.4.0-rollback.tar.gz` 和 `SHA256SUMS`。把两个文件放在同一目录，先校验再解压执行：

```bash
sha256sum -c SHA256SUMS
tar -xzf SSR_Panel-v1.4.0-rollback.tar.gz
bash SSR_Panel-v1.4.0/ssr-admin-panel/rollback.sh --yes
```

回滚入口使用归档内的本地源码，不执行 Git clone；它仍复用更新器的互斥锁、完整备份、失败自动恢复、服务状态验证和 HTTP 健康检查。`config.py`、`mudb.json`、venv 与本地文件不会被归档内容直接覆盖。脚本会输出本次备份目录，便于继续人工恢复。

发布包用于已安装面板的版本恢复，不是全新系统安装包。正常回滚会复用服务器已有依赖；如果目标机缺少系统包或 Python 依赖，补齐依赖时仍可能访问软件源。

## SSR 来源与可复现性

完整安装默认从 `ToyoDAdoubiBackup/shadowsocksr` 的固定提交 `c4507b7af1fe20a5a6adbb5e3b5a86da9d3a35e8` 获取源码，并把实际 revision 写入 `/usr/local/shadowsocksr/.ssr-upstream-revision`。如需自定义上游，`SSR_UPSTREAM_REF` 仍必须是完整 40 位提交哈希：

```bash
SSR_UPSTREAM_REPO="https://github.com/your-name/shadowsocksr.git" \
SSR_UPSTREAM_REF="0123456789abcdef0123456789abcdef01234567" \
```bash
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

仅卸载面板会保留 SSR 的防火墙同步助手，避免后续 `systemctl restart ssr` 失败；使用 `--remove-ssr` 时才会一并清理默认 `18899`、用户端口规则和带托管标记的同步文件。

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
- 导入配置后 `18899` 不通：依次检查 `systemctl status ssr`、`journalctl -u ssr`、`ss -lntup`、本机防火墙和云安全组。
- 依赖安装失败：确认服务器可访问 PyPI 或配置可用的软件源。
