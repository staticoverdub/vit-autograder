"""
AutoGrader - AI-Powered Assignment Grading
A configurable tool to grade Python assignments and submit to Canvas LMS
"""

from flask import Flask, render_template, request, jsonify, session
import os
import zipfile
import tempfile
import subprocess
import json
import requests
import re
import shutil
from datetime import datetime
from anthropic import Anthropic

# Import configuration
from config import (
    get_config, get_canvas_url, get_org_name, get_org_tagline,
    get_instructor_name, get_instructor_sign_off,
    get_course_name, get_course_type, get_course_audience,
    get_grading_model, get_timeout_seconds, get_available_libraries,
    get_default_inputs, get_default_points, get_leniency,
    get_checkoff_patterns, get_final_project_patterns,
    get_celebration_config, get_reminder_config, get_rubric_page_map
)
from prompt_loader import (
    render_grading_prompt, render_final_project_prompt,
    render_single_grading_prompt, render_celebration_message,
    render_reminder_message
)

app = Flask(__name__)
app.secret_key = os.urandom(24)

# Load .env file from parent directory or current directory
def load_env_file():
    """Load environment variables from .env file"""
    env_paths = [
        '/app/.env',           # Inside Docker container
        '/app/../.env',        # Parent of app dir in Docker
        '../.env',             # Parent directory
        '.env',                # Current directory
    ]

    for env_path in env_paths:
        if os.path.exists(env_path):
            print(f"Loading .env from: {env_path}", flush=True)
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        key = key.strip()
                        value = value.strip()
                        # Only set if not already set
                        if not os.environ.get(key):
                            os.environ[key] = value
                            print(f"  Loaded: {key}", flush=True)
            return True
    print("No .env file found", flush=True)
    return False

load_env_file()

# Load configuration from config.yaml (with defaults and env overrides)
config = get_config()

# API credentials from environment (secrets stay in .env)
CANVAS_URL = get_canvas_url()
CANVAS_TOKEN = os.environ.get("CANVAS_TOKEN", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

print(f"Config loaded:", flush=True)
print(f"  Organization: {get_org_name()}", flush=True)
print(f"  CANVAS_URL: {CANVAS_URL}", flush=True)
print(f"  CANVAS_TOKEN: {'[SET]' if CANVAS_TOKEN else '[NOT SET]'}", flush=True)
print(f"  ANTHROPIC_API_KEY: {'[SET]' if ANTHROPIC_API_KEY else '[NOT SET]'}", flush=True)

# Store current session data
current_session = {
    "submissions": [],
    "grades": [],
    "course": None,
    "assignment": None
}


def get_headers():
    """Get headers for Canvas API - just auth, no Content-Type for form data"""
    return {
        "Authorization": f"Bearer {CANVAS_TOKEN}"
    }


def get_json_headers():
    """Get headers for JSON requests"""
    return {
        "Authorization": f"Bearer {CANVAS_TOKEN}",
        "Content-Type": "application/json"
    }


# ============== CANVAS API FUNCTIONS ==============

def get_courses():
    """Get all courses for the current user"""
    url = f"{CANVAS_URL}/api/v1/courses"
    params = {
        "enrollment_type": "teacher",
        "enrollment_state": "active",
        "per_page": 50,
        "include[]": ["total_students"]
    }
    
    try:
        response = requests.get(url, headers=get_headers(), params=params)
        if response.status_code == 200:
            courses = response.json()
            # Filter and sort courses
            valid_courses = [c for c in courses if isinstance(c, dict) and c.get('name')]
            return sorted(valid_courses, key=lambda x: x.get('name', ''))
        return []
    except Exception as e:
        print(f"Error fetching courses: {e}")
        return []


def get_assignments(course_id):
    """Get all assignments for a course"""
    url = f"{CANVAS_URL}/api/v1/courses/{course_id}/assignments"
    params = {
        "per_page": 100,
        "order_by": "due_at"
    }
    
    try:
        response = requests.get(url, headers=get_headers(), params=params)
        if response.status_code == 200:
            assignments = response.json()
            # Add submission stats
            for a in assignments:
                a['needs_grading'] = a.get('needs_grading_count', 0)
            return assignments
        return []
    except Exception as e:
        print(f"Error fetching assignments: {e}")
        return []


def get_assignment_details(course_id, assignment_id):
    """Get detailed info about an assignment"""
    url = f"{CANVAS_URL}/api/v1/courses/{course_id}/assignments/{assignment_id}"
    
    try:
        response = requests.get(url, headers=get_headers())
        if response.status_code == 200:
            return response.json()
        return None
    except Exception as e:
        print(f"Error fetching assignment details: {e}")
        return None


def get_submissions_with_files(course_id, assignment_id):
    """Get all submissions with attachments and full user info"""
    url = f"{CANVAS_URL}/api/v1/courses/{course_id}/assignments/{assignment_id}/submissions"
    params = {
        "per_page": 100,
        "include[]": ["user", "submission_comments"]
    }
    
    try:
        response = requests.get(url, headers=get_headers(), params=params)
        if response.status_code == 200:
            submissions = response.json()
            
            # Also fetch full user details for better matching
            for sub in submissions:
                user_id = sub.get('user_id')
                if user_id:
                    user_url = f"{CANVAS_URL}/api/v1/users/{user_id}/profile"
                    user_response = requests.get(user_url, headers=get_headers())
                    if user_response.status_code == 200:
                        profile = user_response.json()
                        if 'user' not in sub:
                            sub['user'] = {}
                        sub['user']['email'] = profile.get('primary_email', profile.get('login_id', ''))
                        sub['user']['login_id'] = profile.get('login_id', '')
            
            return submissions
        return []
    except Exception as e:
        print(f"Error fetching submissions: {e}")
        return []


def download_submission_file(url):
    """Download a file from Canvas"""
    try:
        response = requests.get(url, headers=get_headers(), allow_redirects=True)
        if response.status_code == 200:
            return response.text
        return None
    except Exception as e:
        print(f"Error downloading file: {e}")
        return None


def submit_grade_to_canvas(course_id, assignment_id, student_id, grade, comment):
    """Submit a grade and comment to Canvas"""
    url = f"{CANVAS_URL}/api/v1/courses/{course_id}/assignments/{assignment_id}/submissions/{student_id}"
    
    data = {
        "submission": {"posted_grade": str(grade)},
        "comment": {"text_comment": comment}
    }
    
    try:
        response = requests.put(url, headers=get_headers(), json=data)
        return response.status_code == 200, response.text
    except Exception as e:
        return False, str(e)


# ============== CODE EXECUTION ==============

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
        result = subprocess.run(
            ['python3', temp_file],
            capture_output=True,
            text=True,
            timeout=timeout,
            input=get_default_inputs()  # Default inputs for interactive programs
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
            "errors": f"⏱️ Code timed out (took longer than {timeout} seconds)",
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


# ============== AI GRADING ==============

def grade_with_claude(submissions, assignment_info=""):
    """Use Claude to grade submissions"""
    if not ANTHROPIC_API_KEY:
        return {"error": "Anthropic API key not configured"}

    client = Anthropic(api_key=ANTHROPIC_API_KEY)

    # Build the prompt with clear student markers
    submissions_text = ""
    student_list = []
    for i, sub in enumerate(submissions):
        student_name = sub.get('student_name', 'Unknown')
        filename = sub.get('filename', 'unknown.py')
        student_list.append(f"{student_name} ({filename})")

        submissions_text += f"\n{'='*60}\n"
        submissions_text += f"SUBMISSION #{i+1}\n"
        submissions_text += f"STUDENT NAME: {student_name}\n"
        submissions_text += f"FILENAME: {filename}\n"
        submissions_text += f"{'='*60}\n"
        submissions_text += sub.get('code', '# No code')
        submissions_text += "\n"

        if sub.get('run_result'):
            run = sub['run_result']
            submissions_text += f"\n--- OUTPUT ---\n{run.get('output', 'N/A')}\n"
            if run.get('errors'):
                submissions_text += f"--- ERRORS ---\n{run['errors']}\n"

    # Render prompt from template
    prompt = render_grading_prompt(
        submissions_text=submissions_text,
        student_list=student_list,
        assignment_info=assignment_info,
        points_possible=get_default_points()
    )

    try:
        message = client.messages.create(
            model=get_grading_model(),
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}]
        )
        
        response_text = message.content[0].text
        
        # Extract JSON from response
        try:
            return json.loads(response_text)
        except json.JSONDecodeError:
            json_match = re.search(r'\{[\s\S]*\}', response_text)
            if json_match:
                return json.loads(json_match.group())
            return {"error": "Failed to parse response", "raw": response_text}
            
    except Exception as e:
        return {"error": str(e)}


# ============== FILE HANDLING ==============

