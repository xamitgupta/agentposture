# Deployment

AgentPosture is one process with one SQLite file. Pick the option that matches how you run
internal tools.

## Local or a single VM

```bash
pip install "agentposture[aws]"         # [aws] only if you use the Bedrock connector
agentposture init --org "Acme Corp"
export AGENTPOSTURE_TOKEN=$(openssl rand -hex 32)
agentposture serve
```

For a service that survives reboots, use the hardened unit in `deploy/systemd/agentposture.service`:
config in `/etc/agentposture/agentposture.yaml`, secrets in `/etc/agentposture/env`
(`chmod 600`), data in `/var/lib/agentposture`.

## Docker

```bash
docker build -t agentposture .
docker run -d --name agentposture -p 127.0.0.1:8484:8484 \
  -v $PWD/agentposture.yaml:/config/agentposture.yaml:ro \
  -v agentposture-data:/data \
  -e AGENTPOSTURE_TOKEN -e GITHUB_TOKEN \
  agentposture
```

Set `storage.path: /data/agentposture.db` in the mounted config. The image runs as a non-root user,
works with a read-only root filesystem, and has a health check on `/healthz`.
`docker compose up` in the repository runs the demo; the compose file shows the lines to change for
real use.

## Kubernetes

`deploy/kubernetes/agentposture.yaml` has a Deployment, Service and PersistentVolumeClaim with a
restricted security context. Keep `replicas: 1` and the `Recreate` strategy (SQLite has one writer).
Use IRSA or EKS Pod Identity for AWS credentials and a Secret for tokens.

## Putting it behind single sign-on

The dashboard shows a map of your organization's AI risk; treat it as sensitive. Recommended setup:

1. Bind AgentPosture to `127.0.0.1` or keep its Service cluster-internal.
2. Put an authenticating proxy in front, such as oauth2-proxy, your ingress controller's OIDC
   support, Cloudflare Access, Google IAP, or AWS ALB authentication, limited to your security, GRC
   and platform groups.
3. Set `server.api_token` so scans and registrations need the token even from inside the network.
4. Expose only `/api/webhooks/*` publicly if you use webhooks; those requests are verified by
   signature.

## Sizing

The tool is light: the registry is rebuilt in memory from evidence on each reconcile, so memory grows
with the number of evidence records, and a few thousand agents need very little. Scans are bound by the source APIs: a GitHub organization with thousands of repositories
takes a while, so schedule it every few hours and rely on webhooks for freshness.

## Backups and upgrades

- Back up the single database file. With the server running, use
  `sqlite3 agentposture.db ".backup backup.db"` for a consistent copy.
- Everything in the database can be rebuilt by scanning, except API registrations, assessment
  history and trend snapshots.
- Upgrades: install the new version and restart. The schema is created on start, and any future
  schema change will ship with an automatic migration noted in CHANGELOG.md.

## Operating it

- `/healthz` for liveness; `/api/sources` shows each source's last result and error.
- `agentposture -v serve` for debug logs.
- A failing source never blocks the others; its error appears on the Sources page.
- Publish a weekly static report for people without dashboard access:
  `agentposture report -f html -o posture.html` (self-contained) or `-f md` for a wiki page.
