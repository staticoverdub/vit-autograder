"""
Prompt template loader for AutoGrader
Renders Jinja2 templates with configuration and context variables
"""

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, TemplateNotFound

from config import get_config

# Find the prompts directory
PROMPTS_DIRS = [
    Path('/app/prompts'),      # Inside Docker
    Path('./prompts'),         # Current directory
    Path('../prompts'),        # Parent directory
]


def get_prompts_dir() -> Path:
    """Find the prompts directory"""
    for prompts_dir in PROMPTS_DIRS:
        if prompts_dir.exists() and prompts_dir.is_dir():
            return prompts_dir
    return Path('./prompts')


# Set up Jinja2 environment
_env = None


def get_jinja_env() -> Environment:
    """Get or create the Jinja2 environment"""
    global _env
    if _env is None:
        prompts_dir = get_prompts_dir()
        if prompts_dir.exists():
            _env = Environment(
                loader=FileSystemLoader(str(prompts_dir)),
                trim_blocks=True,
                lstrip_blocks=True
            )
        else:
            # Fallback to empty environment
            _env = Environment(trim_blocks=True, lstrip_blocks=True)
    return _env


def render_template(template_name: str, **context) -> str:
    """
    Render a prompt template with the given context.

    Args:
        template_name: Name of the template file (e.g., 'grading_standard.j2')
        **context: Additional variables to pass to the template

    Returns:
        Rendered template string
    """
    env = get_jinja_env()
    config = get_config()

    # Merge config into context
    full_context = {
        'config': config,
        'org': config.get('organization', {}),
        'instructor': config.get('instructor', {}),
        'course': config.get('course', {}),
        'grading': config.get('grading', {}),
        'messages': config.get('messages', {}),
        **context
    }

    try:
        template = env.get_template(template_name)
        return template.render(**full_context)
    except TemplateNotFound:
        print(f"Warning: Template '{template_name}' not found, returning empty string", flush=True)
        return ""


def render_grading_prompt(
    submissions_text: str,
    student_list: list,
    assignment_info: str = "",
    points_possible: int = 10
) -> str:
    """Render the standard grading prompt"""
    return render_template(
        'grading_standard.j2',
        submissions_text=submissions_text,
        student_list=student_list,
        assignment_info=assignment_info,
        points_possible=points_possible
    )


def render_final_project_prompt(
    submissions_text: str,
    student_list: list,
    rubric: str
) -> str:
    """Render the final project grading prompt"""
    return render_template(
        'grading_final_project.j2',
        submissions_text=submissions_text,
        student_list=student_list,
        rubric=rubric
    )


def render_single_grading_prompt(
    submission_text: str,
    student_name: str,
    first_name: str,
    filename: str,
    points_possible: int,
    assignment_type: str = "standard",
    rubric_text: str = ""
) -> str:
    """Render the single submission grading prompt"""
    return render_template(
        'grading_single.j2',
        submission_text=submission_text,
        student_name=student_name,
        first_name=first_name,
        filename=filename,
        points_possible=points_possible,
        assignment_type=assignment_type,
        rubric_text=rubric_text
    )


def render_celebration_message(
    student_name: str,
    course_name: str,
    avg_percentage: float,
    grades_summary: str,
    best_summary: str,
    skills_text: str
) -> str:
    """Render the celebration message prompt"""
    return render_template(
        'celebration_message.j2',
        student_name=student_name,
        course_name=course_name,
        avg_percentage=avg_percentage,
        grades_summary=grades_summary,
        best_summary=best_summary,
        skills_text=skills_text
    )


def render_reminder_message(
    first_name: str,
    course_name: str,
    missing_list: str
) -> str:
    """Render the reminder message"""
    return render_template(
        'reminder_message.j2',
        first_name=first_name,
        course_name=course_name,
        missing_list=missing_list
    )
