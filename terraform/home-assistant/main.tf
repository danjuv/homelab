# Everything here lives in Home Assistant's UI-managed storage (/config/.storage
# on the PVC), not in configuration.yaml, so it never conflicts with the files
# seeded by k8s/apps/home-assistant/values.yaml.
#
# IDs are pinned, and Home Assistant rejects creating an ID that already
# exists, so an apply fails instead of taking over runtime-created objects.
# Adopt existing objects explicitly with `import` blocks (see README.md).

data "homeassistant_config" "this" {}

resource "homeassistant_label" "managed" {
  id    = var.managed_label.id
  name  = var.managed_label.name
  color = var.managed_label.color
  icon  = var.managed_label.icon
}

resource "homeassistant_floor" "this" {
  for_each = var.floors

  id      = each.key
  name    = each.value.name
  level   = each.value.level
  icon    = each.value.icon
  aliases = each.value.aliases
}

resource "homeassistant_area" "this" {
  for_each = var.areas

  id       = each.key
  name     = each.value.name
  floor_id = each.value.floor == null ? null : homeassistant_floor.this[each.value.floor].id
  icon     = each.value.icon
  aliases  = each.value.aliases
  labels   = [homeassistant_label.managed.id]
}

resource "homeassistant_input_boolean" "this" {
  for_each = var.input_booleans

  id      = each.key
  name    = each.value.name
  icon    = each.value.icon
  initial = each.value.initial
}
