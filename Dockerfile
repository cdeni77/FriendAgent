FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# Default command runs the webhook server; the scheduler runs as a second
# service from the same image (see docker-compose.yml).
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
