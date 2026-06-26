# SSR Server Optimizer 运维手册

这个工具会修改 SSR 配置、systemd unit 和 sysctl 参数。生产服务器上建议先预检，再执行正式优化。

## 支持环境

- Ubuntu 20.04 / 22.04 / 24.04 / 26.04
- Debian 11 / 12
- systemd
- Python 3
- 旧版 Python ShadowsocksR，默认目录 `/usr/local/shadowsocksr`

## 预检

预检不会写入 `/etc`，也不会修改 SSR 配置：

```bash
bash optimize-ssr.sh --check
```

建议在正式执行前确认输出中的路径：

- `SSR_DIR`
- `SSR_CONFIG`
- `SYSCTL_FILE`
- `SERVICE_FILE`

## 执行优化

```bash
curl -fsSL https://raw.githubusercontent.com/Elegying/SSR_Panel/main/ssr-server-optimizer/optimize-ssr.sh -o optimize-ssr.sh
bash optimize-ssr.sh --check
bash optimize-ssr.sh
```

自定义 SSR 路径：

```bash
SSR_DIR="/usr/local/shadowsocksr" \
SSR_CONFIG="/usr/local/shadowsocksr/user-config.json" \
bash optimize-ssr.sh --check
```

## 执行后验证

```bash
systemctl is-active ssr
journalctl -u ssr -n 50 --no-pager
sysctl -n net.ipv4.tcp_max_syn_backlog
```

如果安装了 SSR Admin Panel，也可以检查：

```bash
systemctl is-active ssr-device-stats || true
```

## 回滚说明

脚本在修改文件前会生成带时间戳的 `.bak.*` 备份。执行过程中如果启动或验证失败，会尝试自动恢复本次修改过的文件。

如果执行成功后仍需人工回滚，请根据实际备份文件恢复：

```bash
ls -1 /usr/local/shadowsocksr/user-config.json.bak.* 2>/dev/null || true
ls -1 /etc/systemd/system/ssr.service.bak.* 2>/dev/null || true
ls -1 /etc/sysctl.d/99-z-ssr-performance.conf.bak.* 2>/dev/null || true
```

恢复后执行：

```bash
systemctl daemon-reload
sysctl --system
systemctl restart ssr
```

## 发布前检查

```bash
python3 -m unittest discover -s tests -q
bash -n optimize-ssr.sh
```

GitHub Actions 会在 push 和 pull request 时自动运行这些检查。

## 注意事项

- 不建议在容器内直接执行正式优化，很多 sysctl 参数可能被宿主机限制。
- 不建议把这个脚本当成通用 Linux 优化脚本；它面向旧版 Python SSR。
- 如需批量服务器执行，建议先在一台测试机完成预检和验证。
