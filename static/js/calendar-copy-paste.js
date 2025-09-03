/**
 * Calendar Copy/Paste Functionality
 * Provides advanced copy and paste capabilities for bookings in the calendar
 */
class CalendarCopyPaste {
    constructor(calendar) {
        this.calendar = calendar;
        this.clipboard = null;
        this.selectedEvents = new Set();
        this.multiSelectMode = false;
        this.pasteCount = 0;
        
        this.initializeEventHandlers();
        this.initializeUI();
    }
    
    initializeEventHandlers() {
        // Keyboard shortcuts
        document.addEventListener('keydown', (e) => {
            // Only handle if no input is focused
            if (document.activeElement.tagName !== 'INPUT' && 
                document.activeElement.tagName !== 'TEXTAREA' && 
                !document.activeElement.isContentEditable) {
                
                if (e.ctrlKey || e.metaKey) {
                    switch (e.key.toLowerCase()) {
                        case 'c':
                            e.preventDefault();
                            this.copySelectedEvents();
                            break;
                        case 'v':
                            e.preventDefault();
                            this.showPasteDialog();
                            break;
                        case 'x':
                            e.preventDefault();
                            this.cutSelectedEvents();
                            break;
                        case 'a':
                            if (e.shiftKey) { // Ctrl+Shift+A to select all visible events
                                e.preventDefault();
                                this.selectAllVisibleEvents();
                            }
                            break;
                        case 'd':
                            e.preventDefault();
                            this.duplicateSelectedEvents();
                            break;
                    }
                }
                
                // ESC to clear selection
                if (e.key === 'Escape') {
                    this.clearSelection();
                }
                
                // Delete key to delete selected events
                if (e.key === 'Delete' && this.selectedEvents.size > 0) {
                    e.preventDefault();
                    this.deleteSelectedEvents();
                }
            }
        });
        
        // Click handling for event selection
        this.calendar.on('eventClick', (info) => {
            if (info.jsEvent.ctrlKey || info.jsEvent.metaKey) {
                // Multi-select mode
                info.jsEvent.preventDefault();
                this.toggleEventSelection(info.event);
            } else if (info.jsEvent.shiftKey && this.selectedEvents.size > 0) {
                // Range select mode
                info.jsEvent.preventDefault();
                this.selectEventRange(info.event);
            } else {
                // Single select (clear others first)
                if (!this.selectedEvents.has(info.event.id)) {
                    this.clearSelection();
                    this.selectEvent(info.event);
                }
            }
        });
        
        // Context menu for right-click operations
        this.calendar.on('eventMouseEnter', (info) => {
            info.el.addEventListener('contextmenu', (e) => {
                e.preventDefault();
                this.showContextMenu(e, info.event);
            });
        });
        
        // Click outside to clear selection
        document.addEventListener('click', (e) => {
            if (!e.target.closest('.fc-event') && !e.target.closest('.copy-paste-menu')) {
                this.clearSelection();
            }
        });
    }
    
