# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in AutoGrader, **please do not open a public issue.**

Instead, email chris@staticoverdub.io with:

- A description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if you have one)

You should receive a response within 48 hours. We'll work with you to understand the issue and coordinate a fix before any public disclosure.

## Scope

This policy covers:

- The AutoGrader application code
- Configuration handling and secret management
- Student code execution sandbox
- Canvas API integration
- File upload and processing

## Known Considerations

- **Student code execution**: AutoGrader executes student-submitted Python code with a configurable timeout and library whitelist. Deployers should run the application in an isolated environment (Docker is recommended).
- **API credentials**: Canvas and Anthropic API keys are stored in `.env` files. Never commit credentials to version control.
- **File uploads**: Uploaded ZIP files are extracted and processed. The application should be run in an environment where filesystem access is appropriately restricted.

## Best Practices for Deployers

- Run AutoGrader in Docker or an otherwise isolated environment
- Use read-only filesystem mounts where possible
- Restrict network access from the code execution sandbox
- Rotate API tokens regularly
- Keep dependencies up to date
