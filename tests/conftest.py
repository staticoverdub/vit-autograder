import sys
import types
import os
import pytest

# Stub the anthropic module so `import app` works without installing it.
# app.py does `from anthropic import Anthropic` at module level.
if "anthropic" not in sys.modules:
    _anthropic = types.ModuleType("anthropic")
    _anthropic.Anthropic = type("Anthropic", (), {})  # dummy class
    sys.modules["anthropic"] = _anthropic

import config as config_module


@pytest.fixture(autouse=True)
def reset_config_cache():
    """Reset the config cache between every test."""
    config_module._config = None
    yield
    config_module._config = None


@pytest.fixture()
def minimal_config(tmp_path):
    """Write a minimal config.yaml and point the loader at it.

    Returns the path so tests can read/modify it.
    """
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(
        "organization:\n"
        "  name: Test Org\n"
        "canvas:\n"
        "  url: https://test.canvas.example.com\n"
    )
    # Monkey-patch load_config_file to use this file
    original = config_module.load_config_file

    def _load():
        import yaml
        with open(cfg_file) as f:
            return yaml.safe_load(f) or {}

    config_module.load_config_file = _load
    yield cfg_file
    config_module.load_config_file = original
