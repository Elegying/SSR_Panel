# SSR 服务器优化工具

[GitHub Actions](https://github.com/Elegying/SSR_Panel/actions)

适用于 Ubuntu / Debian 上老版 Python ShadowsocksR 的一键优化脚本。

## 📚 运维文档

- [生产预检、执行、回滚与排障手册](docs/OPERATIONS.md)
- 每次 push / pull request 会通过 GitHub Actions 自动运行单元测试和 shell 语法检查。

这个项目会自动完成我们前面手动做过的那一套优化，包括：

- 将 SSR 的 `timeout` 调整为 `300`
- 将 SSR 的 `udp_timeout` 调整为 `120`
- 开启 SSR `fast_open`
- 优化内核 TCP 与 socket 缓冲参数，提升稳定性和吞吐表现
- 将 SSR 改为 `systemd` 托管，支持自动重启与开机自启
- 如果检测到 `/opt/ssr-admin-panel`，同步刷新面板设备统计服务
- 在修改前自动备份原配置文件

## 适用环境

- Ubuntu 20.04 及以上
- Debian 系发行版
- SSR 安装目录为 `/usr/local/shadowsocksr`
- 使用 `user-config.json` 的老版 Python SSR

## 一行命令使用

在目标服务器上以 `root` 身份执行：

```bash
curl -fsSL https://raw.githubusercontent.com/Elegying/SSR_Panel/main/ssr-server-optimizer/optimize-ssr.sh | bash
```

如果你想从本地直接远程执行：

```bash
ssh root@你的服务器IP "curl -fsSL https://raw.githubusercontent.com/Elegying/SSR_Panel/main/ssr-server-optimizer/optimize-ssr.sh | bash"
```

## 预检模式

正式优化前可以先做只读检查：

```bash
bash optimize-ssr.sh --check
```

预检只确认 SSR 目录、`user-config.json`、`systemctl`、`python3`、`sysctl` 和 `ss` 是否可用，不会写入 `/etc` 或修改 SSR 配置。

## 脚本会做什么

- 更新 `/usr/local/shadowsocksr/user-config.json`
  - `timeout = 300`
  - `udp_timeout = 120`
  - `fast_open = true`
- 写入 `/etc/sysctl.d/99-z-ssr-performance.conf`
- 如果系统里存在旧的 `tcp_max_syn_backlog = 1024` 覆盖项，会自动修正
- 创建 `/etc/systemd/system/ssr.service`
- 如已安装 SSR Admin Panel，创建或刷新 `ssr-device-stats.service`
- 重载 `sysctl` 与 `systemd`
- 用 `systemd` 重新拉起 SSR
- 执行前输出变更摘要；执行失败时按备份自动恢复已修改文件

## 安全性

- 修改前会创建带时间戳的备份
- 如果启动或校验失败，会恢复已备份文件并重载 systemd
- 除必要优化项外，尽量保留原有 SSR 配置
- 自动识别实际安装的 `python` / `python3` 路径

## 验证与排查

本地发版前建议运行：

```bash
bash -n optimize-ssr.sh
python3 -m unittest discover -s tests -q
```

服务器上执行后可检查：

```bash
systemctl status ssr --no-pager
journalctl -u ssr -n 50 --no-pager
sysctl -n net.ipv4.tcp_max_syn_backlog
```

如果 `sysctl --system` 报告某些内核参数不支持，脚本会输出 `/tmp/ssr-optimizer-sysctl.log` 的位置，方便确认是容器/内核限制还是配置问题。

## 项目文件

- `optimize-ssr.sh`：主优化脚本
- `LICENSE`：MIT 许可证

## 说明

- 当前版本不负责限制 SSR 管理面板访问来源
- 当前版本主要面向你现在使用的这类老版 Python SSR 架构
- 如果后续需要，我可以继续扩展批量多服务器执行、面板访问限制、日志检查等功能
