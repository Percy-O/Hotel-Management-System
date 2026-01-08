from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.conf import settings
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.db import models
from .models import Invoice, Payment, PaymentGateway
from booking.models import Booking
from core.models import Notification, SiteSetting
from django.urls import reverse
import json
import io
import qrcode
import base64
from fpdf import FPDF
import os
import tempfile

def is_admin(user):
    return user.is_authenticated and user.is_staff

@login_required
def invoice_list(request):
    invoices = Invoice.objects.filter(booking__user=request.user).order_by('-issued_date')
    
    # Financial Reports (Transactions, Monthly/Weekly Sales) - Only for Staff/Admin
    context = {'invoices': invoices}
    
    if request.user.is_staff:
        # Transactions (All Payments)
        transactions = Payment.objects.all().order_by('-payment_date')
        
        # Calculate Date Ranges
        now = timezone.now()
        start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        start_of_week = now - timezone.timedelta(days=now.weekday())
        start_of_week = start_of_week.replace(hour=0, minute=0, second=0, microsecond=0)
        start_of_year = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        
        # Sales Aggregations
        monthly_sales = Payment.objects.filter(payment_date__gte=start_of_month).aggregate(total=models.Sum('amount'))['total'] or 0
        weekly_sales = Payment.objects.filter(payment_date__gte=start_of_week).aggregate(total=models.Sum('amount'))['total'] or 0
        yearly_sales = Payment.objects.filter(payment_date__gte=start_of_year).aggregate(total=models.Sum('amount'))['total'] or 0
        
        # Update context
        context.update({
            'transactions': transactions,
            'monthly_sales': monthly_sales,
            'weekly_sales': weekly_sales,
            'yearly_sales': yearly_sales,
            'invoices': Invoice.objects.all().order_by('-issued_date') # Staff sees all invoices
        })
        
    return render(request, 'billing/invoice_list.html', context)

@login_required
def my_invoices(request):
    """View for guests to see their own invoices."""
    if request.user.is_staff:
        return redirect('invoice_list')
        
    invoices = Invoice.objects.filter(
        models.Q(booking__user=request.user) |
        models.Q(event_booking__user=request.user) |
        models.Q(gym_membership__user=request.user)
    ).distinct().order_by('-issued_date')
    
    return render(request, 'billing/my_invoices.html', {'invoices': invoices})

@login_required
def invoice_detail(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk)
    
    # Determine user for permission check
    invoice_user = None
    if invoice.booking: invoice_user = invoice.booking.user
    elif invoice.event_booking: invoice_user = invoice.event_booking.user
    elif invoice.gym_membership: invoice_user = invoice.gym_membership.user
    
    if not request.user.is_staff and invoice_user != request.user:
        messages.error(request, "Access denied.")
        return redirect('home')
    return render(request, 'billing/invoice_detail.html', {'invoice': invoice})

@login_required
def make_payment(request, pk):
    """
    Redirect to payment selection using invoice ID.
    """
    invoice = get_object_or_404(Invoice, pk=pk)
    return redirect('payment_selection', invoice_id=invoice.pk)

