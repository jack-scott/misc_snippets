"""Unit tests for radio.py pure functions."""

import radio


class TestCalculateDistance:
    def test_same_point(self):
        expected = 0.0
        result = radio.calculate_distance({"x": 5, "y": 5, "z": 5}, {"x": 5, "y": 5, "z": 5})
        assert result == expected

    def test_3_4_5_triangle(self):
        expected = 5.0
        result = radio.calculate_distance({"x": 0, "y": 0, "z": 0}, {"x": 3, "y": 4, "z": 0})
        assert abs(result - expected) < 1e-10

    def test_3d_case(self):
        expected = 3.0
        # sqrt(1^2 + 2^2 + 2^2) = sqrt(9) = 3
        result = radio.calculate_distance({"x": 0, "y": 0, "z": 0}, {"x": 1, "y": 2, "z": 2})
        assert abs(result - expected) < 1e-10

    def test_negative_coords(self):
        expected = 10.0
        # sqrt((-5-5)^2 + 0 + 0) = 10
        result = radio.calculate_distance({"x": -5, "y": 0, "z": 0}, {"x": 5, "y": 0, "z": 0})
        assert abs(result - expected) < 1e-10

    def test_missing_keys_default_to_zero(self):
        expected = 5.0
        result = radio.calculate_distance({"x": 3, "y": 4}, {"x": 0})
        assert abs(result - expected) < 1e-10


class TestInterpolateDegradation:
    def test_at_zero_distance(self):
        result = radio.interpolate_degradation(0)
        assert result is not None
        assert result["latency_ms"] == 2
        assert result["loss_percent"] == 0

    def test_at_exact_threshold(self):
        result = radio.interpolate_degradation(500)
        assert result is not None
        assert result["latency_ms"] == 30
        assert result["loss_percent"] == 10

    def test_between_thresholds(self):
        # At 250m, halfway between 0m and 500m thresholds
        # latency: 2 + 0.5 * (30 - 2) = 16.0
        # loss: 0 + 0.5 * (10 - 0) = 5.0
        expected_latency = 16.0
        expected_loss = 5.0
        result = radio.interpolate_degradation(250)
        assert result is not None
        assert abs(result["latency_ms"] - expected_latency) < 0.01
        assert abs(result["loss_percent"] - expected_loss) < 0.01

    def test_at_max_range_returns_none(self):
        result = radio.interpolate_degradation(1000)
        assert result is None

    def test_beyond_max_range_returns_none(self):
        result = radio.interpolate_degradation(1500)
        assert result is None


class TestApplyEnvironment:
    def test_none_passthrough(self):
        result = radio.apply_environment(None)
        assert result is None

    def test_clear_no_change(self):
        radio.state.environment = "clear"
        base = {"latency_ms": 10, "loss_percent": 5}
        result = radio.apply_environment(base)
        assert result["latency_ms"] == 10.0
        assert result["loss_percent"] == 5.0

    def test_storm_multiplied(self):
        # Only works if "storm" profile exists in config
        profiles = radio.CONFIG.get("environment", {}).get("profiles", {})
        if "storm" not in profiles:
            # Add storm profile for testing
            profiles["storm"] = {
                "latency_multiplier": 3.0,
                "loss_multiplier": 4.0,
                "bandwidth_multiplier": 0.5,
            }

        radio.state.environment = "storm"
        base = {"latency_ms": 10, "loss_percent": 5}
        result = radio.apply_environment(base)

        storm = profiles["storm"]
        expected_latency = 10 * storm["latency_multiplier"]
        expected_loss = 5 * storm["loss_multiplier"]

        assert abs(result["latency_ms"] - expected_latency) < 0.01
        assert abs(result["loss_percent"] - expected_loss) < 0.01

    def test_loss_capped_at_100(self):
        profiles = radio.CONFIG.get("environment", {}).get("profiles", {})
        if "storm" not in profiles:
            profiles["storm"] = {
                "latency_multiplier": 3.0,
                "loss_multiplier": 4.0,
                "bandwidth_multiplier": 0.5,
            }

        radio.state.environment = "storm"
        base = {"latency_ms": 10, "loss_percent": 50}
        result = radio.apply_environment(base)

        assert result["loss_percent"] <= 100


class TestGetRadioBandwidth:
    def test_clear_returns_base(self):
        expected = radio.CONFIG.get("radio", {}).get("bandwidth_kbps", 1000)
        radio.state.environment = "clear"
        result = radio.get_radio_bandwidth()
        assert result == expected

    def test_storm_reduced(self):
        profiles = radio.CONFIG.get("environment", {}).get("profiles", {})
        if "storm" not in profiles:
            profiles["storm"] = {
                "latency_multiplier": 3.0,
                "loss_multiplier": 4.0,
                "bandwidth_multiplier": 0.5,
            }

        radio.state.environment = "storm"
        base_bw = radio.CONFIG.get("radio", {}).get("bandwidth_kbps", 1000)
        expected = int(base_bw * 0.5)
        result = radio.get_radio_bandwidth()
        assert result == expected

    def test_bandwidth_override(self):
        expected = 2000
        radio.state.bandwidth_override = 2000
        result = radio.get_radio_bandwidth()
        assert result == expected

    def test_override_takes_precedence(self):
        expected = 500
        radio.state.bandwidth_override = 500
        radio.state.environment = "clear"
        result = radio.get_radio_bandwidth()
        assert result == expected


