from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.urls import reverse
from django.conf import settings
from .models import Booking
from .forms import BookingForm, AdminBookingForm
from hotel.models import Room, RoomType
from core.models import TenantSetting, Notification
import qrcode
import io
from fpdf import FPDF
import os
import datetime

# --- Helper Functions ---

def get_available_rooms(room_type, check_in, check_out):
    """
    Returns a queryset of available rooms of a specific type for the given dates.
    """
    # Find rooms of this type that have bookings overlapping with the requested dates
    # We include PENDING bookings as well to prevent double booking during payment window
    booked_rooms = Room.objects.filter(
        room_type=room_type,
        bookings__check_in_date__lt=check_out,
        bookings__check_out_date__gt=check_in,
        bookings__status__in=[Booking.Status.CONFIRMED, Booking.Status.CHECKED_IN, Booking.Status.PENDING]
    ).values_list('id', flat=True)

    # Return rooms of this type that are NOT in the booked_rooms list
    # and are currently marked as AVAILABLE (for physical status)
    return Room.objects.filter(
        room_type=room_type,
        status__in=[Room.Status.AVAILABLE, Room.Status.CLEANING] # Allow booking cleaning rooms for future
    ).exclude(
        id__in=booked_rooms
    ).exclude(
        status=Room.Status.MAINTENANCE
    )

# --- Views ---

def create_booking(request, room_type_id):
    room_type = get_object_or_404(RoomType, pk=room_type_id)
    
    # Check if user can manage bookings (Admin, Manager, Receptionist)
    can_manage = False
    if request.user.is_authenticated:
        can_manage = request.user.is_staff or getattr(request.user, 'can_manage_bookings', False)
        
    form_class = AdminBookingForm if can_manage else BookingForm
    
    # Context variables
    available_rooms = None
    check_in_str = request.GET.get('check_in')
    check_out_str = request.GET.get('check_out')

    initial_data = {}
    if check_in_str and check_out_str:
        initial_data['check_in_date'] = check_in_str
        initial_data['check_out_date'] = check_out_str
        try:
             # Just for initial lookup visualization
             pass
        except:
            pass

    if request.method == 'POST':
        if can_manage:
            form = form_class(request.POST, tenant=request.tenant) if hasattr(form_class, 'tenant') else form_class(request.POST)
            # Fix: AdminBookingForm might expect tenant kwarg if implemented, but standard ModelForm doesn't. 
            # Looking at form definition, it doesn't seem to have __init__ override, but let's be safe.
            # Actually, standard forms don't take tenant.
            form = form_class(request.POST)
        else:
            form = form_class(request.POST)
            
        if form.is_valid():
            check_in = form.cleaned_data['check_in_date']
            check_out = form.cleaned_data['check_out_date']
            
            # Get available rooms
            available_rooms = get_available_rooms(room_type, check_in, check_out)
            
            # Handle Room Selection (for Admin/Staff)
            selected_room_id = request.POST.get('selected_room')
            room = None
            if selected_room_id:
                room = available_rooms.filter(id=selected_room_id).first()
            
            # Auto-assign if no room selected or valid
            if not room:
                room = available_rooms.first()
                
            if not room:
                messages.error(request, "No rooms available for the selected dates.")
            else:
                # Double check availability (Race condition check)
                if not room.is_available(check_in, check_out):
                     messages.error(request, "Sorry, this room was just booked by another guest.")
                     return redirect('room_detail', pk=room_type.pk)
                     
                booking = form.save(commit=False)
                booking.room = room
                booking.room_type = room_type # If booking has room_type field
                booking.tenant = request.tenant
                
                # Calculate Price
                duration = (check_out - check_in).days
                if duration < 1: duration = 1
                booking.total_price = duration * room_type.price_per_night
                
                if request.user.is_authenticated and not can_manage:
                    booking.user = request.user
                    booking.guest_name = f"{request.user.first_name} {request.user.last_name}"
                    booking.guest_email = request.user.email
                elif can_manage:
                    # Admin might have selected a user
                    if form.cleaned_data.get('user'):
                        booking.user = form.cleaned_data['user']
                    # Guest details are already in form
                
                # If guest fields empty and user exists
                if not booking.guest_name and booking.user:
                    booking.guest_name = booking.user.get_full_name()
                if not booking.guest_email and booking.user:
                    booking.guest_email = booking.user.email

                # Default to PENDING for everyone initially
                booking.status = Booking.Status.PENDING
                booking.save()
                
                # Create Invoice
                invoice = Invoice.objects.create(
                    tenant=request.tenant,
                    booking=booking,
                    amount=booking.total_price,
                    status=Invoice.Status.PENDING,
                    invoice_type=Invoice.Type.BOOKING,
                    due_date=booking.check_in_date.date()
                )
                
                # Handle Payment Logic
                if can_manage:
                    payment_method = form.cleaned_data.get('payment_method')
                    if payment_method in ['CASH', 'TRANSFER']:
                        # Immediate Confirmation
                        booking.status = Booking.Status.CONFIRMED
                        booking.save()
                        
                        invoice.status = Invoice.Status.PAID
                        invoice.save()
                        
                        Payment.objects.create(
                            invoice=invoice,
                            amount=invoice.amount,
                            payment_method=payment_method,
                            transaction_id=f"MANUAL-{timezone.now().timestamp()}"
                        )
                        
                        messages.success(request, f"Booking confirmed and paid via {payment_method}.")
                        return redirect('booking_detail', pk=booking.pk)
                    else:
                        # Staff selected Online Payment -> Redirect to payment page
                        messages.success(request, "Booking created. Proceeding to payment.")
                        return redirect('payment_selection', invoice_id=invoice.pk)
                
                # Guest Flow (Online Booking)
                messages.success(request, "Booking created. Please complete payment to confirm.")
                return redirect('payment_selection', invoice_id=invoice.pk)
    else:
        if request.user.is_authenticated:
             initial_data.update({
                'guest_name': f"{request.user.first_name} {request.user.last_name}",
                'guest_email': request.user.email,
                'guest_phone': getattr(request.user, 'phone_number', ''),
                'first_name': request.user.first_name,
                'last_name': request.user.last_name,
             })
        
        form = form_class(initial=initial_data)

    template_name = 'booking/staff_booking_form.html' if can_manage else 'booking/booking_form.html'

    return render(request, template_name, {
        'form': form, 
        'room_type': room_type,
        'available_rooms': available_rooms
    })