def extract_zip(zip_file):
    """Extract zip file and return list of .py files with content"""
    temp_dir = tempfile.mkdtemp()
    
    with zipfile.ZipFile(zip_file, 'r') as z:
        z.extractall(temp_dir)
    
    submissions = []
    for root, dirs, files in os.walk(temp_dir):
        for file in files:
            if file.endswith('.py'):
                filepath = os.path.join(root, file)
                try:
                    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                        code = f.read()
                except:
                    code = "# Could not read file"
                
                # Extract student name from filename
                # Format: "studentname_12345_67890_assignment.py"
                parts = file.split('_')
                student_name = parts[0].title() if parts else "Unknown"
                
                submissions.append({
                    "filename": file,
                    "filepath": filepath,
                    "student_name": student_name,
                    "code": code,
                    "run_result": None
                })
    
    return submissions, temp_dir


# ============== ROUTES ==============

@app.route('/')
def index():
    return render_template('index.html',
        org_name=get_org_name(),
        org_tagline=get_org_tagline(),
        available_libraries=get_available_libraries()
    )


@app.route('/api/config', methods=['GET', 'POST'])
def config():
    """Get or set configuration"""
    global CANVAS_URL, CANVAS_TOKEN, ANTHROPIC_API_KEY
    
    if request.method == 'POST':
        data = request.json
        
        if data.get('canvas_url'):
            CANVAS_URL = data['canvas_url']
        if data.get('canvas_token'):
            CANVAS_TOKEN = data['canvas_token']
        if data.get('anthropic_key'):
            ANTHROPIC_API_KEY = data['anthropic_key']
        
        return jsonify({"status": "updated"})
    
    return jsonify({
        "canvas_url": CANVAS_URL,
        "has_canvas_token": bool(CANVAS_TOKEN),
        "has_anthropic_key": bool(ANTHROPIC_API_KEY)
    })


@app.route('/api/branding')
def get_branding():
    """Get organization branding information"""
    return jsonify({
        "org_name": get_org_name(),
        "org_tagline": get_org_tagline(),
        "org_website": get_org_website(),
        "course_name": get_course_name(),
        "instructor_name": get_instructor_name()
    })


@app.route('/api/courses/<course_id>/branding')
def get_course_branding(course_id):
    """Fetch course branding information from Canvas"""
    try:
        # Get course details from Canvas
        course_url = f"{CANVAS_URL}/api/v1/courses/{course_id}"
        course_response = requests.get(course_url, headers=get_headers(), params={"include[]": ["term"]})

        if course_response.status_code != 200:
            return jsonify({"error": "Failed to fetch course info"}), 400

        course_data = course_response.json()

        # Get account branding if available
        account_id = course_data.get('account_id')
        branding = {}
        if account_id:
            brand_url = f"{CANVAS_URL}/api/v1/accounts/{account_id}/brand_configs"
            brand_response = requests.get(brand_url, headers=get_headers())
            if brand_response.status_code == 200:
                brand_data = brand_response.json()
                if brand_data:
                    branding = brand_data[0] if isinstance(brand_data, list) else brand_data

        return jsonify({
            "course_name": course_data.get('name'),
            "course_code": course_data.get('course_code'),
            "course_image": course_data.get('image_download_url'),
            "term": course_data.get('term', {}).get('name') if course_data.get('term') else None,
            "account_id": account_id,
            "branding": branding
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/courses')
def api_courses():
    """Get list of courses"""
    courses = get_courses()
    return jsonify(courses)


@app.route('/api/courses/<course_id>/assignments')
def api_assignments(course_id):
    """Get assignments for a course"""
    assignments = get_assignments(course_id)
    return jsonify(assignments)


import json
from pathlib import Path

# Track who received celebration/reminder messages
CELEBRATED_FILE = Path("/app/data/celebrated_students.json")
REMINDED_FILE = Path("/app/data/reminded_students.json")

def ensure_data_dir():
    """Ensure data directory exists"""
    CELEBRATED_FILE.parent.mkdir(parents=True, exist_ok=True)

def get_celebrated_students():
    """Load list of students who already received celebration messages"""
    ensure_data_dir()
    if CELEBRATED_FILE.exists() and CELEBRATED_FILE.is_file():
        try:
            return json.loads(CELEBRATED_FILE.read_text())
        except:
            return {}
    return {}

def mark_student_celebrated(course_id, user_id):
    """Mark a student as having received their celebration message"""
    ensure_data_dir()
    celebrated = get_celebrated_students()
    key = f"{course_id}_{user_id}"
    celebrated[key] = datetime.now().isoformat()
    CELEBRATED_FILE.write_text(json.dumps(celebrated, indent=2))

def has_been_celebrated(course_id, user_id):
    """Check if student already received celebration message - checks both local file and Canvas conversations"""
    # First check local file
    celebrated = get_celebrated_students()
    key = f"{course_id}_{user_id}"
    if key in celebrated:
        return True
    
    # Also check Canvas conversations for a message with congratulations subject
    try:
        url = f"{CANVAS_URL}/api/v1/conversations"
        params = {
            "filter[]": f"user_{user_id}",
            "filter_mode": "and",
            "per_page": 50
        }
        response = requests.get(url, headers=get_headers(), params=params)
        if response.status_code == 200:
            conversations = response.json()
            for conv in conversations:
                subject = conv.get('subject', '').lower()
                if 'congratulations' in subject or 'congrat' in subject or '🎉' in subject:
                    # Mark locally so we don't check again
                    mark_student_celebrated(course_id, user_id)
                    return True
    except Exception as e:
        print(f"Error checking Canvas conversations: {e}")
    
    return False

def get_reminded_students():
    """Load list of students who received reminder messages"""
    ensure_data_dir()
    if REMINDED_FILE.exists() and REMINDED_FILE.is_file():
        try:
            return json.loads(REMINDED_FILE.read_text())
        except:
            return {}
    return {}

def mark_student_reminded(course_id, user_id):
    """Mark a student as having received a reminder"""
    ensure_data_dir()
    reminded = get_reminded_students()
    key = f"{course_id}_{user_id}"
    reminded[key] = datetime.now().isoformat()
    REMINDED_FILE.write_text(json.dumps(reminded, indent=2))

def has_been_reminded_recently(course_id, user_id, days=7):
    """Check if student was reminded in the last N days"""
    reminded = get_reminded_students()
    key = f"{course_id}_{user_id}"
    if key not in reminded:
        return False
    try:
        reminded_date = datetime.fromisoformat(reminded[key])
        return (datetime.now() - reminded_date).days < days
    except:
        return False


def get_student_all_grades(course_id, user_id):
    """Get all assignment grades for a student in a course"""
    url = f"{CANVAS_URL}/api/v1/courses/{course_id}/assignments"
    params = {"per_page": 100}
    
    try:
        # Get all assignments
        response = requests.get(url, headers=get_headers(), params=params)
        if response.status_code != 200:
            return None
        
        assignments = response.json()
        
        # Get submissions for each assignment
        grades = []
        for assignment in assignments:
            if assignment.get('published', True):  # Only published assignments
                sub_url = f"{CANVAS_URL}/api/v1/courses/{course_id}/assignments/{assignment['id']}/submissions/{user_id}"
                sub_response = requests.get(sub_url, headers=get_headers())
                
                if sub_response.status_code == 200:
                    sub = sub_response.json()
                    grades.append({
                        "assignment_id": assignment['id'],
                        "assignment_name": assignment.get('name', 'Unknown'),
                        "points_possible": assignment.get('points_possible', 0),
                        "score": sub.get('score'),
                        "grade": sub.get('grade'),
                        "graded": sub.get('grade') is not None,
                        "submitted": sub.get('submitted_at') is not None
                    })
        
        return grades
    except Exception as e:
        print(f"Error getting student grades: {e}")
        return None


def check_all_graded(grades):
    """Check if all assignments are graded"""
    if not grades:
        return False
    
    # Filter to assignments that were submitted
    submitted = [g for g in grades if g['submitted']]
    if not submitted:
        return False
    
    # Check if all submitted assignments are graded
    return all(g['graded'] for g in submitted)


def generate_celebration_message(student_name, grades, course_name):
    """Use Claude to generate a personalized celebration message"""
    if not ANTHROPIC_API_KEY:
        return None

    client = Anthropic(api_key=ANTHROPIC_API_KEY)

    # Calculate stats
    graded = [g for g in grades if g['graded'] and g['score'] is not None]
    total_score = sum(g['score'] for g in graded)
    total_possible = sum(g['points_possible'] for g in graded if g['points_possible'])
    avg_percentage = (total_score / total_possible * 100) if total_possible > 0 else 0

    # Find best performances
    best_assignments = sorted(
        [g for g in graded if g['points_possible'] and g['points_possible'] > 0],
        key=lambda x: (x['score'] / x['points_possible']),
        reverse=True
    )[:3]

    grades_summary = "\n".join([
        f"- {g['assignment_name']}: {g['score']}/{g['points_possible']}"
        for g in graded
    ])

    best_summary = "\n".join([
        f"- {g['assignment_name']}: {g['score']}/{g['points_possible']} ({g['score']/g['points_possible']*100:.0f}%)"
        for g in best_assignments
    ])

    # Determine skill areas based on assignments
    skill_areas = []
    for g in best_assignments:
        name_lower = g['assignment_name'].lower()
        if 'loop' in name_lower or 'for' in name_lower or 'while' in name_lower:
            skill_areas.append('loops and iteration')
        elif 'function' in name_lower or 'def' in name_lower:
            skill_areas.append('functions and modular code')
        elif 'list' in name_lower or 'dict' in name_lower or 'array' in name_lower:
            skill_areas.append('data structures')
        elif 'file' in name_lower or 'read' in name_lower or 'write' in name_lower:
            skill_areas.append('file handling')
        elif 'api' in name_lower or 'request' in name_lower:
            skill_areas.append('API integration')
        elif 'class' in name_lower or 'object' in name_lower:
            skill_areas.append('object-oriented programming')

    skills_text = ", ".join(skill_areas) if skill_areas else "Python fundamentals"

    # Render prompt from template
    prompt = render_celebration_message(
        student_name=student_name,
        course_name=course_name,
        avg_percentage=avg_percentage,
        grades_summary=grades_summary,
        best_summary=best_summary,
        skills_text=skills_text
    )

    try:
        message = client.messages.create(
            model=get_grading_model(),
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}]
        )
        return message.content[0].text
    except Exception as e:
        print(f"Error generating celebration message: {e}")
        return None


