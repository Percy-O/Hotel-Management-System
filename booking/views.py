import base64
import io
import qrcode
from django.urls import reverse_lazy, reverse
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login, get_user_model
from django.contrib import messages
from django.db.models import Q
from django.utils import timezone
from django.http import HttpResponse
from fpdf import FPDF
from core.email_utils import send_tenant_email, send_branded_email

# Models
from hotel.models import RoomType, Room
from .models import Booking
from billing.models import Invoice
from core.models import Notification
from .forms import BookingForm, AdminBookingForm

User = get_user_model()

def get_available_rooms(room_type, check_in, check_out):
    """
    Returns a queryset of available rooms of a specific type for the given dates.
    """
    # Find rooms of this type that have bookings overlapping with the requested dates
    booked_rooms = Room.objects.filter(
        room_type=room_type,
        bookings__check_in_date__lt=check_out,
        bookings__check_out_date__gt=check_in,
        bookings__status__in=[Booking.Status.CONFIRMED, Booking.Status.CHECKED_IN]
    ).values_list('id', flat=True)

    # Return rooms of this type that are NOT in the booked_rooms list
    # and are currently marked as AVAILABLE (for physical status)
    return Room.objects.filter(
        room_type=room_type,
        status=Room.Status.AVAILABLE
    ).exclude(
        id__in=booked_rooms
    ).exclude(
        status=Room.Status.MAINTENANCE
    )