    initializeUI() {
        // Add copy/paste buttons to toolbar if not already present
        const toolbar = document.querySelector('.calendar-controls');
        if (toolbar && !document.querySelector('.copy-paste-controls')) {
            const copyPasteControls = document.createElement('div');
            copyPasteControls.className = 'copy-paste-controls btn-group me-2';
            copyPasteControls.innerHTML = `
                <button type="button" class="btn btn-outline-secondary" id="copy-btn" title="Copy selected bookings (Ctrl+C)" disabled>
                    <i class="bi bi-clipboard"></i>
                </button>
                <button type="button" class="btn btn-outline-secondary" id="paste-btn" title="Paste bookings (Ctrl+V)" disabled>
                    <i class="bi bi-clipboard-check"></i>
                </button>
                <button type="button" class="btn btn-outline-secondary" id="duplicate-btn" title="Duplicate selected bookings (Ctrl+D)" disabled>
                    <i class="bi bi-copy"></i>
                </button>
            `;
            toolbar.appendChild(copyPasteControls);
            
            // Add event listeners for toolbar buttons
            document.getElementById('copy-btn').addEventListener('click', () => this.copySelectedEvents());
            document.getElementById('paste-btn').addEventListener('click', () => this.showPasteDialog());
            document.getElementById('duplicate-btn').addEventListener('click', () => this.duplicateSelectedEvents());
        }
        
        // Add selection indicator styles
        if (!document.querySelector('#copy-paste-styles')) {
            const styles = document.createElement('style');
            styles.id = 'copy-paste-styles';
            styles.textContent = `
                .fc-event.selected {
                    box-shadow: 0 0 0 2px #007bff !important;
                    opacity: 0.8 !important;
                    z-index: 999 !important;
                }
                
                .fc-event.copied {
                    opacity: 0.6 !important;
                    border-style: dashed !important;
                }
                
                .copy-paste-menu {
                    position: fixed;
                    background: white;
                    border: 1px solid #ccc;
                    border-radius: 4px;
                    box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                    padding: 0.5rem 0;
                    z-index: 1000;
                    min-width: 160px;
                }
                
                .copy-paste-menu-item {
                    display: block;
                    width: 100%;
                    padding: 0.5rem 1rem;
                    border: none;
                    background: none;
                    text-align: left;
                    cursor: pointer;
                    font-size: 0.875rem;
                }
                
                .copy-paste-menu-item:hover {
                    background-color: #f8f9fa;
                }
                
                .copy-paste-menu-item:disabled {
                    opacity: 0.5;
                    cursor: not-allowed;
                }
                
                .selection-info {
                    position: fixed;
                    top: 10px;
                    right: 10px;
                    background: #007bff;
                    color: white;
                    padding: 0.5rem 1rem;
                    border-radius: 4px;
                    font-size: 0.875rem;
                    z-index: 1001;
                    display: none;
                }
            `;
            document.head.appendChild(styles);
        }
    }
    
    selectEvent(event) {
        this.selectedEvents.add(event.id);
        this.updateEventAppearance(event, 'selected');
        this.updateUIState();
    }
    
    deselectEvent(event) {
        this.selectedEvents.delete(event.id);
        this.updateEventAppearance(event, 'deselected');
        this.updateUIState();
    }
    
    toggleEventSelection(event) {
        if (this.selectedEvents.has(event.id)) {
            this.deselectEvent(event);
        } else {
            this.selectEvent(event);
        }
    }
    
    clearSelection() {
        this.selectedEvents.forEach(eventId => {
            const event = this.calendar.getEventById(eventId);
            if (event) {
                this.updateEventAppearance(event, 'deselected');
            }
        });
        this.selectedEvents.clear();
        this.updateUIState();
        this.hideSelectionInfo();
    }
    
    selectAllVisibleEvents() {
        const visibleEvents = this.calendar.getEvents();
        visibleEvents.forEach(event => {
            this.selectEvent(event);
        });
        this.showSelectionInfo(`Selected ${visibleEvents.length} events`);
    }
    
    selectEventRange(endEvent) {
        // Find the last selected event to create a range
        const allEvents = this.calendar.getEvents().sort((a, b) => a.start - b.start);
        const lastSelectedEvent = Array.from(this.selectedEvents)
            .map(id => this.calendar.getEventById(id))
            .filter(e => e)
            .sort((a, b) => a.start - b.start)
            .pop();
        
        if (!lastSelectedEvent) return;
        
        const startIndex = allEvents.findIndex(e => e.id === lastSelectedEvent.id);
        const endIndex = allEvents.findIndex(e => e.id === endEvent.id);
        
        if (startIndex !== -1 && endIndex !== -1) {
            const start = Math.min(startIndex, endIndex);
            const end = Math.max(startIndex, endIndex);
            
            for (let i = start; i <= end; i++) {
                this.selectEvent(allEvents[i]);
            }
        }
    }
    
    updateEventAppearance(event, state) {
        const eventEl = event.el;
        if (!eventEl) return;
        
        switch (state) {
            case 'selected':
                eventEl.classList.add('selected');
                eventEl.classList.remove('copied');
                break;
            case 'deselected':
                eventEl.classList.remove('selected', 'copied');
                break;
            case 'copied':
                eventEl.classList.add('copied');
                break;
        }
    }
    
