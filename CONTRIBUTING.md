# Contributing to AutoGrader

Thanks for your interest in contributing! This guide will help you get started.

## Getting Started

1. Fork the repository
2. Clone your fork:
   ```bash
   git clone https://github.com/your-username/vit-autograder.git
   cd vit-autograder
   ```
3. Create a branch for your work:
   ```bash
   git checkout -b your-feature-name
   ```
4. Set up your environment:
   ```bash
   cp .env.example .env
   cp config.yaml.example config.yaml
   pip install -r requirements.txt
   ```
5. Edit `.env` and `config.yaml` with your credentials and organization details.

## Development

Run locally:

```bash
python app.py
```

Or with Docker:

```bash
docker-compose up --build
```

## Making Changes

- Keep changes focused — one feature or fix per PR.
- Follow the existing code style.
- Update `config.yaml.example` if you add new configuration options.
- Update prompt templates in `prompts/` if you change grading behavior.
- Update the README if your change affects setup or usage.

## Submitting a Pull Request

1. Push your branch to your fork.
2. Open a PR against `main`.
3. Describe what you changed and why.
4. Link any related issues.

## Reporting Bugs

Open an issue with:

- What you expected to happen
- What actually happened
- Steps to reproduce
- Your environment (OS, Python version, Docker version if applicable)

## Requesting Features

Open an issue describing:

- The problem you're trying to solve
- Your proposed solution (if you have one)
- Any alternatives you've considered

## Security

If you discover a security vulnerability, please follow our [Security Policy](SECURITY.md) instead of opening a public issue.

## Code of Conduct

This project follows our [Code of Conduct](CODE_OF_CONDUCT.md). By participating, you agree to uphold it.