def create_booking(request, room_type_id):
    room_type = get_object_or_404(RoomType, pk=room_type_id)
    form_class = AdminBookingForm if request.user.is_staff else BookingForm
    
    # Context variables
    available_rooms = None
    check_in_str = request.GET.get('check_in')
    check_out_str = request.GET.get('check_out')

    if request.method == 'POST':
        form = form_class(request.POST)
        if form.is_valid():
            check_in = form.cleaned_data['check_in_date']
            check_out = form.cleaned_data['check_out_date']
            
            # Get available rooms again to be sure
            available_rooms = get_available_rooms(room_type, check_in, check_out)
            
            # Handle Room Selection
            selected_room_id = request.POST.get('selected_room')
            room = None
            if selected_room_id:
                room = available_rooms.filter(id=selected_room_id).first()
            
            # If no specific room selected or selected room unavailable, auto-assign
            if not room:
                room = available_rooms.first()
            
            if room:
                booking = form.save(commit=False)
                booking.room = room
                
                # Handle User Assignment & Auto-creation
                if request.user.is_staff:
                    # Admin booking logic
                    if booking.user:
                        if not booking.guest_name:
                            booking.guest_name = f"{booking.user.first_name} {booking.user.last_name}"
                        if not booking.guest_email:
                            booking.guest_email = booking.user.email
                    else:
                        # Admin booking for new guest (Walk-in)
                        email = form.cleaned_data.get('guest_email')
                        first_name = form.cleaned_data.get('first_name')
                        last_name = form.cleaned_data.get('last_name')
                        
                        full_name = f"{first_name} {last_name}".strip()
                        if full_name:
                            booking.guest_name = full_name
                            
                        if email and first_name:
                            user = User.objects.filter(email=email).first()
                            if not user:
                                # Create new user
                                password = first_name
                                try:
                                    user = User.objects.create_user(username=email, email=email, password=password)
                                    user.first_name = first_name
                                    user.last_name = last_name
                                    if hasattr(User, 'Role'):
                                        user.role = User.Role.GUEST
                                    user.save()
                                    messages.info(request, f"Guest Account created! Email: {email}, Password: {password}")
                                    
                                    # Send Welcome Email
                                    try:
                                        protocol = 'https' if request.is_secure() else 'http'
                                        host = request.get_host()
                                        login_url = f"{protocol}://{host}/login/"
                                        
                                        send_branded_email(
                                            subject=f"Welcome to {request.tenant.name}",
                                            template_name='emails/welcome_user.html',
                                            context={
                                                'user': user,
                                                'role': 'Guest',
                                                'login_url': login_url,
                                                'password': password # Only acceptable here as it's auto-generated
                                            },
                                            recipient_list=[user.email],
                                            tenant=request.tenant
                                        )
                                    except Exception as e:
                                        print(f"Error sending welcome email: {e}")

                                except Exception as e:
                                    print(f"Error creating user: {e}")
                                    pass
                            
                            if user:
                                booking.user = user

                elif request.user.is_authenticated:
                    booking.user = request.user
                    # Auto-fill guest details if not provided
                    if not booking.guest_name:
                        booking.guest_name = f"{request.user.first_name} {request.user.last_name}"
                    if not booking.guest_email:
                        booking.guest_email = request.user.email
                else:
                    # Guest booking (not logged in)
                    email = form.cleaned_data.get('guest_email')
                    first_name = form.cleaned_data.get('first_name')
                    last_name = form.cleaned_data.get('last_name')
                    
                    # Construct full name for the booking record
                    full_name = f"{first_name} {last_name}".strip()
                    if full_name:
                        booking.guest_name = full_name
                    
                    if email and first_name:
                        user = User.objects.filter(email=email).first()
                        if not user:
                            # Create new user
                            password = first_name # User requested firstname as password
                            try:
                                user = User.objects.create_user(username=email, email=email, password=password)
                                user.first_name = first_name
                                user.last_name = last_name
                                # Assign GUEST role if available, otherwise default
                                if hasattr(User, 'Role'):
                                    user.role = User.Role.GUEST
                                user.save()
                                messages.info(request, f"Account created! Login with Email: {email} and Password: {password}")
                                
                                # Send Welcome Email
                                try:
                                    protocol = 'https' if request.is_secure() else 'http'
                                    host = request.get_host()
                                    login_url = f"{protocol}://{host}/login/"
                                    
                                    send_branded_email(
                                        subject=f"Welcome to {request.tenant.name}",
                                        template_name='emails/welcome_user.html',
                                        context={
                                            'user': user,
                                            'role': 'Guest',
                                            'login_url': login_url,
                                            'password': password
                                        },
                                        recipient_list=[user.email],
                                        tenant=request.tenant
                                    )
                                except Exception as e:
                                    print(f"Error sending welcome email: {e}")

                                # Log the user in
                                login(request, user)
                            except Exception as e:
                                # Handle username conflict or other errors
                                print(f"Error creating user: {e}")
                                pass
                        
                        if user:
                            booking.user = user
                
                # Calculate total price
                # Calculate duration in days, ensuring at least 1 day/night charged if < 24h but overnight? 
                # For simplicity, use days difference. 
                duration = check_out - check_in
                nights = duration.days
                if nights < 1:
                    nights = 1 # Minimum 1 night
                
                # If we want to support hourly, we'd need hourly price. Assuming nightly for now.
                booking.total_price = room_type.price_per_night * nights
                
                # Determine initial status
                # If staff and paying manually: CONFIRMED
                # If staff and paying online: PENDING
                # If guest: PENDING
                
                payment_method = 'ONLINE' # Default
                if request.user.is_staff:
                    payment_method = form.cleaned_data.get('payment_method')
                
                if request.user.is_staff and payment_method in ['CASH', 'TRANSFER']:
                    booking.status = Booking.Status.CONFIRMED
                else:
                    booking.status = Booking.Status.PENDING
                    
                    # Notify Staff of New Pending Booking
                    staff_users = User.objects.filter(role__in=[User.Role.MANAGER, User.Role.RECEPTIONIST])
                    # Save the booking first so it gets a pk
                    booking.save()

                    # Notify Staff of New Pending Booking
                    if booking.status == Booking.Status.PENDING:
                        staff_users = User.objects.filter(role__in=[User.Role.MANAGER, User.Role.RECEPTIONIST])
                        booking_link = reverse('booking_detail', kwargs={'pk': booking.pk})
                    for staff in staff_users:
                        Notification.objects.create(
                            recipient=staff,
                            title="New Booking Request",
                            message=f"New booking from {booking.guest_name} for {room_type.name}.",
                            notification_type=Notification.Type.INFO,
                            link= booking_link
                        )
                booking.save()
                # Generate Invoice
                invoice = Invoice.objects.create(
                    booking=booking,
                    amount=booking.total_price,
                    status=Invoice.Status.PENDING,
                    due_date=booking.check_in_date.date()
                )

                # Handle Payment if Staff and Manual
                if request.user.is_staff and payment_method in ['CASH', 'TRANSFER']:
                    # Create Payment Record
                    from billing.models import Payment
                    Payment.objects.create(
                        invoice=invoice,
                        amount=booking.total_price,
                        payment_method=payment_method,
                        transaction_id=f"MANUAL-{timezone.now().timestamp()}"
                    )
                    # Mark Invoice as Paid
                    invoice.status = Invoice.Status.PAID
                    invoice.save()
                    
                    # Get Currency Symbol
                    currency_symbol = '$'
                    try:
                        from core.models import TenantSetting
                        site_setting = TenantSetting.objects.get(tenant=request.tenant)
                        if site_setting and site_setting.currency_symbol:
                            currency_symbol = site_setting.currency_symbol
                    except:
                        pass

                    messages.success(request, f"Payment of {currency_symbol}{booking.total_price} recorded via {payment_method}.")
                    
                    # Send Notification for Confirmed Booking
                    if booking.user:
                        Notification.objects.create(
                            recipient=booking.user,
                            title="Booking Confirmed",
                            message=f"Your booking for {room_type.name} (Room {room.room_number}) has been confirmed.",
                            notification_type=Notification.Type.SUCCESS,
                            link=f"/booking/{booking.pk}/"
                        )
                        
                        # Send Booking Email
                        try:
                            protocol = 'https' if request.is_secure() else 'http'
                            host = request.get_host()
                            booking_url = f"{protocol}://{host}/booking/{booking.pk}/"
                            
                            send_branded_email(
                                subject=f"Booking Confirmed - #{booking.pk}",
                                template_name='emails/booking_confirmation.html',
                                context={
                                    'booking': booking,
                                    'booking_url': booking_url,
                                },
                                recipient_list=[booking.user.email],
                                tenant=request.tenant
                            )
                        except Exception as e:
                            print(f"Error sending booking email: {e}")
                    
                    messages.success(request, f"Booking confirmed! Your room number is {room.room_number}.")
                    return redirect('booking_detail', pk=booking.pk)
                
                else:
                    # Redirect to Payment Selection
                    # For staff selecting ONLINE, or regular guests
                    return redirect('payment_selection', invoice_id=invoice.pk)
            else:
                messages.error(request, "Sorry, no rooms available for the selected dates.")
    else:
        # Pre-fill dates if passed in query params
        initial_data = {}
        if check_in_str:
            initial_data['check_in_date'] = check_in_str
        if check_out_str:
            initial_data['check_out_date'] = check_out_str

        # If we have dates from GET, check availability to show room selection
        if check_in_str and check_out_str:
            try:
                # Naive parsing, better to use forms to clean, but for display:
                available_rooms = get_available_rooms(room_type, check_in_str, check_out_str)
            except Exception:
                pass

        if request.user.is_authenticated:
             initial_data.update({
                'guest_name': f"{request.user.first_name} {request.user.last_name}",
                'guest_email': request.user.email,
                'guest_phone': getattr(request.user, 'phone_number', ''),
                'first_name': request.user.first_name,
                'last_name': request.user.last_name,
             })
        form = form_class(initial=initial_data)

    if request.user.is_staff:
        template_name = 'booking/staff_booking_form.html'
    else:
        template_name = 'booking/booking_form.html'

    return render(request, template_name, {
        'form': form, 
        'room_type': room_type,
        'available_rooms': available_rooms
    })

