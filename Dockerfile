FROM python:3.11-slim

# Prevent Python from writing .pyc files and buffer stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application configuration and source code
COPY config.yaml .
COPY src/ ./src/

# Create data directory for SQLite database persistence
RUN mkdir -p /app/data

# Default command
CMD ["python", "-m", "src.main"]
