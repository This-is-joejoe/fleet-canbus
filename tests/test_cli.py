"""Device-id resolution tests — guards the --scale unique-id behavior."""
from fleet_canbus.cli import derive_device_id, resolve_device_id


def test_derive_from_compose_replica_hostname_pads_to_three_digits():
    # docker compose --scale assigns hostnames like "<project>-simulator-3"
    assert derive_device_id("fleetcanbus-simulator-3") == "device-003"


def test_derive_handles_underscore_separator():
    # older compose / legacy naming uses underscores
    assert derive_device_id("fleetcanbus_simulator_42") == "device-042"


def test_derive_falls_back_to_full_hostname_without_numeric_suffix():
    # a bare container id (hex, no separator) must not be mis-parsed by its
    # trailing hex digits — it falls back to a unique, hostname-derived id
    assert derive_device_id("a1b2c3d4e5f6") == "device-a1b2c3d4e5f6"


def test_resolve_prefers_explicit_cli_arg():
    # an operator-supplied --device-id always wins
    assert resolve_device_id("forklift-7", "device-env", "host-9") == "forklift-7"


def test_resolve_uses_env_when_no_cli_arg():
    # single-device runs set DEVICE_ID explicitly; honor it over auto-derivation
    assert resolve_device_id(None, "device-env", "host-9") == "device-env"


def test_resolve_derives_from_hostname_when_cli_and_env_absent():
    # the --scale case: nothing set, so each replica derives a unique id
    assert resolve_device_id(None, None, "fleetcanbus-simulator-5") == "device-005"


def test_resolve_treats_empty_env_as_unset():
    # an empty DEVICE_ID must not shadow hostname derivation
    assert resolve_device_id(None, "", "fleetcanbus-simulator-5") == "device-005"