def booking_detail(request, pk):
    booking = get_object_or_404(Booking, pk=pk)
    # Security check: only show booking to the owner or staff
    if request.user.is_authenticated:
        if not request.user.is_staff and booking.user != request.user:
             messages.error(request, "You do not have permission to view this booking.")
             return redirect('home')
    # If unauthenticated, maybe allow via token? For now, require login or rely on session messages.
    
    # Generate QR Code for Display
    barcode_base64 = None
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
        barcode_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
    except Exception as e:
        print(f"QR generation error: {e}")
        pass

    return render(request, 'booking/booking_detail.html', {'booking': booking, 'barcode_base64': barcode_base64})

@login_required
def my_bookings(request):
    bookings = Booking.objects.filter(user=request.user).order_by('-created_at')
    return render(request, 'booking/my_bookings.html', {'bookings': bookings})

@login_required
def booking_list(request):
    # Restrict to staff/admin only
    if not request.user.is_staff:
        return redirect('my_bookings')

    bookings = Booking.objects.all().order_by('-created_at')
    room_types = RoomType.objects.all()
    
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
def check_in_booking(request, pk):
    booking = get_object_or_404(Booking, pk=pk)
    
    # Permission check
    if not request.user.is_staff:
        messages.error(request, "Only staff can perform check-in operations.")
        return redirect('booking_detail', pk=pk)

    if booking.status != Booking.Status.CONFIRMED:
        messages.error(request, f"Cannot check in. Booking status is {booking.get_status_display()}.")
        return redirect('booking_detail', pk=pk)
    
    # Update Booking Status
    booking.status = Booking.Status.CHECKED_IN
    booking.save()
    
    # Update Room Status
    room = booking.room
    room.status = Room.Status.OCCUPIED
    room.save()
    
    # Notify Guest
    if booking.user:
        Notification.objects.create(
            recipient=booking.user,
            title="Welcome!",
            message=f"You have been successfully checked in to Room {room.room_number}. Enjoy your stay!",
            notification_type=Notification.Type.SUCCESS,
            link=reverse('guest_dashboard')
        )
    
    messages.success(request, f"Guest checked in successfully to Room {room.room_number}.")
    return redirect('booking_detail', pk=pk)