    updateUIState() {
        const hasSelection = this.selectedEvents.size > 0;
        const hasClipboard = this.clipboard !== null;
        
        // Update toolbar buttons
        const copyBtn = document.getElementById('copy-btn');
        const pasteBtn = document.getElementById('paste-btn');
        const duplicateBtn = document.getElementById('duplicate-btn');
        
        if (copyBtn) copyBtn.disabled = !hasSelection;
        if (pasteBtn) pasteBtn.disabled = !hasClipboard;
        if (duplicateBtn) duplicateBtn.disabled = !hasSelection;
        
        // Show selection count
        if (hasSelection) {
            this.showSelectionInfo(`${this.selectedEvents.size} booking${this.selectedEvents.size > 1 ? 's' : ''} selected`);
        } else {
            this.hideSelectionInfo();
        }
    }
    
    showSelectionInfo(text) {
        let info = document.querySelector('.selection-info');
        if (!info) {
            info = document.createElement('div');
            info.className = 'selection-info';
            document.body.appendChild(info);
        }
        info.textContent = text;
        info.style.display = 'block';
        
        // Auto-hide after 3 seconds
        clearTimeout(this.selectionInfoTimeout);
        this.selectionInfoTimeout = setTimeout(() => {
            this.hideSelectionInfo();
        }, 3000);
    }
    
    hideSelectionInfo() {
        const info = document.querySelector('.selection-info');
        if (info) {
            info.style.display = 'none';
        }
    }
    
    copySelectedEvents() {
        if (this.selectedEvents.size === 0) return;
        
        const events = Array.from(this.selectedEvents)
            .map(id => this.calendar.getEventById(id))
            .filter(event => event)
            .map(event => ({
                id: event.id,
                title: event.title,
                start: event.start,
                end: event.end,
                extendedProps: event.extendedProps,
                backgroundColor: event.backgroundColor,
                borderColor: event.borderColor,
                textColor: event.textColor
            }));
        
        this.clipboard = {
            events: events,
            operation: 'copy',
            timestamp: new Date()
        };
        
        // Update visual state
        events.forEach(eventData => {
            const event = this.calendar.getEventById(eventData.id);
            if (event) {
                this.updateEventAppearance(event, 'copied');
            }
        });
        
        this.updateUIState();
        this.showSelectionInfo(`Copied ${events.length} booking${events.length > 1 ? 's' : ''}`);
    }
    
    cutSelectedEvents() {
        this.copySelectedEvents();
        if (this.clipboard) {
            this.clipboard.operation = 'cut';
        }
    }
    
    showPasteDialog() {
        if (!this.clipboard || this.clipboard.events.length === 0) return;
        
        const modal = document.createElement('div');
        modal.className = 'modal fade';
        modal.innerHTML = `
            <div class="modal-dialog">
                <div class="modal-content">
                    <div class="modal-header">
                        <h5 class="modal-title">Paste Bookings</h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body">
                        <p>Paste ${this.clipboard.events.length} booking${this.clipboard.events.length > 1 ? 's' : ''}?</p>
                        
                        <div class="mb-3">
                            <label class="form-label">Paste mode:</label>
                            <div class="form-check">
                                <input class="form-check-input" type="radio" name="pasteMode" id="pasteExact" value="exact" checked>
                                <label class="form-check-label" for="pasteExact">
                                    Exact copy (same dates and times)
                                </label>
                            </div>
                            <div class="form-check">
                                <input class="form-check-input" type="radio" name="pasteMode" id="pasteOffset" value="offset">
                                <label class="form-check-label" for="pasteOffset">
                                    Relative to selected date/time
                                </label>
                            </div>
                        </div>
                        
                        <div id="offsetOptions" style="display: none;">
                            <div class="mb-3">
                                <label for="offsetDate" class="form-label">Target start date:</label>
                                <input type="date" class="form-control" id="offsetDate">
                            </div>
                            <div class="mb-3">
                                <label for="offsetTime" class="form-label">Target start time:</label>
                                <input type="time" class="form-control" id="offsetTime" value="09:00">
                            </div>
                        </div>
                        
                        <div class="mb-3">
                            <div class="form-check">
                                <input class="form-check-input" type="checkbox" id="pasteAsTemplate" value="template">
                                <label class="form-check-label" for="pasteAsTemplate">
                                    Create as new bookings (not duplicates)
                                </label>
                            </div>
                        </div>
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancel</button>
                        <button type="button" class="btn btn-primary" id="confirmPaste">Paste</button>
                    </div>
                </div>
            </div>
        `;
        
        document.body.appendChild(modal);
        const bsModal = new bootstrap.Modal(modal);
        
        // Handle paste mode change
        modal.querySelectorAll('input[name="pasteMode"]').forEach(radio => {
            radio.addEventListener('change', () => {
                const offsetOptions = modal.querySelector('#offsetOptions');
                offsetOptions.style.display = radio.value === 'offset' ? 'block' : 'none';
            });
        });
        
        // Set default date to today
        const today = new Date().toISOString().split('T')[0];
        modal.querySelector('#offsetDate').value = today;
        
        // Handle paste confirmation
        modal.querySelector('#confirmPaste').addEventListener('click', () => {
            const mode = modal.querySelector('input[name="pasteMode"]:checked').value;
            const asTemplate = modal.querySelector('#pasteAsTemplate').checked;
            
            let targetStart = null;
            if (mode === 'offset') {
                const date = modal.querySelector('#offsetDate').value;
                const time = modal.querySelector('#offsetTime').value;
                targetStart = new Date(`${date}T${time}`);
            }
            
            this.pasteEvents(mode, targetStart, asTemplate);
            bsModal.hide();
        });
        
        bsModal.show();
        
        // Clean up modal after hiding
        modal.addEventListener('hidden.bs.modal', () => {
            modal.remove();
        });
    }
    
