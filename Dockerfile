FROM selenium/standalone-chrome:latest

USER root

# Install Python and pip without python3-distutils
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-setuptools \
    python3-wheel \
    python3-venv

# Create and use a virtual environment instead of modifying system Python
RUN python3 -m venv /app/venv
ENV PATH="/app/venv/bin:$PATH"

# Set up working directory
WORKDIR /app

# Copy requirements and install in the virtual environment
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose port
EXPOSE 8080

# Run the application with the virtual environment Python
CMD ["/app/venv/bin/python", "-m", "gunicorn", "app:app", "-b", "0.0.0.0:8080", "--timeout", "180"] 