provider "homeassistant" {
  url      = var.home_assistant_url
  token    = var.home_assistant_token
  insecure = var.home_assistant_insecure
  timeout  = var.home_assistant_timeout
}
