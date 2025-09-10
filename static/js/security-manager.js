/**
 * Security Manager for Labitory
 * 
 * Centralized security operations and real-time monitoring
 * 
 * This file is part of Labitory.
 * Copyright (c) 2025 Labitory Contributors
 * Licensed under the MIT License - see LICENSE file for details.
 */

class SecurityManager {
    constructor(options = {}) {
        this.options = {
            apiBaseUrl: '/site-admin/security/',
            autoRefresh: false,
            refreshInterval: 30000, // 30 seconds
            notifications: true,
            ...options
        };
        
        this.refreshInterval = null;
        this.eventListeners = {};
        this.alertThresholds = {
            failedLogins: 5,
            suspiciousActivity: 3,
            tokenCreations: 10
        };
        
        this.init();
    }
    
    init() {
        this.bindEvents();
        if (this.options.autoRefresh) {
            this.startAutoRefresh();
        }
    }
    
    bindEvents() {
        // CSRF token setup for all AJAX requests
        this.setupCSRF();
        
        // Global security event listeners
        document.addEventListener('securityEvent', this.handleSecurityEvent.bind(this));
        
        // Token management events
        this.on('tokenRevoked', this.handleTokenRevoked.bind(this));
        this.on('suspiciousActivity', this.handleSuspiciousActivity.bind(this));
    }
    
    setupCSRF() {
        const csrfToken = this.getCSRFToken();
        
        // Set default CSRF header for all jQuery AJAX requests (if jQuery is available)
        if (window.$ && $.ajaxSetup) {
            $.ajaxSetup({
                beforeSend: (xhr, settings) => {
                    if (!this.csrfSafeMethod(settings.type) && !this.sameOrigin(settings.url)) {
                        xhr.setRequestHeader("X-CSRFToken", csrfToken);
                    }
                }
            });
        }
    }
    
    getCSRFToken() {
        const cookies = document.cookie.split(';');
        for (let cookie of cookies) {
            const [name, value] = cookie.trim().split('=');
            if (name === 'csrftoken') {
                return decodeURIComponent(value);
            }
        }
        
        // Fallback to meta tag or hidden input
        const metaTag = document.querySelector('meta[name=csrf-token]');
        if (metaTag) return metaTag.getAttribute('content');
        
        const hiddenInput = document.querySelector('input[name=csrfmiddlewaretoken]');
        if (hiddenInput) return hiddenInput.value;
        
        return null;
    }
    
    csrfSafeMethod(method) {
        return (/^(GET|HEAD|OPTIONS|TRACE)$/.test(method));
    }
    
    sameOrigin(url) {
        const host = document.location.host;
        const protocol = document.location.protocol;
        const srOrigin = '//' + host;
        const origin = protocol + srOrigin;
        return (url === origin || url.slice(0, origin.length + 1) === origin + '/') ||
               (url === srOrigin || url.slice(0, srOrigin.length + 1) === srOrigin + '/') ||
               !(/^(\/\/|http:|https:).*/.test(url));
    }
    
    // Event system
    on(event, callback) {
        if (!this.eventListeners[event]) {
            this.eventListeners[event] = [];
        }
        this.eventListeners[event].push(callback);
    }
    
    emit(event, data) {
        if (this.eventListeners[event]) {
            this.eventListeners[event].forEach(callback => callback(data));
        }
    }
    
    // API Token Management
    async revokeToken(tokenJti, userId = null) {
        try {
            const response = await fetch(`${this.options.apiBaseUrl}api-tokens/revoke/`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'X-CSRFToken': this.getCSRFToken()
                },
                body: new URLSearchParams({
                    token_jti: tokenJti,
                    user_id: userId || ''
                })
            });
            
            const result = await response.json();
            
