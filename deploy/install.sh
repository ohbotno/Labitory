#!/bin/bash
"""
Production installation script for Labitory.

This script installs and configures Labitory for production deployment
on Ubuntu/Debian systems with Nginx + Gunicorn.
"""

set -e  # Exit on any error

# Configuration
APP_NAME="aperature-booking"
APP_USER="aperature-booking"
APP_GROUP="aperature-booking"
APP_DIR="/opt/aperature-booking"
NGINX_AVAILABLE="/etc/nginx/sites-available"
NGINX_ENABLED="/etc/nginx/sites-enabled"
SYSTEMD_DIR="/etc/systemd/system"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
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

# Check if running as root
check_root() {
    if [[ $EUID -ne 0 ]]; then
        log_error "This script must be run as root (use sudo)"
        exit 1
    fi
}

# Detect OS
detect_os() {
    if [[ -f /etc/os-release ]]; then
        . /etc/os-release
        OS=$NAME
        VER=$VERSION_ID
    else
        log_error "Cannot detect OS. This script supports Ubuntu/Debian systems."
        exit 1
    fi
    
    log_info "Detected OS: $OS $VER"
    
    if [[ "$OS" != *"Ubuntu"* && "$OS" != *"Debian"* ]]; then
        log_warning "This script is designed for Ubuntu/Debian. Proceed with caution."
    fi
}

# Install system dependencies
install_dependencies() {
    log_info "Installing system dependencies..."
    
    apt-get update
    apt-get install -y \
        python3 \
        python3-pip \
        python3-venv \
        python3-dev \
        build-essential \
        libpq-dev \
        postgresql \
        postgresql-contrib \
        nginx \
        supervisor \
        redis-server \
        git \
        curl \
        unzip \
        certbot \
        python3-certbot-nginx
    
    log_success "System dependencies installed"
}

# Create application user
create_user() {
    log_info "Creating application user: $APP_USER"
    
    if ! id "$APP_USER" &>/dev/null; then
        useradd --system --group --home "$APP_DIR" --shell /bin/bash "$APP_USER"
        log_success "User $APP_USER created"
    else
        log_info "User $APP_USER already exists"
    fi
}

# Setup application directory
setup_app_directory() {
    log_info "Setting up application directory: $APP_DIR"
    
    # Create directories
    mkdir -p "$APP_DIR"
    mkdir -p "$APP_DIR/logs"
    mkdir -p "$APP_DIR/media"
    mkdir -p "$APP_DIR/backups"
    mkdir -p "/var/run/$APP_NAME"
    mkdir -p "/var/log/$APP_NAME"
    
    # Set ownership
    chown -R "$APP_USER:$APP_GROUP" "$APP_DIR"
    chown -R "$APP_USER:$APP_GROUP" "/var/run/$APP_NAME"
    chown -R "$APP_USER:$APP_GROUP" "/var/log/$APP_NAME"
    
    log_success "Application directory setup complete"
}

# Install Python application
install_application() {
    log_info "Installing Labitory application..."
    
    # Copy application files (assuming script is run from project root)
    if [[ -f "manage.py" ]]; then
        log_info "Copying application files..."
        cp -r . "$APP_DIR/"
        chown -R "$APP_USER:$APP_GROUP" "$APP_DIR"
    else
        log_error "Application files not found. Please run this script from the project root."
        exit 1
    fi
    
    # Create virtual environment
    log_info "Creating Python virtual environment..."
    sudo -u "$APP_USER" python3 -m venv "$APP_DIR/venv"
    
    # Install Python dependencies
    log_info "Installing Python dependencies..."
    sudo -u "$APP_USER" "$APP_DIR/venv/bin/pip" install --upgrade pip
    sudo -u "$APP_USER" "$APP_DIR/venv/bin/pip" install -r "$APP_DIR/requirements.txt"
    sudo -u "$APP_USER" "$APP_DIR/venv/bin/pip" install gunicorn psycopg2-binary redis django-redis dj-database-url
    
    log_success "Application installed"
}

# Setup database
setup_database() {
    log_info "Setting up PostgreSQL database..."
    
    # Start PostgreSQL service
    systemctl start postgresql
    systemctl enable postgresql
    
    # Create database and user
    sudo -u postgres psql -c "CREATE DATABASE ${APP_NAME} OWNER ${APP_USER};" 2>/dev/null || log_info "Database already exists"
    sudo -u postgres psql -c "CREATE USER ${APP_USER} WITH PASSWORD 'change_me_in_production';" 2>/dev/null || log_info "User already exists"
    sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE ${APP_NAME} TO ${APP_USER};"
    
    log_success "Database setup complete"
    log_warning "Remember to change the default database password!"
}

