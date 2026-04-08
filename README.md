# homelab

Kubernetes homelab managed with ArgoCD using the app of apps pattern. All apps are defined in `k8s/argocd/apps/` and synced automatically.

Helm chart versions are kept up to date via [Renovate](https://docs.renovatebot.com/).

## Stack

| App | Purpose |
|-----|---------|
| ArgoCD | GitOps controller |
| MetalLB | Bare metal load balancer |
| ingress-nginx | Ingress controller |
| external-dns | Automatic DNS records via Pi-hole |
| sealed-secrets | Encrypted secrets safe to commit |
| Seer | Media request management |

## Structure

```
k8s/
  argocd/apps/    # ArgoCD Application manifests (one per app)
  admin/          # Helm values and config for cluster infrastructure
  apps/           # Helm values and config for workloads
```
