# ADR-001: Deployment safety model

## Status

Accepted

## Date

2026-07-10

## Context

SSR_Panel installs and updates root-owned application files, Python dependencies, systemd units, firewall rules, and an old ShadowsocksR codebase. Earlier scripts mixed SysV, naked Python processes, and systemd; inferred success from directory existence; downloaded mutable upstream scripts; and only rolled back a subset of update failures. Those behaviors made a transient package, network, or service error capable of leaving a partially deployed server.

## Decision

- Treat a running systemd manager as a deployment prerequisite and use `ssr.service` as the sole supervisor whenever its managed unit exists.
- Bootstrap and verify the complete OS runtime before cloning project files or creating a venv. Unknown package managers fail closed.
- Pin the default SSR source to a full Git commit and generate the init compatibility script locally. Unverified legacy root-script features are opt-in and disabled by default.
- Treat panel updates as a transaction protected by a process lock. Back up application files, the complete venv, and affected systemd units; restore them on any post-backup error.
- Require both an active systemd service and a successful local HTTP request before committing an update.
- Keep SSR source patching and host optimization outside the default panel-update transaction; operators may request them explicitly.
- Mark managed directories so uninstall can distinguish intended custom targets from arbitrary filesystem paths.

## Alternatives considered

### Continue best-effort in-place updates

Rejected because dependency changes and application files can become incompatible, while service-only rollback cannot restore the previous Python environment.

### Use release-directory symlink swaps

This gives cleaner atomic releases, but would require a disruptive layout migration for existing `/opt/ssr-admin-panel` installations. Full backup and restore provides most of the safety with backward-compatible paths.

### Keep multiple SSR supervisors as fallbacks

Rejected because systemd, SysV autostart, cron monitoring, and daemonized `server.py` can start duplicate processes. A failed canonical supervisor should remain visible instead of silently launching another process model.

### Track mutable upstream branches

Rejected because the same installer command could execute different root-owned code over time. Full commit hashes make deployments reproducible and auditable.

## Consequences

- Automated deployment does not support environments without a real systemd PID 1.
- Update backups consume more disk because they include the venv.
- Updates may take slightly longer due to package verification and HTTP health checks.
- Legacy remote helper features require an explicit risk override.
- Operators gain deterministic SSR sources, one supervisor, and a recoverable update boundary.
