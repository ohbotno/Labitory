/**
 * Calendar Sharing URLs
 * Generates shareable links for calendar views and filters
 */
class CalendarSharing {
    constructor(calendar) {
        this.calendar = calendar;
        this.baseUrl = window.location.origin + window.location.pathname;
        this.initializeSharing();
    }
    
    initializeSharing() {
        this.addSharingControls();
        this.setupURLHandling();
        this.handleIncomingSharedLinks();
    }
    
    addSharingControls() {
        const controlsContainer = document.querySelector('.calendar-controls');
        if (!controlsContainer || document.querySelector('.calendar-sharing')) return;
        
        const sharingContainer = document.createElement('div');
        sharingContainer.className = 'calendar-sharing btn-group me-2';
        sharingContainer.innerHTML = `
            <div class="dropdown">
                <button class="btn btn-outline-secondary dropdown-toggle" type="button" 
                        id="sharingDropdown" data-bs-toggle="dropdown" aria-expanded="false">
                    <i class="bi bi-share"></i> Share
                </button>
                <ul class="dropdown-menu" aria-labelledby="sharingDropdown">
                    <li><h6 class="dropdown-header">Share Calendar View</h6></li>
                    <li><button class="dropdown-item" onclick="calendarSharing.shareCurrentView()">
                        <i class="bi bi-link-45deg"></i> Current View
                    </button></li>
                    <li><button class="dropdown-item" onclick="calendarSharing.shareWithFilters()">
                        <i class="bi bi-funnel"></i> Current View with Filters
                    </button></li>
                    <li><hr class="dropdown-divider"></li>
                    <li><button class="dropdown-item" onclick="calendarSharing.shareDateRange()">
                        <i class="bi bi-calendar-range"></i> Date Range
                    </button></li>
                    <li><button class="dropdown-item" onclick="calendarSharing.shareResource()">
                        <i class="bi bi-cpu"></i> Specific Resource
                    </button></li>
                    <li><hr class="dropdown-divider"></li>
                    <li><button class="dropdown-item" onclick="calendarSharing.openAdvancedSharing()">
                        <i class="bi bi-gear"></i> Advanced Options
                    </button></li>
                </ul>
            </div>
        `;
        
        controlsContainer.appendChild(sharingContainer);
        
        this.createSharingModal();
    }
    
    createSharingModal() {
        const modal = document.createElement('div');
        modal.className = 'modal fade';
        modal.id = 'calendarSharingModal';
        modal.innerHTML = `
            <div class="modal-dialog modal-lg">
                <div class="modal-content">
                    <div class="modal-header">
                        <h5 class="modal-title">Share Calendar</h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body">
                        <div class="mb-3">
                            <label for="sharing-url" class="form-label">Shareable URL</label>
                            <div class="input-group">
                                <input type="text" class="form-control" id="sharing-url" readonly>
                                <button class="btn btn-outline-secondary" type="button" 
                                        onclick="calendarSharing.copyToClipboard()" id="copy-url-btn">
                                    <i class="bi bi-clipboard"></i> Copy
                                </button>
                            </div>
                            <div class="form-text">Anyone with this link can view the calendar with the specified settings.</div>
                        </div>
                        
                        <div class="row">
                            <div class="col-md-6">
                                <div class="mb-3">
                                    <label for="share-view-type" class="form-label">View Type</label>
                                    <select class="form-select" id="share-view-type">
                                        <option value="dayGridMonth">Month View</option>
                                        <option value="timeGridWeek">Week View</option>
                                        <option value="timeGridDay">Day View</option>
                                        <option value="listWeek">List View</option>
                                    </select>
                                </div>
                            </div>
                            <div class="col-md-6">
                                <div class="mb-3">
                                    <label for="share-date" class="form-label">Date</label>
                                    <input type="date" class="form-control" id="share-date">
                                </div>
                            </div>
                        </div>
                        
                        <div class="row">
                            <div class="col-md-6">
                                <div class="mb-3">
                                    <label for="share-resource" class="form-label">Resource Filter</label>
                                    <select class="form-select" id="share-resource">
                                        <option value="">All Resources</option>
                                        <!-- Options populated dynamically -->
                                    </select>
                                </div>
                            </div>
                            <div class="col-md-6">
                                <div class="mb-3">
                                    <label class="form-label">Options</label>
                                    <div class="form-check">
                                        <input class="form-check-input" type="checkbox" id="share-business-hours" checked>
                                        <label class="form-check-label" for="share-business-hours">
                                            Show Business Hours
                                        </label>
                                    </div>
                                    <div class="form-check">
                                        <input class="form-check-input" type="checkbox" id="share-weekends" checked>
                                        <label class="form-check-label" for="share-weekends">
                                            Show Weekends
                                        </label>
                                    </div>
                                </div>
                            </div>
                        </div>
                        
                        <div class="mb-3">
                            <label for="share-expiry" class="form-label">Link Expiry</label>
                            <select class="form-select" id="share-expiry">
                                <option value="">Never</option>
                                <option value="1d">1 Day</option>
                                <option value="1w">1 Week</option>
                                <option value="1m">1 Month</option>
                                <option value="3m">3 Months</option>
                                <option value="1y">1 Year</option>
                            </select>
                            <div class="form-text">After this time, the link will no longer work.</div>
                        </div>
                        
                        <div class="alert alert-info">
                            <h6><i class="bi bi-info-circle"></i> Privacy Notice</h6>
                            <p class="mb-0">Shared calendars will only show bookings and resources that are publicly visible or that the viewer has permission to see. Personal details and private bookings are automatically filtered out.</p>
                        </div>
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Close</button>
                        <button type="button" class="btn btn-primary" onclick="calendarSharing.generateShareLink()">
                            <i class="bi bi-link-45deg"></i> Generate Link
                        </button>
                    </div>
                </div>
            </div>
        `;
        
        document.body.appendChild(modal);
        
        // Populate resource options
        this.populateResourceOptions();
        
        // Update URL when options change
        ['share-view-type', 'share-date', 'share-resource', 'share-business-hours', 'share-weekends', 'share-expiry'].forEach(id => {
            const element = document.getElementById(id);
            if (element) {
                element.addEventListener('change', () => this.updateShareUrl());
            }
        });
    }
    
