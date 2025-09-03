/**
 * Calendar Timezone Support
 * Handles timezone conversion and display for multi-location institutions
 */
class CalendarTimezone {
    constructor(calendar, userSettings = {}) {
        this.calendar = calendar;
        this.userTimezone = userSettings.timezone || this.detectUserTimezone();
        this.systemTimezone = 'UTC'; // Server timezone
        this.dateFormat = userSettings.dateFormat || 'DD/MM/YYYY';
        this.timeFormat = userSettings.timeFormat || '24h';
        
        this.initializeTimezoneSupport();
        this.initializeUI();
    }
    
    detectUserTimezone() {
        // Try to detect user's timezone
        try {
            return Intl.DateTimeFormat().resolvedOptions().timeZone;
        } catch (e) {
            return 'UTC';
        }
    }
    
    initializeTimezoneSupport() {
        // Override FullCalendar's date formatting
        this.originalEventRender = this.calendar.getOption('eventDidMount');
        
        this.calendar.setOption('eventDidMount', (info) => {
            this.formatEventTime(info);
            if (this.originalEventRender) {
                this.originalEventRender(info);
            }
        });
        
        // Override tooltip formatting
        this.setupEventTooltips();
        
        // Handle timezone conversion for event data
        this.calendar.setOption('eventDataTransform', (eventData) => {
            return this.convertEventToUserTimezone(eventData);
        });
    }
    
    initializeUI() {
        // Add timezone selector to calendar controls
        this.addTimezoneSelector();
        
        // Add timezone info display
        this.addTimezoneInfo();
        
        // Add format preferences
        this.addFormatControls();
    }
    
    addTimezoneSelector() {
        const controlsContainer = document.querySelector('.calendar-controls');
        if (!controlsContainer || document.querySelector('.timezone-selector')) return;
        
        const timezoneContainer = document.createElement('div');
        timezoneContainer.className = 'timezone-selector btn-group me-2';
        timezoneContainer.innerHTML = `
            <div class="dropdown">
                <button class="btn btn-outline-secondary dropdown-toggle" type="button" id="timezoneDropdown" data-bs-toggle="dropdown" aria-expanded="false">
                    <i class="bi bi-globe"></i> <span id="current-timezone">${this.formatTimezoneName(this.userTimezone)}</span>
                </button>
                <ul class="dropdown-menu" aria-labelledby="timezoneDropdown" id="timezone-list">
                    <li><h6 class="dropdown-header">Select Timezone</h6></li>
                    <li><hr class="dropdown-divider"></li>
                    <li><button class="dropdown-item" onclick="calendarTimezone.setTimezone('${this.userTimezone}')">
                        <i class="bi bi-geo-alt"></i> Auto-detect (${this.formatTimezoneName(this.userTimezone)})
                    </button></li>
                    <li><hr class="dropdown-divider"></li>
                </ul>
            </div>
        `;
        
        controlsContainer.appendChild(timezoneContainer);
        
        // Populate timezone list
        this.populateTimezoneList();
    }
    