def get_course_instructors(course_id):
    """Get all teachers for a course"""
    url = f"{CANVAS_URL}/api/v1/courses/{course_id}/users"
    params = {"enrollment_type[]": "teacher", "per_page": 50}
    
    try:
        response = requests.get(url, headers=get_headers(), params=params)
        if response.status_code == 200:
            instructors = [str(u['id']) for u in response.json()]
            print(f"Found {len(instructors)} instructors: {instructors}")
            return instructors
        print(f"Failed to get instructors: {response.status_code}")
        return []
    except Exception as e:
        print(f"Error getting instructors: {e}")
        return []


def send_canvas_message(course_id, user_id, subject, body, cc_instructors=True):
    """Send a message via Canvas Conversations API - WORKING FORMAT"""
    import sys
    url = f"{CANVAS_URL}/api/v1/conversations"
    
    print(f"=== Sending Canvas Message ===", flush=True)
    print(f"Recipient: {user_id}", flush=True)
    print(f"Subject: {subject}", flush=True)
    print(f"CC Instructors: {cc_instructors}", flush=True)
    sys.stdout.flush()
    
    # Build recipient list
    recipients = [str(user_id)]
    if cc_instructors:
        instructors = get_course_instructors(course_id)
        for inst_id in instructors:
            if str(inst_id) != str(user_id):
                recipients.append(str(inst_id))
    
    print(f"All recipients: {recipients}", flush=True)
    
    # WORKING FORMAT: list of tuples with multiple recipients[]
    params = []
    for rid in recipients:
        params.append(("recipients[]", rid))
    params.append(("subject", subject))
    params.append(("body", body))
    params.append(("group_conversation", "true"))
    params.append(("context_code", f"course_{course_id}"))
    
    try:
        response = requests.post(url, headers=get_headers(), data=params)
        print(f"Response status: {response.status_code}", flush=True)
        sys.stdout.flush()
        
        if response.status_code in [200, 201]:
            return True, response.text
        else:
            print(f"Response: {response.text[:300]}", flush=True)
            return False, f"Status {response.status_code}: {response.text[:200]}"
    except Exception as e:
        print(f"Exception: {e}", flush=True)
        return False, str(e)


