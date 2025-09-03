/**
 * Mini Calendar Widget
 * Provides a compact calendar widget for quick date navigation
 */
class MiniCalendarWidget {
    constructor(mainCalendar, container = null) {
        this.mainCalendar = mainCalendar;
        this.container = container;
        this.currentDate = new Date();
        this.selectedDate = new Date();
        this.today = new Date();
        this.bookingDates = new Set(); // Store dates with bookings for highlighting
        
        this.months = [
            'January', 'February', 'March', 'April', 'May', 'June',
            'July', 'August', 'September', 'October', 'November', 'December'
        ];
        
        this.initializeWidget();
        this.loadBookingData();
    }
    
    initializeWidget() {
        this.createContainer();
        this.render();
        this.bindEvents();
        
        // Update when main calendar changes
        this.mainCalendar.on('datesSet', (info) => {
            this.selectedDate = new Date(info.start);
            this.currentDate = new Date(info.start);
            this.render();
        });
    }
    
    createContainer() {
        if (!this.container) {
            // Create mini calendar in sidebar or floating position
            const existingContainer = document.querySelector('.mini-calendar-widget');
            if (existingContainer) {
                this.container = existingContainer;
                return;
            }
            
            // Try to add to sidebar first
            const sidebar = document.querySelector('.calendar-sidebar');
            if (sidebar) {
                this.container = document.createElement('div');
                this.container.className = 'mini-calendar-widget card mb-3';
                sidebar.appendChild(this.container);
            } else {
                // Create floating mini calendar
                this.container = document.createElement('div');
                this.container.className = 'mini-calendar-widget floating-mini-calendar';
                this.container.style.cssText = `
                    position: fixed;
                    top: 100px;
                    right: 20px;
                    z-index: 1000;
                    width: 280px;
                    background: white;
                    border: 1px solid #dee2e6;
                    border-radius: 0.375rem;
                    box-shadow: 0 4px 12px rgba(0,0,0,0.15);
                    display: none;
                `;
                document.body.appendChild(this.container);
                
                // Add toggle button to toolbar
                this.addToggleButton();
            }
        }
        
        // Add styles
        this.addStyles();
    }
    
