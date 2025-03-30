FROM python:3.9-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    DEBIAN_FRONTEND=noninteractive

# Install Chrome and other dependencies
RUN apt-get update && apt-get install -y \
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
    curl \
    ca-certificates \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install Chrome with specific version
RUN wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update \
    && apt-get install -y google-chrome-stable \
    && google-chrome-stable --version \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install specific ChromeDriver version (114.0.5735.90)
RUN wget -q https://chromedriver.storage.googleapis.com/114.0.5735.90/chromedriver_linux64.zip \
    && unzip chromedriver_linux64.zip \
    && mv chromedriver /usr/local/bin/chromedriver \
    && chmod +x /usr/local/bin/chromedriver \
    && rm chromedriver_linux64.zip \
    && chromedriver --version

# Create a working directory
WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir Flask==2.0.1 \
    Werkzeug==2.0.1 \
    itsdangerous==2.0.1 \
    Jinja2==3.0.1 \
    MarkupSafe==2.0.1 \
    Flask-Cors==3.0.10 \
    gunicorn==20.1.0 \
    PyJWT==2.8.0 \
    python-dotenv==0.19.0 \
    selenium==4.10.0 \
    beautifulsoup4==4.12.2 \
    requests==2.31.0 \
    psutil==5.9.8 \
    supabase==1.0.3

# Copy application code
COPY . .

# Expose the port
EXPOSE 8080

# Run the application with memory optimization
CMD ["gunicorn", "-b", "0.0.0.0:8080", "app:app", "--timeout", "300", "--workers", "1", "--max-requests", "1"] 