def payment_selection(request, invoice_id):
    invoice = get_object_or_404(Invoice, pk=invoice_id)
    
    # Determine Context Object
    context_obj = None
    context_type = 'unknown'
    user = None
    email = ''
    phone = ''
    name = ''
    description = ''
    
    if invoice.booking:
        context_obj = invoice.booking
        context_type = 'booking'
        user = context_obj.user
        email = context_obj.guest_email
        phone = context_obj.guest_phone
        name = context_obj.guest_name
        description = f"Hotel Booking #{context_obj.booking_id}"
        
        if context_obj.status == Booking.Status.CONFIRMED and invoice.status == Invoice.Status.PAID:
             messages.info(request, "This booking is already paid and confirmed.")
             return redirect('booking_detail', pk=context_obj.pk)

    elif invoice.event_booking:
        context_obj = invoice.event_booking
        context_type = 'event'
        user = context_obj.user
        email = user.email
        phone = getattr(user, 'phone_number', '')
        name = f"{user.first_name} {user.last_name}"
        description = f"Event: {context_obj.event_name}"
        
        if context_obj.status == 'CONFIRMED' and invoice.status == Invoice.Status.PAID:
             messages.info(request, "This event is already paid and confirmed.")
             return redirect('event_booking_detail', pk=context_obj.pk)

    elif invoice.gym_membership:
        context_obj = invoice.gym_membership
        context_type = 'gym'
        user = context_obj.user
        email = user.email
        phone = getattr(user, 'phone_number', '')
        name = f"{user.first_name} {user.last_name}"
        description = f"Gym Membership: {context_obj.plan.name}"
        
        if invoice.status == Invoice.Status.PAID:
             messages.info(request, "This membership is already paid.")
             return redirect('gym_membership_list')

    # Security Check
    if request.user.is_authenticated:
        if not request.user.is_staff and user and user != request.user:
             messages.error(request, "Access denied.")
             return redirect('home')
    
    gateways = PaymentGateway.objects.filter(is_active=True)
    
    # Get Keys
    paystack_key = None
    flutterwave_key = None
    
    paystack_gw = gateways.filter(name=PaymentGateway.Provider.PAYSTACK).first()
    if paystack_gw:
        paystack_key = paystack_gw.public_key
        
    flutterwave_gw = gateways.filter(name=PaymentGateway.Provider.FLUTTERWAVE).first()
    if flutterwave_gw:
        flutterwave_key = flutterwave_gw.public_key

    context = {
        'invoice': invoice,
        'context_obj': context_obj,
        'context_type': context_type,
        'description': description,
        'paystack_enabled': paystack_gw is not None,
        'flutterwave_enabled': flutterwave_gw is not None,
        'paystack_key': paystack_key,
        'flutterwave_key': flutterwave_key,
        'amount': int(invoice.amount * 100) if paystack_gw else invoice.amount, # Paystack uses kobo
        'currency': 'NGN', # Assuming NGN for now
        'email': email,
        'phone': phone,
        'name': name,
        'ref': f"HMS-INV-{invoice.id}-{int(timezone.now().timestamp())}"
    }
    return render(request, 'billing/payment_selection.html', context)

def verify_payment(request, gateway):
    """
    Callback for payment verification
    """
    ref = request.GET.get('reference') or request.GET.get('tx_ref') # Paystack uses reference, FW uses tx_ref
    invoice_id = request.GET.get('invoice_id')
    
    if not ref or not invoice_id:
        messages.error(request, "Invalid payment verification parameters.")
        return redirect('home')
        
    invoice = get_object_or_404(Invoice, pk=invoice_id)
    
    # In a real app, verify with backend API using secret key
    success = True # Simulate verification
    
    if success:
        if invoice.status != Invoice.Status.PAID:
            # Create Payment Record
            Payment.objects.create(
                invoice=invoice,
                amount=invoice.amount,
                payment_method=gateway.upper(),
                transaction_id=ref
            )
            
            # Update Invoice
            invoice.status = Invoice.Status.PAID
            invoice.save()
            
            # Handle Specific Object Updates & Notifications
            redirect_url = 'home'
            
            if invoice.booking:
                booking = invoice.booking
                booking.status = Booking.Status.CONFIRMED
                booking.save()
                redirect_url = reverse('booking_detail', kwargs={'pk': booking.pk})
                
                if booking.user:
                    Notification.objects.create(
                        recipient=booking.user,
                        title="Payment Successful",
                        message=f"Your payment for booking #{booking.booking_id} was successful.",
                        notification_type=Notification.Type.SUCCESS,
                        link=redirect_url
                    )

            elif invoice.event_booking:
                event = invoice.event_booking
                event.status = 'CONFIRMED'
                event.save()
                redirect_url = reverse('event_booking_detail', kwargs={'pk': event.pk})
                
                Notification.objects.create(
                    recipient=event.user,
                    title="Event Payment Successful",
                    message=f"Your payment for event '{event.event_name}' was successful.",
                    notification_type=Notification.Type.SUCCESS,
                    link=redirect_url
                )

            elif invoice.gym_membership:
                gym = invoice.gym_membership
                gym.status = 'ACTIVE'
                gym.payment_status = 'PAID'
                gym.save()
                redirect_url = reverse('gym_membership_list')
                
                Notification.objects.create(
                    recipient=gym.user,
                    title="Gym Membership Active",
                    message=f"Your {gym.plan.name} membership is now active.",
                    notification_type=Notification.Type.SUCCESS,
                    link=redirect_url
                )
            
            messages.success(request, "Payment successful!")
        else:
            messages.info(request, "Payment already recorded.")
            # Determine redirect based on object
            if invoice.booking:
                return redirect('booking_detail', pk=invoice.booking.pk)
            elif invoice.event_booking:
                return redirect('event_booking_detail', pk=invoice.event_booking.pk)
            elif invoice.gym_membership:
                return redirect('gym_membership_list')
            
        return redirect(redirect_url)
    else:
        messages.error(request, "Payment verification failed.")
        return redirect('payment_selection', invoice_id=invoice.pk)

