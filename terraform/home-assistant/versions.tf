terraform {
  # OpenTofu 1.8+ also works; the lock file only holds registry.terraform.io hashes.
  required_version = ">= 1.6.0"

  required_providers {
    homeassistant = {
      # Community provider (MPL-2.0): https://github.com/toelke/terraform-provider-homeassistant
      # Pinned exactly because it is young; Renovate proposes upgrades with the lock file.
      source  = "toelke/homeassistant"
      version = "1.0.0"
    }
  }

  # State stays local (gitignored). It holds no credentials: the provider
  # token is never written to state. See README.md before moving it.
}
