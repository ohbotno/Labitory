#!/bin/bash
"""
Docker entrypoint script for Labitory.

This script initializes the Django application in a Docker container.
"""

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Wait for database to be ready
wait_for_db() {
    log_info "Waiting for database to be ready..."
    
    while ! python manage.py dbshell <<< "SELECT 1;" >/dev/null 2>&1; do
        log_info "Database is unavailable - sleeping"
        sleep 1
    done
    
    log_success "Database is ready"
}

# Run database migrations
run_migrations() {
    log_info "Running database migrations..."
    python manage.py migrate --noinput
    log_success "Migrations completed"
}

# Collect static files
collect_static() {
    log_info "Collecting static files..."
    python manage.py collectstatic --noinput --clear
    log_success "Static files collected"
}

# Create superuser if it doesn't exist
create_superuser() {
    if [[ -n "${DJANGO_SUPERUSER_USERNAME}" && -n "${DJANGO_SUPERUSER_PASSWORD}" && -n "${DJANGO_SUPERUSER_EMAIL}" ]]; then
        log_info "Creating Django superuser..."
        python manage.py shell << EOF
from django.contrib.auth import get_user_model
User = get_user_model()
if not User.objects.filter(username='${DJANGO_SUPERUSER_USERNAME}').exists():
    User.objects.create_superuser('${DJANGO_SUPERUSER_USERNAME}', '${DJANGO_SUPERUSER_EMAIL}', '${DJANGO_SUPERUSER_PASSWORD}')
    print('Superuser created successfully')
else:
    print('Superuser already exists')
EOF
        log_success "Superuser setup completed"
    else
        log_warning "Superuser environment variables not set"
    fi
}

# Load initial data (optional)
load_initial_data() {
    if [[ "${LOAD_INITIAL_DATA}" == "true" ]]; then
        log_info "Loading initial data..."
        
        # Load fixtures if they exist
        if [[ -f "fixtures/initial_data.json" ]]; then
            python manage.py loaddata fixtures/initial_data.json
            log_success "Initial data loaded"
        else
            log_warning "No initial data fixtures found"
        fi
    fi
}

# Setup logging directories
setup_logging() {
    log_info "Setting up logging..."
    mkdir -p /app/logs
    touch /app/logs/aperture_booking.log
    touch /app/logs/aperture_booking_errors.log
    log_success "Logging setup completed"
}

# Start background scheduler (if not disabled)
start_scheduler() {
    if [[ "${DISABLE_SCHEDULER}" != "true" ]]; then
        log_info "Starting background scheduler..."
        python manage.py scheduler &
        log_success "Scheduler started"
    else
        log_info "Scheduler disabled"
    fi
}

# Main initialization
main() {
    log_info "Starting Labitory initialization..."
    
    # Setup logging
    setup_logging
    
    # Wait for dependencies
    wait_for_db
    
    # Database setup
    run_migrations
    
    # Static files
    collect_static
    
    # Create superuser
    create_superuser
    
    # Load initial data
    load_initial_data
    
    # Start scheduler
    start_scheduler
    
    log_success "Initialization completed successfully!"
    
    # Execute the command passed to the container
    exec "$@"
}

# Handle different commands
case "${1:-}" in
    "bash"|"sh")
        # Development: start shell
        exec "$@"
        ;;
    "python")
        # Development: run python commands
        wait_for_db
        exec "$@"
        ;;
    "manage.py")
        # Development: run Django management commands
        wait_for_db
        exec python "$@"
        ;;
    *)
        # Production: full initialization
        main "$@"
        ;;
esac