    addStyles() {
        if (document.querySelector('#mini-calendar-styles')) return;
        
        const styles = document.createElement('style');
        styles.id = 'mini-calendar-styles';
        styles.textContent = `
            .mini-calendar-widget {
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                user-select: none;
            }
            
            .mini-calendar-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                padding: 0.75rem;
                background: #f8f9fa;
                border-bottom: 1px solid #dee2e6;
                border-radius: 0.375rem 0.375rem 0 0;
            }
            
            .mini-calendar-title {
                font-weight: 600;
                font-size: 0.875rem;
                color: #495057;
                margin: 0;
            }
            
            .mini-calendar-nav {
                display: flex;
                gap: 0.25rem;
            }
            
            .mini-calendar-nav button {
                background: none;
                border: none;
                padding: 0.25rem;
                cursor: pointer;
                border-radius: 0.25rem;
                color: #6c757d;
                font-size: 0.75rem;
                width: 24px;
                height: 24px;
                display: flex;
                align-items: center;
                justify-content: center;
            }
            
            .mini-calendar-nav button:hover {
                background: #e9ecef;
                color: #495057;
            }
            
            .mini-calendar-body {
                padding: 0.5rem;
            }
            
            .mini-calendar-weekdays {
                display: grid;
                grid-template-columns: repeat(7, 1fr);
                gap: 1px;
                margin-bottom: 0.25rem;
            }
            
            .mini-calendar-weekday {
                text-align: center;
                font-size: 0.6875rem;
                font-weight: 600;
                color: #6c757d;
                padding: 0.25rem 0;
                text-transform: uppercase;
            }
            
            .mini-calendar-days {
                display: grid;
                grid-template-columns: repeat(7, 1fr);
                gap: 1px;
            }
            
            .mini-calendar-day {
                text-align: center;
                padding: 0.375rem 0.25rem;
                cursor: pointer;
                border-radius: 0.25rem;
                font-size: 0.75rem;
                line-height: 1;
                position: relative;
                transition: all 0.2s ease;
                min-height: 28px;
                display: flex;
                align-items: center;
                justify-content: center;
            }
            
            .mini-calendar-day:hover {
                background: #e3f2fd;
            }
            
            .mini-calendar-day.other-month {
                color: #adb5bd;
            }
            
            .mini-calendar-day.today {
                background: #007bff;
                color: white;
                font-weight: 600;
            }
            
            .mini-calendar-day.selected {
                background: #28a745;
                color: white;
                font-weight: 600;
            }
            
            .mini-calendar-day.has-bookings {
                background: #fff3cd;
                border: 1px solid #ffeaa7;
                color: #856404;
            }
            
            .mini-calendar-day.has-bookings:hover {
                background: #ffecb5;
            }
            
            .mini-calendar-day.today.has-bookings {
                background: #007bff;
                color: white;
                box-shadow: 0 0 0 1px #ffc107;
            }
            
            .mini-calendar-day.selected.has-bookings {
                background: #28a745;
                color: white;
                box-shadow: 0 0 0 1px #ffc107;
            }
            
            .mini-calendar-day .booking-indicator {
                position: absolute;
                bottom: 2px;
                left: 50%;
                transform: translateX(-50%);
                width: 4px;
                height: 4px;
                border-radius: 50%;
                background: #ffc107;
            }
            
            .mini-calendar-footer {
                padding: 0.5rem 0.75rem;
                border-top: 1px solid #dee2e6;
                background: #f8f9fa;
                border-radius: 0 0 0.375rem 0.375rem;
                font-size: 0.75rem;
                color: #6c757d;
                text-align: center;
            }
            
            .floating-mini-calendar .mini-calendar-header {
                cursor: move;
            }
            
            .mini-calendar-toggle {
                position: fixed;
                top: 70px;
                right: 20px;
                z-index: 999;
                background: white;
                border: 1px solid #dee2e6;
                border-radius: 50%;
                width: 40px;
                height: 40px;
                display: flex;
                align-items: center;
                justify-content: center;
                cursor: pointer;
                box-shadow: 0 2px 8px rgba(0,0,0,0.1);
                color: #495057;
            }
            
            .mini-calendar-toggle:hover {
                background: #f8f9fa;
                color: #007bff;
            }
            
            @media (max-width: 768px) {
                .floating-mini-calendar {
                    width: 260px !important;
                    right: 10px !important;
                    top: 80px !important;
                }
                
                .mini-calendar-toggle {
                    right: 10px !important;
                }
            }
        `;
        document.head.appendChild(styles);
    }
    
    addToggleButton() {
        if (document.querySelector('.mini-calendar-toggle')) return;
        
        const toggleButton = document.createElement('div');
        toggleButton.className = 'mini-calendar-toggle';
        toggleButton.innerHTML = '<i class="bi bi-calendar3"></i>';
        toggleButton.title = 'Toggle Mini Calendar';
        
        toggleButton.addEventListener('click', () => {
            this.toggle();
        });
        
        document.body.appendChild(toggleButton);
    }
    
    toggle() {
        const isVisible = this.container.style.display !== 'none';
        this.container.style.display = isVisible ? 'none' : 'block';
        
        // Update toggle button icon
        const toggleButton = document.querySelector('.mini-calendar-toggle i');
        if (toggleButton) {
            toggleButton.className = isVisible ? 'bi bi-calendar3' : 'bi bi-x';
        }
    }
    
