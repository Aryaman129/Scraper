FROM python:3.9-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    DEBIAN_FRONTEND=noninteractive \
    CHROME_VERSION="114.0.5735.90-1"

# Install system dependencies and Chrome with proper error handling
RUN set -euxo pipefail && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
        ca-certificates \
        wget \
        gnupg \
        fonts-liberation \
        libgl1 \
        xvfb \
        && \
    # Install Chrome
    wget -q https://dl.google.com/linux/chrome/deb/pool/main/g/google-chrome-stable/google-chrome-stable_${CHROME_VERSION}_amd64.deb && \
    apt-get install -y ./google-chrome-stable_${CHROME_VERSION}_amd64.deb && \
    rm google-chrome-stable_${CHROME_VERSION}_amd64.deb && \
    # Cleanup
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Verify Chrome installation
RUN google-chrome-stable --version

# Create and set working directory
WORKDIR /app

# Copy requirements first to leverage Docker cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose port
EXPOSE 8080

# Run application
CMD ["gunicorn", "-b", "0.0.0.0:8080", "app:app", "--timeout", "120", "--workers", "1"] 