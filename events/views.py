from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.urls import reverse_lazy
from django.contrib import messages
from .models import EventHall, EventBooking, EventHallImage
from .forms import EventHallForm, EventBookingForm, StaffEventBookingForm, PublicEventBookingForm

# --- Hall Management (Admin/Manager/Event Manager) ---

class EventHallListView(LoginRequiredMixin, ListView):
    model = EventHall
    template_name = 'events/hall_list.html'
    context_object_name = 'halls'

    def get_queryset(self):
        # Staff see all, guests/others see only active
        if self.request.user.is_staff:
            return EventHall.objects.all()
        return EventHall.objects.filter(is_active=True)

class PublicEventHallListView(ListView):
    model = EventHall
    template_name = 'events/public_hall_list.html'
    context_object_name = 'halls'

    def get_queryset(self):
        # Filter by Tenant Isolation
        queryset = EventHall.objects.filter(is_active=True)
        if hasattr(self.request, 'tenant') and self.request.tenant:
            queryset = queryset.filter(tenant=self.request.tenant)
        return queryset

class EventHallDetailView(DetailView):
    model = EventHall
    template_name = 'events/hall_detail.html'
    context_object_name = 'hall'

class EventHallCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    model = EventHall
    form_class = EventHallForm
    template_name = 'events/hall_form.html'
    success_url = reverse_lazy('event_hall_list')

    def test_func(self):
        # Check Module Limit
        if self.request.tenant and self.request.tenant.plan:
             if not self.request.tenant.plan.module_events:
                 return False

        # Explicit check for Tenant Owner
        if self.request.tenant and self.request.tenant.owner == self.request.user:
            return True
        return self.request.user.can_manage_events

    def post(self, request, *args, **kwargs):
        print(f"DEBUG: EventHallCreateView POST. POST keys: {request.POST.keys()}, FILES keys: {request.FILES.keys()}")
        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        # Attach Tenant
        if not self.request.tenant:
            messages.error(self.request, "Cannot create hall without a valid workspace context.")
            return self.form_invalid(form)
            
        form.instance.tenant = self.request.tenant
        
        response = super().form_valid(form)
        # Handle multiple images
        images = self.request.FILES.getlist('gallery_images')
        for image in images:
            EventHallImage.objects.create(hall=self.object, image=image)
            
        messages.success(self.request, "Event Hall created successfully.")
        return response
    
    def form_invalid(self, form):
        messages.error(self.request, "Error creating Event Hall. Please check the form below.")
        print(f"DEBUG: Event Hall Form Errors: {form.errors}") # For console debugging
        return super().form_invalid(form)

class EventHallUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    model = EventHall
    form_class = EventHallForm
    template_name = 'events/hall_form.html'
    success_url = reverse_lazy('event_hall_list')

    def test_func(self):
        # Explicit check for Tenant Owner
        if self.request.tenant and self.request.tenant.owner == self.request.user:
            return True
        return self.request.user.can_manage_events

    def form_valid(self, form):
        response = super().form_valid(form)
        # Handle multiple images
        images = self.request.FILES.getlist('gallery_images')
        for image in images:
            EventHallImage.objects.create(hall=self.object, image=image)
            
        messages.success(self.request, "Event Hall updated successfully.")
        return response

    def form_invalid(self, form):
        messages.error(self.request, "Error updating Event Hall. Please check the form below.")
        return super().form_invalid(form)

