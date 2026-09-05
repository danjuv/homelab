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

## Apps

| App | Purpose |
|-----|---------|
| Sonarr | TV show management |
| Radarr | Movie management |
| Prowlarr | Indexer management |
| qBittorrent | Torrent client |
| Seer | Media request management |
| Tautulli | Plex/media server monitoring |
| Homepage | Dashboard |
| Hermes | Private AI agent API ([setup](k8s/apps/hermes/README.md)) |

## Structure

```
k8s/
  argocd/apps/    # ArgoCD Application manifests (one per app)
  admin/          # Helm values and config for cluster infrastructure
  apps/           # Helm values and config for workloads
```