    populateTimezoneList() {
        const timezoneList = document.getElementById('timezone-list');
        if (!timezoneList) return;
        
        const commonTimezones = [
            { zone: 'UTC', group: 'Universal' },
            { zone: 'Europe/London', group: 'Europe' },
            { zone: 'Europe/Paris', group: 'Europe' },
            { zone: 'Europe/Berlin', group: 'Europe' },
            { zone: 'Europe/Rome', group: 'Europe' },
            { zone: 'Europe/Madrid', group: 'Europe' },
            { zone: 'America/New_York', group: 'North America' },
            { zone: 'America/Chicago', group: 'North America' },
            { zone: 'America/Denver', group: 'North America' },
            { zone: 'America/Los_Angeles', group: 'North America' },
            { zone: 'America/Toronto', group: 'North America' },
            { zone: 'Asia/Tokyo', group: 'Asia' },
            { zone: 'Asia/Shanghai', group: 'Asia' },
            { zone: 'Asia/Singapore', group: 'Asia' },
            { zone: 'Asia/Mumbai', group: 'Asia' },
            { zone: 'Australia/Sydney', group: 'Australia' },
            { zone: 'Australia/Melbourne', group: 'Australia' },
        ];
        
        let currentGroup = '';
        commonTimezones.forEach(tz => {
            if (tz.group !== currentGroup) {
                currentGroup = tz.group;
                const groupHeader = document.createElement('li');
                groupHeader.innerHTML = `<h6 class="dropdown-header">${tz.group}</h6>`;
                timezoneList.appendChild(groupHeader);
            }
            
            const item = document.createElement('li');
            item.innerHTML = `
                <button class="dropdown-item ${tz.zone === this.userTimezone ? 'active' : ''}" 
                        onclick="calendarTimezone.setTimezone('${tz.zone}')">
                    ${this.formatTimezoneName(tz.zone)} ${this.getTimezoneOffset(tz.zone)}
                </button>
            `;
            timezoneList.appendChild(item);
        });
    }
    
    addTimezoneInfo() {
        const calendarContainer = document.querySelector('.calendar-wrapper');
        if (!calendarContainer || document.querySelector('.timezone-info')) return;
        
        const timezoneInfo = document.createElement('div');
        timezoneInfo.className = 'timezone-info alert alert-info';
        timezoneInfo.style.marginBottom = '1rem';
        timezoneInfo.innerHTML = `
            <div class="d-flex justify-content-between align-items-center">
                <div>
                    <i class="bi bi-info-circle"></i>
                    <strong>Timezone:</strong> ${this.formatTimezoneName(this.userTimezone)} 
                    <small class="text-muted">(${this.getTimezoneOffset(this.userTimezone)})</small>
                    <span class="mx-2">|</span>
                    <strong>Current time:</strong> <span id="current-time-display">${this.getCurrentTime()}</span>
                </div>
                <button class="btn btn-sm btn-outline-secondary" onclick="calendarTimezone.toggleTimezoneSettings()">
                    <i class="bi bi-gear"></i> Settings
                </button>
            </div>
        `;
        
        calendarContainer.insertBefore(timezoneInfo, calendarContainer.firstChild);
        
        // Update current time every minute
        setInterval(() => {
            const timeDisplay = document.getElementById('current-time-display');
            if (timeDisplay) {
                timeDisplay.textContent = this.getCurrentTime();
            }
        }, 60000);
    }
    
