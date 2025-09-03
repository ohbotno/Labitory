#!/bin/bash
"""
SSL/HTTPS setup script for Labitory.

This script configures SSL certificates using Let's Encrypt or custom certificates.
"""

set -e  # Exit on any error

# Configuration
APP_NAME="aperature-booking"
NGINX_AVAILABLE="/etc/nginx/sites-available"
NGINX_ENABLED="/etc/nginx/sites-enabled"

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

# Get domain name from user
get_domain() {
    if [[ -z "${DOMAIN:-}" ]]; then
        echo -n "Enter your domain name (e.g., booking.example.com): "
        read -r DOMAIN
    fi
    
    if [[ -z "$DOMAIN" ]]; then
        log_error "Domain name is required"
        exit 1
    fi
    
    log_info "Using domain: $DOMAIN"
}

# Update Nginx configuration with domain
update_nginx_config() {
    log_info "Updating Nginx configuration with domain name..."
    
    # Backup existing config
    cp "$NGINX_AVAILABLE/$APP_NAME" "$NGINX_AVAILABLE/$APP_NAME.backup"
    
    # Replace server_name in config
    sed -i "s/server_name _;/server_name $DOMAIN;/g" "$NGINX_AVAILABLE/$APP_NAME"
    
    # Test Nginx configuration
    nginx -t
    
    log_success "Nginx configuration updated"
}

# Setup Let's Encrypt SSL
setup_letsencrypt() {
    log_info "Setting up Let's Encrypt SSL certificate..."
    
    # Install certbot if not already installed
    if ! command -v certbot &> /dev/null; then
        log_info "Installing certbot..."
        apt-get update
        apt-get install -y certbot python3-certbot-nginx
    fi
    
    # Get certificate
    log_info "Obtaining SSL certificate for $DOMAIN..."
    certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos --email admin@"$DOMAIN"
    
    # Setup auto-renewal
    log_info "Setting up automatic renewal..."
    (crontab -l 2>/dev/null; echo "0 12 * * * /usr/bin/certbot renew --quiet") | crontab -
    
    log_success "Let's Encrypt SSL certificate installed and auto-renewal configured"
}

# Setup custom SSL certificate
setup_custom_ssl() {
    log_info "Setting up custom SSL certificate..."
    
    CERT_DIR="/etc/ssl/certs"
    KEY_DIR="/etc/ssl/private"
    
    echo "Please provide the paths to your SSL certificate files:"
    echo -n "Certificate file (.crt or .pem): "
    read -r CERT_FILE
    echo -n "Private key file (.key): "
    read -r KEY_FILE
    
    if [[ ! -f "$CERT_FILE" ]]; then
        log_error "Certificate file not found: $CERT_FILE"
        exit 1
    fi
    
    if [[ ! -f "$KEY_FILE" ]]; then
        log_error "Private key file not found: $KEY_FILE"
        exit 1
    fi
    
    # Copy certificate files
    cp "$CERT_FILE" "$CERT_DIR/$APP_NAME.crt"
    cp "$KEY_FILE" "$KEY_DIR/$APP_NAME.key"
    
    # Set correct permissions
    chmod 644 "$CERT_DIR/$APP_NAME.crt"
    chmod 600 "$KEY_DIR/$APP_NAME.key"
    
    # Update Nginx configuration to use custom certificates
    sed -i "s|ssl_certificate /etc/ssl/certs/aperature-booking.crt;|ssl_certificate $CERT_DIR/$APP_NAME.crt;|g" "$NGINX_AVAILABLE/$APP_NAME"
    sed -i "s|ssl_certificate_key /etc/ssl/private/aperature-booking.key;|ssl_certificate_key $KEY_DIR/$APP_NAME.key;|g" "$NGINX_AVAILABLE/$APP_NAME"
    
    log_success "Custom SSL certificate installed"
}

# Generate self-signed certificate (for testing)
setup_self_signed() {
    log_warning "Setting up self-signed SSL certificate (for testing only)..."
    
    CERT_DIR="/etc/ssl/certs"
    KEY_DIR="/etc/ssl/private"
    
    # Generate self-signed certificate
    openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
        -keyout "$KEY_DIR/$APP_NAME.key" \
        -out "$CERT_DIR/$APP_NAME.crt" \
        -subj "/C=US/ST=State/L=City/O=Organization/CN=$DOMAIN"
    
    # Set correct permissions
    chmod 644 "$CERT_DIR/$APP_NAME.crt"
    chmod 600 "$KEY_DIR/$APP_NAME.key"
    
    log_success "Self-signed certificate generated"
    log_warning "This certificate will show security warnings in browsers"
}

