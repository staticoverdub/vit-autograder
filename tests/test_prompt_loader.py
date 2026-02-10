"""Tests for prompt_loader.py template rendering."""

import config as config_module
import prompt_loader


class TestGetPromptsDir:
    def test_returns_path(self):
        result = prompt_loader.get_prompts_dir()
        assert result is not None


class TestRenderTemplate:
    def setup_method(self):
        # Reset the cached jinja env so each test picks up fresh state
        prompt_loader._env = None

    def test_missing_template_returns_empty(self, monkeypatch):
        monkeypatch.setattr(config_module, "load_config_file", lambda: {})
        result = prompt_loader.render_template("nonexistent_template.j2")
        assert result == ""

    def test_render_grading_prompt_contains_org(self, monkeypatch):
        monkeypatch.setattr(config_module, "load_config_file", lambda: {
            "organization": {"name": "Test Academy"},
        })
        result = prompt_loader.render_grading_prompt(
            submissions_text="print('hello')",
            student_list=["Alice Smith"],
            assignment_info="Week 1 homework",
            points_possible=10,
        )
        assert "Test Academy" in result

    def test_render_grading_prompt_contains_students(self, monkeypatch):
        monkeypatch.setattr(config_module, "load_config_file", lambda: {})
        result = prompt_loader.render_grading_prompt(
            submissions_text="code here",
            student_list=["Bob Jones", "Carol Lee"],
            assignment_info="",
            points_possible=10,
        )
        assert "Bob Jones" in result
        assert "Carol Lee" in result

    def test_render_grading_prompt_leniency(self, monkeypatch):
        monkeypatch.setattr(config_module, "load_config_file", lambda: {
            "grading": {"leniency": "strict"},
        })
        result = prompt_loader.render_grading_prompt(
            submissions_text="code",
            student_list=["Test Student"],
            points_possible=10,
        )
        assert "strictly" in result.lower()

    def test_render_reminder_message(self, monkeypatch):
        monkeypatch.setattr(config_module, "load_config_file", lambda: {})
        result = prompt_loader.render_reminder_message(
            first_name="Dana",
            course_name="Intro to Python",
            missing_list="- Week 3 HW\n- Week 4 HW",
        )
        assert "Dana" in result
        assert "Intro to Python" in result
        assert "Week 3 HW" in result

    def test_render_final_project_prompt(self, monkeypatch):
        monkeypatch.setattr(config_module, "load_config_file", lambda: {})
        result = prompt_loader.render_final_project_prompt(
            submissions_text="final project code",
            student_list=["Eve Adams"],
            rubric="Must include classes and functions",
        )
        assert "Eve Adams" in result

    def test_render_single_grading_prompt(self, monkeypatch):
        monkeypatch.setattr(config_module, "load_config_file", lambda: {})
        result = prompt_loader.render_single_grading_prompt(
            submission_text="print('hi')",
            student_name="Frank White",
            first_name="Frank",
            filename="hw1.py",
            points_possible=10,
        )
        assert "Frank" in result

    def test_context_overrides_config(self, monkeypatch):
        """Extra context kwargs should be available in the template."""
        monkeypatch.setattr(config_module, "load_config_file", lambda: {})
        result = prompt_loader.render_grading_prompt(
            submissions_text="some code",
            student_list=["Test"],
            assignment_info="Special assignment info here",
            points_possible=20,
        )
        assert "Special assignment info here" in result
        assert "20" in result