    addFormatControls() {
        // Add format controls to settings modal
        const settingsModal = document.createElement('div');
        settingsModal.className = 'modal fade';
        settingsModal.id = 'timezoneSettingsModal';
        settingsModal.innerHTML = `
            <div class="modal-dialog">
                <div class="modal-content">
                    <div class="modal-header">
                        <h5 class="modal-title">Timezone & Format Settings</h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body">
                        <div class="mb-3">
                            <label for="timezone-select" class="form-label">Timezone</label>
                            <select class="form-select" id="timezone-select">
                                <!-- Options populated dynamically -->
                            </select>
                        </div>
                        
                        <div class="mb-3">
                            <label for="date-format-select" class="form-label">Date Format</label>
                            <select class="form-select" id="date-format-select">
                                <option value="DD/MM/YYYY">DD/MM/YYYY (European)</option>
                                <option value="MM/DD/YYYY">MM/DD/YYYY (US)</option>
                                <option value="YYYY-MM-DD">YYYY-MM-DD (ISO)</option>
                                <option value="DD-MM-YYYY">DD-MM-YYYY</option>
                                <option value="DD.MM.YYYY">DD.MM.YYYY (German)</option>
                            </select>
                        </div>
                        
                        <div class="mb-3">
                            <label for="time-format-select" class="form-label">Time Format</label>
                            <select class="form-select" id="time-format-select">
                                <option value="24h">24-hour (13:30)</option>
                                <option value="12h">12-hour (1:30 PM)</option>
                            </select>
                        </div>
                        
                        <div class="alert alert-info">
                            <strong>Preview:</strong> <span id="format-preview"></span>
                        </div>
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancel</button>
                        <button type="button" class="btn btn-primary" onclick="calendarTimezone.saveSettings()">Save Settings</button>
                    </div>
                </div>
            </div>
        `;
        
        document.body.appendChild(settingsModal);
        
        // Populate timezone select
        const timezoneSelect = settingsModal.querySelector('#timezone-select');
        const commonTimezones = [
            'UTC', 'Europe/London', 'Europe/Paris', 'Europe/Berlin', 'Europe/Rome',
            'America/New_York', 'America/Chicago', 'America/Los_Angeles',
            'Asia/Tokyo', 'Asia/Shanghai', 'Asia/Singapore', 'Australia/Sydney'
        ];
        
        commonTimezones.forEach(tz => {
            const option = document.createElement('option');
            option.value = tz;
            option.textContent = `${this.formatTimezoneName(tz)} (${this.getTimezoneOffset(tz)})`;
            option.selected = tz === this.userTimezone;
            timezoneSelect.appendChild(option);
        });
        
        // Set current values
        settingsModal.querySelector('#date-format-select').value = this.dateFormat;
        settingsModal.querySelector('#time-format-select').value = this.timeFormat;
        
        // Update preview on change
        [timezoneSelect, settingsModal.querySelector('#date-format-select'), settingsModal.querySelector('#time-format-select')].forEach(select => {
            select.addEventListener('change', () => this.updateFormatPreview());
        });
        
        // Initial preview
        setTimeout(() => this.updateFormatPreview(), 100);
    }
    
    updateFormatPreview() {
        const modal = document.querySelector('#timezoneSettingsModal');
        if (!modal) return;
        
        const timezone = modal.querySelector('#timezone-select').value;
        const dateFormat = modal.querySelector('#date-format-select').value;
        const timeFormat = modal.querySelector('#time-format-select').value;
        
        const now = new Date();
        const preview = this.formatDateTime(now, { timezone, dateFormat, timeFormat });
        
        modal.querySelector('#format-preview').textContent = preview;
    }
    
    setTimezone(timezone) {
        this.userTimezone = timezone;
        
        // Update UI
        const currentTimezoneSpan = document.getElementById('current-timezone');
        if (currentTimezoneSpan) {
            currentTimezoneSpan.textContent = this.formatTimezoneName(timezone);
        }
        
        // Update timezone info
        const timezoneInfo = document.querySelector('.timezone-info');
        if (timezoneInfo) {
            timezoneInfo.innerHTML = `
                <div class="d-flex justify-content-between align-items-center">
                    <div>
                        <i class="bi bi-info-circle"></i>
                        <strong>Timezone:</strong> ${this.formatTimezoneName(this.userTimezone)} 
                        <small class="text-muted">(${this.getTimezoneOffset(this.userTimezone)})</small>
                        <span class="mx-2">|</span>
                        <strong>Current time:</strong> <span id="current-time-display">${this.getCurrentTime()}</span>
                    </div>
                    <button class="btn btn-sm btn-outline-secondary" onclick="calendarTimezone.toggleTimezoneSettings()">
                        <i class="bi bi-gear"></i> Settings
                    </button>
                </div>
            `;
        }
        
        // Refresh calendar events to show in new timezone
        this.calendar.refetchEvents();
        
        // Save preference
        this.saveUserPreference('timezone', timezone);
    }
    
    toggleTimezoneSettings() {
        const modal = new bootstrap.Modal(document.getElementById('timezoneSettingsModal'));
        modal.show();
    }
    
