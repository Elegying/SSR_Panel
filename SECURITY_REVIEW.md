# CodeQL 告警处理记录（2026-10-09）

## #1–#9：异常信息外泄

进程执行、日志读取、更新状态写入、备份和分享链接异常统一返回不含异常对象的固定提示。
操作仍明确返回失败，保留原有 HTTP 状态、事务和备份保护。测试注入含内部路径/敏感查询内容的异常，
验证进程返回值和真实 Flask 接口不会回显该内容。

## #10、#11：脱敏测试使用的假口令

位置在 tests/test_installers.py 的 test_ssr_install_log_sanitizer_removes_credentials_and_share_links。
写入的是常量 fixture-secret-value，不是用户口令或运行时秘密；TemporaryDirectory 隔离测试文件。
测试故意生成包含假口令、分享链接及宽松权限的日志，验证生产脱敏器将内容清除并把权限收紧到 0600。
删除这段测试或预先脱敏会丢失原来的安全回归覆盖。因此以 used in tests 关闭这两条，而保留测试。

## #12、#13：mudb.json 的 0640

SSR 后端由 root 运行，面板以专用非登录用户 ssr-panel 运行。mudb.json 由 root 拥有，
仅 root 可写、专用 ssr-panel 组可读，其他用户无权限。0600 会使低权限面板无法读取账号数据，
将文件改由面板拥有则会扩大面板写入权限。

新增显式校验：面板 UID/GID 必须非 root，组名必须为 ssr-panel；专用组不能包含其他附加成员，
也不能被其他账号用作主组。不满足时拒绝写入和权限调整。保留 0640，并以 false positive 记录
这两处经过隔离校验的最小共享读取权限。扫描规则继续启用，不做全局排除。