@login_required
def booking_detail(request, pk):
    booking = get_object_or_404(Booking, pk=pk)
    
    # Permission Check
    if not request.user.is_staff and booking.user != request.user:
        messages.error(request, "Access denied.")
        return redirect('home')

    return render(request, 'booking/booking_detail.html', {'booking': booking})

@login_required
def booking_list(request):
    # Restrict to authorized staff only
    if not getattr(request.user, 'can_manage_bookings', False) and not getattr(request.user, 'can_view_bookings', False):
         return redirect('my_bookings')

    # Ensure Tenant Isolation
    if hasattr(request, 'tenant') and request.tenant:
        bookings = Booking.objects.filter(tenant=request.tenant)
        room_types = RoomType.objects.filter(tenant=request.tenant)
    else:
        bookings = Booking.objects.none()
        room_types = RoomType.objects.none()

    bookings = bookings.order_by('-created_at')
    
    # Filters
    status = request.GET.get('status')
    if status:
        bookings = bookings.filter(status=status)
        
    date_from = request.GET.get('date_from')
    if date_from:
        bookings = bookings.filter(check_in_date__gte=date_from)
        
    search = request.GET.get('search')
    if search:
        if search.isdigit():
            bookings = bookings.filter(id=search)
        else:
            bookings = bookings.filter(
                Q(guest_name__icontains=search) | 
                Q(guest_email__icontains=search)
            )
            
    return render(request, 'booking/booking_list.html', {
        'bookings': bookings,
        'room_types': room_types
    })