@login_required
def check_out_booking(request, pk):
    booking = get_object_or_404(Booking, pk=pk)
    
    # Permission check
    if not request.user.is_staff:
        messages.error(request, "Only staff can perform check-out operations.")
        return redirect('booking_detail', pk=pk)

    if booking.status != Booking.Status.CHECKED_IN:
        messages.error(request, f"Cannot check out. Booking status is {booking.get_status_display()}.")
        return redirect('booking_detail', pk=pk)
    
    # Update Booking Status
    booking.status = Booking.Status.CHECKED_OUT
    booking.save()
    
    # Update Room Status - Mark as Cleaning or Available? Usually Cleaning first.
    room = booking.room
    room.status = Room.Status.CLEANING
    room.save()
    
    # Notify Cleaners
    cleaners = User.objects.filter(role='CLEANER')
    
    # Dashboard Notification
    for cleaner in cleaners:
        Notification.objects.create(
            recipient=cleaner,
            title="Room Ready for Cleaning",
            message=f"Room {room.room_number} has been vacated and needs cleaning.",
            notification_type=Notification.Type.INFO,
            link=reverse_lazy('staff_room_list') + "?status=CLEANING"
        )
        
        # Email Notification
        if cleaner.email:
            try:
                send_tenant_email(
                    subject=f"Cleaning Required: Room {room.room_number}",
                    message=f"Hello {cleaner.first_name},\n\nRoom {room.room_number} has been checked out and is ready for cleaning.\n\nPlease attend to it.\n\nThank you.",
                    recipient_list=[cleaner.email],
                    tenant=room.tenant,
                    fail_silently=True
                )
            except Exception as e:
                print(f"Failed to send email to {cleaner.email}: {e}")

    # Notify Manager as well for oversight
    managers = User.objects.filter(role='MANAGER')
    for manager in managers:
         Notification.objects.create(
            recipient=manager,
            title="Room Checked Out",
            message=f"Room {room.room_number} checked out. Marked for cleaning.",
            notification_type=Notification.Type.INFO,
            link=reverse_lazy('booking_detail', kwargs={'pk': booking.pk})
        )
    
    messages.success(request, f"Guest checked out. Room {room.room_number} marked for cleaning.")
    return redirect('booking_detail', pk=pk)