    pasteEvents(mode = 'exact', targetStart = null, asTemplate = false) {
        if (!this.clipboard || this.clipboard.events.length === 0) return;
        
        const events = this.clipboard.events;
        let pastedCount = 0;
        
        if (mode === 'offset' && targetStart) {
            // Calculate offset from first event
            const firstEvent = events[0];
            const originalStart = new Date(firstEvent.start);
            const offset = targetStart.getTime() - originalStart.getTime();
            
            events.forEach(eventData => {
                const newStart = new Date(new Date(eventData.start).getTime() + offset);
                const newEnd = new Date(new Date(eventData.end).getTime() + offset);
                
                this.createBookingFromClipboard(eventData, newStart, newEnd, asTemplate);
                pastedCount++;
            });
        } else {
            // Exact copy
            events.forEach(eventData => {
                this.createBookingFromClipboard(eventData, eventData.start, eventData.end, asTemplate);
                pastedCount++;
            });
        }
        
        // If it was a cut operation, delete original events
        if (this.clipboard.operation === 'cut') {
            this.deleteOriginalEvents();
        }
        
        this.showSelectionInfo(`Pasted ${pastedCount} booking${pastedCount > 1 ? 's' : ''}`);
        this.calendar.refetchEvents();
        
        // Clear clipboard after paste
        this.clipboard = null;
        this.updateUIState();
    }
    
    createBookingFromClipboard(eventData, newStart, newEnd, asTemplate) {
        const formData = new FormData();
        formData.append('title', asTemplate ? `Copy of ${eventData.title}` : eventData.title);
        formData.append('start_time', new Date(newStart).toISOString().slice(0, 16));
        formData.append('end_time', new Date(newEnd).toISOString().slice(0, 16));
        formData.append('description', eventData.extendedProps.description || '');
        formData.append('resource_id', eventData.extendedProps.resource_id);
        
        fetch('/api/bookings/', {
            method: 'POST',
            headers: {
                'X-CSRFToken': getCSRFToken()
            },
            body: formData
        })
        .then(response => response.json())
        .then(data => {
            if (!response.ok) {
                console.error('Error creating booking:', data);
            }
        })
        .catch(error => {
            console.error('Error creating booking:', error);
        });
    }
    
    duplicateSelectedEvents() {
        if (this.selectedEvents.size === 0) return;
        
        const events = Array.from(this.selectedEvents)
            .map(id => this.calendar.getEventById(id))
            .filter(event => event);
        
        events.forEach(event => {
            // Duplicate to next available slot (e.g., next week)
            const nextWeekStart = new Date(event.start);
            nextWeekStart.setDate(nextWeekStart.getDate() + 7);
            
            const nextWeekEnd = new Date(event.end);
            nextWeekEnd.setDate(nextWeekEnd.getDate() + 7);
            
            this.createBookingFromClipboard({
                title: event.title,
                extendedProps: event.extendedProps
            }, nextWeekStart, nextWeekEnd, true);
        });
        
        this.showSelectionInfo(`Duplicated ${events.length} booking${events.length > 1 ? 's' : ''} to next week`);
        
        setTimeout(() => {
            this.calendar.refetchEvents();
        }, 1000);
    }
    
