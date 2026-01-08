from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.urls import reverse_lazy
from django.contrib import messages
from .models import EventHall, EventBooking, EventHallImage
from .forms import EventHallForm, EventBookingForm

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

class EventHallDetailView(LoginRequiredMixin, DetailView):
    model = EventHall
    template_name = 'events/hall_detail.html'
    context_object_name = 'hall'

class EventHallCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    model = EventHall
    form_class = EventHallForm
    template_name = 'events/hall_form.html'
    success_url = reverse_lazy('event_hall_list')

    def test_func(self):
        return self.request.user.can_manage_events

    def form_valid(self, form):
        response = super().form_valid(form)
        # Handle multiple images
        images = self.request.FILES.getlist('gallery_images')
        for image in images:
            EventHallImage.objects.create(hall=self.object, image=image)
            
        messages.success(self.request, "Event Hall created successfully.")
        return response

class EventHallUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    model = EventHall
    form_class = EventHallForm
    template_name = 'events/hall_form.html'
    success_url = reverse_lazy('event_hall_list')

    def test_func(self):
        return self.request.user.can_manage_events

    def form_valid(self, form):
        response = super().form_valid(form)
        # Handle multiple images
        images = self.request.FILES.getlist('gallery_images')
        for image in images:
            EventHallImage.objects.create(hall=self.object, image=image)
            
        messages.success(self.request, "Event Hall updated successfully.")
        return response

class EventHallDeleteView(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    model = EventHall
    template_name = 'events/hall_confirm_delete.html'
    success_url = reverse_lazy('event_hall_list')

    def test_func(self):
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
