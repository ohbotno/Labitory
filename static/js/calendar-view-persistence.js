/**
 * Calendar View Persistence - Remember user's calendar view preferences
 */
class CalendarViewPersistence {
    constructor(calendar) {
        this.calendar = calendar;
        this.storageKey = 'calendar-view-preferences';
        this.loadPreferences();
        this.attachListeners();
    }

    loadPreferences() {
        const saved = localStorage.getItem(this.storageKey);
        if (saved) {
            try {
                const prefs = JSON.parse(saved);
                
                // Restore view type if saved
                if (prefs.viewType) {
                    this.calendar.changeView(prefs.viewType);
                }
                
                // Restore date if it's within reasonable range (last 30 days)
                if (prefs.currentDate) {
                    const savedDate = new Date(prefs.currentDate);
                    const now = new Date();
                    const daysDiff = Math.abs(now - savedDate) / (1000 * 60 * 60 * 24);
                    
                    if (daysDiff <= 30) {
                        this.calendar.gotoDate(savedDate);
                    }
                }
            } catch (e) {
                console.error('Error loading calendar preferences:', e);
            }
        }
    }

    savePreferences() {
        const prefs = {
            viewType: this.calendar.view.type,
            currentDate: this.calendar.getDate().toISOString(),
            savedAt: new Date().toISOString()
        };
        
        try {
            localStorage.setItem(this.storageKey, JSON.stringify(prefs));
        } catch (e) {
            console.error('Error saving calendar preferences:', e);
        }
    }

    attachListeners() {
        // Save preferences when view changes
        this.calendar.on('viewDidMount', () => {
            this.savePreferences();
        });
        
        // Save preferences when date changes
        this.calendar.on('datesSet', () => {
            this.savePreferences();
        });
    }

    // Method to clear saved preferences
    clearPreferences() {
        localStorage.removeItem(this.storageKey);
    }
}