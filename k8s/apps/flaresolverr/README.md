# FlareSolverr

Internal-only [FlareSolverr](https://github.com/FlareSolverr/FlareSolverr) proxy
that Prowlarr can route Cloudflare/DDoS-GUARD-protected indexers through
(for example 1337x). It runs one replica in the `media` namespace beside
Prowlarr and is reachable only inside the cluster.

## What this deploys

- `Deployment/flaresolverr` (1 replica) from
  `ghcr.io/flaresolverr/flaresolverr:v3.5.2`, pinned by digest.
- `Service/flaresolverr` of type `ClusterIP` on port `8191`.
- `NetworkPolicy/flaresolverr`: only the Prowlarr pod may call port `8191`;
  FlareSolverr may resolve DNS and reach the public web on 80/443. There is no
  ingress, NodePort, LoadBalancer or tailnet exposure and no authentication, so
  do not expose it.

The manifests are rendered by the `app-template` chart. `values.yaml` is the
source of truth; `networkpolicy.yaml` is applied by the ArgoCD Application
`k8s/argocd/apps/flaresolverr.yaml` via `directory.include`.

## Internal Service DNS URL

Prowlarr connects to FlareSolverr at:

```
http://flaresolverr.media.svc.cluster.local:8191
```

Within the `media` namespace the short form `http://flaresolverr:8191` works
too. Do not use the ingress host: this Service has no Ingress.

## Manual setup in Prowlarr

Live configuration is deliberately not managed by GitOps, so set this up by
hand in the Prowlarr UI:

1. `Settings -> Indexers -> Indexer Proxies -> + -> FlareSolverr`.
2. **Name**: `FlareSolverr`.
3. **Tags**: create and apply a tag, e.g. `flaresolverr`. Only indexers that
   share a tag with the proxy use it, so the tag must match on both sides.
4. **Host**: `http://flaresolverr.media.svc.cluster.local:8191`.
5. Save, then edit the Cloudflare-protected indexer (e.g. 1337x) and add the
   same `flaresolverr` tag to it.
6. Click **Test**:
   - On the indexer proxy, **Test** makes Prowlarr send a request *through*
     FlareSolverr to its own `/ping` endpoint and validates the JSON response,
     confirming FlareSolverr is reachable and working.
   - On the tagged indexer, **Test** verifies the indexer itself responds. The
     proxy only engages when Prowlarr detects a Cloudflare response, so a
     passing indexer test alone is not proof the proxy was used.

A quick connectivity check from any pod in the cluster:

```sh
curl -s http://flaresolverr.media.svc.cluster.local:8191/health
# {"status":"ok"}
```

## Caveats

FlareSolverr is a **best-effort** Cloudflare helper. It is not guaranteed to
solve every challenge, and Cloudflare changes obfuscation regularly. It also
says nothing about the torrents themselves: it neither validates that a
release is genuine nor detects malicious content. Keep using the existing
indexer/quality checks and treat any release with the usual caution.

## Image updates

The image tag and digest are pinned and, following the repo convention, are
tracked by Renovate (the `k8s/apps/**/values.yaml` custom manager). The
`v3.5.2` digest was verified against both the GitHub Container Registry and
Docker Hub.

## Security notes

- Runs as the image's non-root user (`1000:1000`), `runAsNonRoot: true`,
  `allowPrivilegeEscalation: false`, all capabilities dropped, and the
  `RuntimeDefault` seccomp profile. No privileged mode and no added
  capabilities.
- `readOnlyRootFilesystem` is intentionally **not** enabled: Chromium and
  `undetected-chromedriver` write their profile, cache and patched driver under
  the non-root home directory, so a read-only root would prevent browser
  start-up. For the same reason FlareSolverr runs Chromium with
  `--no-sandbox`; this is required for it to work as a non-root user inside a
  container.
- No media volumes, config PVCs or credentials are mounted. The app has no
  `/config` mount by design and reads everything from environment variables.