@login_required
def view_barcode_pass(request, pk):
    booking = get_object_or_404(Booking, pk=pk)
    
    # Permission check
    if not request.user.can_view_bookings and booking.user != request.user:
         messages.error(request, "You do not have permission to view this pass.")
         return redirect('home')

    # Generate QR Code for Display
    barcode_base64 = None
    try:
        # Use QR Code for verification URL
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
        rv = io.BytesIO()
        img.save(rv, format="PNG")
        
        # Convert to base64 string
        barcode_base64 = base64.b64encode(rv.getvalue()).decode('utf-8')
    except Exception as e:
        print(f"QR generation error: {e}")
        pass

    return render(request, 'booking/entry_pass.html', {'booking': booking, 'barcode_base64': barcode_base64})

@login_required
def add_booking_selection(request):
    if not request.user.can_manage_bookings:
        messages.error(request, "Access denied.")
        return redirect('home')
        
    room_types = RoomType.objects.all()
    return render(request, 'booking/add_booking_selection.html', {'room_types': room_types})

@login_required
def verify_booking(request):
    if not request.user.can_manage_bookings:
        messages.error(request, "Access denied.")
        return redirect('home')
        
    booking = None
    search_query = ""
    
    # Check POST first, then GET
    if request.method == 'POST':
        search_query = request.POST.get('barcode', '').strip()
    elif request.GET.get('code'):
        search_query = request.GET.get('code', '').strip()
    
    if search_query:
        # Handle full URL scan
        if 'code=' in search_query:
            try:
                # simple extraction for verify_booking?code=123
                search_query = search_query.split('code=')[1].split('&')[0]
            except IndexError:
                pass

        # Try finding by ID first
        if search_query.isdigit():
            booking = Booking.objects.filter(id=search_query).first()
        
        # Try finding by Booking Reference ID (HMS-YYYY-ID)
        if not booking and search_query.startswith('HMS-'):
            try:
                parts = search_query.split('-')
                if len(parts) == 3:
                    booking_pk = int(parts[2])
                    booking = Booking.objects.filter(id=booking_pk).first()
            except (ValueError, IndexError):
                pass
        
        if not booking:
            messages.error(request, f"No booking found with ID: {search_query}")
        else:
            messages.success(request, "Booking verified successfully.")
                
    return render(request, 'booking/verify_booking.html', {'booking': booking, 'search_query': search_query})

