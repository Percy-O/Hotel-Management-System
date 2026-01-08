from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Count, Sum, Max
from django.contrib import messages
from booking.models import Booking
from .models import GuestProfile

from accounts.models import User

@staff_member_required
def guest_list(request):
    # Aggregate guests by email
    # We use guest_email as the unique identifier for a "guest profile"
    guests = Booking.objects.values('guest_email', 'guest_name', 'guest_phone').annotate(
        total_bookings=Count('id'),
        total_spent=Sum('total_price'),
        last_stay=Max('check_out_date')
    ).exclude(guest_email='').order_by('-last_stay')

    # Sync and attach profiles
    guest_list_with_profiles = []
    for guest in guests:
        email = guest['guest_email']
        if email:
            # Lazy creation/fetching of profile
            profile, created = GuestProfile.objects.get_or_create(email=email)
            
            # Link User if exists and not linked
            if not profile.user:
                user = User.objects.filter(email=email).first()
                if user:
                    profile.user = user
                    profile.save()

            # Update basic info if created or missing
            if created or not profile.first_name:
                name_parts = guest['guest_name'].split()
                if name_parts:
                    profile.first_name = name_parts[0]
                    profile.last_name = ' '.join(name_parts[1:]) if len(name_parts) > 1 else ''
                profile.phone_number = guest['guest_phone'] or ''
                profile.save()
            
            # Create a mutable copy of the dictionary or just add to it
            # ValuesQuerySet returns dicts, so we can modify them
            guest['profile'] = profile
            guest_list_with_profiles.append(guest)

    vip_count = GuestProfile.objects.filter(is_vip=True).count()
    returning_count = sum(1 for g in guests if g['total_bookings'] > 1)

    return render(request, 'guests/guest_list.html', {
        'guests': guest_list_with_profiles,
        'vip_count': vip_count,
        'returning_count': returning_count
    })

@staff_member_required
def guest_detail(request):
    # Since we don't have a Guest ID, we'll use email from query param
    email = request.GET.get('email')
    if not email:
        return render(request, 'guests/guest_list.html') # Or error page
    
    # Get all bookings for this email
    bookings = Booking.objects.filter(guest_email=email).order_by('-check_in_date')
    
    # Calculate stats
    stats = bookings.aggregate(
        total_spent=Sum('total_price'),
        total_stays=Count('id')
    )
    
    # Get latest contact info
    latest_booking = bookings.first()
    
    # Get or Create Profile
    profile, created = GuestProfile.objects.get_or_create(email=email)
    if created and latest_booking:
         name_parts = latest_booking.guest_name.split()
         if name_parts:
             profile.first_name = name_parts[0]
             profile.last_name = ' '.join(name_parts[1:]) if len(name_parts) > 1 else ''
         profile.phone_number = latest_booking.guest_phone or ''
         profile.save()

    guest_info = {
        'name': latest_booking.guest_name if latest_booking else profile.first_name + ' ' + profile.last_name,
        'email': email,
        'phone': latest_booking.guest_phone if latest_booking else profile.phone_number,
        'user': latest_booking.user if latest_booking else profile.user
    }

    return render(request, 'guests/guest_detail.html', {
        'guest': guest_info,
        'bookings': bookings,
        'stats': stats,
        'profile': profile
    })

@staff_member_required
def toggle_vip(request, profile_id):
    profile = get_object_or_404(GuestProfile, id=profile_id)
    profile.is_vip = not profile.is_vip
    profile.save()
    status = "VIP" if profile.is_vip else "Regular"
    messages.success(request, f"Guest {profile.email} is now a {status} guest.")
    return redirect(request.META.get('HTTP_REFERER', 'guest_list'))