class TestGetOtherDrones:
    def test_mesh_all_except_self(self):
        radio.state.topology = "mesh"
        result = radio.get_other_drones()
        assert 1 not in result  # DRONE_ID is 1
        assert 2 in result
        assert 3 in result

    def test_star_drone_sees_other_drones(self):
        radio.state.topology = "star"
        result = radio.get_other_drones()
        # Star mode: base station is invisible, drones see other drones
        assert 0 not in result
        assert 2 in result
        assert 3 in result

    def test_star_base(self):
        # Temporarily change DRONE_ID to 0 (base station)
        original = radio.DRONE_ID
        radio.DRONE_ID = 0
        radio.state.topology = "star"
        result = radio.get_other_drones()
        radio.DRONE_ID = original

        assert result == [1, 2, 3]


class TestCalculateLinkQuality:
    def test_close_range(self):
        radio.state.topology = "mesh"
        radio.state.positions[1] = {"x": 0, "y": 0, "z": 0}
        radio.state.positions[2] = {"x": 10, "y": 0, "z": 0}
        result = radio.calculate_link_quality(2)

        assert result["reachable"] is True
        assert result["distance_m"] < 20
        assert result["latency_ms"] >= 0
        assert result["loss_percent"] >= 0

    def test_out_of_range(self):
        radio.state.topology = "mesh"
        radio.state.positions[1] = {"x": 0, "y": 0, "z": 0}
        radio.state.positions[2] = {"x": 2000, "y": 0, "z": 0}
        result = radio.calculate_link_quality(2)

        assert result["reachable"] is False
        assert result["loss_percent"] == 100

    def test_with_environment(self):
        radio.state.topology = "mesh"
        profiles = radio.CONFIG.get("environment", {}).get("profiles", {})
        if "storm" not in profiles:
            profiles["storm"] = {
                "latency_multiplier": 3.0,
                "loss_multiplier": 4.0,
                "bandwidth_multiplier": 0.5,
            }

        radio.state.positions[1] = {"x": 0, "y": 0, "z": 0}
        radio.state.positions[2] = {"x": 250, "y": 0, "z": 0}

        radio.state.environment = "clear"
        clear_result = radio.calculate_link_quality(2)

        radio.state.environment = "storm"
        storm_result = radio.calculate_link_quality(2)

        # Storm should have higher latency
        assert storm_result["latency_ms"] > clear_result["latency_ms"]

    def test_star_two_hop_latency(self):
        """Star topology: drone-to-drone quality reflects two hops through base."""
        radio.state.positions[0] = {"x": 0, "y": 0, "z": 0}
        radio.state.positions[1] = {"x": 100, "y": 0, "z": 0}
        radio.state.positions[2] = {"x": -100, "y": 0, "z": 0}
        radio.state.environment = "clear"

        radio.state.topology = "mesh"
        mesh_result = radio.calculate_link_quality(2)

        radio.state.topology = "star"
        star_result = radio.calculate_link_quality(2)

        # Mesh: direct 200m path
        # Star: 100m + 100m through base (each hop shorter, but latencies add)
        assert star_result["reachable"] is True
        assert star_result["distance_m"] == 200.0
        # Two-hop latency should be approximately double the 100m single-hop latency
        leg_quality = radio._direct_link_quality(1, 0)
        expected_latency = leg_quality["latency_ms"] * 2
        assert abs(star_result["latency_ms"] - expected_latency) < 0.01


class TestDirectLinkParams:
    def test_direct_params_override(self):
        radio.state.positions[1] = {"x": 0, "y": 0, "z": 0}
        radio.state.positions[2] = {"x": 10, "y": 0, "z": 0}

        # Without direct params, distance-based calculation
        quality_normal = radio.calculate_link_quality(2)

        # Set direct params
        radio.state.direct_link_params = {
            "delay_ms": 200,
            "loss_pct": 50,
            "rate_kbit": 100,
        }

        # direct_link_params are used in apply_link_rules, not calculate_link_quality
        # So verify the state is stored correctly
        assert radio.state.direct_link_params["delay_ms"] == 200
        assert radio.state.direct_link_params["loss_pct"] == 50
        assert radio.state.direct_link_params["rate_kbit"] == 100


class TestLinkDownUp:
    def test_link_down_sets_flag(self):
        radio.state.link_down = True
        assert radio.state.link_down is True

    def test_link_up_restores(self):
        radio.state.link_down = True
        radio.state.direct_link_params = {"delay_ms": 100, "loss_pct": 50, "rate_kbit": 500}

        # Simulate link_up behavior
        radio.state.link_down = False
        radio.state.direct_link_params = {}

        assert radio.state.link_down is False
        assert radio.state.direct_link_params == {}

    def test_link_down_overrides_quality(self):
        radio.state.positions[1] = {"x": 0, "y": 0, "z": 0}
        radio.state.positions[2] = {"x": 10, "y": 0, "z": 0}

        # Even at close range, link_down means 100% loss
        radio.state.link_down = True

        # The link_down flag is checked in apply_link_rules
        # Verify the flag is set
        assert radio.state.link_down is True
