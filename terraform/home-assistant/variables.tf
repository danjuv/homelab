variable "home_assistant_url" {
  description = "Base URL of Home Assistant, without /api. Defaults to the ingress from k8s/apps/home-assistant/values.yaml."
  type        = string
  default     = "https://homeassistant.home.lab"

  validation {
    condition     = can(regex("^https?://[^/]+/?$", var.home_assistant_url))
    error_message = "home_assistant_url must be a base URL such as https://homeassistant.home.lab, without a path."
  }
}

variable "home_assistant_token" {
  description = "Long-lived access token of a Home Assistant admin user. Set with TF_VAR_home_assistant_token; never commit it."
  type        = string
  sensitive   = true
  nullable    = false

  validation {
    condition     = length(trimspace(var.home_assistant_token)) > 0
    error_message = "home_assistant_token must not be empty."
  }
}

variable "home_assistant_insecure" {
  description = "Skip TLS verification. Prefer trusting the homelab CA instead (see README.md)."
  type        = bool
  default     = false
}

variable "home_assistant_timeout" {
  description = "Per-request timeout as a Go duration."
  type        = string
  default     = "30s"
}

variable "managed_label" {
  description = "Label applied to every area Terraform creates, so they are recognisable in the UI."
  type = object({
    id    = string
    name  = string
    color = optional(string)
    icon  = optional(string)
  })
  default = {
    id    = "terraform"
    name  = "Managed by Terraform"
    color = "indigo"
    icon  = "mdi:robot"
  }
}

variable "floors" {
  description = "Floors to create, keyed by floor ID (slug). IDs that already exist in Home Assistant fail on create; import them instead."
  type = map(object({
    name    = string
    level   = optional(number)
    icon    = optional(string)
    aliases = optional(set(string))
  }))
  default = {}

  validation {
    condition     = alltrue([for id in keys(var.floors) : can(regex("^[a-z0-9_]+$", id))])
    error_message = "Floor IDs must be slugs (lowercase letters, digits and underscores)."
  }
}

variable "areas" {
  description = "Areas to create, keyed by area ID (slug). `floor` is a key of var.floors. Onboarding creates some areas (e.g. living_room); import those instead of redeclaring them."
  type = map(object({
    name    = string
    floor   = optional(string)
    icon    = optional(string)
    aliases = optional(set(string))
  }))
  default = {}

  validation {
    condition     = alltrue([for id in keys(var.areas) : can(regex("^[a-z0-9_]+$", id))])
    error_message = "Area IDs must be slugs (lowercase letters, digits and underscores)."
  }

  validation {
    condition     = alltrue([for a in values(var.areas) : a.floor == null || contains(keys(var.floors), a.floor)])
    error_message = "Every area floor must be a key of var.floors."
  }
}

variable "input_booleans" {
  description = "Toggle helpers (input_boolean) to create, keyed by helper ID; the entity is input_boolean.<id>. Terraform manages the definition, never the current state."
  type = map(object({
    name    = string
    icon    = optional(string)
    initial = optional(bool)
  }))
  default = {}

  validation {
    condition     = alltrue([for id in keys(var.input_booleans) : can(regex("^[a-z0-9_]+$", id))])
    error_message = "Helper IDs must be slugs (lowercase letters, digits and underscores)."
  }
}