@login_required
def download_barcode(request, pk):
    booking = get_object_or_404(Booking, pk=pk)
    
    # Permission check
    if not request.user.can_view_bookings and booking.user != request.user:
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

    # Import SiteSetting to get theme
    from core.models import SiteSetting
    settings = SiteSetting.load()
    current_theme = settings.theme
    currency_symbol = settings.currency_symbol if hasattr(settings, 'currency_symbol') and settings.currency_symbol else '$'

    # Define Theme Colors (R, G, B)
    # Default fallback: Green (#13ec6d -> 19, 236, 109)
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
    text_color = (30, 41, 59) # Slate 800
    light_text_color = (100, 116, 139) # Slate 500
    
    # Generate PDF (Standard Receipt Size - A5)
    pdf = FPDF(orientation='P', unit='mm', format='A5')
    pdf.set_auto_page_break(auto=False) # Disable auto break for background
    pdf.add_page()
    
    # --- Full Page Background Pattern ---
    # User requested to tile the logo or hotel name until it fills the page without space.
    # To avoid visual chaos, we will make it very faint.
    
    # Pattern Config
    start_x = 0
    start_y = 0
    page_w = 148
    page_h = 210
    
    # Try to use Logo first
    logo_path = None
    if settings.hotel_logo:
        try:
            if os.path.exists(settings.hotel_logo.path):
                logo_path = settings.hotel_logo.path
        except:
            pass
            
    if logo_path:
        # Tile Image
        tile_w = 25
        tile_h = 25 # Assume square-ish for pattern simplicity
        
        y = start_y
        while y < page_h:
            x = start_x
            while x < page_w:
                pdf.image(logo_path, x=x, y=y, w=tile_w, h=tile_h)
                x += tile_w
            y += tile_h
            
    else:
        # Tile Hotel Name
        # We can use faint text color which is safe and looks good.
        pdf.set_font("Arial", 'B', 12)
        pdf.set_text_color(245, 245, 245) # Very light gray
        
        # Calculate rough width of text
        text = settings.hotel_name.upper()
        # Add a very small separator to distinguish repeats slightly, or none as requested
        text_w = pdf.get_string_width(text) + 2 
        text_h = 8 # Line height
        
        y = start_y
        while y < page_h:
            x = start_x
            # Offset every other line for better texture
            if (y // text_h) % 2 == 1:
                x = -text_w / 2
                
            while x < page_w:
                pdf.text(x, y + text_h/2, text)
                x += text_w
            y += text_h

    # Re-enable auto page break for content, if needed, but be careful
    pdf.set_auto_page_break(auto=True, margin=10)

    # --- Decorative Header ---
    # Top Right Aligned Hotel Info
    
    # Hotel Name
    pdf.set_y(10)
    pdf.set_font("Arial", 'B', 16)
    pdf.set_text_color(*primary_color)
    pdf.cell(0, 8, txt=settings.hotel_name.upper(), ln=1, align="R")
    
    # Address & Contact Info (Small, below name)
    pdf.set_font("Arial", '', 8)
    pdf.set_text_color(60, 60, 60)
    # Placeholder address if not in settings, or use what we have
    address = "123 Luxury Ave, Paradise City" # Default or from settings
    email = "info@grandhotel.com"
    phone = "+1 234 567 8900"
    
    pdf.cell(0, 4, txt=address, ln=1, align="R")
    pdf.cell(0, 4, txt=email, ln=1, align="R")
    pdf.cell(0, 4, txt=phone, ln=1, align="R")
    
    # Gold Separator Line
    pdf.ln(2)
    pdf.set_draw_color(*primary_color)
    pdf.set_line_width(0.5)
    pdf.line(10, pdf.get_y(), 138, pdf.get_y())
    pdf.set_line_width(0.2) # Reset

    # --- Main Content Container ---
    
    # --- Receipt Title & Meta ---
    pdf.ln(5)
    # Reset Y to safe area below header
    pdf.set_y(35)
    
    pdf.set_font("Arial", 'B', 20)
    pdf.set_text_color(30, 41, 59)
    pdf.cell(70, 10, txt="RECEIPT", ln=0, align="L")
    
    # Receipt Box (Right)
    pdf.set_fill_color(240, 240, 240)
    pdf.set_font("Arial", 'B', 10)
    # Adjusted width to align with right margin (10mm left + 128mm content = 138mm right edge)
    pdf.cell(58, 10, txt=f"#{booking.booking_id}", ln=1, align="R", fill=True)
    
    pdf.ln(5)
    
    # --- Two Columns: Bill To & Details ---
    col_y = pdf.get_y()
    
    # Column 1: Bill To
    pdf.set_fill_color(*primary_color)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Arial", 'B', 9)
    pdf.cell(60, 6, txt="  BILL TO", ln=1, fill=True)
    
    pdf.set_text_color(30, 41, 59)
    pdf.set_font("Arial", 'B', 10)
    pdf.ln(2)
    pdf.cell(60, 5, txt=booking.guest_name, ln=1)
    
    pdf.set_font("Arial", '', 9)
    pdf.cell(60, 4, txt=booking.guest_email, ln=1)
    if booking.guest_phone:
        pdf.cell(60, 4, txt=booking.guest_phone, ln=1)
        
    # Column 2: Details (Right)
    # Align to right margin: 10 + 128 = 138. Box width 58. Start X = 138 - 58 = 80.
    pdf.set_xy(80, col_y)
    pdf.set_fill_color(30, 41, 59) # Dark/Black background for "BOOKING DETAILS"
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Arial", 'B', 9)
    pdf.cell(58, 6, txt="  BOOKING DETAILS", ln=1, fill=True)
    
    pdf.set_x(80)
    pdf.ln(2)
    
    def print_detail_row(label, value):
        x = pdf.get_x()
        pdf.set_font("Arial", '', 8)
        pdf.set_text_color(100, 100, 100)
        pdf.cell(20, 4, txt=label, align="L")
        pdf.set_font("Arial", 'B', 8)
        pdf.set_text_color(30, 41, 59)
        pdf.cell(38, 4, txt=value, align="R", ln=1)
        pdf.set_x(x)

    pdf.set_x(80)
    print_detail_row("Date:", booking.created_at.strftime("%Y-%m-%d"))
    print_detail_row("Check-in:", booking.check_in_date.strftime("%b %d, %Y"))
    print_detail_row("Check-out:", booking.check_out_date.strftime("%b %d, %Y"))
    
    # Payment Method
    pm_display = "N/A"
    if booking.invoices.exists():
        payment = booking.invoices.first().payments.last()
        if payment:
            pm_display = payment.get_payment_method_display()
    print_detail_row("Payment:", pm_display)
    
    # Payment Status
    status = "UNPAID"
    if booking.invoices.exists() and booking.invoices.first().status == 'PAID':
        status = "PAID"
    print_detail_row("Status:", status)

    pdf.ln(10)
    
    # --- Financial Table ---
    # Header
    pdf.set_y(max(pdf.get_y(), col_y + 35)) # Ensure we don't overlap if content is long
    
    pdf.set_fill_color(240, 240, 240)
    pdf.set_text_color(30, 41, 59)
    pdf.set_font("Arial", 'B', 9)
    
    # Reduced widths to sum to 128mm (10mm left margin + 128mm width + 10mm right margin = 148mm A5 width)
    w_desc = 65
    w_rate = 20
    w_qty = 13
    w_total = 30
    
    pdf.cell(w_desc, 8, txt="  Description", border="B", fill=True)
    pdf.cell(w_rate, 8, txt="Rate", border="B", fill=True, align="C")
    pdf.cell(w_qty, 8, txt="Qty", border="B", fill=True, align="C")
    pdf.cell(w_total, 8, txt="Total  ", border="B", fill=True, align="R", ln=1)
    
    # Rows
    pdf.set_font("Arial", '', 9)
    
    # Room Charge
    currency_symbol = '$'
    if hasattr(settings, 'currency_symbol') and settings.currency_symbol:
        currency_symbol = settings.currency_symbol
        if currency_symbol == '₦':
             currency_symbol = 'N'

    desc = f"{booking.room.room_type.name} - Room {booking.room.room_number}"
    rate = f"{currency_symbol}{booking.room.room_type.price_per_night}"
    qty = str(booking.duration_days)
    
    # Base room total
    room_total = booking.total_price
    total = f"{currency_symbol}{room_total}"
    
    pdf.cell(w_desc, 8, txt=f"  {desc}", border="B")
    pdf.cell(w_rate, 8, txt=rate, border="B", align="C")
    pdf.cell(w_qty, 8, txt=qty, border="B", align="C")
    pdf.cell(w_total, 8, txt=f"{total}  ", border="B", align="R", ln=1)
    
    # Room Service Orders
    orders_total = 0
    orders = booking.orders.exclude(status='CANCELLED')
    if orders.exists():
        for order in orders:
            for item in order.items.all():
                item_name = item.menu_item.name
                # Truncate if too long to fit in description column
                if len(item_name) > 30:
                    item_name = item_name[:27] + "..."
                
                item_price = item.menu_item.price
                item_qty = item.quantity
                item_subtotal = item_price * item_qty
                orders_total += item_subtotal
                
                desc_txt = f"  {item_name} (Order #{order.id})"
                rate_str = f"{currency_symbol}{item_price}"
                qty_str = str(item_qty)
                total_str = f"{currency_symbol}{item_subtotal}"
                
                pdf.cell(w_desc, 8, txt=desc_txt, border="B")
                pdf.cell(w_rate, 8, txt=rate_str, border="B", align="C")
                pdf.cell(w_qty, 8, txt=qty_str, border="B", align="C")
                pdf.cell(w_total, 8, txt=f"{total_str}  ", border="B", align="R", ln=1)

    # --- Totals ---
    pdf.ln(2)
    
    grand_total = room_total + orders_total
    
    def print_total_row(label, value, is_bold=False):
        pdf.set_x(80) # Align with right column block
        pdf.set_font("Arial", 'B' if is_bold else '', 9 if not is_bold else 11)
        pdf.set_text_color(30, 41, 59)
        pdf.cell(25, 6, txt=label, align="R")
        pdf.cell(33, 6, txt=value + "  ", align="R", ln=1)

    print_total_row("Subtotal:", f"{currency_symbol}{grand_total}")
    print_total_row("Tax (0%):", f"{currency_symbol}0.00")
    
    pdf.set_x(80)
    pdf.set_draw_color(30, 41, 59)
    pdf.line(105, pdf.get_y(), 138, pdf.get_y())
    
    print_total_row("TOTAL:", f"{currency_symbol}{grand_total}", is_bold=True)
    
    # --- Footer ---
    pdf.set_y(-45)
    
    # QR Code (Left)
    try:
        # Generate Verification URL
        verification_url = request.build_absolute_uri(reverse('verify_booking')) + f"?code={booking.booking_id}"
        
        qr = qrcode.QRCode(box_size=10, border=2)
        qr.add_data(verification_url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        
        import tempfile
        import os
        with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as tmp_file:
            img.save(tmp_file, format="PNG")
            tmp_path = tmp_file.name
            
        pdf.image(tmp_path, x=10, y=pdf.get_y(), w=25)
        os.unlink(tmp_path)
    except:
        pass
        
    # Thank You Note (Right of QR)
    pdf.set_xy(40, -40)
    pdf.set_font("Arial", 'B', 10)
    pdf.cell(0, 5, txt="THANK YOU FOR YOUR BUSINESS!", ln=1)
    
    pdf.set_x(40)
    pdf.set_font("Arial", '', 8)
    pdf.set_text_color(100, 100, 100)
    pdf.multi_cell(0, 4, txt="For any inquiries concerning this receipt, please contact us using the details above.")
    
    # Bottom Bar
    pdf.set_auto_page_break(auto=False) # Disable auto break for footer
    pdf.set_y(-10)
    pdf.set_fill_color(*primary_color)
    pdf.rect(0, 200, 148, 10, 'F') # Bottom colored strip
    
    # Line 1: Hotel Website/Name
    pdf.set_y(201)
    pdf.set_font("Arial", 'I', 7)
    pdf.set_text_color(255, 255, 255)
    hotel_text = settings.website_url if hasattr(settings, 'website_url') else settings.hotel_name
    pdf.cell(0, 4, txt=hotel_text, align="C", ln=1)
    
    # Line 2: Powered by TechOhr (Link)
    pdf.set_font("Arial", 'B', 6)
    pdf.cell(0, 4, txt="Powered by TechOhr", align="C", link="https://techohr.com.ng")
    # Output PDF
    import tempfile
    import os

    # Create a temporary file for the PDF
    with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_pdf:
        tmp_pdf_path = tmp_pdf.name

    try:
        pdf.output(name=tmp_pdf_path, dest='F')
        
        # Read the file content
        with open(tmp_pdf_path, 'rb') as f:
            pdf_content = f.read()
            
        # Create response
        response = HttpResponse(pdf_content, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="Receipt_{booking.id}.pdf"'
        
    finally:
        # Clean up
        if os.path.exists(tmp_pdf_path):
            os.unlink(tmp_pdf_path)
    
    return response
