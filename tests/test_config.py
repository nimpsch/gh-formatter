import pytest

from gh_formatter.config import Config, ConfigError


def test_defaults():
    config = Config()
    assert config.indent == 2
    assert config.sequence_indent == 4
    assert config.sequence_offset == 2
    assert config.input_casing == "dash-case"
    assert config.job_casing == "snake_case"
    assert config.list_style == "block"
    assert config.quote_style == "double"
    assert config.blank_line_between_steps is True
    assert config.blank_line_between_jobs is True
    assert "branches" in config.list_keys
    assert config.rule_enabled("anything") is True


def test_override():
    config = Config({"indent": 4, "list_style": "flow"})
    assert config.indent == 4
    assert config.list_style == "flow"


def test_rule_toggles():
    config = Config({"rules": {"capitalize-names": False}})
    assert config.rule_enabled("capitalize-names") is False
    assert config.rule_enabled("key-ordering") is True


@pytest.mark.parametrize(
    "bad",
    [
        {"list_style": "sideways"},
        {"input_casing": "camelCase"},
        {"indent": 0},
        {"indent": "two"},
        {"indent": True},
        {"unknown_option": 1},
        {"rules": {"x": "yes"}},
        {"key_order_workflow": "name"},
        {"blank_line_between_steps": "yes"},
        {"sequence_offset": 4, "sequence_indent": 4},
        {"quote_style": "backtick"},
    ],
)
def test_invalid_values_rejected(bad):
    with pytest.raises(ConfigError):
        Config(bad)


def test_non_mapping_rejected():
    with pytest.raises(ConfigError):
        Config(["indent", 2])


def test_missing_explicit_config_path_rejected(tmp_path):
    with pytest.raises(ConfigError):
        Config.load(str(tmp_path / "does-not-exist.yml"))


def test_load_from_yaml_file(tmp_path, monkeypatch):
    config_file = tmp_path / "custom.yml"
    config_file.write_text("indent: 4\n", encoding="utf-8")
    config = Config.load(str(config_file))
    assert config.indent == 4


def test_invalid_yaml_config_rejected(tmp_path):
    config_file = tmp_path / "broken.yml"
    config_file.write_text("indent: [unclosed", encoding="utf-8")
    with pytest.raises(ConfigError):
        Config.load(str(config_file))
