# SSR_Panel

SSR_Panel is the unified repository for SSR and AnyTLS management tooling.

## Projects

- `ssr-admin-panel`: SSR user traffic and account management panel.
- `anytls-panel`: AnyTLS and multi-protocol node management panel.
- `ssr-server-optimizer`: one-command optimizer for legacy Python SSR servers.

The original repositories were imported as Git subtrees, so their histories remain traceable in this monorepo. Each subproject keeps its own README, scripts, tests, and deployment notes.

## One-Command Deploy

SSR + admin panel:

```bash
curl -fsSL https://raw.githubusercontent.com/Elegying/SSR_Panel/main/ssr-admin-panel/install-all.sh -o install-all.sh && bash install-all.sh
```

SSR admin panel only:

```bash
curl -fsSL https://raw.githubusercontent.com/Elegying/SSR_Panel/main/ssr-admin-panel/install.sh -o install.sh && bash install.sh
```

AnyTLS panel:

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/Elegying/SSR_Panel/main/anytls-panel/deploy.sh)
```

SSR server optimizer:

```bash
curl -fsSL https://raw.githubusercontent.com/Elegying/SSR_Panel/main/ssr-server-optimizer/optimize-ssr.sh | bash
```

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
