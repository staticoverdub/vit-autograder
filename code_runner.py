"""
Sandboxed Python code execution for AutoGrader.
Runs student code in a subprocess with timeout and input injection.
Environment variables are stripped to prevent secret leakage.
"""

import os
import re
import subprocess
import tempfile

from config import get_default_inputs, get_timeout_seconds

# Minimal environment for student code — no secrets, no API keys
_SAFE_ENV = {
    "PATH": "/usr/local/bin:/usr/bin:/bin",
    "HOME": "/tmp",
    "LANG": "en_US.UTF-8",
}


def run_python_code(code, timeout=None):
    """Safely run Python code and capture output"""
    if timeout is None:
        timeout = get_timeout_seconds()

    # Create a temporary file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write(code)
        temp_file = f.name

    try:
        # Run with timeout, provide input for input() calls
        # Use a clean environment to prevent secret leakage
        result = subprocess.run(
            ['python3', temp_file],
            capture_output=True,
            text=True,
            timeout=timeout,
            input=get_default_inputs(),
            env=_SAFE_ENV,
        )

        output = result.stdout
        errors = result.stderr

        # Clean up ANSI codes if any
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        output = ansi_escape.sub('', output)
        errors = ansi_escape.sub('', errors)

        return {
            "success": result.returncode == 0,
            "output": output[:2000] if output else "(no output)",
            "errors": errors[:1000] if errors else None,
            "returncode": result.returncode
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "output": "",
            "errors": f"Code timed out (took longer than {timeout} seconds)",
            "returncode": -1
        }
    except Exception as e:
        return {
            "success": False,
            "output": "",
            "errors": f"Error running code: {str(e)}",
            "returncode": -1
        }
    finally:
        os.unlink(temp_file)
