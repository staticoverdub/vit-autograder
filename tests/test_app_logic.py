"""Tests for pure-logic helpers in app.py.

These tests import individual functions and patch config accessors where
needed so no Flask app, Canvas API, or Anthropic key is required.
"""

import config as config_module


# ── helpers to import app functions without triggering side-effects ──

def _import_app_functions():
    """Import target functions from app.py.

    app.py runs top-level code (load_env_file, Canvas/Anthropic key reads)
    on import. We let that happen once; it is harmless in a test environment
    because the env vars are simply empty strings.
    """
    import app as app_module
    return app_module


# ── detect_assignment_type ─────────────────────────────────────────

class TestDetectAssignmentType:
    def test_checkoff_pattern(self, monkeypatch):
        monkeypatch.setattr(config_module, "load_config_file", lambda: {})
        app = _import_app_functions()
        assert app.detect_assignment_type("LinkedIn Profile Setup") == "checkoff"

    def test_final_project_pattern(self, monkeypatch):
        monkeypatch.setattr(config_module, "load_config_file", lambda: {})
        app = _import_app_functions()
        assert app.detect_assignment_type("W4P1 Final Submission") == "final_project"

    def test_standard_assignment(self, monkeypatch):
        monkeypatch.setattr(config_module, "load_config_file", lambda: {})
        app = _import_app_functions()
        assert app.detect_assignment_type("Week 2 Homework") == "standard"

    def test_case_insensitive(self, monkeypatch):
        monkeypatch.setattr(config_module, "load_config_file", lambda: {})
        app = _import_app_functions()
        assert app.detect_assignment_type("LINKEDIN assignment") == "checkoff"


# ── grade_checkoff_assignment ──────────────────────────────────────

class TestGradeCheckoffAssignment:
    def test_full_credit_when_submitted(self, monkeypatch):
        monkeypatch.setattr(config_module, "load_config_file", lambda: {})
        app = _import_app_functions()
        result = app.grade_checkoff_assignment({
            "submitted_at": "2026-01-15T10:00:00Z",
            "student_name": "Jane Doe",
        })
        assert result["grade"] == 10
        assert "Jane" in result["comment"]

    def test_zero_when_not_submitted(self, monkeypatch):
        monkeypatch.setattr(config_module, "load_config_file", lambda: {})
        app = _import_app_functions()
        result = app.grade_checkoff_assignment({
            "student_name": "Bob Smith",
        })
        assert result["grade"] == 0
        assert "Bob" in result["comment"]

    def test_first_name_extraction(self, monkeypatch):
        monkeypatch.setattr(config_module, "load_config_file", lambda: {})
        app = _import_app_functions()
        result = app.grade_checkoff_assignment({
            "submitted_at": "2026-01-15T10:00:00Z",
            "student_name": "Alice Wonderland",
        })
        assert result["comment"].startswith("Alice")

    def test_missing_student_name(self, monkeypatch):
        monkeypatch.setattr(config_module, "load_config_file", lambda: {})
        app = _import_app_functions()
        result = app.grade_checkoff_assignment({
            "submitted_at": "2026-01-15T10:00:00Z",
        })
        assert result["student_name"] == "Student"

    def test_submitted_via_attachment(self, monkeypatch):
        monkeypatch.setattr(config_module, "load_config_file", lambda: {})
        app = _import_app_functions()
        result = app.grade_checkoff_assignment({
            "attachments": [{"filename": "hw.py"}],
            "student_name": "Test User",
        })
        assert result["grade"] == 10


# ── check_all_graded ──────────────────────────────────────────────

class TestCheckAllGraded:
    def test_empty_list(self, monkeypatch):
        monkeypatch.setattr(config_module, "load_config_file", lambda: {})
        app = _import_app_functions()
        assert app.check_all_graded([]) is False

    def test_none_submitted(self, monkeypatch):
        monkeypatch.setattr(config_module, "load_config_file", lambda: {})
        app = _import_app_functions()
        grades = [
            {"submitted": False, "graded": False},
            {"submitted": False, "graded": False},
        ]
        assert app.check_all_graded(grades) is False

    def test_partial_grading(self, monkeypatch):
        monkeypatch.setattr(config_module, "load_config_file", lambda: {})
        app = _import_app_functions()
        grades = [
            {"submitted": True, "graded": True},
            {"submitted": True, "graded": False},
        ]
        assert app.check_all_graded(grades) is False

    def test_all_graded(self, monkeypatch):
        monkeypatch.setattr(config_module, "load_config_file", lambda: {})
        app = _import_app_functions()
        grades = [
            {"submitted": True, "graded": True},
            {"submitted": True, "graded": True},
        ]
        assert app.check_all_graded(grades) is True

    def test_unsubmitted_ignored(self, monkeypatch):
        monkeypatch.setattr(config_module, "load_config_file", lambda: {})
        app = _import_app_functions()
        grades = [
            {"submitted": True, "graded": True},
            {"submitted": False, "graded": False},
        ]
        assert app.check_all_graded(grades) is True


# ── html_to_text ──────────────────────────────────────────────────

class TestHtmlToText:
    def test_strips_script_tags(self, monkeypatch):
        monkeypatch.setattr(config_module, "load_config_file", lambda: {})
        app = _import_app_functions()
        html = "<p>Hello</p><script>alert('x')</script>"
        result = app.html_to_text(html)
        assert "alert" not in result
        assert "Hello" in result

    def test_strips_style_tags(self, monkeypatch):
        monkeypatch.setattr(config_module, "load_config_file", lambda: {})
        app = _import_app_functions()
        html = "<style>body{color:red}</style><p>Content</p>"
        result = app.html_to_text(html)
        assert "color" not in result
        assert "Content" in result

    def test_converts_br(self, monkeypatch):
        monkeypatch.setattr(config_module, "load_config_file", lambda: {})
        app = _import_app_functions()
        assert "\n" in app.html_to_text("Line1<br>Line2")

    def test_converts_p(self, monkeypatch):
        monkeypatch.setattr(config_module, "load_config_file", lambda: {})
        app = _import_app_functions()
        assert "\n" in app.html_to_text("<p>Para1</p><p>Para2</p>")

    def test_converts_li(self, monkeypatch):
        monkeypatch.setattr(config_module, "load_config_file", lambda: {})
        app = _import_app_functions()
        result = app.html_to_text("<ul><li>Item</li></ul>")
        assert "Item" in result

    def test_decodes_entities(self, monkeypatch):
        monkeypatch.setattr(config_module, "load_config_file", lambda: {})
        app = _import_app_functions()
        assert "&" in app.html_to_text("&amp;")

    def test_empty_input(self, monkeypatch):
        monkeypatch.setattr(config_module, "load_config_file", lambda: {})
        app = _import_app_functions()
        assert app.html_to_text("") == ""

    def test_none_input(self, monkeypatch):
        monkeypatch.setattr(config_module, "load_config_file", lambda: {})
        app = _import_app_functions()
        assert app.html_to_text(None) == ""
