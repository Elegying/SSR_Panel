# SSR_Panel

SSR_Panel is the unified repository for SSR and AnyTLS management tooling.

## Projects

- `ssr-admin-panel`: SSR user traffic and account management panel.
- `anytls-panel`: AnyTLS and multi-protocol node management panel.
- `ssr-server-optimizer`: one-command optimizer for legacy Python SSR servers.

The original repositories were imported as Git subtrees, so their histories remain traceable in this monorepo. Each subproject keeps its own README, scripts, tests, and deployment notes.

## Layout

```text
SSR_Panel/
  ssr-admin-panel/
  anytls-panel/
  ssr-server-optimizer/
```

## Common Checks

Python syntax check:

```bash
python -m compileall ssr-admin-panel anytls-panel ssr-server-optimizer
```

Shell script syntax check:

```bash
bash -n ssr-admin-panel/*.sh anytls-panel/*.sh ssr-server-optimizer/*.sh
```

For runtime installation, deployment, and service configuration, follow the README inside the relevant subproject.
