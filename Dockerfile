FROM python:3.11-slim

WORKDIR /app

# Unbuffered output for real-time logging
ENV PYTHONUNBUFFERED=1

# Install dependencies from requirements.txt (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install common libraries that student code might use
# These are available when running student submissions
RUN pip install --no-cache-dir openpyxl pandas numpy matplotlib

# Create non-root user for security
RUN useradd --create-home appuser

# Copy app files
COPY app.py .
COPY config.py .
COPY code_runner.py .
COPY prompt_loader.py .
COPY templates/ templates/

# Create writable directories owned by appuser
RUN mkdir -p uploads data && chown -R appuser:appuser /app

USER appuser

# Expose port
EXPOSE 5000

# Run the app
CMD ["python", "-u", "app.py"]
