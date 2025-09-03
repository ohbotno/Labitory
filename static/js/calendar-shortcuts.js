/**
 * Calendar Shortcuts - Keyboard shortcuts for calendar navigation
 */
class CalendarShortcuts {
    constructor(calendar) {
        this.calendar = calendar;
        this.initializeShortcuts();
    }

    initializeShortcuts() {
        document.addEventListener('keydown', (e) => {
            // Skip if user is typing in an input field
            if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') {
                return;
            }

            // Navigation shortcuts
            switch(e.key) {
                case 'ArrowLeft':
                    if (e.ctrlKey || e.metaKey) {
                        this.calendar.prev();
                        e.preventDefault();
                    }
                    break;
                case 'ArrowRight':
                    if (e.ctrlKey || e.metaKey) {
                        this.calendar.next();
                        e.preventDefault();
                    }
                    break;
                case 't':
                    // Go to today
                    if (!e.ctrlKey && !e.metaKey && !e.altKey) {
                        this.calendar.today();
                        e.preventDefault();
                    }
                    break;
                case 'm':
                    // Month view
                    if (!e.ctrlKey && !e.metaKey && !e.altKey) {
                        this.calendar.changeView('dayGridMonth');
                        e.preventDefault();
                    }
                    break;
                case 'w':
                    // Week view
                    if (!e.ctrlKey && !e.metaKey && !e.altKey) {
                        this.calendar.changeView('timeGridWeek');
                        e.preventDefault();
                    }
                    break;
                case 'd':
                    // Day view
                    if (!e.ctrlKey && !e.metaKey && !e.altKey) {
                        this.calendar.changeView('timeGridDay');
                        e.preventDefault();
                    }
                    break;
            }
        });
    }
}