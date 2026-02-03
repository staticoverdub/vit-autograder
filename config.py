"""
Configuration loader for AutoGrader
Loads settings from config.yaml with environment variable overrides
"""

import os
from pathlib import Path

# Try to import yaml, provide helpful error if missing
try:
    import yaml
except ImportError:
    yaml = None

# Default configuration values
DEFAULTS = {
    "organization": {
        "name": "Your Organization",
        "website": "https://example.com",
        "tagline": "AI-Powered Assignment Grading"
    },
    "instructor": {
        "name": "Instructor",
        "sign_off": "— Your Teaching Team"
    },
    "canvas": {
        "url": "https://canvas.instructure.com"
    },
    "course": {
        "name": "Introduction to Python",
        "type": "introductory",
        "audience": "students learning to code"
    },
    "grading": {
        "default_points": 10,
        "leniency": "lenient",  # strict, moderate, lenient
        "timeout_seconds": 10,
        "available_libraries": [
            "requests", "json", "openpyxl", "pandas", "numpy",
            "matplotlib", "math", "random", "datetime", "os", "re"
        ],
        "default_inputs": "5\ntest\nyes\n100\n",
        "model": "claude-sonnet-4-20250514",
        "checkoff_patterns": ["linkedin", "opligon", "profile", "setup", "account"],
        "final_project_patterns": ["w4p1", "w4p2", "final", "project", "capstone"]
    },
    "messages": {
        "celebration": {
            "resources": [
                {"label": "Organization Website", "url": "https://example.com"},
                {"label": "More Classes", "url": "https://example.com/classes"}
            ],
            "next_steps": [
                "Advanced Python",
                "Web Development",
                "Data Science"
            ]
        },
        "reminder": {
            "deadline_days": 7,
            "sign_off": "— Your Instructor"
        }
    },
    "rubric_page_map": {
        "w4p1": "W4P1 Lesson Custom",
        "w4p2": "W4P2 Lesson Custom"
    }
}


def deep_merge(base: dict, override: dict) -> dict:
    """Deep merge two dictionaries, with override taking precedence"""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config_file() -> dict:
    """Load configuration from config.yaml file"""
    if yaml is None:
        print("Warning: PyYAML not installed, using defaults only", flush=True)
        return {}

    config_paths = [
        Path('/app/config.yaml'),        # Inside Docker container
        Path('/app/../config.yaml'),     # Parent of app dir in Docker
        Path('../config.yaml'),          # Parent directory
        Path('config.yaml'),             # Current directory
    ]

    for config_path in config_paths:
        if config_path.exists():
            print(f"Loading config from: {config_path}", flush=True)
            try:
                with open(config_path) as f:
                    config = yaml.safe_load(f)
                    return config if config else {}
            except Exception as e:
                print(f"Error loading config: {e}", flush=True)
                return {}

    print("No config.yaml found, using defaults", flush=True)
    return {}


def apply_env_overrides(config: dict) -> dict:
    """Apply environment variable overrides to config"""
    # Canvas URL can be overridden by environment variable
    if os.environ.get("CANVAS_URL"):
        if "canvas" not in config:
            config["canvas"] = {}
        config["canvas"]["url"] = os.environ["CANVAS_URL"]

    # Organization name override
    if os.environ.get("ORG_NAME"):
        if "organization" not in config:
            config["organization"] = {}
        config["organization"]["name"] = os.environ["ORG_NAME"]

    # Grading model override
    if os.environ.get("GRADING_MODEL"):
        if "grading" not in config:
            config["grading"] = {}
        config["grading"]["model"] = os.environ["GRADING_MODEL"]

    return config


# Global config instance
_config = None


def get_config() -> dict:
    """Get the merged configuration (cached)"""
    global _config
    if _config is None:
        file_config = load_config_file()
        merged = deep_merge(DEFAULTS, file_config)
        _config = apply_env_overrides(merged)
    return _config


def reload_config() -> dict:
    """Force reload of configuration"""
    global _config
    _config = None
    return get_config()


# Convenience accessors
def get_org_name() -> str:
    return get_config()["organization"]["name"]


def get_org_website() -> str:
    return get_config()["organization"]["website"]


def get_org_tagline() -> str:
    return get_config()["organization"]["tagline"]


def get_instructor_name() -> str:
    return get_config()["instructor"]["name"]


def get_instructor_sign_off() -> str:
    return get_config()["instructor"]["sign_off"]


def get_canvas_url() -> str:
    return get_config()["canvas"]["url"]


def get_course_name() -> str:
    return get_config()["course"]["name"]


def get_course_type() -> str:
    return get_config()["course"]["type"]


def get_course_audience() -> str:
    return get_config()["course"]["audience"]


def get_grading_config() -> dict:
    return get_config()["grading"]


def get_default_points() -> int:
    return get_config()["grading"]["default_points"]


def get_leniency() -> str:
    return get_config()["grading"]["leniency"]


def get_timeout_seconds() -> int:
    return get_config()["grading"]["timeout_seconds"]


def get_available_libraries() -> list:
    return get_config()["grading"]["available_libraries"]


def get_default_inputs() -> str:
    return get_config()["grading"]["default_inputs"]


def get_grading_model() -> str:
    return get_config()["grading"]["model"]


def get_checkoff_patterns() -> list:
    return get_config()["grading"]["checkoff_patterns"]


def get_final_project_patterns() -> list:
    return get_config()["grading"]["final_project_patterns"]


def get_celebration_config() -> dict:
    return get_config()["messages"]["celebration"]


def get_reminder_config() -> dict:
    return get_config()["messages"]["reminder"]


def get_rubric_page_map() -> dict:
    return get_config().get("rubric_page_map", {})
