/**
 * Calendar Print Fallback - Improved print functionality for calendar
 */
class CalendarPrintFallback {
    constructor(calendar) {
        this.calendar = calendar;
        this.initializePrintStyles();
    }

    initializePrintStyles() {
        // Add print-specific styles
        const styleSheet = document.createElement('style');
        styleSheet.innerHTML = `
            @media print {
                /* Hide non-essential elements */
                .navbar, .sidebar, .btn, .modal, .fc-toolbar-chunk button {
                    display: none !important;
                }
                
                /* Ensure calendar is visible and properly sized */
                #calendar {
                    width: 100% !important;
                    height: auto !important;
                }
                
                /* Make sure all events are visible */
                .fc-event {
                    color: #000 !important;
                    background-color: #fff !important;
                    border: 1px solid #000 !important;
                    -webkit-print-color-adjust: exact;
                    print-color-adjust: exact;
                }
                
                /* Ensure text is readable */
                .fc-event-title, .fc-event-time {
                    color: #000 !important;
                    font-size: 10pt !important;
                }
                
                /* Show full calendar without scrolling */
                .fc-scroller {
                    overflow: visible !important;
                    height: auto !important;
                }
                
                /* Page break handling */
                .fc-day {
                    page-break-inside: avoid;
                }
            }
        `;
        document.head.appendChild(styleSheet);
    }

    // Method to trigger print with proper preparation
    print() {
        // Store current view state
        const currentView = this.calendar.view.type;
        
        // Switch to month view for better printing if in day/week view
        if (currentView === 'timeGridDay') {
            this.calendar.changeView('dayGridMonth');
            setTimeout(() => {
                window.print();
                // Restore original view after printing
                setTimeout(() => {
                    this.calendar.changeView(currentView);
                }, 100);
            }, 100);
        } else {
            window.print();
        }
    }
}