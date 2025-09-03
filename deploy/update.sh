#!/bin/bash
"""
Update script for Labitory production deployment.

This script safely updates an existing Labitory installation.
"""

set -e  # Exit on any error

# Configuration
APP_NAME="aperature-booking"
APP_USER="aperature-booking"
APP_DIR="/opt/aperature-booking"
BACKUP_DIR="/opt/aperature-booking/backups"

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

# Create backup
create_backup() {
    log_info "Creating backup before update..."
    
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    BACKUP_FILE="$BACKUP_DIR/pre_update_backup_$TIMESTAMP.tar.gz"
    
    # Create backup using Django management command
    cd "$APP_DIR"
    sudo -u "$APP_USER" DJANGO_SETTINGS_MODULE=aperture_booking.settings_production \
        "$APP_DIR/venv/bin/python" manage.py create_backup \
        --backup-name "pre_update_backup_$TIMESTAMP" \
        --include-database \
        --include-media \
        --include-configuration
    
    log_success "Backup created: $BACKUP_FILE"
}

# Stop services
stop_services() {
    log_info "Stopping services..."
    
    systemctl stop aperature-booking.service
    systemctl stop aperature-booking-scheduler.service
    
    log_success "Services stopped"
}

# Update application code
update_code() {
    log_info "Updating application code..."
    
    # Backup current code
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    cp -r "$APP_DIR" "$APP_DIR.backup.$TIMESTAMP" || log_warning "Could not backup current code"
    
    # Update from git (if using git deployment)
    if [[ -d "$APP_DIR/.git" ]]; then
        cd "$APP_DIR"
        sudo -u "$APP_USER" git pull origin main
    else
        log_info "Not a git repository. Please manually update the code."
        read -p "Press enter after updating the code manually..."
    fi
    
    # Update Python dependencies
    log_info "Updating Python dependencies..."
    sudo -u "$APP_USER" "$APP_DIR/venv/bin/pip" install --upgrade pip
    sudo -u "$APP_USER" "$APP_DIR/venv/bin/pip" install -r "$APP_DIR/requirements.txt" --upgrade
    
    log_success "Code updated"
}

# Run migrations and collect static files
update_database() {
    log_info "Running database migrations..."
    
    cd "$APP_DIR"
    sudo -u "$APP_USER" DJANGO_SETTINGS_MODULE=aperture_booking.settings_production \
        "$APP_DIR/venv/bin/python" manage.py migrate
    
    log_info "Collecting static files..."
    sudo -u "$APP_USER" DJANGO_SETTINGS_MODULE=aperture_booking.settings_production \
        "$APP_DIR/venv/bin/python" manage.py collectstatic --noinput
    
    log_success "Database and static files updated"
}

# Update systemd services
update_services() {
    log_info "Updating systemd services..."
    
    # Copy updated service files
    cp "$APP_DIR/deploy/aperature-booking.service" "/etc/systemd/system/"
    cp "$APP_DIR/deploy/aperature-booking.socket" "/etc/systemd/system/"
    cp "$APP_DIR/deploy/aperature-booking-scheduler.service" "/etc/systemd/system/"
    
    # Reload systemd
    systemctl daemon-reload
    
    log_success "Services updated"
}

# Start services
start_services() {
    log_info "Starting services..."
    
    systemctl start aperature-booking.socket
    systemctl start aperature-booking.service
    systemctl start aperature-booking-scheduler.service
    
    # Reload nginx
    systemctl reload nginx
    
    log_success "Services started"
}

# Verify deployment
verify_deployment() {
    log_info "Verifying deployment..."
    
    # Check service status
    if systemctl is-active --quiet aperature-booking.service; then
        log_success "Labitory service is running"
    else
        log_error "Labitory service failed to start"
        log_info "Check logs: journalctl -u aperature-booking.service"
        exit 1
    fi
    
    if systemctl is-active --quiet aperature-booking-scheduler.service; then
        log_success "Scheduler service is running"
    else
        log_warning "Scheduler service is not running"
        log_info "Check logs: journalctl -u aperature-booking-scheduler.service"
    fi
    
    # Test HTTP response
    sleep 5  # Give the service time to start
    if curl -f -s http://localhost/health/ > /dev/null; then
        log_success "Application is responding to HTTP requests"
    else
        log_warning "Application may not be responding properly"
        log_info "Check Nginx logs: tail -f /var/log/nginx/aperature-booking.error.log"
    fi
    
    log_success "Deployment verification complete"
}

# Rollback function
rollback() {
    log_error "Update failed. Starting rollback..."
    
    # Stop services
    systemctl stop aperature-booking.service
    systemctl stop aperature-booking-scheduler.service
    
    # Find latest backup
    LATEST_BACKUP=$(ls -t "$APP_DIR".backup.* 2>/dev/null | head -n1)
    
    if [[ -n "$LATEST_BACKUP" ]]; then
        log_info "Restoring from backup: $LATEST_BACKUP"
        rm -rf "$APP_DIR"
        mv "$LATEST_BACKUP" "$APP_DIR"
        
        # Restart services
        systemctl start aperature-booking.socket
        systemctl start aperature-booking.service
        systemctl start aperature-booking-scheduler.service
        
        log_success "Rollback completed"
    else
        log_error "No backup found for rollback"
        exit 1
    fi
}

# Main update function
main() {
    log_info "Starting Labitory update..."
    
    check_root
    
    # Set trap for rollback on error
    trap rollback ERR
    
    create_backup
    stop_services
    update_code
    update_database
    update_services
    start_services
    verify_deployment
    
    # Remove trap
    trap - ERR
    
    log_success "Update completed successfully!"
    echo
    echo "=============================================="
    echo "Labitory Update Complete"
    echo "=============================================="
    echo
    echo "Application URL: http://$(hostname -I | awk '{print $1}')"
    echo "Admin URL: http://$(hostname -I | awk '{print $1}')/admin/"
    echo
    echo "If you experience any issues:"
    echo "1. Check service logs: journalctl -u aperature-booking.service"
    echo "2. Check Nginx logs: tail -f /var/log/nginx/aperature-booking.error.log"
    echo "3. Check application logs: tail -f $APP_DIR/logs/aperture_booking.log"
    echo
}

# Handle command line arguments
case "${1:-}" in
    --rollback)
        rollback
        ;;
    *)
        main "$@"
        ;;
esac