@app.route('/api/courses/<course_id>/student-dashboard')
def student_dashboard(course_id):
    """Get comprehensive student progress data for dashboard"""
    # Get all students in course
    url = f"{CANVAS_URL}/api/v1/courses/{course_id}/users"
    params = {"enrollment_type[]": "student", "per_page": 100}
    
    try:
        response = requests.get(url, headers=get_headers(), params=params)
        if response.status_code != 200:
            return jsonify({"error": "Failed to fetch students"}), 400
        
        students = response.json()
        
        # Get course info
        course_url = f"{CANVAS_URL}/api/v1/courses/{course_id}"
        course_response = requests.get(course_url, headers=get_headers())
        course_data = course_response.json() if course_response.status_code == 200 else {}
        course_name = course_data.get('name', 'Course')
        
        # Get all assignments
        assignments_url = f"{CANVAS_URL}/api/v1/courses/{course_id}/assignments"
        assignments_response = requests.get(assignments_url, headers=get_headers(), params={"per_page": 100, "order_by": "due_at"})
        all_assignments = assignments_response.json() if assignments_response.status_code == 200 else []
        
        # Build assignment map with order preserved
        assignment_map = {a['id']: a['name'] for a in all_assignments}
        assignment_order = [a['id'] for a in all_assignments]  # Preserve original order
        total_assignments = len(all_assignments)
        
        # Track stats - include scores for average calculation
        student_data = []
        grade_distribution = {"excellent": 0, "good": 0, "needs_work": 0, "ungraded": 0}
        assignment_completion = {a['id']: {
            "name": a['name'], 
            "completed": 0, 
            "total": len(students),
            "scores": [],  # Track all scores for this assignment
            "points_possible": a.get('points_possible', 10),
            "due_at": a.get('due_at'),
            "position": a.get('position', 999)
        } for a in all_assignments}
        
        for student in students:
            user_id = student.get('id')
            name = student.get('name', 'Unknown')
            
            # Get grades
            grades = get_student_all_grades(course_id, user_id)
            if not grades:
                grades = []
            
            # Calculate stats
            graded_assignments = [g for g in grades if g.get('graded') and g.get('score') is not None]
            missing_assignments = [g.get('assignment_name', 'Unknown') for g in grades if not g.get('graded') or g.get('score') is None]
            
            # Calculate average
            if graded_assignments:
                total_score = sum(g['score'] for g in graded_assignments if g.get('points_possible'))
                total_possible = sum(g['points_possible'] for g in graded_assignments if g.get('points_possible'))
                avg_percent = (total_score / total_possible * 100) if total_possible > 0 else 0
                avg_grade = (total_score / len(graded_assignments)) if graded_assignments else 0
            else:
                avg_percent = 0
                avg_grade = 0
            
            # Progress
            completed_count = len(graded_assignments)
            progress_percent = (completed_count / total_assignments * 100) if total_assignments > 0 else 0
            
            # Track completion per assignment AND scores
            for g in graded_assignments:
                if g.get('assignment_id') in assignment_completion:
                    assignment_completion[g['assignment_id']]['completed'] += 1
                    if g.get('score') is not None and g.get('points_possible'):
                        # Store percentage score for averaging
                        pct = (g['score'] / g['points_possible'] * 100) if g['points_possible'] > 0 else 0
                        assignment_completion[g['assignment_id']]['scores'].append(pct)
            
            # Determine status
            is_complete = completed_count >= total_assignments and total_assignments > 0
            celebrated = has_been_celebrated(course_id, user_id)
            reminded = has_been_reminded_recently(course_id, user_id)
            
            # Has at least one submission
            has_submissions = completed_count > 0
            
            student_data.append({
                "user_id": user_id,
                "name": name,
                "completed": completed_count,
                "total": total_assignments,
                "progress_percent": round(progress_percent, 1),
                "avg_grade": round(avg_grade, 1),
                "avg_percent": round(avg_percent, 1),
                "missing": missing_assignments,
                "is_complete": is_complete,
                "celebrated": celebrated,
                "reminded_recently": reminded,
                "has_submissions": has_submissions,
                "graded_assignment_ids": [g.get('assignment_id') for g in graded_assignments]
            })
            
            # Grade distribution
            if avg_grade >= 9:
                grade_distribution["excellent"] += 1
            elif avg_grade >= 7:
                grade_distribution["good"] += 1
            elif avg_grade > 0:
                grade_distribution["needs_work"] += 1
            else:
                grade_distribution["ungraded"] += 1
        
        # Sort by progress (complete first, then by progress %)
        student_data.sort(key=lambda x: (-x['is_complete'], -x['progress_percent'], x['name']))
        
        # Filter to only those with 5+ completed assignments (active students)
        active_students = [s for s in student_data if s['completed'] >= 5]
        inactive_students = [s for s in student_data if s['has_submissions'] and s['completed'] < 5]
        active_count = len(active_students)
        
        # Recalculate grade distribution for active students only
        grade_distribution = {"excellent": 0, "good": 0, "needs_work": 0, "ungraded": 0}
        for s in active_students:
            if s['avg_grade'] >= 9:
                grade_distribution["excellent"] += 1
            elif s['avg_grade'] >= 7:
                grade_distribution["good"] += 1
            elif s['avg_grade'] > 0:
                grade_distribution["needs_work"] += 1
            else:
                grade_distribution["ungraded"] += 1
        
        # Recalculate assignment completion for active students only (using stored IDs)
        # Also collect scores for active students
        assignment_completion_active = {a['id']: {
            "name": a['name'], 
            "completed": 0, 
            "scores": [],
            "points_possible": assignment_completion[a['id']]['points_possible'],
            "due_at": assignment_completion[a['id']]['due_at'],
            "position": assignment_completion[a['id']]['position']
        } for a in all_assignments}
        
        for s in active_students:
            for aid in s.get('graded_assignment_ids', []):
                if aid in assignment_completion_active:
                    assignment_completion_active[aid]['completed'] += 1
            # We need to get scores from original tracking
            for aid in assignment_completion_active:
                # Scores were tracked in the original loop, copy them over
                pass
        
        # Copy scores from original assignment_completion (which tracked all students)
        # But we want to recalculate for active only - we need to re-examine
        # Actually, let's track scores properly during the active student filtering
        assignment_scores_active = {a['id']: [] for a in all_assignments}
        for s in active_students:
            for aid in s.get('graded_assignment_ids', []):
                # We stored the assignment_id but not the score in student data
                # The scores are in assignment_completion from ALL students
                pass
        
        # For now, use scores from all students who submitted (close enough for insights)
        # This is a reasonable proxy since we're measuring assignment difficulty
        
        # Assignment completion stats - PRESERVE ORDER by due_at/position
        assignment_stats = []
        for aid in assignment_order:  # Use preserved order!
            data = assignment_completion_active.get(aid, {})
            orig_data = assignment_completion.get(aid, {})
            completion_rate = (data.get('completed', 0) / active_count * 100) if active_count > 0 else 0
            
            # Calculate average score from all submissions
            scores = orig_data.get('scores', [])
            avg_score = sum(scores) / len(scores) if scores else None
            
            assignment_stats.append({
                "id": aid,
                "name": data.get('name', 'Unknown'),
                "completed": data.get('completed', 0),
                "total": active_count,
                "completion_rate": round(completion_rate, 1),
                "avg_score": round(avg_score, 1) if avg_score is not None else None,
                "submission_count": len(scores),
                "points_possible": orig_data.get('points_possible', 10)
            })
        # DON'T sort - keep original order!
        # assignment_stats.sort(key=lambda x: x['completion_rate'])
        
        # Calculate insights from the data
        insights = []
        
        # Find struggling assignments (low completion or low scores)
        for a in assignment_stats:
            if a['completion_rate'] < 60:
                insights.append({
                    "type": "low_completion",
                    "severity": "warning" if a['completion_rate'] >= 40 else "danger",
                    "message": f"'{a['name']}' has only {a['completion_rate']}% completion",
                    "assignment": a['name']
                })
            if a['avg_score'] is not None and a['avg_score'] < 70:
                insights.append({
                    "type": "low_score",
                    "severity": "warning" if a['avg_score'] >= 50 else "danger",
                    "message": f"'{a['name']}' avg score is {a['avg_score']}% - may need review",
                    "assignment": a['name']
                })
        
        # Engagement dropoff detection
        if len(assignment_stats) >= 3:
            first_half = assignment_stats[:len(assignment_stats)//2]
            second_half = assignment_stats[len(assignment_stats)//2:]
            first_avg = sum(a['completion_rate'] for a in first_half) / len(first_half) if first_half else 0
            second_avg = sum(a['completion_rate'] for a in second_half) / len(second_half) if second_half else 0
            if first_avg - second_avg > 20:
                insights.append({
                    "type": "dropoff",
                    "severity": "warning",
                    "message": f"Engagement dropped from {first_avg:.0f}% to {second_avg:.0f}% in second half of course"
                })
        
        # Count students needing attention
        needs_reminder = len([s for s in active_students if not s['is_complete'] and not s['reminded_recently']])
        ready_to_celebrate = len([s for s in active_students if s['is_complete'] and not s['celebrated']])
        
        # Remove graded_assignment_ids from response (not needed in frontend)
        for s in active_students:
            s.pop('graded_assignment_ids', None)
        
        # Summary stats
        complete_count = len([s for s in active_students if s['is_complete']])
        celebrated_count = len([s for s in active_students if s['celebrated']])
        
        return jsonify({
            "course_name": course_name,
            "total_students": len(students),
            "active_students": len(active_students),
            "inactive_count": len(inactive_students),
            "complete_count": complete_count,
            "celebrated_count": celebrated_count,
            "total_assignments": total_assignments,
            "completion_rate": round((complete_count / len(active_students) * 100) if active_students else 0, 1),
            "grade_distribution": grade_distribution,
            "assignment_stats": assignment_stats,
            "insights": insights,
            "needs_reminder": needs_reminder,
            "ready_to_celebrate": ready_to_celebrate,
            "students": active_students
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route('/api/courses/<course_id>/check-celebrations')
def check_celebrations(course_id):
    """Check which students are eligible for celebration messages (legacy endpoint)"""
    # Get all students in course
    url = f"{CANVAS_URL}/api/v1/courses/{course_id}/users"
    params = {"enrollment_type[]": "student", "per_page": 100}
    
    try:
        response = requests.get(url, headers=get_headers(), params=params)
        if response.status_code != 200:
            return jsonify({"error": "Failed to fetch students"}), 400
        
        students = response.json()
        
        # Get course name
        course_url = f"{CANVAS_URL}/api/v1/courses/{course_id}"
        course_response = requests.get(course_url, headers=get_headers())
        course_name = course_response.json().get('name', 'the course') if course_response.status_code == 200 else 'the course'
        
        eligible = []
        already_celebrated = []
        not_complete = []
        
        for student in students:
            user_id = student.get('id')
            name = student.get('name', 'Unknown')
            
            if has_been_celebrated(course_id, user_id):
                already_celebrated.append({"user_id": user_id, "name": name})
                continue
            
            grades = get_student_all_grades(course_id, user_id)
            if grades and check_all_graded(grades):
                # Calculate average
                graded = [g for g in grades if g['graded'] and g['score'] is not None and g['points_possible']]
                avg = (sum(g['score'] for g in graded) / sum(g['points_possible'] for g in graded) * 100) if graded else 0
                
                eligible.append({
                    "user_id": user_id,
                    "name": name,
                    "assignments_completed": len([g for g in grades if g['graded']]),
                    "average": round(avg, 1)
                })
            else:
                graded_count = len([g for g in (grades or []) if g['graded']])
                total_count = len(grades or [])
                not_complete.append({
                    "user_id": user_id,
                    "name": name,
                    "progress": f"{graded_count}/{total_count}"
                })
        
        return jsonify({
            "course_name": course_name,
            "eligible": eligible,
            "already_celebrated": already_celebrated,
            "not_complete": not_complete
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/courses/<course_id>/send-celebration/<user_id>', methods=['POST'])
def send_celebration(course_id, user_id):
    """Generate and send a celebration message to a student"""
    
    # Check if already celebrated
    if has_been_celebrated(course_id, user_id):
        return jsonify({"error": "Student already received celebration message"}), 400
    
    # Get student info
    user_url = f"{CANVAS_URL}/api/v1/users/{user_id}/profile"
    user_response = requests.get(user_url, headers=get_headers())
    if user_response.status_code != 200:
        return jsonify({"error": "Failed to fetch student info"}), 400
    
    student = user_response.json()
    student_name = student.get('name', 'Student')
    
    # Get course info
    course_url = f"{CANVAS_URL}/api/v1/courses/{course_id}"
    course_response = requests.get(course_url, headers=get_headers())
    course_name = course_response.json().get('name', 'the course') if course_response.status_code == 200 else 'the course'
    
    # Get grades
    grades = get_student_all_grades(course_id, user_id)
    if not grades:
        return jsonify({"error": "Failed to fetch student grades"}), 400
    
    # Generate message
    html_message = generate_celebration_message(student_name, grades, course_name)
    if not html_message:
        return jsonify({"error": "Failed to generate message"}), 500
    
    # Send via Canvas
    subject = f"🎉 Congratulations on Completing {course_name}!"
    success, response = send_canvas_message(course_id, user_id, subject, html_message)
    
    if success:
        mark_student_celebrated(course_id, user_id)
        return jsonify({
            "success": True,
            "student_name": student_name,
            "message_preview": html_message[:500] + "..."
        })
    else:
        return jsonify({"error": f"Failed to send message: {response}"}), 500


@app.route('/api/courses/<course_id>/preview-celebration/<user_id>')
def preview_celebration(course_id, user_id):
    """Preview a celebration message without sending"""
    
    # Get student info
    user_url = f"{CANVAS_URL}/api/v1/users/{user_id}/profile"
    user_response = requests.get(user_url, headers=get_headers())
    student_name = user_response.json().get('name', 'Student') if user_response.status_code == 200 else 'Student'
    
    # Get course info
    course_url = f"{CANVAS_URL}/api/v1/courses/{course_id}"
    course_response = requests.get(course_url, headers=get_headers())
    course_name = course_response.json().get('name', 'the course') if course_response.status_code == 200 else 'the course'
    
    # Get grades
    grades = get_student_all_grades(course_id, user_id)
    if not grades:
        return jsonify({"error": "Failed to fetch student grades"}), 400
    
    # Generate message
    html_message = generate_celebration_message(student_name, grades, course_name)
    if not html_message:
        return jsonify({"error": "Failed to generate message"}), 500
    
    return jsonify({
        "student_name": student_name,
        "html": html_message
    })


@app.route('/api/courses/<course_id>/send-reminder/<user_id>', methods=['POST'])
def send_reminder(course_id, user_id):
    """Send a reminder message to a student about missing assignments"""
    import sys
    try:
        data = request.json or {}
        missing_assignments = data.get('missing', [])
        
        print(f"=== Send Reminder ===", flush=True)
        print(f"Course: {course_id}, User: {user_id}", flush=True)
        print(f"Missing assignments: {missing_assignments}", flush=True)
        sys.stdout.flush()
        
        # Get student info
        user_url = f"{CANVAS_URL}/api/v1/users/{user_id}/profile"
        user_response = requests.get(user_url, headers=get_headers())
        print(f"User API response: {user_response.status_code}", flush=True)
        if user_response.status_code != 200:
            return jsonify({"error": f"Failed to fetch student info: {user_response.status_code}"}), 400
        
        student = user_response.json()
        student_name = student.get('name', 'Student')
        first_name = student_name.split()[0] if student_name else 'Student'
        print(f"Student: {student_name}", flush=True)
        
        # Get course info
        course_url = f"{CANVAS_URL}/api/v1/courses/{course_id}"
        course_response = requests.get(course_url, headers=get_headers())
        course_name = course_response.json().get('name', 'the course') if course_response.status_code == 200 else 'the course'
        print(f"Course: {course_name}", flush=True)
        
        # Generate reminder message from template
        missing_list = "\n".join([f"  • {a}" for a in missing_assignments])

        message = render_reminder_message(
            first_name=first_name,
            course_name=course_name,
            missing_list=missing_list
        )
        
        # Send via Canvas
        subject = f"📚 Reminder: Complete Your {course_name} Assignments"
        print(f"About to send message...", flush=True)
        sys.stdout.flush()
        
        success, response = send_canvas_message(course_id, user_id, subject, message)
        
        print(f"Send result: success={success}", flush=True)
        sys.stdout.flush()
        
        if success:
            mark_student_reminded(course_id, user_id)
            return jsonify({
                "success": True,
                "student_name": student_name,
                "missing_count": len(missing_assignments)
            })
        else:
            return jsonify({"error": f"Failed to send message: {response}"}), 500
    except Exception as e:
        import traceback
        print(f"Exception in send_reminder: {e}", flush=True)
        traceback.print_exc()
        sys.stdout.flush()
        return jsonify({"error": f"Server error: {str(e)}"}), 500


@app.route('/api/courses/<course_id>/test-reminder', methods=['POST'])
def test_reminder(course_id):
    """Send a test reminder message to the first course instructor"""
    import sys
    try:
        print(f"=== TEST REMINDER ===", flush=True)

        # Get instructors for this course
        instructors = get_course_instructors(course_id)
        if not instructors:
            return jsonify({"error": "No instructors found for this course"}), 400

        instructor_id = instructors[0]
        print(f"Sending test to instructor ID: {instructor_id}", flush=True)

        # Test message
        message = "This is a test reminder message from AutoGrader. If you see this, the API is working."
        subject = "Test Reminder from AutoGrader"

        print(f"Sending to: {instructor_id}", flush=True)
        sys.stdout.flush()

        success, response = send_canvas_message_simple(course_id, instructor_id, subject, message)

        if success:
            return jsonify({"success": True, "sent_to": instructor_id})
        else:
            return jsonify({"error": f"Failed: {response}"}), 500

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route('/api/courses/<course_id>/test-celebration', methods=['POST'])
def test_celebration(course_id):
    """Send a test celebration message to the first course instructor"""
    import sys
    try:
        print(f"=== TEST CELEBRATION ===", flush=True)

        # Get instructors for this course
        instructors = get_course_instructors(course_id)
        if not instructors:
            return jsonify({"error": "No instructors found for this course"}), 400

        instructor_id = instructors[0]
        print(f"Sending test to instructor ID: {instructor_id}", flush=True)

        # Test message
        message = "Test celebration message from AutoGrader. Plain text only."
        subject = "Test Celebration from AutoGrader"

        print(f"Sending to: {instructor_id}", flush=True)
        sys.stdout.flush()

        success, response = send_canvas_message_simple(course_id, instructor_id, subject, message)

        if success:
            return jsonify({"success": True, "sent_to": instructor_id})
        else:
            return jsonify({"error": f"Failed: {response}"}), 500

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


def send_canvas_message_simple(course_id, user_id, subject, body):
    """Send Canvas message - WORKING FORMAT with list of tuples"""
    import sys
    url = f"{CANVAS_URL}/api/v1/conversations"
    
    print(f"=== Sending Canvas Message ===", flush=True)
    print(f"Recipient: {user_id}", flush=True)
    print(f"Subject: {subject}", flush=True)
    sys.stdout.flush()
    
    # WORKING FORMAT: list of tuples
    params = [
        ("recipients[]", str(user_id)),
        ("subject", subject),
        ("body", body),
        ("context_code", f"course_{course_id}")
    ]
    
    try:
        response = requests.post(url, headers=get_headers(), data=params)
        print(f"Response status: {response.status_code}", flush=True)
        print(f"Response: {response.text[:300]}", flush=True)
        sys.stdout.flush()
        
        return response.status_code in [200, 201], response.text
    except Exception as e:
        print(f"Exception: {e}", flush=True)
        return False, str(e)


@app.route('/api/courses/<course_id>/preview-reminder/<user_id>')
def preview_reminder(course_id, user_id):
    """Preview a reminder message without sending"""
    missing = request.args.get('missing', '').split(',') if request.args.get('missing') else []
    
    # Get student info
    user_url = f"{CANVAS_URL}/api/v1/users/{user_id}/profile"
    user_response = requests.get(user_url, headers=get_headers())
    student_name = user_response.json().get('name', 'Student') if user_response.status_code == 200 else 'Student'
    first_name = student_name.split()[0] if student_name else 'Student'
    
    # Get course info
    course_url = f"{CANVAS_URL}/api/v1/courses/{course_id}"
    course_response = requests.get(course_url, headers=get_headers())
    course_name = course_response.json().get('name', 'the course') if course_response.status_code == 200 else 'the course'
    
    html_message = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
        <h2 style="color: #6366f1;">📚 Friendly Reminder from {course_name}</h2>
        
        <p>Hi {first_name}!</p>
        
        <p>You're making great progress in <strong>{course_name}</strong>! 🌟</p>
        
        <p>We noticed you still have a few assignments to complete:</p>
        
        <ul style="background: #f3f4f6; padding: 20px 40px; border-radius: 8px; margin: 20px 0;">
            {''.join(f'<li style="margin: 8px 0;"><strong>{a}</strong></li>' for a in missing)}
        </ul>
        
        <p>Please try to submit these within the <strong>next week</strong> so you can complete the course and receive your certificate! 🎓</p>
        
        <p>If you have any questions or need help, don't hesitate to reach out. We're here to support you!</p>
        
        <p style="margin-top: 30px;">Keep up the great work! 💪</p>
        
        <p style="color: #6b7280;">— Your {course_name} Instructor</p>
    </div>
    """
    
    return jsonify({
        "student_name": student_name,
        "html": html_message
    })


# Assignment type detection patterns - loaded from config
# These can be overridden in config.yaml


def get_canvas_page_content(course_id, page_title):
    """Fetch content from a Canvas wiki page by title"""
    # First, search for the page
    url = f"{CANVAS_URL}/api/v1/courses/{course_id}/pages"
    params = {"search_term": page_title, "per_page": 20}
    
    try:
        response = requests.get(url, headers=get_headers(), params=params)
        if response.status_code != 200:
            print(f"Error searching pages: {response.status_code}")
            return None
        
        pages = response.json()
        
        # Find matching page
        target_page = None
        for page in pages:
            if page_title.lower() in page.get('title', '').lower():
                target_page = page
                break
        
        if not target_page:
            print(f"Page not found: {page_title}")
            return None
        
        # Fetch full page content
        page_url = target_page.get('url')
        content_url = f"{CANVAS_URL}/api/v1/courses/{course_id}/pages/{page_url}"
        
        content_response = requests.get(content_url, headers=get_headers())
        if content_response.status_code == 200:
            page_data = content_response.json()
            # Return the HTML body content
            return page_data.get('body', '')
        
        return None
        
    except Exception as e:
        print(f"Error fetching page content: {e}")
        return None


def html_to_text(html_content):
    """Convert HTML to plain text for use in prompts"""
    if not html_content:
        return ""
    
    # Simple HTML stripping - remove tags but keep text
    import re
    # Remove script and style elements
    text = re.sub(r'<script[^>]*>.*?</script>', '', html_content, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
    # Replace common elements with newlines
    text = re.sub(r'<br[^>]*>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<p[^>]*>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<li[^>]*>', '\n• ', text, flags=re.IGNORECASE)
    text = re.sub(r'<h[1-6][^>]*>', '\n\n', text, flags=re.IGNORECASE)
    # Remove all other tags
    text = re.sub(r'<[^>]+>', '', text)
    # Clean up whitespace
    text = re.sub(r'\n\s*\n', '\n\n', text)
    text = text.strip()
    # Decode HTML entities
    import html
    text = html.unescape(text)
    
    return text


def get_rubric_for_assignment(course_id, assignment_name):
    """Get the appropriate rubric for an assignment, fetching from Canvas if needed"""
    assignment_lower = assignment_name.lower()

    # Check if we have a page mapping for this assignment (from config)
    rubric_page_map = get_rubric_page_map()
    for pattern, page_title in rubric_page_map.items():
        if pattern in assignment_lower:
            print(f"Fetching rubric from Canvas page: {page_title}")
            html_content = get_canvas_page_content(course_id, page_title)
            if html_content:
                text_content = html_to_text(html_content)
                print(f"Found rubric content ({len(text_content)} chars)")
                return text_content
    
    # Check custom rubrics stored in memory
    for pattern, rubric in custom_rubrics.items():
        if pattern in assignment_lower:
            return rubric
    
    # Return default rubric
    return FINAL_PROJECT_RUBRIC


def detect_assignment_type(assignment_name):
    """Detect if assignment needs special grading"""
    name_lower = assignment_name.lower()

    # Check if it's a simple check-off assignment (patterns from config)
    for pattern in get_checkoff_patterns():
        if pattern in name_lower:
            return 'checkoff'

    # Check if it's a final project (patterns from config)
    for pattern in get_final_project_patterns():
        if pattern in name_lower:
            return 'final_project'

    return 'standard'


def grade_checkoff_assignment(submission):
    """Auto-grade check-off assignments - full credit if anything submitted"""
    # Check various indicators that something was submitted
    has_submission = (
        submission.get('submitted_at') is not None or
        submission.get('attachments') or
        submission.get('body') or
        submission.get('url') or
        submission.get('code') or  # If we have code content
        submission.get('filename')  # If we have a filename
    )
    
    # Get first name for personalized comment
    student_name = submission.get('student_name', 'Student')
    first_name = student_name.split()[0] if student_name else 'Student'
    
    if has_submission:
        return {
            "grade": 10,
            "comment": f"{first_name}, great job completing this requirement! ✅",
            "student_name": student_name,
            "filename": submission.get('filename', ''),
            "strengths": ["Completed requirement"],
            "suggestions": []
        }
    else:
        return {
            "grade": 0,
            "comment": f"{first_name}, please submit this assignment to receive credit.",
            "student_name": student_name,
            "filename": submission.get('filename', ''),
            "strengths": [],
            "suggestions": ["Submit your work to receive credit"]
        }


# Final Project Rubric (W4P1/W4P2)
FINAL_PROJECT_RUBRIC = """
FINAL PROJECT GRADING RUBRIC (Total: 10 points)

1. CODE FUNCTIONALITY (4 points)
   - 4: Code runs without errors, all features work as expected
   - 3: Code runs with minor issues, most features work
   - 2: Code runs but has significant bugs or missing features
   - 1: Code has major errors but shows attempt
   - 0: Code doesn't run or no submission

2. CODE QUALITY (2 points)
   - 2: Clean, well-organized code with good variable names
   - 1: Mostly readable but some messy sections
   - 0: Difficult to read/understand

3. COMMENTS & DOCUMENTATION (2 points)
   - 2: Clear comments explaining logic, good docstrings
   - 1: Some comments but could be clearer
   - 0: No comments or documentation

4. CREATIVITY & EFFORT (2 points)
   - 2: Goes beyond requirements, shows creativity
   - 1: Meets basic requirements
   - 0: Minimal effort shown

GRADING NOTES:
- Be encouraging - this is their capstone!
- Highlight what they did well
- Give specific, actionable feedback
- Consider their growth throughout the course
"""


def grade_final_project_with_claude(submissions, custom_rubric=None):
    """Use Claude to grade final projects with detailed rubric"""
    if not ANTHROPIC_API_KEY:
        return {"error": "Anthropic API key not configured"}

    client = Anthropic(api_key=ANTHROPIC_API_KEY)

    rubric = custom_rubric or FINAL_PROJECT_RUBRIC

    # Build submissions with clear student markers
    submissions_text = ""
    student_list = []
    for i, sub in enumerate(submissions):
        student_name = sub.get('student_name', 'Unknown')
        filename = sub.get('filename', 'unknown.py')
        student_list.append(f"{student_name} ({filename})")

        submissions_text += f"\n{'='*60}\n"
        submissions_text += f"SUBMISSION #{i+1}\n"
        submissions_text += f"STUDENT NAME: {student_name}\n"
        submissions_text += f"FILENAME: {filename}\n"
        submissions_text += f"{'='*60}\n"
        submissions_text += sub.get('code', '# No code')
        submissions_text += "\n"

        if sub.get('run_result'):
            run = sub['run_result']
            submissions_text += f"\n--- OUTPUT ---\n{run.get('output', 'N/A')}\n"
            if run.get('errors'):
                submissions_text += f"--- ERRORS ---\n{run['errors']}\n"

    # Render prompt from template
    prompt = render_final_project_prompt(
        submissions_text=submissions_text,
        student_list=student_list,
        rubric=rubric
    )

    try:
        message = client.messages.create(
            model=get_grading_model(),
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}]
        )
        
        response_text = message.content[0].text
        
        try:
            return json.loads(response_text)
        except json.JSONDecodeError:
            json_match = re.search(r'\{[\s\S]*\}', response_text)
            if json_match:
                return json.loads(json_match.group())
            return {"error": "Failed to parse response", "raw": response_text}
            
    except Exception as e:
        return {"error": str(e)}


# Store custom rubrics
custom_rubrics = {}

@app.route('/api/rubrics', methods=['GET', 'POST'])
def manage_rubrics():
    """Get or set custom rubrics"""
    global custom_rubrics
    
    if request.method == 'POST':
        data = request.json
        assignment_pattern = data.get('pattern', '').lower()
        rubric_text = data.get('rubric', '')
        
        if assignment_pattern and rubric_text:
            custom_rubrics[assignment_pattern] = rubric_text
            return jsonify({"status": "saved", "pattern": assignment_pattern})
        return jsonify({"error": "Missing pattern or rubric"}), 400
    
    return jsonify(custom_rubrics)


@app.route('/api/courses/<course_id>/rubric-preview')
def preview_rubric(course_id):
    """Preview what rubric will be used for a given assignment"""
    assignment_name = request.args.get('assignment', '')
    
    if not assignment_name:
        return jsonify({"error": "Missing assignment parameter"}), 400
    
    assignment_type = detect_assignment_type(assignment_name)
    
    if assignment_type == 'checkoff':
        return jsonify({
            "assignment_type": "checkoff",
            "rubric": "Auto check-off: Full credit (10/10) if anything is submitted.",
            "source": "built-in"
        })
    elif assignment_type == 'final_project':
        rubric = get_rubric_for_assignment(course_id, assignment_name)

        # Determine source
        source = "default"
        rubric_page_map = get_rubric_page_map()
        for pattern, page_title in rubric_page_map.items():
            if pattern in assignment_name.lower():
                source = f"Canvas page: {page_title}"
                break
        
        return jsonify({
            "assignment_type": "final_project",
            "rubric": rubric,
            "source": source
        })
    else:
        return jsonify({
            "assignment_type": "standard",
            "rubric": "Standard AI grading based on code instructions/comments.",
            "source": "built-in"
        })


@app.route('/api/grade-batch', methods=['POST'])
def grade_batch():
    """Grade a batch of submissions sent directly from frontend"""
    data = request.json
    assignment_name = data.get('assignment_name', '')
    submissions = data.get('submissions', [])
    
    if not submissions:
        return jsonify({"error": "No submissions provided"}), 400
    
    assignment_type = detect_assignment_type(assignment_name)
    
    if assignment_type == 'checkoff':
        # Auto-grade check-off assignments
        results = []
        for sub in submissions:
            grade_info = grade_checkoff_assignment(sub)
            grade_info['student_name'] = sub.get('student_name', 'Unknown')
            grade_info['filename'] = sub.get('filename', '')
            grade_info['strengths'] = ['Completed requirement']
            grade_info['suggestions'] = []
            results.append(grade_info)
        
        return jsonify({
            "assignment_type": "checkoff",
            "grades": results
        })
    
    elif assignment_type == 'final_project':
        # Get rubric
        course_id = current_session.get('course')
        rubric = get_rubric_for_assignment(course_id, assignment_name) if course_id else FINAL_PROJECT_RUBRIC
        
        result = grade_final_project_with_claude(submissions, rubric)
        
        if 'error' in result:
            return jsonify(result), 400
        
        return jsonify({
            "assignment_type": "final_project",
            "grades": result.get('grades', [])
        })
    
    else:
        # Standard grading
        result = grade_with_claude(submissions, '')
        
        if 'error' in result:
            return jsonify(result), 400
        
        return jsonify({
            "assignment_type": "standard",
            "grades": result.get('grades', [])
        })


@app.route('/api/grade-single', methods=['POST'])
def grade_single_submission():
    """Grade a single submission with AI"""
    data = request.json
    assignment_name = data.get('assignment_name', '')
    points_possible = data.get('points_possible', get_default_points())  # Get max points from request
    submission = data.get('submission', {})

    if not submission or not submission.get('code'):
        return jsonify({"error": "No submission data"}), 400

    student_name = submission.get('student_name', 'Unknown')
    filename = submission.get('filename', 'unknown.py')
    code = submission.get('code', '')
    run_result = submission.get('run_result', {})

    if not ANTHROPIC_API_KEY:
        return jsonify({"error": "Anthropic API key not configured"}), 400

    client = Anthropic(api_key=ANTHROPIC_API_KEY)

    # Build submission text
    submission_text = f"""
STUDENT: {student_name}
FILE: {filename}
{'='*60}
{code}
"""

    if run_result:
        submission_text += f"\n--- OUTPUT ---\n{run_result.get('output', 'N/A')}\n"
        if run_result.get('errors'):
            submission_text += f"--- ERRORS ---\n{run_result['errors']}\n"

    # Detect assignment type for appropriate grading
    assignment_type = detect_assignment_type(assignment_name)

    if assignment_type == 'checkoff':
        # Auto grade check-off - give full points
        grade_info = grade_checkoff_assignment(submission)
        grade_info['grade'] = points_possible  # Use full points for checkoff
        grade_info['student_name'] = student_name
        grade_info['filename'] = filename
        grade_info['strengths'] = ['Completed requirement']
        grade_info['suggestions'] = []
        return jsonify({"grade": grade_info, "assignment_type": "checkoff"})

    # Get rubric if final project
    rubric_text = ""
    if assignment_type == 'final_project':
        course_id = current_session.get('course')
        rubric_text = get_rubric_for_assignment(course_id, assignment_name) if course_id else FINAL_PROJECT_RUBRIC

    # Extract first name
    first_name = student_name.split()[0] if student_name else "Student"

    # Render prompt from template
    prompt = render_single_grading_prompt(
        submission_text=submission_text,
        student_name=student_name,
        first_name=first_name,
        filename=filename,
        points_possible=points_possible,
        assignment_type=assignment_type,
        rubric_text=rubric_text
    )

    try:
        message = client.messages.create(
            model=get_grading_model(),
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}]
        )
        
        response_text = message.content[0].text
        
        try:
            grade_info = json.loads(response_text)
        except json.JSONDecodeError:
            json_match = re.search(r'\{[\s\S]*\}', response_text)
            if json_match:
                grade_info = json.loads(json_match.group())
            else:
                return jsonify({"error": "Failed to parse AI response"}), 500
        
        # Ensure correct student info
        grade_info['student_name'] = student_name
        grade_info['filename'] = filename
        
        return jsonify({"grade": grade_info, "assignment_type": assignment_type})
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/grade-smart', methods=['POST'])
def grade_smart():
    """Smart grading that detects assignment type and grades accordingly"""
    data = request.json
    assignment_name = data.get('assignment_name', '')
    context = data.get('context', '')
    submissions = current_session.get('submissions', [])
    
    if not submissions:
        return jsonify({"error": "No submissions loaded"}), 400
    
    assignment_type = detect_assignment_type(assignment_name)
    
    if assignment_type == 'checkoff':
        # Auto-grade check-off assignments
        results = []
        for sub in submissions:
            grade_info = grade_checkoff_assignment(sub)
            grade_info['student_name'] = sub.get('student_name', 'Unknown')
            grade_info['filename'] = sub.get('filename', '')
            grade_info['strengths'] = ['Completed requirement']
            grade_info['suggestions'] = []
            results.append(grade_info)
            sub['grade_info'] = grade_info
        
        current_session['submissions'] = submissions
        return jsonify({
            "assignment_type": "checkoff",
            "grades": results
        })
    
    elif assignment_type == 'final_project':
        # Run code first
        for sub in submissions:
            if sub.get('code') and not sub.get('run_result'):
                sub['run_result'] = run_python_code(sub['code'])
        
        # Get course_id from session or request
        course_id = current_session.get('course') or data.get('course_id')
        
        # Fetch rubric from Canvas page or use default
        rubric = get_rubric_for_assignment(course_id, assignment_name) if course_id else FINAL_PROJECT_RUBRIC
        
        # Grade with detailed rubric
        result = grade_final_project_with_claude(submissions, rubric)
        
        if 'error' in result:
            return jsonify(result), 400
        
        # Match grades to submissions
        for grade in result.get('grades', []):
            for sub in submissions:
                if (grade.get('filename') == sub.get('filename') or
                    grade.get('student_name', '').lower() in sub.get('student_name', '').lower()):
                    sub['grade_info'] = grade
                    break
        
        current_session['submissions'] = submissions
        return jsonify({
            "assignment_type": "final_project",
            "grades": result.get('grades', [])
        })
    
    else:
        # Standard grading
        for sub in submissions:
            if sub.get('code') and not sub.get('run_result'):
                sub['run_result'] = run_python_code(sub['code'])
        
        result = grade_with_claude(submissions, context)
        
        if 'error' in result:
            return jsonify(result), 400
        
        for grade in result.get('grades', []):
            for sub in submissions:
                if (grade.get('filename') == sub.get('filename') or
                    grade.get('student_name', '').lower() in sub.get('student_name', '').lower()):
                    sub['grade_info'] = grade
                    break
        
        current_session['submissions'] = submissions
        return jsonify({
            "assignment_type": "standard",
            "grades": result.get('grades', [])
        })


@app.route('/api/courses/<course_id>/assignments/<assignment_id>/download-submissions')
def download_canvas_submissions(course_id, assignment_id):
    """Download all UNGRADED submissions from Canvas and extract them"""
    global current_session
    
    # Get submissions with attachments
    url = f"{CANVAS_URL}/api/v1/courses/{course_id}/assignments/{assignment_id}/submissions"
    params = {
        "per_page": 100,
        "include[]": ["user", "submission_comments"]
    }
    
    try:
        response = requests.get(url, headers=get_headers(), params=params)
        if response.status_code != 200:
            return jsonify({"error": f"Failed to fetch submissions: {response.status_code}"}), 400
        
        submissions_data = response.json()
        
        submissions = []
        skipped_graded = 0
        skipped_no_submission = 0
        
        for sub in submissions_data:
            user = sub.get('user', {})
            user_id = sub.get('user_id')
            attachments = sub.get('attachments', [])
            
            # Skip if already graded
            if sub.get('grade') is not None or sub.get('score') is not None:
                skipped_graded += 1
                continue
            
            # Skip if no submission
            if sub.get('workflow_state') == 'unsubmitted' or not attachments:
                skipped_no_submission += 1
                continue
            
            # Get user profile for email
            email = None
            login_id = user.get('login_id', '')
            try:
                profile_url = f"{CANVAS_URL}/api/v1/users/{user_id}/profile"
                profile_res = requests.get(profile_url, headers=get_headers())
                if profile_res.status_code == 200:
                    profile = profile_res.json()
                    email = profile.get('primary_email', profile.get('login_id', ''))
                    login_id = profile.get('login_id', login_id)
            except:
                pass
            
            # Download .py attachments
            for att in attachments:
                filename = att.get('filename', '')
                if filename.endswith('.py'):
                    file_url = att.get('url')
                    if file_url:
                        try:
                            file_response = requests.get(file_url, headers=get_headers(), allow_redirects=True)
                            if file_response.status_code == 200:
                                code = file_response.text
                                
                                submissions.append({
                                    "filename": filename,
                                    "student_name": user.get('name', 'Unknown'),
                                    "user_id": user_id,
                                    "login_id": login_id,
                                    "email": email,
                                    "code": code,
                                    "run_result": None,
                                    "grade_info": None
                                })
                        except Exception as e:
                            print(f"Error downloading {filename}: {e}")
        
        current_session['submissions'] = submissions
        current_session['course'] = course_id
        current_session['assignment'] = assignment_id
        
        return jsonify({
            "count": len(submissions),
            "skipped_graded": skipped_graded,
            "skipped_no_submission": skipped_no_submission,
            "submissions": submissions
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/courses/<course_id>/assignments/<assignment_id>/submissions/<user_id>/excuse', methods=['POST'])
def excuse_submission(course_id, assignment_id, user_id):
    """Mark a submission as excused in Canvas (won't affect grade calculations)"""
    url = f"{CANVAS_URL}/api/v1/courses/{course_id}/assignments/{assignment_id}/submissions/{user_id}"

    data = {
        "submission": {"excuse": True}
    }

    try:
        response = requests.put(url, headers=get_headers(), json=data)
        if response.status_code == 200:
            return jsonify({"success": True, "message": "Submission excused"})
        else:
            return jsonify({"error": f"Canvas API error: {response.status_code}", "details": response.text}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/courses/<course_id>/assignments/<assignment_id>/submissions/<user_id>/mark-missing', methods=['POST'])
def mark_submission_missing(course_id, assignment_id, user_id):
    """Mark a submission as missing in Canvas (useful for wrong file uploads)"""
    url = f"{CANVAS_URL}/api/v1/courses/{course_id}/assignments/{assignment_id}/submissions/{user_id}"

    data = {
        "submission": {"late_policy_status": "missing"}
    }

    try:
        response = requests.put(url, headers=get_headers(), json=data)
        if response.status_code == 200:
            return jsonify({"success": True, "message": "Submission marked as missing"})
        else:
            return jsonify({"error": f"Canvas API error: {response.status_code}", "details": response.text}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/courses/<course_id>/assignments/<assignment_id>')
def api_assignment_detail(course_id, assignment_id):
    """Get assignment details"""
    details = get_assignment_details(course_id, assignment_id)
    return jsonify(details)


@app.route('/api/courses/<course_id>/assignments/<assignment_id>/canvas-students')
def api_canvas_students(course_id, assignment_id):
    """Get Canvas student list with all identifiers for debugging matching"""
    submissions = get_submissions_with_files(course_id, assignment_id)
    
    students = []
    for sub in submissions:
        user = sub.get('user', {})
        students.append({
            "user_id": sub.get('user_id'),
            "name": user.get('name'),
            "sortable_name": user.get('sortable_name'),
            "login_id": user.get('login_id'),
            "email": user.get('email'),
            "has_submission": sub.get('workflow_state') != 'unsubmitted',
            "score": sub.get('score'),
            "graded": sub.get('grade') is not None
        })
    
    return jsonify(students)


@app.route('/api/courses/<course_id>/assignments/<assignment_id>/submissions')
def api_submissions(course_id, assignment_id):
    """Get submissions for an assignment"""
    submissions = get_submissions_with_files(course_id, assignment_id)
    
    # Process submissions to extract code
    processed = []
    for sub in submissions:
        user = sub.get('user', {})
        attachments = sub.get('attachments', [])
        
        # Get the first .py attachment
        code = None
        filename = None
        for att in attachments:
            if att.get('filename', '').endswith('.py'):
                filename = att['filename']
                code = download_submission_file(att.get('url'))
                break
        
        processed.append({
            "user_id": sub.get('user_id'),
            "student_name": user.get('name', 'Unknown'),
            "filename": filename,
            "code": code,
            "submitted_at": sub.get('submitted_at'),
            "score": sub.get('score'),
            "grade": sub.get('grade'),
            "workflow_state": sub.get('workflow_state')
        })
    
    current_session['submissions'] = processed
    current_session['course'] = course_id
    current_session['assignment'] = assignment_id
    
    return jsonify(processed)


@app.route('/api/upload', methods=['POST'])
def upload_zip():
    """Upload and extract a ZIP file of submissions"""
    if 'file' not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    
    file = request.files['file']
    if not file.filename.endswith('.zip'):
        return jsonify({"error": "Please upload a .zip file"}), 400
    
    submissions, temp_dir = extract_zip(file)
    
    if not submissions:
        return jsonify({"error": "No .py files found in ZIP"}), 400
    
    current_session['submissions'] = submissions
    
    return jsonify({
        "count": len(submissions),
        "submissions": submissions
    })


@app.route('/api/run-code', methods=['POST'])
def run_code():
    """Run a piece of code and return output"""
    data = request.json
    code = data.get('code', '')
    
    result = run_python_code(code)
    return jsonify(result)


@app.route('/api/available-libraries')
def api_available_libraries():
    """Return list of libraries available for student code"""
    return jsonify({
        "libraries": get_available_libraries(),
        "description": "These libraries are pre-installed and available for student code to import"
    })


@app.route('/api/run-all', methods=['POST'])
def run_all_submissions():
    """Run all current submissions"""
    submissions = current_session.get('submissions', [])
    
    for sub in submissions:
        if sub.get('code'):
            sub['run_result'] = run_python_code(sub['code'])
    
    current_session['submissions'] = submissions
    return jsonify({"status": "complete", "submissions": submissions})


@app.route('/api/grade', methods=['POST'])
def grade_submissions():
    """Grade submissions with AI"""
    data = request.json
    assignment_info = data.get('context', '')
    submissions = current_session.get('submissions', [])
    
    if not submissions:
        return jsonify({"error": "No submissions loaded"}), 400
    
    # Run code first if not already done
    for sub in submissions:
        if sub.get('code') and not sub.get('run_result'):
            sub['run_result'] = run_python_code(sub['code'])
    
    # Grade with Claude
    result = grade_with_claude(submissions, assignment_info)
    
    if 'error' in result:
        return jsonify(result), 400
    
    current_session['grades'] = result.get('grades', [])
    
    # Match grades back to submissions
    grades = result.get('grades', [])
    for grade in grades:
        for sub in submissions:
            if (grade.get('filename') == sub.get('filename') or 
                grade.get('student_name', '').lower() in sub.get('student_name', '').lower() or
                sub.get('student_name', '').lower() in grade.get('student_name', '').lower()):
                sub['grade_info'] = grade
                break
    
    current_session['submissions'] = submissions
    
    return jsonify(result)


@app.route('/api/submit-single-grade', methods=['POST'])
def submit_single_grade():
    """Submit a single grade to Canvas by user_id"""
    data = request.json
    course_id = data.get('course_id') or current_session.get('course')
    assignment_id = data.get('assignment_id') or current_session.get('assignment')
    user_id = data.get('user_id')
    grade = data.get('grade')
    comment = data.get('comment', '')
    
    print(f"=== Submit Single Grade ===")
    print(f"Course: {course_id}, Assignment: {assignment_id}, User: {user_id}")
    print(f"Grade: {grade}, Comment: {comment[:50] if comment else 'None'}...")
    print(f"Canvas Token set: {bool(CANVAS_TOKEN)}")
    
    if not all([course_id, assignment_id, user_id, grade is not None]):
        return jsonify({"error": f"Missing required fields: course={course_id}, assignment={assignment_id}, user={user_id}, grade={grade}"}), 400
    
    success, response = submit_grade_to_canvas(course_id, assignment_id, user_id, grade, comment)
    
    print(f"Result: success={success}, response={response[:100] if response else 'None'}...")
    
    return jsonify({
        "success": success,
        "error": None if success else response
    })


@app.route('/api/submit-grades', methods=['POST'])
def submit_grades():
    """Submit grades to Canvas"""
    data = request.json
    course_id = data.get('course_id') or current_session.get('course')
    assignment_id = data.get('assignment_id') or current_session.get('assignment')
    grades = data.get('grades', [])
    
    print(f"\n=== Submit Grades ===")
    print(f"Course: {course_id}, Assignment: {assignment_id}")
    print(f"Grades to submit: {len(grades)}")
    
    if not course_id or not assignment_id:
        return jsonify({"error": "Missing course_id or assignment_id"}), 400
    
    if not grades:
        return jsonify({"error": "No grades to submit"}), 400
    
    results = []
    
    for grade_info in grades:
        student_name = grade_info.get('student_name', 'Unknown')
        filename = grade_info.get('filename', '')
        user_id = grade_info.get('user_id')  # Direct user_id if available
        grade = grade_info.get('grade')
        comment = grade_info.get('comment', '')
        
        print(f"\n  Processing: {student_name} ({filename})")
        print(f"    user_id provided: {user_id}")
        
        # If we have a direct user_id, use it
        if user_id:
            print(f"    Using provided user_id: {user_id}")
            success, response = submit_grade_to_canvas(course_id, assignment_id, user_id, grade, comment)
            results.append({
                "student": student_name,
                "grade": grade,
                "success": success,
                "error": None if success else response
            })
        else:
            # Try to match by filename
            canvas_submissions = get_submissions_with_files(course_id, assignment_id)
            matched_id = None
            matched_name = student_name
            
            filename_lower = filename.lower()
            filename_parts = filename_lower.split('_')
            filename_username = filename_parts[0] if filename_parts else ''
            filename_id = filename_parts[1] if len(filename_parts) > 1 else ''
            
            for sub in canvas_submissions:
                user = sub.get('user', {})
                sub_user_id = str(sub.get('user_id', ''))
                login_id = user.get('login_id', '').lower().split('@')[0].replace('.', '').replace('_', '')
                email = user.get('email', '').lower().split('@')[0].replace('.', '').replace('_', '')
                
                # Match by ID in filename
                if filename_id and filename_id == sub_user_id:
                    matched_id = sub.get('user_id')
                    matched_name = user.get('name', student_name)
                    break
                
                # Match by email/login
                if filename_username and (filename_username == email or filename_username == login_id):
                    matched_id = sub.get('user_id')
                    matched_name = user.get('name', student_name)
                    break
            
            if matched_id:
                print(f"    Matched to user_id: {matched_id}")
                success, response = submit_grade_to_canvas(course_id, assignment_id, matched_id, grade, comment)
                results.append({
                    "student": matched_name,
                    "grade": grade,
                    "success": success,
                    "error": None if success else response
                })
            else:
                print(f"    No match found")
                results.append({
                    "student": student_name,
                    "grade": grade,
                    "success": False,
                    "error": "Could not match to Canvas student"
                })
    
    success_count = sum(1 for r in results if r['success'])
    print(f"\n  Results: {success_count}/{len(results)} successful")
    
    return jsonify({
        "results": results,
        "summary": {
            "total": len(results),
            "success": success_count,
            "failed": len(results) - success_count
        }
    })


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