    populateResourceOptions() {
        const resourceSelect = document.getElementById('share-resource');
        if (!resourceSelect) return;
        
        // Get resources from the main calendar filter if available
        const mainResourceFilter = document.getElementById('resource-filter');
        if (mainResourceFilter) {
            Array.from(mainResourceFilter.options).forEach(option => {
                if (option.value) {
                    const newOption = document.createElement('option');
                    newOption.value = option.value;
                    newOption.textContent = option.textContent;
                    resourceSelect.appendChild(newOption);
                }
            });
        }
    }
    
    shareCurrentView() {
        const currentView = this.calendar.view;
        const currentDate = this.calendar.getDate();
        
        const shareUrl = this.buildShareUrl({
            view: currentView.type,
            date: currentDate.toISOString().split('T')[0]
        });
        
        this.showQuickShare(shareUrl, 'Current Calendar View');
    }
    
    shareWithFilters() {
        const currentView = this.calendar.view;
        const currentDate = this.calendar.getDate();
        const resourceFilter = document.getElementById('resource-filter');
        
        const params = {
            view: currentView.type,
            date: currentDate.toISOString().split('T')[0]
        };
        
        if (resourceFilter && resourceFilter.value) {
            params.resource = resourceFilter.value;
        }
        
        const shareUrl = this.buildShareUrl(params);
        this.showQuickShare(shareUrl, 'Current View with Filters');
    }
    
    shareDateRange() {
        // Open modal with date range selection
        this.openAdvancedSharing();
        document.getElementById('share-view-type').value = 'timeGridWeek';
        this.updateShareUrl();
    }
    
    shareResource() {
        const resourceFilter = document.getElementById('resource-filter');
        if (!resourceFilter || !resourceFilter.value) {
            alert('Please select a resource first from the main calendar filter.');
            return;
        }
        
        const params = {
            view: 'dayGridMonth',
            resource: resourceFilter.value
        };
        
        const shareUrl = this.buildShareUrl(params);
        this.showQuickShare(shareUrl, `Resource: ${resourceFilter.options[resourceFilter.selectedIndex].text}`);
    }
    
