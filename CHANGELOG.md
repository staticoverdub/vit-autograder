# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [1.1.0] - 2026-02-10

### Security
- XSS: escape all user-controlled data (student names, course names, filenames) in HTML templates via `escapeHtml()`
- Default to `127.0.0.1` binding (not `0.0.0.0`); Docker sets `HOST=0.0.0.0` explicitly
- `debug=True` removed; controlled via `FLASK_DEBUG` env var (defaults to false)
- Zip slip protection: validate all zip entries stay within target directory
- Temp directory cleanup after zip extraction
- Removed `filepath` from API responses (information disclosure)
- Config endpoint made read-only; removed POST handler for credential updates
- Settings modal is now read-only (credentials managed via `.env` only)
- HTML-escape inline reminder messages to prevent stored XSS
- Added security headers: `X-Content-Type-Options`, `X-Frame-Options`, `X-XSS-Protection`, `Referrer-Policy`
- `SECRET_KEY` loaded from env var (randomized fallback)
- Subprocess runs with stripped environment (`_SAFE_ENV`) to prevent secret leakage

## [1.0.0] - 2026-02-10

### Added
- Docker image build verification in CI
- Screenshot placeholder in README for project discovery

### Changed
- Extracted `code_runner.py` module from app.py (sandboxed code execution)
- app.py reduced by ~50 lines; cleaner separation of concerns
- Updated project structure in README

### Fixed
- Missing `get_org_website` import causing runtime crash on `/api/config`
- Module-level `config` variable shadowing Flask route function
- 5 bare `except` clauses replaced with specific exception types
- Removed dead code (`assignment_map`, `assignment_scores_active` pass-only loop)
- Removed unused `subprocess` import from app.py

## [0.4.0] - 2026-02-10

### Added
- Test suite with 58 pytest tests covering config, app logic, code execution, and prompt rendering
- GitHub Actions CI workflow with linting and tests on push/PR
- `Makefile` with `install`, `test`, `lint`, `run`, `docker` targets
- `.dockerignore` to keep builds lean and secure
- Bug report and feature request issue templates
- Pull request template with test checklist
- Dependabot configuration for pip and GitHub Actions
- Ruff linter integration (`make lint`)
- `config.yaml.example` validation tests

### Changed
- README: added CI/license badges, test instructions, contributing links, updated project structure
- Dockerfile: uses `requirements.txt`, `--no-cache-dir`, runs as non-root user
- `.gitignore`: added test/build artifact patterns
- Codebase linted clean with ruff (import sorting, unused imports, whitespace)

## [0.3.0] - 2026-02-10

### Added
- LICENSE (MIT)
- CONTRIBUTING.md with development workflow and guidelines
- CODE_OF_CONDUCT.md (Contributor Covenant)
- SECURITY.md with vulnerability reporting instructions
- `.env.example` for onboarding new contributors

## [0.2.0] - 2026-02-03

### Added
- Skip/excuse submission controls for wrong file uploads
- Ability to mark submissions as excused or skip them during grading

## [0.1.0] - 2026-02-03

### Added
- Configurable, organization-agnostic grading platform
- AI-powered Python assignment grading via Anthropic Claude
- Canvas LMS integration for fetching submissions and posting grades
- `config.yaml`-driven settings with environment variable overrides
- Assignment type detection (standard, checkoff, final project)
- Sandboxed Python code execution with timeout support
- HTML-to-text conversion for submission content
- Jinja2 prompt templates for grading rubrics
- Docker support with `Dockerfile` and `docker-compose.yml`
- Flask web UI for managing grading sessions