            if (result.success) {
                this.emit('tokenRevoked', { tokenJti, userId, result });
                this.showNotification('Token revoked successfully', 'success');
                return true;
            } else {
                this.showNotification(result.error || 'Failed to revoke token', 'error');
                return false;
            }
        } catch (error) {
            console.error('Token revocation failed:', error);
            this.showNotification('Token revocation failed', 'error');
            return false;
        }
    }
    
    async revokeAllUserTokens(userId) {
        try {
            const response = await fetch(`${this.options.apiBaseUrl}api-tokens/revoke-all/`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'X-CSRFToken': this.getCSRFToken()
                },
                body: new URLSearchParams({
                    user_id: userId
                })
            });
            
            const result = await response.json();
            
            if (result.success) {
                this.emit('allTokensRevoked', { userId, result });
                this.showNotification(result.message, 'success');
                return true;
            } else {
                this.showNotification(result.error || 'Failed to revoke tokens', 'error');
                return false;
            }
        } catch (error) {
            console.error('Bulk token revocation failed:', error);
            this.showNotification('Bulk token revocation failed', 'error');
            return false;
        }
    }
    
    // Security Monitoring
    async getSecurityMetrics() {
        try {
            const response = await fetch(`${this.options.apiBaseUrl}metrics/`, {
                headers: {
                    'X-CSRFToken': this.getCSRFToken()
                }
            });
            
            if (response.ok) {
                return await response.json();
            } else {
                throw new Error('Failed to fetch security metrics');
            }
        } catch (error) {
            console.error('Security metrics fetch failed:', error);
            return null;
        }
    }
    
    async getSecurityEvents(filters = {}) {
        try {
            const params = new URLSearchParams(filters);
            const response = await fetch(`${this.options.apiBaseUrl}events/?${params}`, {
                headers: {
                    'X-CSRFToken': this.getCSRFToken()
                }
            });
            
            if (response.ok) {
                return await response.json();
            } else {
                throw new Error('Failed to fetch security events');
            }
        } catch (error) {
            console.error('Security events fetch failed:', error);
            return null;
        }
    }
    
    // Real-time monitoring
    startAutoRefresh() {
        if (this.refreshInterval) {
            clearInterval(this.refreshInterval);
        }
        
        this.refreshInterval = setInterval(async () => {
            await this.checkSecurityAlerts();
        }, this.options.refreshInterval);
        
        this.emit('autoRefreshStarted', { interval: this.options.refreshInterval });
    }
    
    stopAutoRefresh() {
        if (this.refreshInterval) {
            clearInterval(this.refreshInterval);
            this.refreshInterval = null;
        }
        
        this.emit('autoRefreshStopped', {});
    }
    
    async checkSecurityAlerts() {
        const metrics = await this.getSecurityMetrics();
        if (!metrics) return;
        
        // Check for threshold violations
        if (metrics.failedLogins > this.alertThresholds.failedLogins) {
            this.emit('securityAlert', {
                type: 'failedLogins',
                count: metrics.failedLogins,
                threshold: this.alertThresholds.failedLogins
            });
        }
        
        if (metrics.suspiciousActivity > this.alertThresholds.suspiciousActivity) {
            this.emit('securityAlert', {
                type: 'suspiciousActivity',
                count: metrics.suspiciousActivity,
                threshold: this.alertThresholds.suspiciousActivity
            });
        }
        
        // Update dashboard if present
        this.updateSecurityDashboard(metrics);
    }
    
    updateSecurityDashboard(metrics) {
        // Update metric cards
        const metricElements = {
            'total-api-tokens': metrics.totalApiTokens,
            'active-sessions': metrics.activeSessions,
            'security-events': metrics.securityEvents,
            'failed-logins': metrics.failedLogins
        };
        
        for (const [elementId, value] of Object.entries(metricElements)) {
            const element = document.getElementById(elementId);
            if (element) {
                element.textContent = value || '0';
            }
        }
        
        // Update charts if Chart.js is available and charts exist
        if (window.Chart && metrics.chartData) {
            this.updateCharts(metrics.chartData);
        }
    }
    
    updateCharts(chartData) {
        // Update login trends chart
        if (window.loginTrendsChart && chartData.loginTrends) {
            window.loginTrendsChart.data.datasets[0].data = chartData.loginTrends.successful;
            window.loginTrendsChart.data.datasets[1].data = chartData.loginTrends.failed;
            window.loginTrendsChart.update();
        }
    }
    
    // Event handlers
    handleSecurityEvent(event) {
        const { type, data } = event.detail;
        
        switch (type) {
            case 'failedLogin':
                this.handleFailedLogin(data);
                break;
            case 'suspiciousActivity':
                this.handleSuspiciousActivity(data);
                break;
            case 'tokenCreated':
                this.handleTokenCreated(data);
                break;
        }
    }
    
    handleTokenRevoked(data) {
        // Update UI to reflect revoked token
        const tokenRow = document.querySelector(`tr[data-token-jti="${data.tokenJti}"]`);
        if (tokenRow) {
            const statusBadge = tokenRow.querySelector('.token-status-badge');
            if (statusBadge) {
                statusBadge.textContent = 'Revoked';
                statusBadge.className = 'badge bg-danger token-status-badge';
            }
            
            // Disable revoke button
            const revokeBtn = tokenRow.querySelector('.btn-outline-danger');
            if (revokeBtn) {
                revokeBtn.disabled = true;
                revokeBtn.innerHTML = '<i class="fas fa-ban"></i>';
            }
        }
    }
    
    handleFailedLogin(data) {
        if (this.options.notifications) {
            this.showNotification(`Failed login attempt from ${data.ipAddress}`, 'warning');
        }
    }
    
    handleSuspiciousActivity(data) {
        if (this.options.notifications) {
            this.showNotification(`Suspicious activity detected: ${data.description}`, 'error');
        }
    }
    
    handleTokenCreated(data) {
        // Refresh token list if we're on the tokens page
        if (window.location.pathname.includes('api-tokens')) {
            setTimeout(() => window.location.reload(), 1000);
        }
    }
    
    // Notifications
    showNotification(message, type = 'info') {
        if (!this.options.notifications) return;
        
        // Use Bootstrap toast if available
        if (window.bootstrap && bootstrap.Toast) {
            this.showBootstrapToast(message, type);
        } else {
            // Fallback to alert
            alert(message);
        }
    }
    
    showBootstrapToast(message, type) {
        const toastContainer = this.getOrCreateToastContainer();
        
        const toastId = `toast-${Date.now()}`;
        const toastHTML = `
            <div id="${toastId}" class="toast" role="alert" aria-live="assertive" aria-atomic="true">
                <div class="toast-header">
                    <i class="fas fa-shield-alt me-2 text-${type === 'error' ? 'danger' : type}"></i>
                    <strong class="me-auto">Security</strong>
                    <button type="button" class="btn-close" data-bs-dismiss="toast" aria-label="Close"></button>
                </div>
                <div class="toast-body">
                    ${message}
                </div>
            </div>
        `;
        
        toastContainer.insertAdjacentHTML('beforeend', toastHTML);
        
        const toastElement = document.getElementById(toastId);
        const toast = new bootstrap.Toast(toastElement, { delay: 5000 });
        toast.show();
        
        // Remove toast element after it's hidden
        toastElement.addEventListener('hidden.bs.toast', () => {
            toastElement.remove();
        });
    }
    
    getOrCreateToastContainer() {
        let container = document.getElementById('toast-container');
        if (!container) {
            container = document.createElement('div');
            container.id = 'toast-container';
            container.className = 'toast-container position-fixed top-0 end-0 p-3';
            container.style.zIndex = '1080';
            document.body.appendChild(container);
        }
        return container;
    }
    
    // Utility methods
    exportSecurityData(format = 'csv', filters = {}) {
        const params = new URLSearchParams({
            ...filters,
            export: format
        });
        
        window.location.href = `${this.options.apiBaseUrl}export/?${params}`;
    }
    
    generateSecurityReport(options = {}) {
        const params = new URLSearchParams(options);
        window.open(`${this.options.apiBaseUrl}report/?${params}`, '_blank');
    }
    
    // Cleanup
    destroy() {
        this.stopAutoRefresh();
        
        // Remove event listeners
        document.removeEventListener('securityEvent', this.handleSecurityEvent);
        
        // Clear event listeners
        this.eventListeners = {};
    }
}

// Auto-initialize if in security section
document.addEventListener('DOMContentLoaded', () => {
    if (window.location.pathname.includes('/site-admin/security/')) {
        window.securityManager = new SecurityManager({
            autoRefresh: false, // Can be enabled per page
            notifications: true
        });
        
        // Global security manager reference
        window.SecurityManager = SecurityManager;
    }
});

// Export for module systems
if (typeof module !== 'undefined' && module.exports) {
    module.exports = SecurityManager;
}
if (typeof define === 'function' && define.amd) {
    define([], () => SecurityManager);
}