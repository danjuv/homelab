# Hermes

Deploys the [unofficial Hermes Agent chart](https://github.com/ultraworkers/hermes-agent-helm-chart)
in the `hermes` namespace through Argo CD. The chart commit and container digest
are pinned. Kubernetes runs the gateway directly instead of the image's root-only
s6 supervisor. Operator CRDs are intentionally skipped.

State uses a single-writer 5Gi Longhorn PVC with `Recreate` updates. Argo CD does
not automatically prune or delete the PVC. The pod runs non-root with a read-only
root filesystem and no Kubernetes service-account token. Ingress is denied by
NetworkPolicy; outbound access remains available for model APIs and agent tools.

## Access

There is no web UI or ingress. Forward the API to localhost:

```bash
kubectl -n hermes port-forward service/hermes 8642:8642
```

In a separate terminal, retrieve the generated API credential and verify access:

```bash
export HERMES_API_KEY="$(kubectl -n hermes get secret hermes-secrets \
  -o jsonpath='{.data.API_SERVER_KEY}' | base64 --decode)"
curl --fail http://127.0.0.1:8642/health
curl --fail http://127.0.0.1:8642/v1/models \
  -H "Authorization: Bearer $HERMES_API_KEY"
```

OpenAI-compatible clients use base URL `http://127.0.0.1:8642/v1`, the generated
key, and model `hermes-agent`. Treat the key as shell access to the agent pod.
Do not forward to `0.0.0.0` or expose the API without additional access controls.

## OpenRouter Credentials

The initial Secret contains only `API_SERVER_KEY`. Health and model discovery can
work without a model-provider key, but inference cannot. The configured upstream
model is `anthropic/claude-opus-4.6` through OpenRouter.

Use a private env file outside the repository containing `OPENROUTER_API_KEY=...`.
From the repository root, seal it while preserving the existing API access key:

```bash
set -o pipefail
kubectl create secret generic hermes-secrets --namespace hermes \
  --from-env-file=/absolute/path/to/hermes.env \
  --from-file=API_SERVER_KEY=<(kubectl -n hermes get secret hermes-secrets \
    -o jsonpath='{.data.API_SERVER_KEY}' | base64 --decode) \
  --dry-run=client -o json | \
  kubeseal --controller-name helm-sealed-secrets \
    --controller-namespace kube-system --format yaml \
    --sealed-secret-file k8s/apps/hermes/sealedsecret.yaml

kubeseal --validate --controller-name helm-sealed-secrets \
  --controller-namespace kube-system < k8s/apps/hermes/sealedsecret.yaml
```

Increment `podAnnotations.hermes.home.lab/credentials-revision` in `values.yaml`
and commit and push both files together. Argo CD syncs the SealedSecret in an
earlier wave, then rolls out the gateway to reload credentials. Do not directly
apply the Secret or restart the Deployment.
Only the encrypted SealedSecret belongs in Git. Avoid storing credentials in the
PVC's `.env`, which can override Kubernetes-injected values.

## GitOps

Deploy and update Hermes by committing and pushing to the repository's watched
branch. The root application discovers `k8s/argocd/apps/hermes.yaml`; Hermes then
syncs this directory's values and SealedSecret automatically. Do not create the
Application through the Argo CD CLI or apply workload manifests directly.

Validate values against a checkout of the pinned chart:

```bash
helm lint /path/to/hermes-agent-helm-chart -f k8s/apps/hermes/values.yaml
helm template hermes /path/to/hermes-agent-helm-chart --namespace hermes \
  -f k8s/apps/hermes/values.yaml | kubectl apply --dry-run=server -n hermes -f -
kubectl apply --dry-run=server -f k8s/argocd/apps/hermes.yaml
```
