from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from hotel.models import RoomType
from .models import TenantSetting, Notification
from .forms import SiteSettingForm
from tenants.utils import get_current_tenant

# ... (Previous imports)

from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt

@csrf_exempt
@login_required
def mark_notification_read(request, notification_id):
    if request.method == 'POST':
        notification = get_object_or_404(Notification, id=notification_id, recipient=request.user)
        notification.is_read = True
        notification.save()
        return JsonResponse({'status': 'success'})
    return JsonResponse({'status': 'error'}, status=400)

@login_required
def get_unread_notifications(request):
    """API to get unread notifications count and latest unread notification for toast/sound"""
    unread_count = Notification.objects.filter(recipient=request.user, is_read=False).count()
    latest = Notification.objects.filter(recipient=request.user, is_read=False).order_by('-created_at').first()
    
    data = {
        'unread_count': unread_count,
        'latest_id': latest.id if latest else None,
        'latest_title': latest.title if latest else None,
        'latest_message': latest.message if latest else None,
        'latest_type': latest.notification_type if latest else None,
    }
    return JsonResponse(data)

@login_required
def test_notification(request):
    """Creates a test notification for the current user to verify the system."""
    Notification.objects.create(
        recipient=request.user,
        title="Test Notification",
        message="This is a test notification to verify the sound and toast system.",
        notification_type=Notification.Type.SUCCESS,
        link=request.META.get('HTTP_REFERER', '/')
    )
    messages.success(request, "Test notification created! Watch for the toast and listen for the sound.")
    return redirect(request.META.get('HTTP_REFERER', 'dashboard'))

@login_required
def notification_list(request):
    notifications = Notification.objects.filter(recipient=request.user).order_by('-created_at')
    
    # Mark all as read when viewing list
    unread = notifications.filter(is_read=False)
    unread.update(is_read=True)
    
    return render(request, 'core/notification_list.html', {'notifications': notifications})

def home(request):
    if hasattr(request, 'tenant') and request.tenant:
        # Public Hotel Site
        room_types = RoomType.objects.filter(tenant=request.tenant).order_by('price_per_night')
        return render(request, 'core/public_home.html', {'room_types': room_types, 'tenant': request.tenant})
    
    # SaaS Landing Page (No Tenant)
    return render(request, 'core/saas_landing.html')

@login_required
def update_theme(request):
    """Deprecated: Use settings_view instead."""
    if not request.user.is_staff:
        messages.error(request, "Permission denied.")
        return redirect('home')
        
    if request.method == 'POST':
        theme = request.POST.get('theme')
        if theme and request.tenant:
            settings, created = TenantSetting.objects.get_or_create(tenant=request.tenant)
            settings.theme = theme
            settings.save()
            messages.success(request, "Theme updated successfully.")
            
    return redirect(request.META.get('HTTP_REFERER', 'dashboard'))

@login_required
def settings_view(request):
    if not request.user.is_staff:
        messages.error(request, "Permission denied.")
        return redirect('dashboard')
    
    if not request.tenant:
         messages.error(request, "No tenant context.")
         return redirect('dashboard')

    settings, created = TenantSetting.objects.get_or_create(tenant=request.tenant)
    
    if request.method == 'POST':
        form = SiteSettingForm(request.POST, request.FILES, instance=settings)
        if form.is_valid():
            form.save()
            messages.success(request, "Settings updated successfully.")
            return redirect('settings')
    else:
        form = SiteSettingForm(instance=settings)
    
    return render(request, 'core/settings.html', {'form': form})
