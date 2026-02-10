"""Tests for run_python_code() from code_runner.py."""

import config as config_module
from code_runner import run_python_code


class TestRunPythonCode:
    def test_successful_script(self, monkeypatch):
        monkeypatch.setattr(config_module, "load_config_file", lambda: {})
        result = run_python_code("print('hello world')")
        assert result["success"] is True
        assert "hello world" in result["output"]
        assert result["returncode"] == 0

    def test_syntax_error(self, monkeypatch):
        monkeypatch.setattr(config_module, "load_config_file", lambda: {})
        result = run_python_code("def foo(")
        assert result["success"] is False
        assert result["returncode"] != 0

    def test_timeout(self, monkeypatch):
        monkeypatch.setattr(config_module, "load_config_file", lambda: {})
        result = run_python_code("import time; time.sleep(30)", timeout=1)
        assert result["success"] is False
        assert "timed out" in result["errors"]
        assert result["returncode"] == -1

    def test_output_truncation(self, monkeypatch):
        monkeypatch.setattr(config_module, "load_config_file", lambda: {})
        # Print more than 2000 chars
        result = run_python_code("print('A' * 5000)")
        assert result["success"] is True
        assert len(result["output"]) <= 2000

    def test_no_output(self, monkeypatch):
        monkeypatch.setattr(config_module, "load_config_file", lambda: {})
        result = run_python_code("x = 1")
        assert result["success"] is True
        assert result["output"] == "(no output)"
