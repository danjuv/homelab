# Home Assistant (Terraform)

Configures the Home Assistant application deployed by
[`k8s/apps/home-assistant`](../../k8s/apps/home-assistant/values.yaml) at
<https://homeassistant.home.lab>, using the community
[`toelke/homeassistant`](https://registry.terraform.io/providers/toelke/homeassistant/1.0.0)
provider (pinned to `1.0.0`; hashes in `.terraform.lock.hcl`).

Unlike `k8s/`, nothing here is applied automatically: ArgoCD does not run
Terraform. A human runs `plan`/`apply` from a workstation.

## Kubernetes vs. Terraform

| Concern | Owner | Where |
|---|---|---|
| Image/version, CPU/memory, probes, `TZ` | Kubernetes (ArgoCD) | `k8s/apps/home-assistant/values.yaml` |
| Storage (Longhorn PVC at `/config`), ingress, TLS, NetworkPolicy | Kubernetes (ArgoCD) | same |
| Reverse-proxy settings (`http.yaml`) | Kubernetes (ArgoCD) | same, ConfigMap |
| Starter `configuration.yaml` | Kubernetes, **first boot only**; afterwards hand-edited on the PVC | same |
| Onboarding, owner/users, long-lived tokens | Manual, in the UI | - |
| Labels, floors, areas, toggle helpers | **Terraform** | this directory |
| Everything else (integrations, devices, automations, dashboards, ...) | UI, until it is moved here | - |

Terraform talks to Home Assistant's REST/WebSocket API, and the objects it
creates live in Home Assistant's UI-managed storage (`/config/.storage` on the
PVC). It never touches `configuration.yaml` or `http.yaml`, so it cannot
conflict with what ArgoCD manages. Changing the pod (image, resources, proxy
settings) is a Git change under `k8s/`; changing what Home Assistant knows
about your home is a change here.

## What is managed

- `homeassistant_label.managed`: a label with the pinned ID `terraform`, put on
  every area Terraform creates. This is the only object the default
  configuration creates.
- `homeassistant_floor.this`, `homeassistant_area.this`,
  `homeassistant_input_boolean.this`: driven by the `floors`, `areas` and
  `input_booleans` maps in [`terraform.tfvars`](terraform.tfvars), all empty by
  default. Map keys are the pinned IDs.
- `data.homeassistant_config.this` (read-only): version, location and time zone
  as outputs, to check that the URL and token work.