    render() {
        const year = this.currentDate.getFullYear();
        const month = this.currentDate.getMonth();
        
        this.container.innerHTML = `
            <div class="mini-calendar-header">
                <h6 class="mini-calendar-title">${this.months[month]} ${year}</h6>
                <div class="mini-calendar-nav">
                    <button type="button" class="prev-year" title="Previous Year">‹‹</button>
                    <button type="button" class="prev-month" title="Previous Month">‹</button>
                    <button type="button" class="today" title="Today">•</button>
                    <button type="button" class="next-month" title="Next Month">›</button>
                    <button type="button" class="next-year" title="Next Year">››</button>
                </div>
            </div>
            <div class="mini-calendar-body">
                <div class="mini-calendar-weekdays">
                    <div class="mini-calendar-weekday">Su</div>
                    <div class="mini-calendar-weekday">Mo</div>
                    <div class="mini-calendar-weekday">Tu</div>
                    <div class="mini-calendar-weekday">We</div>
                    <div class="mini-calendar-weekday">Th</div>
                    <div class="mini-calendar-weekday">Fr</div>
                    <div class="mini-calendar-weekday">Sa</div>
                </div>
                <div class="mini-calendar-days">
                    ${this.renderDays()}
                </div>
            </div>
            <div class="mini-calendar-footer">
                Click a date to navigate
            </div>
        `;
        
        // Make draggable if floating
        if (this.container.classList.contains('floating-mini-calendar')) {
            this.makeDraggable();
        }
    }
    
    renderDays() {
        const year = this.currentDate.getFullYear();
        const month = this.currentDate.getMonth();
        
        // First day of the month
        const firstDay = new Date(year, month, 1);
        const lastDay = new Date(year, month + 1, 0);
        
        // Start from the Sunday of the week containing the first day
        const startDate = new Date(firstDay);
        startDate.setDate(startDate.getDate() - firstDay.getDay());
        
        const days = [];
        const currentDate = new Date(startDate);
        
        // Generate 6 weeks (42 days) to ensure consistent layout
        for (let i = 0; i < 42; i++) {
            const dayNumber = currentDate.getDate();
            const isCurrentMonth = currentDate.getMonth() === month;
            const isToday = this.isSameDay(currentDate, this.today);
            const isSelected = this.isSameDay(currentDate, this.selectedDate);
            const hasBookings = this.hasBookingsOnDate(currentDate);
            
            let classes = ['mini-calendar-day'];
            if (!isCurrentMonth) classes.push('other-month');
            if (isToday) classes.push('today');
            if (isSelected) classes.push('selected');
            if (hasBookings) classes.push('has-bookings');
            
            const dateString = currentDate.toISOString().split('T')[0];
            
            days.push(`
                <div class="${classes.join(' ')}" data-date="${dateString}">
                    ${dayNumber}
                    ${hasBookings ? '<div class="booking-indicator"></div>' : ''}
                </div>
            `);
            
            currentDate.setDate(currentDate.getDate() + 1);
        }
        
        return days.join('');
    }
    
    bindEvents() {
        this.container.addEventListener('click', (e) => {
            const target = e.target;
            
            if (target.classList.contains('prev-year')) {
                this.currentDate.setFullYear(this.currentDate.getFullYear() - 1);
                this.render();
            } else if (target.classList.contains('next-year')) {
                this.currentDate.setFullYear(this.currentDate.getFullYear() + 1);
                this.render();
            } else if (target.classList.contains('prev-month')) {
                this.currentDate.setMonth(this.currentDate.getMonth() - 1);
                this.render();
            } else if (target.classList.contains('next-month')) {
                this.currentDate.setMonth(this.currentDate.getMonth() + 1);
                this.render();
            } else if (target.classList.contains('today')) {
                this.currentDate = new Date();
                this.selectedDate = new Date();
                this.render();
                this.mainCalendar.today();
            } else if (target.classList.contains('mini-calendar-day') && target.dataset.date) {
                const selectedDate = new Date(target.dataset.date + 'T12:00:00');
                this.selectedDate = selectedDate;
                this.render();
                
                // Navigate main calendar to selected date
                this.mainCalendar.gotoDate(selectedDate);
                
                // Show day view if clicking on a date with bookings
                if (target.classList.contains('has-bookings')) {
                    this.mainCalendar.changeView('timeGridDay');
                }
            }
        });
        
        // Keyboard navigation
        this.container.addEventListener('keydown', (e) => {
            if (e.target.classList.contains('mini-calendar-day')) {
                this.handleKeyboardNavigation(e);
            }
        });
    }
    
