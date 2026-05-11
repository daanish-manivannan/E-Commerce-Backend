# Stage 1: Build stage
FROM python:3.11-slim as builder
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir --prefix=/install -r requirements.txt

# ... (First stage/Builder remains the same)

# Stage 2: Runtime stage
FROM python:3.11-slim
WORKDIR /app
COPY --from=builder /install /usr/local
COPY . /app/

# --- ADD THIS BLOCK ---
# Provide dummy values so collectstatic doesn't fail
ENV STRIPE_PUBLIC_KEY=dummy
ENV STRIPE_SECRET_KEY=dummy
ENV STRIPE_WEBHOOK_SECRET=dummy
ENV DJANGO_SECRET_KEY=dummy
# ----------------------

RUN python manage.py collectstatic --noinput

CMD ["gunicorn", "--bind", "0.0.0.0:8000", "config.wsgi:application"]

# Create the folder for WhiteNoise to collect files into
RUN python manage.py collectstatic --noinput

# Production command using Gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "config.wsgi:application"]