@login_required
def download_receipt(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk)
    
    # Permission check: Owner or Staff
    invoice_user = None
    if invoice.booking: invoice_user = invoice.booking.user
    elif invoice.event_booking: invoice_user = invoice.event_booking.user
    elif invoice.gym_membership: invoice_user = invoice.gym_membership.user

    if not request.user.is_staff and invoice_user != request.user:
         messages.error(request, "You do not have permission to download this receipt.")
         return redirect('home')

    settings = SiteSetting.load()
    current_theme = settings.theme
    currency_symbol = settings.currency_symbol if hasattr(settings, 'currency_symbol') and settings.currency_symbol else '$'

    # Define Theme Colors (R, G, B)
    THEME_COLORS = {
        'theme-default': (19, 236, 109),
        'theme-light': (19, 236, 109), 
        'theme-blue': (59, 130, 246), 
        'theme-luxury': (212, 175, 55),
        'theme-forest': (74, 222, 128),
        'theme-ocean': (6, 182, 212),
        'theme-sunset': (244, 114, 182),
        'theme-royal': (167, 139, 250),
        'theme-minimal': (113, 113, 122),
    }

    primary_color = THEME_COLORS.get(current_theme, (19, 236, 109))
    
    # Generate PDF (Standard Receipt Size - A5)
    pdf = FPDF(orientation='P', unit='mm', format='A5')
    pdf.set_auto_page_break(auto=False)
    pdf.add_page()
    
    # --- Decorative Header ---
    pdf.set_y(10)
    pdf.set_font("Arial", 'B', 16)
    pdf.set_text_color(*primary_color)
    pdf.cell(0, 8, txt=settings.hotel_name.upper(), ln=1, align="R")
    
    pdf.set_font("Arial", '', 8)
    pdf.set_text_color(60, 60, 60)
    pdf.cell(0, 4, txt="Official Receipt", ln=1, align="R")
    
    pdf.ln(2)
    pdf.set_draw_color(*primary_color)
    pdf.set_line_width(0.5)
    pdf.line(10, pdf.get_y(), 138, pdf.get_y())
    pdf.set_line_width(0.2)

    # --- Receipt Info ---
    pdf.ln(5)
    pdf.set_font("Arial", 'B', 20)
    pdf.set_text_color(30, 41, 59)
    pdf.cell(70, 10, txt="RECEIPT", ln=0, align="L")
    
    pdf.set_fill_color(240, 240, 240)
    pdf.set_font("Arial", 'B', 10)
    pdf.cell(58, 10, txt=f"INV #{invoice.id}", ln=1, align="R", fill=True)
    
    pdf.ln(5)
    
    # --- Details ---
    col_y = pdf.get_y()
    
    # Bill To
    pdf.set_fill_color(*primary_color)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Arial", 'B', 9)
    pdf.cell(60, 6, txt="  BILL TO", ln=1, fill=True)
    
    pdf.set_text_color(30, 41, 59)
    pdf.set_font("Arial", 'B', 10)
    pdf.ln(2)
    
    guest_name = "Guest"
    guest_email = ""
    
    if invoice.booking:
        guest_name = invoice.booking.guest_name
        guest_email = invoice.booking.guest_email
    elif invoice_user:
        guest_name = f"{invoice_user.first_name} {invoice_user.last_name}"
        guest_email = invoice_user.email
        
    pdf.cell(60, 5, txt=guest_name, ln=1)
    pdf.set_font("Arial", '', 9)
    pdf.cell(60, 4, txt=guest_email, ln=1)
    
    # Details Column
    pdf.set_xy(80, col_y)
    pdf.set_fill_color(30, 41, 59)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Arial", 'B', 9)
    pdf.cell(58, 6, txt="  DETAILS", ln=1, fill=True)
    
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
    print_detail_row("Date:", invoice.issued_date.strftime("%Y-%m-%d"))
    
    status = invoice.get_status_display().upper()
    print_detail_row("Status:", status)
    
    payment = invoice.payments.last()
    if payment:
        print_detail_row("Method:", payment.get_payment_method_display())
        print_detail_row("Ref:", payment.transaction_id[:15] + "..." if len(payment.transaction_id) > 15 else payment.transaction_id)

    pdf.ln(10)
    
    # --- Line Items ---
    pdf.set_y(max(pdf.get_y(), col_y + 35))
    
    pdf.set_fill_color(240, 240, 240)
    pdf.set_text_color(30, 41, 59)
    pdf.set_font("Arial", 'B', 9)
    
    w_desc = 98
    w_total = 30
    
    pdf.cell(w_desc, 8, txt="  Description", border="B", fill=True)
    pdf.cell(w_total, 8, txt="Total  ", border="B", fill=True, align="R", ln=1)
    
    pdf.set_font("Arial", '', 9)
    
    desc = "Service Charge"
    if invoice.booking:
        desc = f"Hotel Booking: {invoice.booking.room.room_type.name}"
    elif invoice.event_booking:
        desc = f"Event Booking: {invoice.event_booking.event_name}"
    elif invoice.gym_membership:
        desc = f"Gym Membership: {invoice.gym_membership.plan.name}"
        
    pdf.cell(w_desc, 8, txt=f"  {desc}", border="B")
    pdf.cell(w_total, 8, txt=f"{currency_symbol}{invoice.amount}  ", border="B", align="R", ln=1)
    
    # Totals
    pdf.ln(5)
    pdf.set_font("Arial", 'B', 11)
    pdf.cell(w_desc, 8, txt="TOTAL", align="R")
    pdf.cell(w_total, 8, txt=f"{currency_symbol}{invoice.amount}  ", align="R", border="T")
    
    # Output
    with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_pdf:
        tmp_pdf_path = tmp_pdf.name

    try:
        pdf.output(name=tmp_pdf_path, dest='F')
        with open(tmp_pdf_path, 'rb') as f:
            pdf_content = f.read()
        response = HttpResponse(pdf_content, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="Receipt_{invoice.id}.pdf"'
    finally:
        if os.path.exists(tmp_pdf_path):
            os.unlink(tmp_pdf_path)
            
    return response

@user_passes_test(is_admin)
def payment_settings(request):
    gateways = PaymentGateway.objects.all()
    
    # Ensure default entries exist
    if not gateways.exists():
        PaymentGateway.objects.get_or_create(name=PaymentGateway.Provider.PAYSTACK)
        PaymentGateway.objects.get_or_create(name=PaymentGateway.Provider.FLUTTERWAVE)
        gateways = PaymentGateway.objects.all()
    
    if request.method == 'POST':
        for gw in gateways:
            is_active = request.POST.get(f"{gw.name}_active") == 'on'
            public_key = request.POST.get(f"{gw.name}_public")
            secret_key = request.POST.get(f"{gw.name}_secret")
            
            gw.is_active = is_active
            gw.public_key = public_key
            gw.secret_key = secret_key
            gw.save()
        
        messages.success(request, "Payment settings updated.")
        return redirect('payment_settings')
        
    return render(request, 'billing/payment_settings.html', {'gateways': gateways})