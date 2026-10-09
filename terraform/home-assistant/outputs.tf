output "home_assistant_version" {
  description = "Version reported by the instance; confirms the URL and token work."
  value       = data.homeassistant_config.this.version
}

output "location_name" {
  description = "Location name set during onboarding."
  value       = data.homeassistant_config.this.location_name
}

output "time_zone" {
  description = "Time zone of the instance; should match TZ in k8s/apps/home-assistant/values.yaml."
  value       = data.homeassistant_config.this.time_zone
}

output "managed_label_id" {
  description = "ID of the label applied to Terraform-managed areas."
  value       = homeassistant_label.managed.id
}

output "area_ids" {
  description = "IDs of Terraform-managed areas."
  value       = { for k, a in homeassistant_area.this : k => a.id }
}

output "input_boolean_entity_ids" {
  description = "Entity IDs of Terraform-managed toggle helpers."
  value       = { for k, h in homeassistant_input_boolean.this : k => h.entity_id }
}
