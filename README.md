# homelab

Kubernetes homelab managed with ArgoCD using the app of apps pattern. All apps are defined in `k8s/argocd/apps/` and synced automatically.

Helm chart versions are kept up to date via [Renovate](https://docs.renovatebot.com/).

## Infrastructure

| App | Purpose |
|-----|---------|
| ArgoCD | GitOps controller |
| MetalLB | Bare metal load balancer |
| ingress-nginx | Ingress controller (via Tailscale) |
| Tailscale | Mesh VPN and load balancer |
| cert-manager | TLS certificate management |
| external-dns | Automatic DNS records via Pi-hole |
| sealed-secrets | Encrypted secrets safe to commit |
| Longhorn | Distributed block storage |
| csi-driver-nfs | NFS CSI driver |
| nfs-volumes | NFS persistent volume definitions |
| OpenCode | Autonomous coding agent; opens PRs from background tasks |

## Apps

| App | Purpose | URL |
|-----|---------|-----|
| Sonarr | TV show management | [sonarr.home.lab](https://sonarr.home.lab) |
| Radarr | Movie management | [radarr.home.lab](https://radarr.home.lab) |
| Prowlarr | Indexer management | [prowlarr.home.lab](https://prowlarr.home.lab) |
| qBittorrent | Torrent client | [qbt.home.lab](https://qbt.home.lab) |
| Seer | Media request management | [overseerr.home.lab](https://overseerr.home.lab) |
| Tautulli | Plex/media server monitoring | [tautulli.home.lab](https://tautulli.home.lab) |
| Homepage | Dashboard | [home.lab](https://home.lab) |
| Home Assistant | Home automation | [homeassistant.home.lab](https://homeassistant.home.lab) |

## Structure

```
k8s/
  argocd/apps/    # ArgoCD Application manifests (one per app)
  admin/          # Helm values and config for cluster infrastructure
  apps/           # Helm values and config for workloads
terraform/
  home-assistant/ # Home Assistant application config (applied by hand)
```

## Terraform

ArgoCD deploys workloads; it does not run Terraform. `terraform/` holds application-level
configuration that lives inside an app rather than in Kubernetes, applied by hand with
`terraform plan`/`apply`. Credentials come from `TF_VAR_*` environment variables and are never
committed. `terraform fmt`, `validate` and `test` run without credentials.

| Root | Configures |
|------|------------|
| [`terraform/home-assistant`](terraform/home-assistant/README.md) | Home Assistant labels, floors, areas and helpers |
