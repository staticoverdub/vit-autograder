"""Tests for run_python_code() from app.py."""

import config as config_module


def _get_run_python_code():
    import app as app_module
    return app_module.run_python_code


class TestRunPythonCode:
    def test_successful_script(self, monkeypatch):
        monkeypatch.setattr(config_module, "load_config_file", lambda: {})
        run = _get_run_python_code()
        result = run("print('hello world')")
        assert result["success"] is True
        assert "hello world" in result["output"]
        assert result["returncode"] == 0

    def test_syntax_error(self, monkeypatch):
        monkeypatch.setattr(config_module, "load_config_file", lambda: {})
        run = _get_run_python_code()
        result = run("def foo(")
        assert result["success"] is False
        assert result["returncode"] != 0

    def test_timeout(self, monkeypatch):
        monkeypatch.setattr(config_module, "load_config_file", lambda: {})
        run = _get_run_python_code()
        result = run("import time; time.sleep(30)", timeout=1)
        assert result["success"] is False
        assert "timed out" in result["errors"]
        assert result["returncode"] == -1

    def test_output_truncation(self, monkeypatch):
        monkeypatch.setattr(config_module, "load_config_file", lambda: {})
        run = _get_run_python_code()
        # Print more than 2000 chars
        code = "print('A' * 5000)"
        result = run(code)
        assert result["success"] is True
        assert len(result["output"]) <= 2000

    def test_no_output(self, monkeypatch):
        monkeypatch.setattr(config_module, "load_config_file", lambda: {})
        run = _get_run_python_code()
        result = run("x = 1")
        assert result["success"] is True
        assert result["output"] == "(no output)"