@login_required
def add_booking_selection(request):
    if not getattr(request.user, 'can_manage_bookings', False):
        messages.error(request, "Access denied.")
        return redirect('home')
        
    if hasattr(request, 'tenant') and request.tenant:
        room_types = RoomType.objects.filter(tenant=request.tenant)
    else:
        room_types = RoomType.objects.none()
        
    return render(request, 'booking/add_booking_selection.html', {'room_types': room_types})

@login_required
def verify_booking(request):
    if not getattr(request.user, 'can_manage_bookings', False):
        messages.error(request, "Access denied.")
        return redirect('home')
        
    booking = None
    search_query = request.GET.get('code') or request.GET.get('q')
    
    if search_query:
        # Try finding by Booking Reference
        booking = Booking.objects.filter(booking_reference__iexact=search_query).first()
            
        # Fallback: Try finding by ID (Legacy Support)
        if not booking and search_query.isdigit():
            if hasattr(request, 'tenant') and request.tenant:
                booking = Booking.objects.filter(id=search_query, tenant=request.tenant).first()
            else:
                booking = Booking.objects.filter(id=search_query).first()
        
        if not booking:
            messages.error(request, f"No booking found with ID: {search_query}")
        else:
            messages.success(request, "Booking verified successfully.")
                
    return render(request, 'booking/verify_booking.html', {'booking': booking, 'search_query': search_query})

@login_required
def check_in_booking(request, pk):
    booking = get_object_or_404(Booking, pk=pk)
    
    if not getattr(request.user, 'can_manage_bookings', False):
        messages.error(request, "Access denied.")
        return redirect('home')

    if booking.status == Booking.Status.CONFIRMED:
        # Check Date Validity
        now = timezone.now()
        # Allow check-in on the day of check-in (ignoring specific time for flexibility)
        # or if check-in date is in the past (late arrival)
        # But prevent check-in if it's too early (e.g. booked for next week)
        
        # We'll allow check-in if today is >= booking.check_in_date.date()
        if now.date() < booking.check_in_date.date():
             messages.error(request, f"Cannot check-in yet. Booking is for {booking.check_in_date.strftime('%Y-%m-%d')}.")
             return redirect('booking_detail', pk=pk)
             
        booking.status = Booking.Status.CHECKED_IN
        # Update actual check-in time to now if desired, but keep original reservation dates for record
        # booking.check_in_date = now 
        booking.save()
        
        # Update Room Status
        room = booking.room
        room.status = Room.Status.OCCUPIED
        room.save()
        
        messages.success(request, f"Checked in {booking.guest_name} to Room {room.room_number}")
    else:
        messages.error(request, "Booking is not in CONFIRMED state.")
        
    return redirect('booking_detail', pk=pk)

@login_required
def check_out_booking(request, pk):
    booking = get_object_or_404(Booking, pk=pk)
    
    if not getattr(request.user, 'can_manage_bookings', False):
        messages.error(request, "Access denied.")
        return redirect('home')

    if booking.status == Booking.Status.CHECKED_IN:
        booking.status = Booking.Status.CHECKED_OUT
        booking.check_out_date = timezone.now() # Record actual checkout time
        booking.save()
        
        # Update Room Status
        room = booking.room
        room.status = Room.Status.CLEANING
        room.save()
        
        # Notify Cleaners? (Handled by signals or manual check)
        
        messages.success(request, f"Checked out {booking.guest_name}. Room {room.room_number} marked for cleaning.")
    else:
        messages.error(request, "Booking is not currently CHECKED_IN.")
        
    return redirect('booking_detail', pk=pk)