# Enable HTTPS in Django settings
enable_django_https() {
    log_info "Enabling HTTPS in Django settings..."
    
    ENV_FILE="/opt/aperature-booking/.env"
    
    if [[ -f "$ENV_FILE" ]]; then
        # Update or add HTTPS setting
        if grep -q "USE_HTTPS" "$ENV_FILE"; then
            sed -i "s/USE_HTTPS=.*/USE_HTTPS=True/" "$ENV_FILE"
        else
            echo "USE_HTTPS=True" >> "$ENV_FILE"
        fi
        
        log_success "HTTPS enabled in Django settings"
    else
        log_warning "Django environment file not found at $ENV_FILE"
    fi
}

# Switch to HTTPS Nginx configuration
switch_to_https_config() {
    log_info "Switching to HTTPS Nginx configuration..."
    
    # Use the full HTTPS configuration
    cp "/opt/aperature-booking/deploy/nginx.conf" "$NGINX_AVAILABLE/$APP_NAME"
    
    # Update domain name
    sed -i "s/server_name _;/server_name $DOMAIN;/g" "$NGINX_AVAILABLE/$APP_NAME"
    
    # Test and reload Nginx
    nginx -t
    systemctl reload nginx
    
    log_success "Switched to HTTPS configuration"
}

# Test SSL configuration
test_ssl() {
    log_info "Testing SSL configuration..."
    
    # Test with curl
    if curl -f -s "https://$DOMAIN/health/" > /dev/null; then
        log_success "HTTPS is working correctly"
    else
        log_warning "HTTPS may not be working properly"
        log_info "Check Nginx error logs: tail -f /var/log/nginx/error.log"
    fi
    
    # Test SSL certificate
    log_info "SSL certificate information:"
    echo | openssl s_client -servername "$DOMAIN" -connect "$DOMAIN:443" 2>/dev/null | openssl x509 -noout -dates
}

# Display SSL status
display_ssl_status() {
    log_success "SSL configuration completed!"
    echo
    echo "=============================================="
    echo "SSL Configuration Summary"
    echo "=============================================="
    echo
    echo "Domain: $DOMAIN"
    echo "HTTPS URL: https://$DOMAIN"
    echo "Admin URL: https://$DOMAIN/admin/"
    echo
    echo "Certificate location:"
    echo "  - Certificate: /etc/ssl/certs/$APP_NAME.crt"
    echo "  - Private key: /etc/ssl/private/$APP_NAME.key"
    echo
    echo "Configuration files:"
    echo "  - Nginx: $NGINX_AVAILABLE/$APP_NAME"
    echo "  - Django: /opt/aperature-booking/.env"
    echo
    echo "Test your SSL configuration:"
    echo "  - Browser: https://$DOMAIN"
    echo "  - SSL test: https://www.ssllabs.com/ssltest/"
    echo "  - Command: curl -I https://$DOMAIN"
    echo
}

# Main menu
show_menu() {
    echo "=============================================="
    echo "Labitory SSL Setup"
    echo "=============================================="
    echo
    echo "Choose SSL certificate type:"
    echo "1) Let's Encrypt (recommended for production)"
    echo "2) Custom certificate (bring your own)"
    echo "3) Self-signed (testing only)"
    echo "4) Exit"
    echo
    echo -n "Enter your choice (1-4): "
}

# Main function
main() {
    log_info "Starting SSL setup for Labitory..."
    
    check_root
    get_domain
    update_nginx_config
    
    while true; do
        show_menu
        read -r choice
        
        case $choice in
            1)
                setup_letsencrypt
                break
                ;;
            2)
                setup_custom_ssl
                break
                ;;
            3)
                setup_self_signed
                break
                ;;
            4)
                log_info "SSL setup cancelled"
                exit 0
                ;;
            *)
                log_error "Invalid choice. Please enter 1-4."
                ;;
        esac
    done
    
    enable_django_https
    switch_to_https_config
    
    # Restart services
    systemctl restart aperature-booking.service
    systemctl reload nginx
    
    test_ssl
    display_ssl_status
}

# Handle command line arguments
case "${1:-}" in
    --letsencrypt)
        DOMAIN="$2"
        check_root
        get_domain
        update_nginx_config
        setup_letsencrypt
        enable_django_https
        switch_to_https_config
        systemctl restart aperature-booking.service
        systemctl reload nginx
        test_ssl
        display_ssl_status
        ;;
    --help)
        echo "Usage: $0 [--letsencrypt domain.com] [--help]"
        echo
        echo "Options:"
        echo "  --letsencrypt DOMAIN    Setup Let's Encrypt automatically"
        echo "  --help                  Show this help"
        echo
        echo "Interactive mode: $0"
        ;;
    *)
        main "$@"
        ;;
esac