Every ID is pinned, and Home Assistant refuses to create an ID that already
exists. If an object was already created in the UI, or by onboarding (which
creates the `living_room`, `kitchen` and `bedroom` areas), `apply` fails instead
of taking it over. To adopt one, declare it and import it explicitly (see
[Adopting existing objects](#adopting-existing-objects)).

## Prerequisites

- Terraform `>= 1.6` (CI uses 1.16.5). OpenTofu should work too, but it is not
  tested here, and it adds `registry.opentofu.org` hashes to the lock file
  (`tofu providers lock`).
- Network access to `https://homeassistant.home.lab`: the ingress is only
  reachable through ingress-nginx over Tailscale, and the NetworkPolicy blocks
  in-cluster callers other than ingress-nginx.
- A client that trusts the homelab CA (`homelab-ca-issuer`), see
  [TLS](#tls).
- Onboarding completed in the browser, and a token (next section).

## Creating the token

The provider needs a **long-lived access token of an admin user**. The token is
a secret and must never be committed.

1. Open <https://homeassistant.home.lab> and finish onboarding if you haven't.
2. Optional, recommended: under *Settings → People → Users*, create a dedicated
   user such as `terraform` with *Administrator* on, so its token can be revoked
   on its own and changes show who made them. Log in as that user.
3. Open your profile (bottom-left) → *Security* → *Long-lived access tokens* →
   *Create token*. Name it `terraform` and copy it; Home Assistant shows it
   only once. It is valid for 10 years; delete it on the same page to revoke it.
4. Store it in your password manager.

## Supplying the token

The token is the sensitive variable `home_assistant_token`. Terraform redacts
it in output and does not write it to state. A saved plan file (`-out`) does
contain variable values, so treat `*.tfplan` as secret (gitignored here) and
delete it after applying. Pass the token through the environment:

```sh
# From a password manager, e.g. pass, 1Password (op) or Bitwarden (bw):
export TF_VAR_home_assistant_token="$(pass show homelab/home-assistant/terraform-token)"
# Or type it without echo or shell history:
read -rs TF_VAR_home_assistant_token && export TF_VAR_home_assistant_token
```

If you prefer a file, put `home_assistant_token = "..."` in
`secret.auto.tfvars` (loaded automatically) or `<name>.secret.tfvars` (pass with
`-var-file`). Both patterns are in this directory's `.gitignore`. Nothing else
in this root is secret, so `terraform.tfvars` is committed.

If this is ever run in-cluster (e.g. as an Argo Workflow), use the repo's
SealedSecrets: a human seals a Secret with the key `token` and the workflow
maps it to `TF_VAR_home_assistant_token`.

## TLS

The certificate is issued by the private `homelab-ca-issuer`. Keep TLS
verification on (`home_assistant_insecure = false`, the default):

- **macOS / Windows:** trust the homelab CA in the system store, as for the
  browser. The provider (Go) uses the system verifier.
- **Linux:** add the CA to the system store (`/usr/local/share/ca-certificates`
  + `update-ca-certificates`), or point `SSL_CERT_FILE` at a bundle. Note that
  `SSL_CERT_FILE` *replaces* the system roots, so a bundle holding only the
  homelab CA breaks `terraform init` against the public registry. Append it to
  the system bundle instead:

  ```sh
  kubectl -n home-assistant get secret home-assistant-homelab-tls \
    -o jsonpath='{.data.ca\.crt}' | base64 -d > homelab-ca.crt   # needs Secret read access
  cat /etc/ssl/certs/ca-certificates.crt homelab-ca.crt > ca-bundle.crt
  export SSL_CERT_FILE="$PWD/ca-bundle.crt"
  ```

  (`*.crt` is gitignored here.)

## Usage

```sh
cd terraform/home-assistant
terraform init                  # downloads the provider pinned in .terraform.lock.hcl
terraform plan -out=ha.tfplan   # needs TF_VAR_home_assistant_token and network access
terraform apply ha.tfplan && rm ha.tfplan
```

Checks that need no Home Assistant and no token (run them before every PR):

```sh
terraform fmt -check -recursive
terraform init -backend=false
terraform validate
terraform test                  # tests/*.tftest.hcl, with a mocked provider
```

To point at another instance (e.g. a port-forward), set
`TF_VAR_home_assistant_url=http://localhost:8123`.

## Adding configuration

Edit [`terraform.tfvars`](terraform.tfvars):

```hcl
floors = {
  ground_floor = { name = "Ground Floor", level = 0, icon = "mdi:home-floor-0" }
}

areas = {
  office = { name = "Office", floor = "ground_floor", icon = "mdi:desk" }
}

input_booleans = {
  guest_mode = { name = "Guest Mode", icon = "mdi:account-group" }
}
```

For things these maps don't cover (automations, dashboards, integrations,
entity settings), add resources from the
[provider docs](https://registry.terraform.io/providers/toelke/homeassistant/1.0.0/docs)
to `main.tf`. Check the limitations below first.

## Adopting existing objects

Declare the object, then add an `import` block (e.g. in an `imports.tf`) and
review the plan before applying. For an area created by onboarding:

```hcl
# terraform.tfvars
areas = {
  living_room = { name = "Living Room" }
}

# imports.tf
import {
  to = homeassistant_area.this["living_room"]
  id = "living_room"
}
```

`terraform plan` then shows what Terraform would change on the existing
object, e.g. adding the `terraform` label, or clearing aliases or an icon set in
the UI that the map doesn't declare. Copy those values into `terraform.tfvars`
if you want to keep them. Remove the `import` block after the apply.

## State

State is local (`terraform.tfstate`, gitignored) and holds only object IDs and
names, no credentials. Losing it is harmless: re-import the objects. If several
machines need to apply, move it to a shared backend (e.g. the `kubernetes`
backend, which stores state in a Secret) and record that here.

If the Home Assistant PVC is lost or restored from an older backup, the next
`plan` detects the missing objects and recreates them.

## Provider limitations

- **Young community provider.** `toelke/homeassistant` 1.0.0 was released on
  2026-10-06 by a single maintainer, and its README says the code is
  AI-generated. It follows semver from 1.0. It is pinned exactly, and Renovate
  bump PRs are not automerged; read the changelog before upgrading.
- **Home Assistant version window.** It supports the six latest monthly
  Home Assistant releases (currently 2026.5 to 2026.10) and does not check the
  version. The deployment is 2026.10.0. When Renovate bumps the image, bump the
  provider too if needed.
- **Admin token only.** Users, onboarding and tokens can't be managed; the token
  is bootstrapped by hand.
- **No YAML config.** `configuration.yaml`, YAML-only integrations and
  `http.yaml` are out of scope (the last is managed by Kubernetes).
- **Integrations** (`homeassistant_integration`) are created by answering
  their config flow. Drift is only detected when the entry is gone. Flows that
  need OAuth/browser login, a menu, or a device button press are unsupported.
- **Automations, scripts and scenes** created by the provider are stored in the
  `automations.yaml`/`scripts.yaml`/`scenes.yaml` files the UI also edits. UI
  edits to them show up as drift and the next apply reverts them. They are not
  managed here yet for that reason.
- **No discovery.** The pod has no host networking, so integrations that rely
  on mDNS/SSDP/Bluetooth discovery must be configured by host/IP (see PR #176).
