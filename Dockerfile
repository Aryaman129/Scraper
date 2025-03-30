FROM python:3.9-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    DEBIAN_FRONTEND=noninteractive

# Install Chrome and dependencies with version pinning
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    gnupg \
    unzip \
    fonts-liberation \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libatspi2.0-0 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libgbm1 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libwayland-client0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxkbcommon0 \
    libxrandr2 \
    xdg-utils \
    libu2f-udev \
    libvulkan1 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install Chrome from official repo with version pinning
RUN echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list \
    && wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && apt-get update \
    && apt-get install -y google-chrome-stable=114.0.5735.90-1 \
    && rm -rf /var/lib/apt/lists/* \
    && google-chrome-stable --version

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8080

# Add Xvfb support for headless operation
CMD ["sh", "-c", "xvfb-run --auto-servernum gunicorn -b 0.0.0.0:8080 app:app --timeout 120 --workers 1"] 