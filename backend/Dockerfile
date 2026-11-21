FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Run as a normal user, never as root.
# /uploads holds car photos, /documents drivers' legal documents (a Docker
# volume takes its owner and permissions from here).
RUN useradd --create-home etike && mkdir -p /uploads /documents \
    && chown -R etike /app /uploads /documents && chmod 700 /documents
USER etike

EXPOSE 8000

# 3 workers is plenty for a small VPS; tune with GUNICORN_WORKERS if needed.
CMD ["sh", "-c", "gunicorn wsgi:app --bind 0.0.0.0:8000 --workers ${GUNICORN_WORKERS:-3}"]
