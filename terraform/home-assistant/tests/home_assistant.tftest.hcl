# Offline tests: `terraform test` uses a mocked provider, so no Home Assistant
# or token is needed.

mock_provider "homeassistant" {
  mock_data "homeassistant_config" {
    defaults = {
      version       = "2026.10.0"
      location_name = "Home"
      time_zone     = "Australia/Sydney"
    }
  }
}

variables {
  home_assistant_token = "test-token-not-real"
}

run "defaults_only_create_the_label" {
  command = plan

  assert {
    condition     = homeassistant_label.managed.id == "terraform"
    error_message = "The managed label must have the pinned ID 'terraform'."
  }

  assert {
    condition     = length(homeassistant_area.this) == 0 && length(homeassistant_floor.this) == 0 && length(homeassistant_input_boolean.this) == 0
    error_message = "Defaults must not create floors, areas or helpers."
  }

  assert {
    condition     = var.home_assistant_url == "https://homeassistant.home.lab" && var.home_assistant_insecure == false
    error_message = "Defaults must target the ingress with TLS verification on."
  }
}

run "areas_link_floors_and_label" {
  command = apply

  variables {
    floors = {
      ground_floor = { name = "Ground Floor", level = 0 }
    }
    areas = {
      office = { name = "Office", floor = "ground_floor" }
      garage = { name = "Garage" }
    }
    input_booleans = {
      guest_mode = { name = "Guest Mode" }
    }
  }

  assert {
    condition     = homeassistant_area.this["office"].floor_id == homeassistant_floor.this["ground_floor"].id
    error_message = "Areas must reference their floor by ID."
  }

  assert {
    condition     = homeassistant_area.this["garage"].floor_id == null
    error_message = "Areas without a floor must not set floor_id."
  }

  assert {
    condition     = contains(homeassistant_area.this["office"].labels, homeassistant_label.managed.id)
    error_message = "Managed areas must carry the managed label."
  }

  assert {
    condition     = output.home_assistant_version == "2026.10.0"
    error_message = "The config data source must feed the version output."
  }
}

run "rejects_unknown_floor" {
  command = plan

  variables {
    areas = {
      office = { name = "Office", floor = "attic" }
    }
  }

  expect_failures = [var.areas]
}

run "rejects_non_slug_ids" {
  command = plan

  variables {
    input_booleans = {
      "Guest Mode" = { name = "Guest Mode" }
    }
  }

  expect_failures = [var.input_booleans]
}

run "rejects_url_with_path" {
  command = plan

  variables {
    home_assistant_url = "https://homeassistant.home.lab/api"
  }

  expect_failures = [var.home_assistant_url]
}