@login_required
def download_barcode(request, pk):
    booking = get_object_or_404(Booking, pk=pk)
    
    # Permission check
    if not getattr(request.user, 'can_view_bookings', False) and booking.user != request.user:
         messages.error(request, "You do not have permission to download this barcode.")
         return redirect('home')

    try:
        # Generate Verification URL
        verification_url = request.build_absolute_uri(reverse('verify_booking')) + f"?code={booking.booking_id}"
        
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(verification_url)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white")
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")

        response = HttpResponse(buffer.getvalue(), content_type='image/png')
        response['Content-Disposition'] = f'attachment; filename="qrcode_{booking.booking_id}.png"'
        return response
    except Exception as e:
        messages.error(request, f"Error generating QR code: {e}")
        return redirect('booking_detail', pk=pk)

@login_required
def download_receipt(request, pk):
    booking = get_object_or_404(Booking, pk=pk)
    
    # Permission check: Owner or Staff
    if not request.user.is_staff and booking.user != request.user:
         messages.error(request, "You do not have permission to download this receipt.")
         return redirect('home')

    # Import TenantSetting to get theme
    settings = None
    if request.tenant:
        settings = TenantSetting.objects.filter(tenant=request.tenant).first()
    
    # Fallback values
    current_theme = settings.theme if settings else 'theme-default'
    hotel_name = settings.hotel_name if settings else "Hotel Management System"
    
    # Currency Symbol Mapping
    CURRENCY_SYMBOLS = {
        'USD': '$', 'EUR': '€', 'GBP': '£', 'NGN': '₦', 
        'JPY': '¥', 'CAD': '$', 'AUD': '$', 'INR': '₹', 'ZAR': 'R'
    }
    currency_symbol = '$'
    if settings:
        currency_symbol = CURRENCY_SYMBOLS.get(settings.currency, settings.currency)
        if hasattr(settings, 'currency_symbol'): # In case it was added as property
             currency_symbol = settings.currency_symbol

    # Define Theme Colors (R, G, B)
    THEME_COLORS = {
        'theme-default': (19, 236, 109),
        'theme-light': (19, 236, 109), 
        'theme-blue': (59, 130, 246), # #3b82f6
        'theme-luxury': (212, 175, 55), # #d4af37
        'theme-forest': (74, 222, 128), # #4ade80
        'theme-ocean': (6, 182, 212), # #06b6d4
        'theme-sunset': (244, 114, 182), # #f472b6
        'theme-royal': (167, 139, 250), # #a78bfa
        'theme-minimal': (113, 113, 122), # #71717a
    }

    primary_color = THEME_COLORS.get(current_theme, (19, 236, 109))
    
    # Generate PDF (Standard Receipt Size - A5)
    pdf = FPDF(orientation='P', unit='mm', format='A5')
    pdf.set_auto_page_break(auto=False)
    pdf.add_page()
    
    # Header
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 10, hotel_name, ln=True, align='C')
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, "Booking Receipt", ln=True, align='C')
    pdf.ln(5)
    
    # Booking Info
    pdf.set_font("Arial", '', 10)
    pdf.cell(0, 8, f"Booking Ref: {booking.booking_id}", ln=True)
    pdf.cell(0, 8, f"Guest: {booking.guest_name}", ln=True)
    pdf.cell(0, 8, f"Room: {booking.room.room_number} ({booking.room.room_type.name})", ln=True)
    pdf.cell(0, 8, f"Check-in: {booking.check_in_date.strftime('%Y-%m-%d %H:%M')}", ln=True)
    pdf.cell(0, 8, f"Check-out: {booking.check_out_date.strftime('%Y-%m-%d %H:%M')}", ln=True)
    pdf.ln(5)
    
    # Financials
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, f"Total Paid: {currency_symbol}{booking.total_price:,.2f}", ln=True)
    
    # Output
    buffer = io.BytesIO()
    pdf_content = pdf.output(dest='S').encode('latin-1')
    buffer.write(pdf_content)
    buffer.seek(0)
    
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="receipt_{booking.booking_id}.pdf"'
    return response

