# Homepage

Self-hosted [Homepage](https://gethomepage.dev) dashboard for the homelab.

- Chart: `homepage` from `https://jameswynn.github.io/helm-charts/`
  (pinned in `k8s/argocd/apps/homepage.yaml`; the container image is bumped
  separately by Renovate).
- Namespace: `homepage`. Reachable at <https://home.lab>.
- Everything is configured through this directory's `values.yaml` under the
  chart's `config` key. The chart serialises each key into its own file on the
  `/app/config` volume (`services.yaml`, `settings.yaml`, `widgets.yaml`,
  `kubernetes.yaml`, ...). There is no further templating.
- All service cards are declared statically here. Kubernetes discovery
  (`enableRbac: true` plus `kubernetes.mode: cluster`) is used only by the
  `kubernetes` information widget, not to discover services.

## Two kinds of URL — do not mix them

- `href` is the **public, browser-facing** URL. Use the HTTPS ingress host
  from the app's own values file (for example
  `k8s/apps/sonarr/values.yaml` -> `sonarr.home.lab`). These are the links a
  person clicks.
- `widget.url` and `settings.providers.*.url` are **cluster-internal** URLs the
  Homepage pod calls directly. Use the Kubernetes Service DNS name and port
  (for example `http://sonarr.media:8989`). Never rewrite these to the public
  host: `*.home.lab` names are not expected to resolve from inside the cluster,
  and the widgets would break.

`tools/validate_homepage.py` checks that every `href` host is declared
somewhere under `k8s/`, so a card cannot point at a host the repository does
not create.

## Secrets

Widget credentials are referenced as `{{HOMEPAGE_VAR_*}}` placeholders and
injected at runtime from the `homepage-secrets` Secret, which is mounted with
`envFrom` and kept in `sealedsecret.yaml`.

- Only the `HOMEPAGE_VAR_*` **keys** live here; the values are encrypted in the
  SealedSecret. Never commit a plaintext key.
- Adding a widget that needs a new secret means a human must seal the value
  into `homepage-secrets` (see the sealed-secrets app under `k8s/admin`). List
  the required keys in the PR rather than inventing them.
- Removing a widget does not require removing its secret entry.

## Adding or changing a service

1. Confirm the public host in the app's own `values.yaml` ingress block under
   `k8s/apps/<app>/` and the internal Service name/port from that same file.
2. Add the card to the matching group (Media, Home, AI, Infrastructure). Give
   it an `icon` from
   [dashboard-icons](https://github.com/homarr-labs/dashboard-icons) (plain
   `name.png`), or a prefixed `si-*`/`sh-*`/`mdi-*` icon if the set has one.
3. If the app exposes a documented Homepage widget, add a `widget` block with
   the internal URL; reference any credential as `{{HOMEPAGE_VAR_*}}`.
4. Keep the group's entry in `settings.layout` present so ordering and column
   counts stay intentional.

## Validating changes

```sh
# Fast, network-free check of this app's config and links.
python3 tools/validate_homepage.py

# Full render + kubeconform of every ArgoCD Application (needs helm,
# kustomize, kubeconform and network access for remote charts).
python3 tools/validate_k8s.py
```

`helm template` for just this app:

```sh
helm template homepage homepage \
  --repo https://jameswynn.github.io/helm-charts/ --version 2.1.0 \
  --namespace homepage --values k8s/apps/homepage/values.yaml
```
