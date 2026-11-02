FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Run as a normal user, never as root.
RUN useradd --create-home etike && chown -R etike /app
USER etike

EXPOSE 8000

# 3 workers is plenty for a small VPS; tune with GUNICORN_WORKERS if needed.
CMD ["sh", "-c", "gunicorn wsgi:app --bind 0.0.0.0:8000 --workers ${GUNICORN_WORKERS:-3}"]
