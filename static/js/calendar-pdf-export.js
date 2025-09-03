/**
 * Calendar PDF Export - Export calendar view to PDF
 */
class CalendarPDFExport {
    constructor(calendar) {
        this.calendar = calendar;
        this.initializeExport();
    }

    initializeExport() {
        // Add export button if it doesn't exist
        const toolbar = document.querySelector('.fc-toolbar-chunk:last-child');
        if (toolbar && !document.getElementById('calendar-pdf-export')) {
            const exportBtn = document.createElement('button');
            exportBtn.id = 'calendar-pdf-export';
            exportBtn.className = 'btn btn-sm btn-outline-secondary ms-2';
            exportBtn.innerHTML = '<i class="bi bi-file-pdf"></i> Export PDF';
            exportBtn.title = 'Export current view to PDF';
            exportBtn.onclick = () => this.exportToPDF();
            toolbar.appendChild(exportBtn);
        }
    }

    exportToPDF() {
        // Use browser's print functionality as PDF export
        window.print();
    }

    // Helper method to prepare calendar for printing
    prepareForPrint() {
        // The CSS should handle print styles
        // This is a placeholder for any JavaScript-based adjustments
    }
}