class EventHallDeleteView(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    model = EventHall
    template_name = 'events/hall_confirm_delete.html'
    success_url = reverse_lazy('event_hall_list')

    def test_func(self):
        # Explicit check for Tenant Owner
        if self.request.tenant and self.request.tenant.owner == self.request.user:
            return True
        return self.request.user.can_manage_events

# --- Booking Management ---

class EventBookingListView(LoginRequiredMixin, ListView):
    model = EventBooking
    template_name = 'events/booking_list.html'
    context_object_name = 'bookings'
    ordering = ['-created_at']

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.user.can_manage_events:
            return qs # All bookings
        return qs.filter(user=self.request.user) # My bookings

class EventBookingCreateView(LoginRequiredMixin, CreateView):
    model = EventBooking
    form_class = EventBookingForm
    template_name = 'events/booking_form.html'
    success_url = reverse_lazy('event_booking_list')

    def form_valid(self, form):
        form.instance.user = self.request.user
        messages.success(self.request, "Booking request submitted successfully.")
        response = super().form_valid(form)
        
        # Create Invoice
        from billing.models import Invoice
        Invoice.objects.create(
            event_booking=form.instance,
            amount=form.instance.total_price,
            status=Invoice.Status.PENDING,
            due_date=form.instance.start_time.date()
        )
        
        # Create Notification
        from core.models import Notification
        Notification.objects.create(
            recipient=self.request.user,
            title="Event Booking Submitted",
            message=f"Your booking request for {form.instance.event_name} at {form.instance.hall.name} has been submitted and is pending approval.",
            notification_type='INFO',
            link=reverse_lazy('event_booking_detail', kwargs={'pk': form.instance.pk})
        )

        # Send Confirmation Email
        try:
            from core.utils import send_branded_email
            user = self.request.user
            context = {'booking': self.object, 'user': user}
            send_branded_email(
                subject=f"Event Booking Confirmation - {self.object.event_name}",
                template_name='emails/event_booking_confirmation.html',
                context=context,
                recipient_list=[user.email],
                tenant=self.request.tenant
            )
            messages.success(self.request, f"Receipt sent to {user.email}")
        except Exception as e:
            print(f"Error sending email: {e}")

        return response

class EventBookingDetailView(LoginRequiredMixin, DetailView):
    model = EventBooking
    template_name = 'events/booking_detail.html'
    context_object_name = 'booking'

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.user.can_manage_events:
            return qs
        return qs.filter(user=self.request.user)

@login_required
def update_booking_status(request, pk, status):
    if not request.user.can_manage_events:
        messages.error(request, "Permission denied.")
        return redirect('event_booking_list')
    
    booking = get_object_or_404(EventBooking, pk=pk)
    if status in ['CONFIRMED', 'COMPLETED', 'CANCELLED']:
        booking.status = status
        booking.save()
        messages.success(request, f"Booking status updated to {status}.")
        
        # Create Notification
        from core.models import Notification
        Notification.objects.create(
            recipient=booking.user,
            title=f"Event Booking {status.title()}",
            message=f"Your booking for {booking.event_name} has been {status.lower()}.",
            notification_type='SUCCESS' if status in ['CONFIRMED', 'COMPLETED'] else 'WARNING',
            link=reverse_lazy('event_booking_detail', kwargs={'pk': booking.pk})
        )
    
    return redirect('event_booking_detail', pk=pk)

class StaffEventBookingView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    model = EventBooking
    form_class = StaffEventBookingForm
    template_name = 'events/staff_booking_form.html'
    success_url = reverse_lazy('event_booking_list')

    def test_func(self):
        # Explicit check for Tenant Owner
        if self.request.tenant and self.request.tenant.owner == self.request.user:
            return True
        return self.request.user.can_manage_events

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        # Pass request to form if needed, though mostly handled in view logic
        return kwargs

    def form_valid(self, form):
        from django.contrib.auth import get_user_model
        from django.utils.crypto import get_random_string
        from core.email_utils import send_branded_email
        from billing.models import Invoice

        User = get_user_model()
        guest_email = form.cleaned_data.get('guest_email')
        guest_name = form.cleaned_data.get('guest_name')
        guest_phone = form.cleaned_data.get('guest_phone')

        user = None
        created_password = None

        # 1. Handle User Resolution
        if guest_email:
            try:
                user = User.objects.get(email=guest_email)
                messages.info(self.request, f"Found existing user: {user.username}")
            except User.DoesNotExist:
                # Create new Guest User
                username = guest_email.split('@')[0]
                # Ensure unique username
                base_username = username
                counter = 1
                while User.objects.filter(username=username).exists():
                    username = f"{base_username}{counter}"
                    counter += 1
                
                created_password = get_random_string(8)
                user = User.objects.create_user(
                    username=username,
                    email=guest_email,
                    password=created_password,
                    first_name=guest_name or "Guest",
                    phone_number=guest_phone,
                    role=User.Role.GUEST
                )
                messages.success(self.request, f"Created new guest account for {guest_email}")
        else:
            # If no email, link to the staff member (not ideal but fallback) or require email
            # Ideally we should require email for receipt, but if not provided:
            messages.warning(self.request, "No email provided. Booking linked to current staff user.")
            user = self.request.user

        # 2. Set Booking Details
        form.instance.user = user
        form.instance.status = 'CONFIRMED' # Manual booking is confirmed immediately
        
        response = super().form_valid(form)
        
        # 3. Create Paid Invoice
        invoice = Invoice.objects.create(
            event_booking=self.object,
            amount=self.object.total_price,
            status=Invoice.Status.PAID, # Assumed paid at desk
            due_date=self.object.start_time.date()
        )

        # 4. Send Receipt Email
        if user.email:
            context = {
                'booking': self.object,
                'user': user,
                'password': created_password, # Only if created
                'invoice': invoice,
                'qr_url': self.object.qr_code.url if self.object.qr_code else None
            }
            
            # We'll need a template for this
            try:
                send_branded_email(
                    subject=f"Event Booking Confirmation - {self.object.event_name}",
                    template_name='emails/event_booking_confirmation.html', 
                    context=context,
                    recipient_list=[user.email],
                    tenant=self.request.tenant
                )
                messages.success(self.request, f"Receipt sent to {user.email}")
            except Exception as e:
                messages.error(self.request, f"Failed to send email: {e}")

        return response

class EventVerificationView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    """
    View to verify event bookings via QR code or Reference ID.
    Acts as a dashboard for verification.
    """
    model = EventBooking
    template_name = 'events/verify_booking.html'
    context_object_name = 'bookings'

    def test_func(self):
        # Explicit check for Tenant Owner
        if self.request.tenant and self.request.tenant.owner == self.request.user:
            return True
        return self.request.user.can_manage_events

    def get_queryset(self):
        query = self.request.GET.get('q')
        if not query:
            return EventBooking.objects.none()
        
        # Parse QR Code content: EVENT-BOOKING-{id}-{username}
        booking_id = query
        if query.startswith('EVENT-BOOKING-'):
            parts = query.split('-')
            if len(parts) >= 3:
                booking_id = parts[2]
        
        # Filter by tenant if applicable (though ID is unique)
        qs = EventBooking.objects.filter(id=booking_id)
        if hasattr(self.request, 'tenant') and self.request.tenant:
            # Join through Hall -> Tenant
            qs = qs.filter(hall__tenant=self.request.tenant)
            
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['query'] = self.request.GET.get('q', '')
        return context

class PublicEventBookingCreateView(CreateView):
    model = EventBooking
    form_class = PublicEventBookingForm
    template_name = 'events/public_booking_form.html'
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs
        
    def get_initial(self):
        initial = super().get_initial()
        hall_id = self.request.GET.get('hall')
        if hall_id:
            hall = get_object_or_404(EventHall, pk=hall_id)
            initial['hall'] = hall
        return initial

    def form_valid(self, form):
        from django.contrib.auth import get_user_model, login
        from django.utils.crypto import get_random_string
        from billing.models import Invoice
        
        User = get_user_model()
        user = self.request.user
        
        # 1. Handle User Creation/Auth
        if not user.is_authenticated:
            email = form.cleaned_data['email']
            full_name = form.cleaned_data['full_name']
            phone_number = form.cleaned_data['phone_number']
            
            try:
                user = User.objects.get(email=email)
                # Ideally prompt for login, but for smoother flow we might link or error
                # For now, let's link but maybe not login to avoid security risk without password
                # Or require them to login first. 
                # Strategy: If user exists, attach booking to them. If they want to see it, they must login.
                pass 
            except User.DoesNotExist:
                # Create Guest User
                username = email.split('@')[0]
                base_username = username
                counter = 1
                while User.objects.filter(username=username).exists():
                    username = f"{base_username}{counter}"
                    counter += 1
                
                password = get_random_string(8)
                user = User.objects.create_user(
                    username=username,
                    email=email,
                    password=password,
                    first_name=full_name.split(' ')[0],
                    last_name=' '.join(full_name.split(' ')[1:]) if ' ' in full_name else '',
                    phone_number=phone_number,
                    role=User.Role.GUEST
                )
                
                # Auto-login the new user so they can pay
                login(self.request, user)
                
                # Send welcome email with password
                # (Implementation skipped for brevity, similar to staff booking)
        
        form.instance.user = user
        form.instance.status = 'PENDING'
        
        response = super().form_valid(form)
        
        # 2. Create Invoice
        invoice = Invoice.objects.create(
            event_booking=self.object,
            amount=self.object.total_price,
            status=Invoice.Status.PENDING,
            due_date=self.object.start_time.date(),
            tenant=self.request.tenant if hasattr(self.request, 'tenant') else None
        )
        
        # 3. Redirect to Payment
        return redirect('payment_selection', invoice_id=invoice.pk)