# Configure application
configure_application() {
    log_info "Configuring application..."
    
    # Create production settings file
    if [[ ! -f "$APP_DIR/aperture_booking/settings_local.py" ]]; then
        cp "$APP_DIR/aperture_booking/settings_production.py" "$APP_DIR/aperture_booking/settings_local.py"
        
        # Generate secret key
        SECRET_KEY=$(python3 -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())')
        
        # Create environment file
        cat > "$APP_DIR/.env" << EOF
SECRET_KEY=$SECRET_KEY
DEBUG=False
ALLOWED_HOSTS=localhost,127.0.0.1
DB_NAME=$APP_NAME
DB_USER=$APP_USER
DB_PASSWORD=change_me_in_production
DB_HOST=localhost
DB_PORT=5432
EMAIL_HOST=localhost
EMAIL_PORT=587
EMAIL_USE_TLS=True
DEFAULT_FROM_EMAIL=noreply@aperature-booking.com
TIME_ZONE=UTC
LANGUAGE_CODE=en-gb
EOF
        
        chown "$APP_USER:$APP_GROUP" "$APP_DIR/.env"
        chmod 600 "$APP_DIR/.env"
        
        log_success "Environment configuration created"
        log_warning "Please edit $APP_DIR/.env with your production settings"
    else
        log_info "Settings already configured"
    fi
    
    # Run Django setup
    log_info "Running Django migrations and collecting static files..."
    cd "$APP_DIR"
    sudo -u "$APP_USER" DJANGO_SETTINGS_MODULE=aperture_booking.settings_production "$APP_DIR/venv/bin/python" manage.py migrate
    sudo -u "$APP_USER" DJANGO_SETTINGS_MODULE=aperture_booking.settings_production "$APP_DIR/venv/bin/python" manage.py collectstatic --noinput
    
    log_success "Application configured"
}

# Install systemd services
install_systemd_services() {
    log_info "Installing systemd services..."
    
    # Copy service files
    cp "$APP_DIR/deploy/aperature-booking.service" "$SYSTEMD_DIR/"
    cp "$APP_DIR/deploy/aperature-booking.socket" "$SYSTEMD_DIR/"
    cp "$APP_DIR/deploy/aperature-booking-scheduler.service" "$SYSTEMD_DIR/"
    
    # Reload systemd and enable services
    systemctl daemon-reload
    systemctl enable aperature-booking.socket
    systemctl enable aperature-booking.service
    systemctl enable aperature-booking-scheduler.service
    
    log_success "Systemd services installed"
}

# Configure Nginx
configure_nginx() {
    log_info "Configuring Nginx..."
    
    # Copy Nginx configuration
    cp "$APP_DIR/deploy/nginx-http-only.conf" "$NGINX_AVAILABLE/$APP_NAME"
    
    # Enable site
    ln -sf "$NGINX_AVAILABLE/$APP_NAME" "$NGINX_ENABLED/$APP_NAME"
    
    # Remove default site
    rm -f "$NGINX_ENABLED/default"
    
    # Test Nginx configuration
    nginx -t
    
    log_success "Nginx configured"
}

# Start services
start_services() {
    log_info "Starting services..."
    
    # Start and enable services
    systemctl start redis-server
    systemctl enable redis-server
    
    systemctl start aperature-booking.socket
    systemctl start aperature-booking.service
    systemctl start aperature-booking-scheduler.service
    
    systemctl reload nginx
    systemctl enable nginx
    
    log_success "Services started"
}

# Create admin user
create_admin_user() {
    log_info "Creating Django admin user..."
    
    cd "$APP_DIR"
    echo "Please create an admin user for the Django application:"
    sudo -u "$APP_USER" DJANGO_SETTINGS_MODULE=aperture_booking.settings_production "$APP_DIR/venv/bin/python" manage.py createsuperuser
    
    log_success "Admin user created"
}

# Display completion message
display_completion() {
    log_success "Installation completed successfully!"
    echo
    echo "=============================================="
    echo "Labitory Installation Complete"
    echo "=============================================="
    echo
    echo "Application URL: http://$(hostname -I | awk '{print $1}')"
    echo "Admin URL: http://$(hostname -I | awk '{print $1}')/admin/"
    echo
    echo "Configuration files:"
    echo "  - Application: $APP_DIR/.env"
    echo "  - Nginx: $NGINX_AVAILABLE/$APP_NAME"
    echo "  - Systemd: $SYSTEMD_DIR/aperature-booking.*"
    echo
    echo "Log files:"
    echo "  - Application: $APP_DIR/logs/"
    echo "  - Nginx: /var/log/nginx/"
    echo "  - Systemd: journalctl -u aperature-booking"
    echo
    echo "Next steps:"
    echo "1. Edit $APP_DIR/.env with your production settings"
    echo "2. Update ALLOWED_HOSTS in the environment file"
    echo "3. Configure your database password"
    echo "4. Configure email settings"
    echo "5. Set up SSL with: certbot --nginx -d yourdomain.com"
    echo "6. Configure backups and monitoring"
    echo
    log_warning "Remember to secure your installation and change default passwords!"
}

# Main installation function
main() {
    log_info "Starting Labitory installation..."
    
    check_root
    detect_os
    install_dependencies
    create_user
    setup_app_directory
    install_application
    setup_database
    configure_application
    install_systemd_services
    configure_nginx
    start_services
    create_admin_user
    display_completion
}

# Run main function
main "$@"