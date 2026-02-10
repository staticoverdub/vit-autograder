import os
import config as config_module
from config import (
    deep_merge,
    apply_env_overrides,
    reload_config,
    get_config,
    get_org_name,
    get_canvas_url,
    get_grading_model,
    get_default_points,
    get_leniency,
    get_timeout_seconds,
)


# ── deep_merge ──────────────────────────────────────────────────────

class TestDeepMerge:
    def test_nested_merge(self):
        base = {"a": {"x": 1, "y": 2}}
        override = {"a": {"y": 99}}
        result = deep_merge(base, override)
        assert result == {"a": {"x": 1, "y": 99}}

    def test_override_precedence(self):
        base = {"key": "old"}
        override = {"key": "new"}
        assert deep_merge(base, override)["key"] == "new"

    def test_new_keys_added(self):
        base = {"a": 1}
        override = {"b": 2}
        result = deep_merge(base, override)
        assert result == {"a": 1, "b": 2}

    def test_override_replaces_non_dict_with_dict(self):
        base = {"a": "string"}
        override = {"a": {"nested": True}}
        result = deep_merge(base, override)
        assert result == {"a": {"nested": True}}

    def test_does_not_mutate_base(self):
        base = {"a": {"x": 1}}
        override = {"a": {"y": 2}}
        deep_merge(base, override)
        assert base == {"a": {"x": 1}}

    def test_empty_override(self):
        base = {"a": 1}
        assert deep_merge(base, {}) == {"a": 1}

    def test_empty_base(self):
        override = {"a": 1}
        assert deep_merge({}, override) == {"a": 1}


# ── apply_env_overrides ────────────────────────────────────────────

class TestApplyEnvOverrides:
    def test_canvas_url_override(self, monkeypatch):
        monkeypatch.setenv("CANVAS_URL", "https://override.example.com")
        cfg = {"canvas": {"url": "https://original.example.com"}}
        result = apply_env_overrides(cfg)
        assert result["canvas"]["url"] == "https://override.example.com"

    def test_org_name_override(self, monkeypatch):
        monkeypatch.setenv("ORG_NAME", "Override Org")
        cfg = {"organization": {"name": "Original"}}
        result = apply_env_overrides(cfg)
        assert result["organization"]["name"] == "Override Org"

    def test_grading_model_override(self, monkeypatch):
        monkeypatch.setenv("GRADING_MODEL", "claude-opus-4-6")
        cfg = {"grading": {"model": "claude-sonnet-4-20250514"}}
        result = apply_env_overrides(cfg)
        assert result["grading"]["model"] == "claude-opus-4-6"

    def test_creates_missing_sections(self, monkeypatch):
        monkeypatch.setenv("CANVAS_URL", "https://new.example.com")
        cfg = {}
        result = apply_env_overrides(cfg)
        assert result["canvas"]["url"] == "https://new.example.com"

    def test_no_override_when_env_unset(self, monkeypatch):
        monkeypatch.delenv("CANVAS_URL", raising=False)
        monkeypatch.delenv("ORG_NAME", raising=False)
        monkeypatch.delenv("GRADING_MODEL", raising=False)
        cfg = {"canvas": {"url": "https://original.example.com"}}
        result = apply_env_overrides(cfg)
        assert result["canvas"]["url"] == "https://original.example.com"


# ── reload_config ──────────────────────────────────────────────────

class TestReloadConfig:
    def test_cache_invalidation(self, minimal_config):
        cfg1 = get_config()
        assert cfg1["organization"]["name"] == "Test Org"

        # Rewrite the config file
        minimal_config.write_text(
            "organization:\n  name: Reloaded Org\n"
        )
        cfg2 = reload_config()
        assert cfg2["organization"]["name"] == "Reloaded Org"


# ── accessor defaults ──────────────────────────────────────────────

class TestAccessorDefaults:
    """When no config.yaml is present, accessors should return DEFAULTS."""

    def test_org_name_default(self, monkeypatch):
        # Ensure no env overrides interfere
        monkeypatch.delenv("ORG_NAME", raising=False)
        # Patch loader to return empty (no file)
        monkeypatch.setattr(config_module, "load_config_file", lambda: {})
        assert get_org_name() == "Your Organization"

    def test_canvas_url_default(self, monkeypatch):
        monkeypatch.delenv("CANVAS_URL", raising=False)
        monkeypatch.setattr(config_module, "load_config_file", lambda: {})
        assert get_canvas_url() == "https://canvas.instructure.com"

    def test_grading_model_default(self, monkeypatch):
        monkeypatch.delenv("GRADING_MODEL", raising=False)
        monkeypatch.setattr(config_module, "load_config_file", lambda: {})
        assert get_grading_model() == "claude-sonnet-4-20250514"

    def test_default_points(self, monkeypatch):
        monkeypatch.setattr(config_module, "load_config_file", lambda: {})
        assert get_default_points() == 10

    def test_leniency_default(self, monkeypatch):
        monkeypatch.setattr(config_module, "load_config_file", lambda: {})
        assert get_leniency() == "lenient"

    def test_timeout_default(self, monkeypatch):
        monkeypatch.setattr(config_module, "load_config_file", lambda: {})
        assert get_timeout_seconds() == 10