    saveSettings() {
        const modal = document.querySelector('#timezoneSettingsModal');
        const timezone = modal.querySelector('#timezone-select').value;
        const dateFormat = modal.querySelector('#date-format-select').value;
        const timeFormat = modal.querySelector('#time-format-select').value;
        
        this.userTimezone = timezone;
        this.dateFormat = dateFormat;
        this.timeFormat = timeFormat;
        
        // Update UI
        this.setTimezone(timezone);
        
        // Save all preferences
        this.saveUserPreference('timezone', timezone);
        this.saveUserPreference('dateFormat', dateFormat);
        this.saveUserPreference('timeFormat', timeFormat);
        
        // Close modal
        const modalInstance = bootstrap.Modal.getInstance(modal);
        modalInstance.hide();
        
        // Show success message
        this.showTimezoneMessage('Settings saved successfully!', 'success');
    }
    
    convertEventToUserTimezone(eventData) {
        // Convert start and end times from server timezone to user timezone
        if (eventData.start) {
            eventData.start = this.convertToUserTimezone(eventData.start);
        }
        if (eventData.end) {
            eventData.end = this.convertToUserTimezone(eventData.end);
        }
        
        return eventData;
    }
    
    convertToUserTimezone(dateString) {
        // Convert UTC/server time to user timezone
        const utcDate = new Date(dateString);
        return new Date(utcDate.toLocaleString("en-US", {timeZone: this.userTimezone}));
    }
    
    convertToServerTimezone(date) {
        // Convert user timezone to UTC/server time
        const userDate = new Date(date.toLocaleString("en-US", {timeZone: this.userTimezone}));
        const utcDate = new Date(date.toLocaleString("en-US", {timeZone: "UTC"}));
        const offset = utcDate.getTime() - userDate.getTime();
        return new Date(date.getTime() + offset);
    }
    
    formatEventTime(info) {
        // Format event time display according to user preferences
        const event = info.event;
        const eventEl = info.el;
        
        // Update time display in event
        const timeEl = eventEl.querySelector('.fc-event-time');
        if (timeEl && event.start) {
            const formattedTime = this.formatTime(event.start);
            if (event.end) {
                const formattedEndTime = this.formatTime(event.end);
                timeEl.textContent = `${formattedTime} - ${formattedEndTime}`;
            } else {
                timeEl.textContent = formattedTime;
            }
        }
    }
    
    setupEventTooltips() {
        // Add timezone-aware tooltips to events
        this.calendar.setOption('eventMouseEnter', (info) => {
            const event = info.event;
            
            const tooltip = document.createElement('div');
            tooltip.className = 'timezone-tooltip';
            tooltip.style.cssText = `
                position: fixed;
                background: #333;
                color: white;
                padding: 8px 12px;
                border-radius: 4px;
                font-size: 12px;
                z-index: 1000;
                max-width: 300px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.3);
            `;
            
            const startTime = this.formatDateTime(event.start);
            const endTime = event.end ? this.formatDateTime(event.end) : '';
            const timezone = this.formatTimezoneName(this.userTimezone);
            
            tooltip.innerHTML = `
                <strong>${event.title}</strong><br>
                <strong>Start:</strong> ${startTime}<br>
                ${endTime ? `<strong>End:</strong> ${endTime}<br>` : ''}
                <strong>Timezone:</strong> ${timezone}
            `;
            
            document.body.appendChild(tooltip);
            
            // Position tooltip
            const updateTooltipPosition = (e) => {
                tooltip.style.left = (e.clientX + 10) + 'px';
                tooltip.style.top = (e.clientY - 10) + 'px';
            };
            
            info.jsEvent.target.addEventListener('mousemove', updateTooltipPosition);
            updateTooltipPosition(info.jsEvent);
            
            // Store tooltip reference
            info.el.tooltipElement = tooltip;
        });
        
        this.calendar.setOption('eventMouseLeave', (info) => {
            if (info.el.tooltipElement) {
                info.el.tooltipElement.remove();
                delete info.el.tooltipElement;
            }
        });
    }
    