    handleKeyboardNavigation(e) {
        const currentDay = e.target;
        const currentDate = new Date(currentDay.dataset.date + 'T12:00:00');
        let newDate;
        
        switch (e.key) {
            case 'ArrowLeft':
                newDate = new Date(currentDate);
                newDate.setDate(newDate.getDate() - 1);
                break;
            case 'ArrowRight':
                newDate = new Date(currentDate);
                newDate.setDate(newDate.getDate() + 1);
                break;
            case 'ArrowUp':
                newDate = new Date(currentDate);
                newDate.setDate(newDate.getDate() - 7);
                break;
            case 'ArrowDown':
                newDate = new Date(currentDate);
                newDate.setDate(newDate.getDate() + 7);
                break;
            case 'Enter':
            case ' ':
                e.preventDefault();
                currentDay.click();
                return;
            default:
                return;
        }
        
        if (newDate) {
            e.preventDefault();
            this.selectedDate = newDate;
            
            // Change month if necessary
            if (newDate.getMonth() !== this.currentDate.getMonth()) {
                this.currentDate = new Date(newDate);
                this.render();
            } else {
                this.render();
            }
            
            // Focus new date
            const newDateString = newDate.toISOString().split('T')[0];
            const newDayElement = this.container.querySelector(`[data-date="${newDateString}"]`);
            if (newDayElement) {
                newDayElement.focus();
            }
        }
    }
    
    makeDraggable() {
        const header = this.container.querySelector('.mini-calendar-header');
        let isDragging = false;
        let dragOffset = { x: 0, y: 0 };
        
        header.addEventListener('mousedown', (e) => {
            isDragging = true;
            const rect = this.container.getBoundingClientRect();
            dragOffset.x = e.clientX - rect.left;
            dragOffset.y = e.clientY - rect.top;
            
            document.addEventListener('mousemove', handleDrag);
            document.addEventListener('mouseup', stopDrag);
        });
        
        const handleDrag = (e) => {
            if (!isDragging) return;
            
            this.container.style.left = (e.clientX - dragOffset.x) + 'px';
            this.container.style.top = (e.clientY - dragOffset.y) + 'px';
            this.container.style.right = 'auto';
        };
        
        const stopDrag = () => {
            isDragging = false;
            document.removeEventListener('mousemove', handleDrag);
            document.removeEventListener('mouseup', stopDrag);
        };
    }
    
    loadBookingData() {
        // Load booking data to highlight dates with bookings
        this.updateBookingDates();
        
        // Refresh booking data when main calendar events change
        this.mainCalendar.on('eventsSet', () => {
            this.updateBookingDates();
        });
    }
    
    updateBookingDates() {
        this.bookingDates.clear();
        
        const events = this.mainCalendar.getEvents();
        events.forEach(event => {
            if (event.start) {
                const dateString = event.start.toISOString().split('T')[0];
                this.bookingDates.add(dateString);
            }
        });
        
        // Re-render to show updated booking indicators
        if (this.container.innerHTML) {
            this.render();
        }
    }
    
    hasBookingsOnDate(date) {
        const dateString = date.toISOString().split('T')[0];
        return this.bookingDates.has(dateString);
    }
    
    isSameDay(date1, date2) {
        return date1.toDateString() === date2.toDateString();
    }
    
    // Public methods
    goToDate(date) {
        this.selectedDate = new Date(date);
        this.currentDate = new Date(date);
        this.render();
    }
    
    refresh() {
        this.updateBookingDates();
        this.render();
    }
    
    destroy() {
        if (this.container && this.container.parentNode) {
            this.container.parentNode.removeChild(this.container);
        }
        
        const toggleButton = document.querySelector('.mini-calendar-toggle');
        if (toggleButton && toggleButton.parentNode) {
            toggleButton.parentNode.removeChild(toggleButton);
        }
    }
}