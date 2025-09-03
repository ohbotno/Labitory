# Production Dockerfile for Labitory
# Multi-stage build for optimized production image

# Build stage
FROM python:3.11-slim as builder

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies for building
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Create and activate virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy requirements and install Python dependencies
COPY requirements.txt /tmp/requirements.txt
RUN pip install --upgrade pip && \
    pip install -r /tmp/requirements.txt && \
    pip install gunicorn psycopg2-binary redis django-redis dj-database-url

# Production stage
FROM python:3.11-slim as production

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=aperture_booking.settings_production \
    PATH="/opt/venv/bin:$PATH"

# Create app user
RUN groupadd --system app && \
    useradd --system --group app --home /app --shell /bin/bash app

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    libpq5 \
    nginx \
    supervisor \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy virtual environment from builder stage
COPY --from=builder /opt/venv /opt/venv

# Create application directory structure
RUN mkdir -p /app/staticfiles /app/media /app/logs /app/backups \
    && chown -R app:app /app

# Copy application code
COPY --chown=app:app . /app/

# Copy configuration files
COPY deploy/nginx-docker.conf /etc/nginx/sites-available/aperature-booking
COPY deploy/supervisord.conf /etc/supervisor/conf.d/aperature-booking.conf
COPY deploy/gunicorn.conf.py /app/gunicorn.conf.py

# Remove default nginx site and enable aperature-booking
RUN rm -f /etc/nginx/sites-enabled/default && \
    ln -s /etc/nginx/sites-available/aperature-booking /etc/nginx/sites-enabled/

# Set working directory
WORKDIR /app

# Collect static files
RUN python manage.py collectstatic --noinput --settings=aperture_booking.settings_production

# Create entrypoint script
COPY deploy/docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Expose ports
EXPOSE 80 443

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost/health/ || exit 1

# Switch to app user
USER app

# Set entrypoint
ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["supervisord", "-c", "/etc/supervisor/supervisord.conf", "-n"]