    formatDateTime(date, options = {}) {
        const tz = options.timezone || this.userTimezone;
        const dateFormat = options.dateFormat || this.dateFormat;
        const timeFormat = options.timeFormat || this.timeFormat;
        
        if (!date) return '';
        
        const d = new Date(date);
        
        // Format date
        let formattedDate;
        const day = String(d.getDate()).padStart(2, '0');
        const month = String(d.getMonth() + 1).padStart(2, '0');
        const year = d.getFullYear();
        
        switch (dateFormat) {
            case 'MM/DD/YYYY':
                formattedDate = `${month}/${day}/${year}`;
                break;
            case 'YYYY-MM-DD':
                formattedDate = `${year}-${month}-${day}`;
                break;
            case 'DD-MM-YYYY':
                formattedDate = `${day}-${month}-${year}`;
                break;
            case 'DD.MM.YYYY':
                formattedDate = `${day}.${month}.${year}`;
                break;
            default: // DD/MM/YYYY
                formattedDate = `${day}/${month}/${year}`;
        }
        
        // Format time
        const formattedTime = timeFormat === '12h' ? 
            d.toLocaleTimeString('en-US', { 
                hour: 'numeric', 
                minute: '2-digit', 
                timeZone: tz 
            }) :
            d.toLocaleTimeString('en-GB', { 
                hour: '2-digit', 
                minute: '2-digit',
                hour12: false,
                timeZone: tz 
            });
        
        return `${formattedDate} ${formattedTime}`;
    }
    
    formatTime(date) {
        if (!date) return '';
        
        const d = new Date(date);
        return this.timeFormat === '12h' ? 
            d.toLocaleTimeString('en-US', { 
                hour: 'numeric', 
                minute: '2-digit', 
                timeZone: this.userTimezone 
            }) :
            d.toLocaleTimeString('en-GB', { 
                hour: '2-digit', 
                minute: '2-digit',
                hour12: false,
                timeZone: this.userTimezone 
            });
    }
    
    getCurrentTime() {
        return this.formatDateTime(new Date());
    }
    
    formatTimezoneName(timezone) {
        return timezone.replace('_', ' ').replace('/', ' / ');
    }
    
    getTimezoneOffset(timezone) {
        const now = new Date();
        const utc = new Date(now.toLocaleString('en-US', { timeZone: 'UTC' }));
        const tz = new Date(now.toLocaleString('en-US', { timeZone: timezone }));
        const offset = (tz.getTime() - utc.getTime()) / (1000 * 60 * 60);
        
        const sign = offset >= 0 ? '+' : '-';
        const hours = Math.floor(Math.abs(offset));
        const minutes = Math.floor((Math.abs(offset) % 1) * 60);
        
        return `UTC${sign}${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}`;
    }
    
    saveUserPreference(key, value) {
        // Save to localStorage
        localStorage.setItem(`calendar_${key}`, value);
        
        // Save to server if user is logged in
        if (typeof saveUserPreference === 'function') {
            saveUserPreference(key, value);
        }
    }
    
    loadUserPreferences() {
        // Load from localStorage
        const timezone = localStorage.getItem('calendar_timezone');
        const dateFormat = localStorage.getItem('calendar_dateFormat');
        const timeFormat = localStorage.getItem('calendar_timeFormat');
        
        if (timezone) this.userTimezone = timezone;
        if (dateFormat) this.dateFormat = dateFormat;
        if (timeFormat) this.timeFormat = timeFormat;
    }
    
    showTimezoneMessage(message, type = 'info') {
        const alertDiv = document.createElement('div');
        alertDiv.className = `alert alert-${type} alert-dismissible fade show`;
        alertDiv.style.cssText = 'position: fixed; top: 20px; right: 20px; z-index: 1050; min-width: 300px;';
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
}

// Global reference for onclick handlers
let calendarTimezone;