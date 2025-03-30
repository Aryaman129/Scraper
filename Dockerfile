FROM selenium/standalone-chrome:latest

USER root

# Install Python and required packages
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-dev \
    build-essential \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Set up app directory
WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

# Expose port
EXPOSE 8080

# Run with longer timeout and memory optimization
CMD ["python3", "-m", "gunicorn", "-b", "0.0.0.0:8080", "app:app", "--timeout", "300", "--workers", "1", "--max-requests", "1"] 