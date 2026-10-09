# Non-secret Home Assistant configuration; safe to commit.
# The token is NOT set here: use TF_VAR_home_assistant_token (see README.md).

# home_assistant_url = "https://homeassistant.home.lab"

# Every map starts empty so the first apply only creates the "terraform" label.
# Uncomment and adapt; keys are the pinned IDs Home Assistant will use.

floors = {
  # ground_floor = { name = "Ground Floor", level = 0, icon = "mdi:home-floor-0" }
}

areas = {
  # Onboarding already creates living_room, kitchen and bedroom; import those
  # (README.md) rather than declaring them here, or the apply fails.
  # office = { name = "Office", floor = "ground_floor", icon = "mdi:desk" }
}

input_booleans = {
  # guest_mode = { name = "Guest Mode", icon = "mdi:account-group" }
}
