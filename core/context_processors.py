from .models import SiteSetting, Notification

def site_settings(request):
    context = {'site_settings': SiteSetting.load()}
    if request.user.is_authenticated:
        # Get unread notifications for the user or broadcast ones (recipient=None)
        # Note: Handling broadcast read status requires a M2M table, simpler to just show user-specific ones or all
        # For simplicity, we just count user-specific unread ones + all broadcast ones (assuming broadcast aren't "read" per user in this simple model)
        # Better: just count user specific ones for now.
        count = Notification.objects.filter(recipient=request.user, is_read=False).count()
        context['unread_notifications_count'] = count
    return context
