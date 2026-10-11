# Homepage

The homelab dashboard, served at <https://home.lab>.

## Files

| File | Purpose |
|------|---------|
| `values.yaml` | Helm values for the [Homepage chart](https://github.com/jameswynn/helm-charts) (`homepage`), applied by `k8s/argocd/apps/homepage.yaml`. |
| `sealedsecret.yaml` | Encrypted API keys and credentials, consumed by the pod via `envFrom`. Created by a human with `kubeseal`; never edited by hand. |

`values.yaml` has two halves: deployment settings (`image`, `ingress`, `env`,
...) and the Homepage application config under `config:`.

## How `config:` becomes Homepage config

The chart writes each key under `config:` to the matching file in
`/app/config`:

| Value | File |
|-------|------|
| `config.services` | `services.yaml` |
| `config.widgets` | `widgets.yaml` |
| `config.settings` | `settings.yaml` |
| `config.kubernetes` | `kubernetes.yaml` |
| `config.bookmarks` | `bookmarks.yaml` |

## Adding or editing a service

Services live under a group in `config.services`. A group is a list, and each
service is a single-key map:

```yaml
    - Media:            # group
        - Sonarr:       # service name (shown in the UI)
            icon: sonarr.png
            href: https://sonarr.home.lab
            description: TV Shows
            widget:
              type: sonarr
              url: http://sonarr.media:8989
              key: "{{HOMEPAGE_VAR_SONARR_KEY}}"
```

* `icon` and `href` are required. `href` is the external URL; add the matching
  Ingress in the service's own manifest (they follow `<name>.home.lab`).
* A widget's `url` is the in-cluster address
  (`http://<service>.<namespace>:<port>`), not the external one.
* Credentials are referenced as `"{{HOMEPAGE_VAR_*}}"`. The variable must be a
  key in `sealedsecret.yaml`; add new ones by sealing the value with `kubeseal`
  (a human step) — never commit plaintext.
* The group is ordered and styled in `config.settings.layout`.

## Adding or editing an info widget

`config.widgets` is a list of single-key maps rendered above the services. Its
options must match the deployed Homepage version (currently `v2.5.0`, set by
the `image.tag` above); unknown options are silently ignored by Homepage, so
check `src/components/widgets` upstream before adding one.

Layout groups in `config.settings.layout` must each name a group defined in
`config.services`.

## Icons

Homepage v2.5.0 resolves icons against three built-in sets:

* `name.png` / `name.svg` / `name.webp` — [homarr-labs/dashboard-icons](https://github.com/homarr-labs/dashboard-icons)
* `sh-name` — [selfh.st/icons](https://github.com/selfhst/icons)
* `mdi-name` / `si-name` — Material / Simple Icons

A name that is missing from its set renders as a broken image (no error), so
prefer the validator's icon check when changing one.

## Validation

Reproducible config check (needs `PyYAML`; `uv` is available in the devenv):

```sh
uv run --with pyyaml python tools/validate_homepage.py --check-icons
```

It checks the embedded YAML, that every `href` host is declared by another
manifest in this repo, that every `HOMEPAGE_VAR_*` reference has a
`SealedSecret` key, that widget options match the deployed Homepage version,
and that icons resolve on the CDN.

Render the chart and schema-check the result:

```sh
helm template homepage homepage \
  --repo https://jameswynn.github.io/helm-charts/ --version 2.1.0 \
  --namespace homepage -f k8s/apps/homepage/values.yaml \
  | kubeconform -strict -summary -ignore-missing-schemas \
      -kubernetes-version "${KUBERNETES_VERSION:-1.35.0}"
```

## Manual checks

* Widgets only render their data with the live service reachable, so after
  changing a `url` or credential, reload <https://home.lab> and confirm the
  card still reports.
* `HOMEPAGE_ALLOWED_HOSTS` must list every hostname Homepage is served on.
  It is currently `home.lab` only, so access via an IP or the Tailscale name is
  rejected by design.
* Icons are fetched from public CDNs by the browser at page load.
