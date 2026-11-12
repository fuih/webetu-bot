FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY webetu_client.py .

# By default, runs continuous daemon scheduling daily bookings at 20:00
CMD ["python", "webetu_client.py", "daemon", "--hour", "20", "--minute", "0"]

