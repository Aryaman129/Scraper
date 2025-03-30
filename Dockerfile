FROM selenium/standalone-chrome:latest

USER root
RUN apt-get update && apt-get install -y python3 python3-pip \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

COPY . .
EXPOSE 8080
CMD ["python3", "-m", "gunicorn", "-b", "0.0.0.0:8080", "app:app", "--timeout", "300", "--workers", "1", "--max-requests", "1"] 