    openAdvancedSharing() {
        // Pre-fill with current calendar state
        const currentView = this.calendar.view;
        const currentDate = this.calendar.getDate();
        const resourceFilter = document.getElementById('resource-filter');
        
        document.getElementById('share-view-type').value = currentView.type;
        document.getElementById('share-date').value = currentDate.toISOString().split('T')[0];
        
        if (resourceFilter && resourceFilter.value) {
            document.getElementById('share-resource').value = resourceFilter.value;
        }
        
        document.getElementById('share-business-hours').checked = this.calendar.getOption('businessHours') !== false;
        document.getElementById('share-weekends').checked = this.calendar.getOption('weekends') !== false;
        
        this.updateShareUrl();
        
        const modal = new bootstrap.Modal(document.getElementById('calendarSharingModal'));
        modal.show();
    }
    
    updateShareUrl() {
        const params = this.getShareParams();
        const shareUrl = this.buildShareUrl(params);
        
        const urlInput = document.getElementById('sharing-url');
        if (urlInput) {
            urlInput.value = shareUrl;
        }
    }
    
    getShareParams() {
        return {
            view: document.getElementById('share-view-type')?.value,
            date: document.getElementById('share-date')?.value,
            resource: document.getElementById('share-resource')?.value,
            businessHours: document.getElementById('share-business-hours')?.checked,
            weekends: document.getElementById('share-weekends')?.checked,
            expiry: document.getElementById('share-expiry')?.value
        };
    }
    
    buildShareUrl(params) {
        const url = new URL(this.baseUrl);
        const searchParams = new URLSearchParams();
        
        // Add share identifier
        searchParams.set('shared', '1');
        
        // Add parameters
        Object.entries(params).forEach(([key, value]) => {
            if (value !== undefined && value !== null && value !== '') {
                if (typeof value === 'boolean') {
                    searchParams.set(key, value ? '1' : '0');
                } else {
                    searchParams.set(key, value);
                }
            }
        });
        
        url.search = searchParams.toString();
        return url.toString();
    }
    
    generateShareLink() {
        this.updateShareUrl();
        
        // Optional: Save share link to server for tracking/expiry
        const params = this.getShareParams();
        if (params.expiry) {
            this.saveShareLink(params);
        }
        
        // Show success message
        this.showSharingMessage('Share link generated successfully!', 'success');
    }
    
