# --- STAGE 1: Build stage ---
FROM python:3.11-slim as builder
WORKDIR /app

# Prevent Python from writing .pyc files and enable unbuffered logging
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Install system dependencies required for psycopg2 (Postgres driver)
RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies into a temporary folder (/install)
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir --prefix=/install -r requirements.txt


# --- STAGE 2: Runtime stage ---
FROM python:3.11-slim
WORKDIR /app

# Copy the installed Python packages from the builder stage
COPY --from=builder /install /usr/local

# Copy the actual Django project code
COPY . /app/

# --- BUILD-TIME DUMMY VARIABLES ---
# These are strictly for the 'collectstatic' command below.
# They prevent Django and SimpleJWT from crashing due to empty settings.
ENV DJANGO_SECRET_KEY=temporary_build_key
ENV SECRET_KEY=temporary_build_key
ENV STRIPE_PUBLIC_KEY=dummy
ENV STRIPE_SECRET_KEY=dummy
ENV STRIPE_WEBHOOK_SECRET=dummy
# Signals settings.py to use a mock database during build
ENV DB_IGNORE=True 
# ----------------------------------

# Collect static files for WhiteNoise/Nginx
RUN python manage.py collectstatic --noinput

# Final command to run the application
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "config.wsgi:application"]