FROM python:3.11-slim

WORKDIR /app

# Unbuffered output for real-time logging
ENV PYTHONUNBUFFERED=1

# Install dependencies for the app
RUN pip install flask anthropic requests PyYAML Jinja2

# Install common libraries that student code might use
# These are available when running student submissions
RUN pip install openpyxl pandas numpy matplotlib

# Copy app files
COPY app.py .
COPY config.py .
COPY prompt_loader.py .
COPY templates/ templates/
COPY prompts/ prompts/

# Expose port
EXPOSE 5000

# Run the app with unbuffered output
CMD ["python", "-u", "app.py"]