    saveShareLink(params) {
        // Optional server-side tracking for expiry and analytics
        fetch('/api/calendar/share-links/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': this.getCSRFToken()
            },
            body: JSON.stringify({
                params: params,
                expiry: params.expiry,
                created_at: new Date().toISOString()
            })
        }).catch(error => {
            console.warn('Failed to save share link:', error);
        });
    }
    
    showQuickShare(url, title) {
        // Create quick share popup
        const popup = document.createElement('div');
        popup.className = 'quick-share-popup';
        popup.style.cssText = `
            position: fixed;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            background: white;
            border: 1px solid #dee2e6;
            border-radius: 0.375rem;
            padding: 1.5rem;
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
            z-index: 1050;
            min-width: 400px;
            max-width: 600px;
        `;
        
        popup.innerHTML = `
            <div class="d-flex justify-content-between align-items-start mb-3">
                <h6 class="mb-0">${title}</h6>
                <button type="button" class="btn-close" onclick="this.parentNode.parentNode.remove()"></button>
            </div>
            <div class="input-group mb-3">
                <input type="text" class="form-control" value="${url}" readonly id="quick-share-url">
                <button class="btn btn-outline-secondary" type="button" onclick="calendarSharing.copyToClipboard('quick-share-url')">
                    <i class="bi bi-clipboard"></i> Copy
                </button>
            </div>
            <div class="d-flex justify-content-between">
                <small class="text-muted">Share this link to let others view your calendar</small>
                <button class="btn btn-sm btn-outline-primary" onclick="calendarSharing.openAdvancedSharing(); this.parentNode.parentNode.parentNode.remove();">
                    More Options
                </button>
            </div>
        `;
        
        document.body.appendChild(popup);
        
        // Auto-remove after 10 seconds
        setTimeout(() => {
            if (popup.parentNode) {
                popup.remove();
            }
        }, 10000);
    }
    
    copyToClipboard(inputId = 'sharing-url') {
        const input = document.getElementById(inputId);
        if (!input) return;
        
        input.select();
        input.setSelectionRange(0, 99999); // For mobile devices
        
        try {
            document.execCommand('copy');
            this.showSharingMessage('Link copied to clipboard!', 'success');
            
            // Update button to show success
            const copyBtn = document.getElementById('copy-url-btn');
            if (copyBtn) {
                const originalText = copyBtn.innerHTML;
                copyBtn.innerHTML = '<i class="bi bi-check"></i> Copied!';
                copyBtn.classList.remove('btn-outline-secondary');
                copyBtn.classList.add('btn-success');
                
                setTimeout(() => {
                    copyBtn.innerHTML = originalText;
                    copyBtn.classList.remove('btn-success');
                    copyBtn.classList.add('btn-outline-secondary');
                }, 2000);
            }
        } catch (err) {
            console.error('Failed to copy: ', err);
            this.showSharingMessage('Failed to copy link. Please copy manually.', 'warning');
        }
    }
    
    setupURLHandling() {
        // Handle browser back/forward
        window.addEventListener('popstate', () => {
            this.handleIncomingSharedLinks();
        });
    }
    
    handleIncomingSharedLinks() {
        const urlParams = new URLSearchParams(window.location.search);
        
        if (urlParams.get('shared')) {
            // This is a shared link, apply the parameters
            const view = urlParams.get('view');
            const date = urlParams.get('date');
            const resource = urlParams.get('resource');
            const businessHours = urlParams.get('businessHours');
            const weekends = urlParams.get('weekends');
            
            // Show shared link indicator
            this.showSharedLinkIndicator();
            
            // Apply view type
            if (view && ['dayGridMonth', 'timeGridWeek', 'timeGridDay', 'listWeek'].includes(view)) {
                this.calendar.changeView(view);
            }
            
            // Apply date
            if (date) {
                try {
                    const targetDate = new Date(date);
                    this.calendar.gotoDate(targetDate);
                } catch (e) {
                    console.warn('Invalid date in shared link:', date);
                }
            }
            
            // Apply resource filter
            if (resource) {
                const resourceFilter = document.getElementById('resource-filter');
                if (resourceFilter) {
                    resourceFilter.value = resource;
                    resourceFilter.dispatchEvent(new Event('change'));
                }
            }
            
            // Apply business hours setting
            if (businessHours !== null) {
                this.calendar.setOption('businessHours', businessHours === '1');
            }
            
            // Apply weekends setting
            if (weekends !== null) {
                this.calendar.setOption('weekends', weekends === '1');
            }
        }
    }
    
    showSharedLinkIndicator() {
        // Remove any existing indicator
        const existing = document.querySelector('.shared-link-indicator');
        if (existing) existing.remove();
        
        // Create indicator
        const indicator = document.createElement('div');
        indicator.className = 'shared-link-indicator alert alert-info alert-dismissible fade show';
        indicator.style.marginBottom = '1rem';
        indicator.innerHTML = `
            <div class="d-flex align-items-center">
                <i class="bi bi-share me-2"></i>
                <span>You're viewing a shared calendar link</span>
                <button type="button" class="btn btn-sm btn-outline-info ms-auto me-2" onclick="calendarSharing.clearSharedView()">
                    View Full Calendar
                </button>
                <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
            </div>
        `;
        
        const calendarContainer = document.querySelector('.calendar-wrapper');
        if (calendarContainer) {
            calendarContainer.insertBefore(indicator, calendarContainer.firstChild);
        }
    }
    
    clearSharedView() {
        // Remove shared parameters from URL
        const url = new URL(window.location);
        url.search = '';
        window.history.replaceState({}, '', url);
        
        // Reload to reset to default view
        window.location.reload();
    }
    
    showSharingMessage(message, type = 'info') {
        const alertDiv = document.createElement('div');
        alertDiv.className = `alert alert-${type} alert-dismissible fade show`;
        alertDiv.style.cssText = 'position: fixed; top: 20px; right: 20px; z-index: 1060; min-width: 300px;';
        alertDiv.innerHTML = `
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        `;
        
        document.body.appendChild(alertDiv);
        
        // Auto-remove after 3 seconds
        setTimeout(() => {
            if (alertDiv.parentNode) {
                alertDiv.remove();
            }
        }, 3000);
    }
    
    getCSRFToken() {
        return document.querySelector('[name=csrfmiddlewaretoken]')?.value || '';
    }
}

// Global reference for onclick handlers
let calendarSharing;