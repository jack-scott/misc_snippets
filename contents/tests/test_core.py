import pytest

from contents import core


# ── env_var_name ──────────────────────────────────────────────────────────────

def test_env_var_name_simple():
    assert core.env_var_name("perception", "params") == "PERCEPTION_PARAMS"


def test_env_var_name_replaces_non_alnum_with_underscore():
    assert core.env_var_name("cadvisor-monitor", "diagnostics") == "CADVISOR_MONITOR_DIAGNOSTICS"


# ── label_key ──────────────────────────────────────────────────────────────────

def test_label_key():
    assert core.label_key("cadvisor_monitor", "diagnostics") == "io.ros.pkg.cadvisor_monitor.diagnostics"


# ── encode ─────────────────────────────────────────────────────────────────────

def test_encode_raw64_default_scheme(tmp_path):
    f = tmp_path / "analyzers.yaml"
    f.write_text("cadvisor_monitor:\n  type: GenericAnalyzer\n")

    value = core.encode(str(f))

    assert value.startswith("raw64:")


def test_encode_canon_uses_canon64_scheme(tmp_path):
    f = tmp_path / "analyzers.yaml"
    f.write_text("cadvisor_monitor:\n  type: GenericAnalyzer\n")

    value = core.encode(str(f), canon=True)

    assert value.startswith("canon64:")


def test_encode_is_deterministic(tmp_path):
    f = tmp_path / "analyzers.yaml"
    f.write_text("cadvisor_monitor:\n  type: GenericAnalyzer\n")

    assert core.encode(str(f)) == core.encode(str(f))
    assert core.encode(str(f), canon=True) == core.encode(str(f), canon=True)


# ── decode_value ───────────────────────────────────────────────────────────────

def test_decode_value_round_trips_raw64(tmp_path):
    f = tmp_path / "analyzers.yaml"
    original = b"cadvisor_monitor:\n  type: GenericAnalyzer\n"
    f.write_bytes(original)

    value = core.encode(str(f))

    assert core.decode_value(value) == original


def test_decode_value_round_trips_canon64(tmp_path):
    f = tmp_path / "analyzers.yaml"
    f.write_bytes(b"cadvisor_monitor:\n  type: GenericAnalyzer\n")

    value = core.encode(str(f), canon=True)
    recovered = core.decode_value(value)

    import yaml
    assert yaml.safe_load(recovered) == {"cadvisor_monitor": {"type": "GenericAnalyzer"}}


def test_decode_value_raises_on_missing_colon():
    with pytest.raises(ValueError):
        core.decode_value("no-colon-here")


# ── decode / list_packages (docker.from_env() stubbed) ────────────────────────

class _FakeImage:
    def __init__(self, labels):
        self.labels = labels


class _FakeImages:
    def __init__(self, labels):
        self._labels = labels

    def get(self, image_ref):
        return _FakeImage(self._labels)


class _FakeClient:
    def __init__(self, labels):
        self.images = _FakeImages(labels)


def _stub_docker(monkeypatch, labels):
    monkeypatch.setattr(core.docker, "from_env", lambda: _FakeClient(labels))


def test_decode_cmd_field_returns_raw_string_unencoded(monkeypatch):
    _stub_docker(monkeypatch, {
        "io.ros.pkg.cadvisor_monitor.cmd": "ros2 run cadvisor_monitor container_stats_publisher",
    })

    assert core.decode("fake:latest", "cadvisor_monitor", "cmd") == b"ros2 run cadvisor_monitor container_stats_publisher"


def test_decode_diagnostics_field_still_base64_decodes(monkeypatch):
    _stub_docker(monkeypatch, {
        "io.ros.pkg.cadvisor_monitor.diagnostics": "raw64:aGVsbG8=",
    })

    assert core.decode("fake:latest", "cadvisor_monitor", "diagnostics") == b"hello"


def test_list_packages_groups_fields_by_pkg(monkeypatch):
    _stub_docker(monkeypatch, {
        "io.ros.pkg.cadvisor_monitor.cmd": "...",
        "io.ros.pkg.cadvisor_monitor.diagnostics": "raw64:...",
        "io.ros.pkg.other_pkg.params": "raw64:...",
        "some.unrelated.label": "x",
    })

    packages = core.list_packages("fake:latest")

    assert set(packages["cadvisor_monitor"]) == {"cmd", "diagnostics"}
    assert set(packages["other_pkg"]) == {"params"}
    assert "unrelated" not in packages


def test_list_packages_empty_when_no_matching_labels(monkeypatch):
    _stub_docker(monkeypatch, {"some.unrelated.label": "x"})

    assert core.list_packages("fake:latest") == {}
