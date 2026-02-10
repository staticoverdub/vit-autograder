# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

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
