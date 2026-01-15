from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from hotel.models import RoomType
from .models import TenantSetting, Notification, AuditLog
from .forms import SiteSettingForm
from tenants.utils import get_current_tenant
from .utils import log_audit

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

from tenants.models import Plan

def home(request):
    if hasattr(request, 'tenant') and request.tenant:
        # Public Hotel Site
        tenant = request.tenant
        
        # Fetch Context Data
        room_types = RoomType.objects.filter(tenant=tenant).order_by('price_per_night')
        
        # Optional: Services if installed
        # Using a try-except or check for installed apps is better, but for now assuming apps exist
        # Services (Dining)
        from services.models import MenuItem
        menu_items = MenuItem.objects.filter(tenant=tenant, is_available=True)[:6]
        
        # Events
        from events.models import EventHall
        event_halls = EventHall.objects.filter(tenant=tenant)[:3]
        
        # Gym
        from gym.models import GymPlan
        gym_plans = GymPlan.objects.filter(tenant=tenant)
        
        # Hotel Info
        from hotel.models import Hotel
        hotel_info = Hotel.objects.filter(tenant=tenant).first()
        
        context = {
            'tenant': tenant,
            'room_types': room_types,
            'hotel': hotel_info,
            'menu_items': menu_items,
            'event_halls': event_halls,
        }
        return render(request, 'core/public_home.html', context)
    
    # SaaS Landing Page (No Tenant)
    plans = Plan.objects.filter(is_public=True).order_by('price')
    return render(request, 'core/saas_landing.html', {'plans': plans})

def about_us(request):
    """Public About Us Page"""
    return render(request, 'core/about_us.html')

from django.core.mail import send_mail
from .models import TenantSetting, Notification, AuditLog, ContactMessage

def contact_us(request):
    """Public Contact Us Page"""
    if request.method == 'POST':
        name = request.POST.get('name')
        email = request.POST.get('email')
        subject = request.POST.get('subject')
        message_text = request.POST.get('message')
        
        # Save to DB
        contact_msg = ContactMessage.objects.create(
            tenant=request.tenant,
            name=name,
            email=email,
            subject=subject,
            message=message_text
        )
        
        # Notify Admins/Managers via Dashboard Notification
        # Find staff users for this tenant
        staff_users = User.objects.filter(tenant=request.tenant, role__in=['admin', 'manager'])
        for user in staff_users:
            Notification.objects.create(
                recipient=user,
                title=f"New Inquiry: {subject}",
                message=f"From: {name} ({email})\n\n{message_text[:100]}...",
                notification_type=Notification.Type.INFO,
                link=f"/dashboard/messages/{contact_msg.id}/" # Placeholder link
            )
            
        # Send Email to Hotel Admin Email (from TenantSettings)
        if request.tenant:
            settings = TenantSetting.objects.filter(tenant=request.tenant).first()
            if settings and settings.contact_email:
                try:
                    send_mail(
                        subject=f"New Website Inquiry: {subject}",
                        message=f"Name: {name}\nEmail: {email}\n\nMessage:\n{message_text}",
                        from_email=None, # Use default
                        recipient_list=[settings.contact_email],
                        fail_silently=True
                    )
                except Exception as e:
                    print(f"Failed to send contact email: {e}")
        
        messages.success(request, "Your message has been sent successfully! We will get back to you soon.")
        return redirect('contact_us')
        
    return render(request, 'core/contact_us.html')

def faqs_view(request):
    """Public FAQs Page"""
    return render(request, 'core/faqs.html')

def privacy_policy_view(request):
    """Public Privacy Policy Page"""
    return render(request, 'core/privacy.html')

def terms_conditions_view(request):
    """Public Terms & Conditions Page"""
    return render(request, 'core/terms.html')

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

from core.email_utils import send_tenant_email

@login_required
def test_email_config(request):
    """
    Sends a test email using the current tenant's settings.
    """
    if not request.user.is_staff or not request.tenant:
        messages.error(request, "Permission denied.")
        return redirect('settings')
        
    try:
        sent = send_tenant_email(
            subject=f"Test Email from {request.tenant.name}",
            message="This is a test email to verify your SMTP configuration. If you received this, your email settings are correct!",
            recipient_list=[request.user.email],
            tenant=request.tenant,
            fail_silently=False
        )
        
        if sent:
            messages.success(request, f"Test email sent successfully to {request.user.email}")
        else:
            messages.error(request, "Failed to send test email. Check your SMTP logs.")
            
    except Exception as e:
        messages.error(request, f"Error sending test email: {str(e)}")
        
    return redirect('settings')

@login_required
def settings_view(request):
    if not request.user.can_manage_settings:
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
            print(f"DEBUG: Saved Settings for {request.tenant}. Theme: {settings.theme}")
            
            log_audit(
                request,
                action=AuditLog.Action.UPDATE,
                module='Settings',
                details=f"Updated site settings. Theme: {settings.theme}"
            )
            
            messages.success(request, "Settings updated successfully.")
            return redirect('settings')
        else:
            print(f"DEBUG: Form Errors: {form.errors}")
            messages.error(request, f"Error updating settings: {form.errors}")
    else:
        form = SiteSettingForm(instance=settings)
    
    # Check if plan allows custom email
    show_email_settings = False
    current_plan = None
    if request.tenant and request.tenant.plan:
        current_plan = request.tenant.plan
        if request.tenant.plan.allow_custom_email:
            show_email_settings = True
            
    # Get all public plans for upgrade comparison
    all_plans = Plan.objects.filter(is_public=True).order_by('price')

    return render(request, 'core/settings.html', {
        'form': form, 
        'show_email_settings': show_email_settings,
        'current_plan': current_plan,
        'all_plans': all_plans,
        'tenant': request.tenant
    })