@login_required
def view_barcode_pass(request, pk):
    booking = get_object_or_404(Booking, pk=pk)
    # Permission check
    if not request.user.is_staff and booking.user != request.user:
        messages.error(request, "Access denied.")
        return redirect('home')
        
    return render(request, 'booking/barcode_pass.html', {'booking': booking})

@login_required
def my_bookings(request):
    bookings = Booking.objects.filter(user=request.user).order_by('-created_at')
    
    # Tenant filter if applicable
    if request.tenant:
        bookings = bookings.filter(tenant=request.tenant)
        
    return render(request, 'booking/my_bookings.html', {'bookings': bookings})

@login_required
def extend_booking(request, pk):
    booking = get_object_or_404(Booking, pk=pk)
    
    # Permission: Owner or Staff
    if not request.user.is_staff and booking.user != request.user:
        messages.error(request, "Access denied.")
        return redirect('home')
        
    # Check if booking can be extended
    if booking.status not in [Booking.Status.CHECKED_IN, Booking.Status.CONFIRMED]:
        messages.error(request, "This booking cannot be extended.")
        return redirect('booking_detail', pk=pk)

    if request.method == 'POST':
        new_check_out_str = request.POST.get('new_check_out_date')
        if not new_check_out_str:
            messages.error(request, "Please select a new checkout date.")
            return redirect('extend_booking', pk=pk)
            
        try:
            # Handle both date and datetime inputs
            from django.utils.dateparse import parse_datetime
            import datetime
            
            new_check_out = parse_datetime(new_check_out_str)
            if not new_check_out:
                 pass 

            # Ensure timezone aware
            if new_check_out and timezone.is_naive(new_check_out):
                new_check_out = timezone.make_aware(new_check_out)
                
            if not new_check_out:
                 messages.error(request, "Invalid date format.")
                 return redirect('extend_booking', pk=pk)
                
            if new_check_out <= booking.check_out_date:
                messages.error(request, "New checkout date must be after the current checkout date.")
                return redirect('extend_booking', pk=pk)
                
            # Check Availability
            conflicting_bookings = Booking.objects.filter(
                room=booking.room,
                status__in=[Booking.Status.CONFIRMED, Booking.Status.CHECKED_IN],
                check_in_date__lt=new_check_out,
                check_out_date__gt=booking.check_out_date
            ).exclude(pk=booking.pk)
            
            if conflicting_bookings.exists():
                messages.error(request, "Room is not available for the selected dates.")
                return redirect('extend_booking', pk=pk)
                
            # Calculate Cost
            # Calculate difference in days (ceiling)
            diff = new_check_out - booking.check_out_date
            additional_days = diff.days
            if diff.seconds > 0:
                additional_days += 1
                
            if additional_days <= 0:
                 additional_days = 0 

            # Price calculation
            price_per_night = booking.room.room_type.price_per_night
            additional_cost = additional_days * price_per_night
            
            # Update Booking
            booking.check_out_date = new_check_out
            booking.total_price += additional_cost
            booking.save()
            
            # Notify Staff
            from core.models import Notification
            from django.contrib.auth import get_user_model
            User = get_user_model()
            
            staff_roles = [User.Role.ADMIN, User.Role.MANAGER, User.Role.RECEPTIONIST]
            staff_users = User.objects.filter(role__in=staff_roles)
            if request.tenant:
                 # Ideally filter by tenant membership
                 pass
            
            for staff in staff_users:
                Notification.objects.create(
                    recipient=staff,
                    title="Stay Extended",
                    message=f"Booking #{booking.id} (Room {booking.room.room_number}) extended by {additional_days} days.",
                    notification_type=Notification.Type.INFO,
                    link=reverse('booking_detail', args=[booking.pk])
                )
            
            messages.success(request, f"Stay extended successfully! Additional cost: {additional_cost}")
            return redirect('booking_detail', pk=pk)
            
        except Exception as e:
            messages.error(request, f"Error extending booking: {e}")
            
    return render(request, 'booking/extend_booking.html', {'booking': booking})
