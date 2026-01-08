// Notification System
document.addEventListener('DOMContentLoaded', () => {
    console.log("Notification System Loaded");
    
    // Audio Context for generated sound
    const AudioContext = window.AudioContext || window.webkitAudioContext;
    let audioContext;

    function initAudio() {
        if (!audioContext) {
            audioContext = new AudioContext();
        }
        if (audioContext.state === 'suspended') {
            audioContext.resume();
        }
    }

    // Initialize audio on first interaction
    document.addEventListener('click', initAudio, { once: true });
    document.addEventListener('keydown', initAudio, { once: true });

    function playNotificationSound() {
        if (!audioContext) {
            initAudio();
        }
        
        if (!audioContext) return;

        try {
            const oscillator = audioContext.createOscillator();
            const gainNode = audioContext.createGain();

            oscillator.type = 'sine';
            oscillator.frequency.setValueAtTime(500, audioContext.currentTime); // 500Hz
            oscillator.frequency.exponentialRampToValueAtTime(1000, audioContext.currentTime + 0.1); // Chirp up

            gainNode.gain.setValueAtTime(0.3, audioContext.currentTime);
            gainNode.gain.exponentialRampToValueAtTime(0.01, audioContext.currentTime + 0.5);

            oscillator.connect(gainNode);
            gainNode.connect(audioContext.destination);

            oscillator.start();
            oscillator.stop(audioContext.currentTime + 0.5);
            console.log("Sound played");
        } catch (e) {
            console.error("Audio Playback Failed:", e);
        }
    }

    function showToast(title, message, type) {
        // Determine Colors
        let bg = '#1f2937';
        let text = '#ffffff';
        if (typeof themeConfig !== 'undefined' && typeof currentTheme !== 'undefined') {
            const theme = themeConfig[currentTheme] ? currentTheme : 'theme-default';
            if (themeConfig[theme]) {
                bg = themeConfig[theme].surfaceDark;
                text = themeConfig[theme].textMain;
            }
        }

        if (typeof Swal !== 'undefined') {
            const Toast = Swal.mixin({
                toast: true,
                position: 'top-end',
                showConfirmButton: false,
                timer: 5000,
                timerProgressBar: true,
                background: bg,
                color: text,
                didOpen: (toast) => {
                    toast.addEventListener('mouseenter', Swal.stopTimer)
                    toast.addEventListener('mouseleave', Swal.resumeTimer)
                    toast.addEventListener('click', () => {
                        window.location.href = '/core/notifications/';
                    })
                }
            });

            Toast.fire({
                icon: (type || 'info').toLowerCase(),
                title: title,
                text: message
            });
        }
    }

    // Check for pending notification from reload
    const pendingNotification = sessionStorage.getItem('pending_notification');
    if (pendingNotification) {
        try {
            const data = JSON.parse(pendingNotification);
            console.log("Showing pending notification after reload");
            
            // Small delay to ensure interaction/audio init if possible (though auto-play might block sound)
            // We rely on user having interacted previously or browser allowing it.
            setTimeout(() => {
                playNotificationSound();
                showToast(data.latest_title, data.latest_message, data.latest_type);
                
                // Automatically mark as read after showing
                if (data.latest_id) {
                    fetch(`/api/notifications/${data.latest_id}/read/`, {
                        method: 'POST',
                        headers: {
                            'X-CSRFToken': getCookie('csrftoken') || ''
                        }
                    }).catch(err => console.error("Failed to mark read:", err));
                }
            }, 500);
            
            sessionStorage.removeItem('pending_notification');
        } catch (e) {
            console.error("Error parsing pending notification", e);
        }
    }

    // Helper to get cookie
    function getCookie(name) {
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    }

    function checkNotifications() {
        fetch('/api/notifications/unread/')
            .then(response => {
                if (response.status === 401 || response.status === 403) {
                    return null; // Not logged in
                }
                if (!response.ok) {
                    throw new Error('Network response was not ok');
                }
                return response.json();
            })
            .then(data => {
                if (!data) return;

                // Update Badge
                const badge = document.getElementById('notification-badge');
                if (badge) {
                    if (data.unread_count > 0) {
                        badge.textContent = data.unread_count;
                        badge.classList.remove('hidden');
                    } else {
                        badge.classList.add('hidden');
                    }
                }

                // Parse IDs as integers for reliable comparison
                const latestId = parseInt(data.latest_id);
                let lastSeenId = parseInt(localStorage.getItem('last_notification_id')) || 0;

                // Check for new notification
                if (latestId && latestId > lastSeenId) {
                    console.log(`New Notification Detected: ID ${latestId} > LastSeen ${lastSeenId}`);
                    
                    // Update storage immediately to prevent loop
                    localStorage.setItem('last_notification_id', latestId);

                    // Store notification data for after reload
                    sessionStorage.setItem('pending_notification', JSON.stringify(data));

                    // Reload page to refresh dashboard
                    console.log("Reloading dashboard...");
                    window.location.reload();
                }
            })
            .catch(error => {
                // Silently fail for network errors to avoid console spam
            });
    }

    // Poll every 3 seconds
    setInterval(checkNotifications, 3000);

    // Expose globally for debugging
    window.playNotificationSound = playNotificationSound;
    window.checkNotifications = checkNotifications;
});