    deleteSelectedEvents() {
        if (this.selectedEvents.size === 0) return;
        
        if (confirm(`Delete ${this.selectedEvents.size} selected booking${this.selectedEvents.size > 1 ? 's' : ''}?`)) {
            this.deleteOriginalEvents();
            this.clearSelection();
        }
    }
    
    deleteOriginalEvents() {
        this.selectedEvents.forEach(eventId => {
            fetch(`/api/bookings/${eventId}/`, {
                method: 'DELETE',
                headers: {
                    'X-CSRFToken': getCSRFToken()
                }
            })
            .catch(error => {
                console.error('Error deleting booking:', error);
            });
        });
        
        setTimeout(() => {
            this.calendar.refetchEvents();
        }, 500);
    }
    
    showContextMenu(event, calendarEvent) {
        // Remove existing context menu
        const existingMenu = document.querySelector('.copy-paste-menu');
        if (existingMenu) {
            existingMenu.remove();
        }
        
        const menu = document.createElement('div');
        menu.className = 'copy-paste-menu';
        menu.style.left = event.pageX + 'px';
        menu.style.top = event.pageY + 'px';
        
        const isSelected = this.selectedEvents.has(calendarEvent.id);
        const hasClipboard = this.clipboard !== null;
        
        menu.innerHTML = `
            <button class="copy-paste-menu-item" onclick="this.selectEvent">${isSelected ? 'Deselect' : 'Select'}</button>
            <button class="copy-paste-menu-item" onclick="this.copyContextEvent">Copy</button>
            <button class="copy-paste-menu-item" onclick="this.cutContextEvent">Cut</button>
            <button class="copy-paste-menu-item" ${!hasClipboard ? 'disabled' : ''} onclick="this.pasteHere">Paste Here</button>
            <hr style="margin: 0.25rem 0;">
            <button class="copy-paste-menu-item" onclick="this.duplicateContextEvent">Duplicate</button>
            <button class="copy-paste-menu-item" onclick="this.deleteContextEvent">Delete</button>
        `;
        
        document.body.appendChild(menu);
        
        // Store current event for context operations
        this.contextEvent = calendarEvent;
        
        // Add click handlers
        menu.querySelector('button:nth-child(1)').onclick = () => {
            this.toggleEventSelection(this.contextEvent);
            menu.remove();
        };
        
        menu.querySelector('button:nth-child(2)').onclick = () => {
            if (!isSelected) this.selectEvent(this.contextEvent);
            this.copySelectedEvents();
            menu.remove();
        };
        
        menu.querySelector('button:nth-child(3)').onclick = () => {
            if (!isSelected) this.selectEvent(this.contextEvent);
            this.cutSelectedEvents();
            menu.remove();
        };
        
        menu.querySelector('button:nth-child(4)').onclick = () => {
            if (hasClipboard) {
                // Paste at this event's time
                const targetStart = new Date(this.contextEvent.start);
                this.pasteEvents('offset', targetStart, false);
            }
            menu.remove();
        };
        
        menu.querySelector('button:nth-child(6)').onclick = () => {
            if (!isSelected) this.selectEvent(this.contextEvent);
            this.duplicateSelectedEvents();
            menu.remove();
        };
        
        menu.querySelector('button:nth-child(7)').onclick = () => {
            if (!isSelected) this.selectEvent(this.contextEvent);
            this.deleteSelectedEvents();
            menu.remove();
        };
        
        // Remove menu when clicking outside
        setTimeout(() => {
            document.addEventListener('click', function removeMenu() {
                menu.remove();
                document.removeEventListener('click', removeMenu);
            }, 100);
        });
    }
}

// Helper function to get CSRF token
function getCSRFToken() {
    return document.querySelector('[name=csrfmiddlewaretoken]').value;
}