from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from core.email_utils import send_tenant_email
from django.conf import settings
from .models import MenuItem, GuestOrder, OrderItem, HousekeepingRequest, HousekeepingServiceType
from .forms import HousekeepingSettingsForm
from booking.models import Booking
from billing.models import Invoice
from core.models import Notification, TenantSetting
from accounts.models import User
from django.db.models import Q

from django.views.generic import ListView, CreateView, UpdateView, DeleteView
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.urls import reverse_lazy, reverse

# --- Menu Management Views ---

class MenuManagementMixin(UserPassesTestMixin):
    def test_func(self):
        user = self.request.user
        return user.can_manage_menu

class MenuItemListView(LoginRequiredMixin, MenuManagementMixin, ListView):
    model = MenuItem
    template_name = 'services/menu_item_list.html'
    context_object_name = 'menu_items'
    ordering = ['category', 'name']

class MenuItemCreateView(LoginRequiredMixin, MenuManagementMixin, CreateView):
    model = MenuItem
    fields = ['name', 'description', 'price', 'category', 'image', 'is_available']
    template_name = 'services/menu_item_form.html'
    success_url = reverse_lazy('menu_item_list')

    def form_valid(self, form):
        messages.success(self.request, "Menu item created successfully.")
        return super().form_valid(form)

class MenuItemUpdateView(LoginRequiredMixin, MenuManagementMixin, UpdateView):
    model = MenuItem
    fields = ['name', 'description', 'price', 'category', 'image', 'is_available']
    template_name = 'services/menu_item_form.html'
    success_url = reverse_lazy('menu_item_list')

    def form_valid(self, form):
        messages.success(self.request, "Menu item updated successfully.")
        return super().form_valid(form)

class MenuItemDeleteView(LoginRequiredMixin, MenuManagementMixin, DeleteView):
    model = MenuItem
    template_name = 'services/menu_item_confirm_delete.html'
    success_url = reverse_lazy('menu_item_list')

    def delete(self, request, *args, **kwargs):
        messages.success(self.request, "Menu item deleted successfully.")
        return super().delete(request, *args, **kwargs)

@login_required
def menu_list(request):
    active_booking = Booking.objects.filter(
        user=request.user, 
        status='CHECKED_IN'
    ).first()

    menu_items = MenuItem.objects.filter(is_available=True)
    # Group by category
    items_by_category = {}
    for cat_code, cat_name in MenuItem.CATEGORY_CHOICES:
        items = menu_items.filter(category=cat_code)
        if items.exists():
            items_by_category[cat_name] = items

    context = {
        'items_by_category': items_by_category,
        'active_booking': active_booking
    }
    return render(request, 'services/menu_list.html', context)

from django.db import transaction

@login_required
def place_order(request):
    if request.method == 'POST':
        active_booking = Booking.objects.filter(
            user=request.user, 
            status='CHECKED_IN'
        ).first()

        if not active_booking and not request.user.is_staff:
            messages.error(request, "You must be checked in to place an order.")
            return redirect('guest_dashboard')
        
        room_num = active_booking.room.room_number if active_booking else "Staff Order"
        
        try:
            with transaction.atomic():
                # Create Order
                order = GuestOrder.objects.create(
                    user=request.user,
                    booking=active_booking,
                    room_number=room_num,
                    status='AWAITING_PAYMENT',
                    note=request.POST.get('note', '')
                )
                
                # Process Items
                items_data = request.POST.getlist('items') # Expecting format "item_id:quantity"
                
                has_items = False
                for key, value in request.POST.items():
                    if key.startswith('quantity_') and int(value) > 0:
                        item_id = key.split('_')[1]
                        menu_item = get_object_or_404(MenuItem, id=item_id)
                        OrderItem.objects.create(
                            order=order,
                            menu_item=menu_item,
                            quantity=int(value)
                        )
                        has_items = True
                
                if not has_items:
                    # Transaction will roll back if we raise exception, but here we can just return
                    # However, since we are in atomic block, explicit rollback or raising exception is better.
                    # But since we created 'order' above, we should just let the block finish or raise error.
                    # Actually, if we return, the commit happens. We must raise exception to rollback? 
                    # Or just don't create the order if no items.
                    # Let's check items BEFORE creating order?
                    pass

                if not has_items:
                     raise ValueError("No items selected")

                order.calculate_total()
                
                # Create Invoice
                invoice = Invoice.objects.create(
                    booking=active_booking, # Can be null if staff order
                    amount=order.total_price,
                    status='PENDING',
                    invoice_type=Invoice.Type.SERVICE
                )
                order.invoice = invoice
                order.save()

            messages.info(request, "Please complete payment to process your order.")
            return redirect('payment_selection', invoice_id=invoice.id)

        except ValueError:
            messages.warning(request, "No items selected.")
            return redirect('menu_list')
        except Exception as e:
            messages.error(request, f"An error occurred: {str(e)}")
            return redirect('menu_list')

    return redirect('menu_list')

@login_required
def my_orders(request):
    orders = GuestOrder.objects.filter(user=request.user).order_by('-created_at')
    return render(request, 'services/my_orders.html', {'orders': orders})

@login_required
def staff_order_list(request):
    # Staff/Kitchen/Admin/Manager
    if not (request.user.is_staff or request.user.role in [User.Role.MANAGER, User.Role.ADMIN, User.Role.KITCHEN]):
         messages.error(request, "Access denied.")
         return redirect('home')

    orders = GuestOrder.objects.exclude(status__in=['DELIVERED', 'CANCELLED', 'AWAITING_PAYMENT']).order_by('created_at')
    return render(request, 'services/staff_order_list.html', {'orders': orders})

@login_required
def staff_order_history(request):
    if not (request.user.is_staff or request.user.role in [User.Role.MANAGER, User.Role.ADMIN, User.Role.KITCHEN]):
         messages.error(request, "Access denied.")
         return redirect('home')
         
    # Show orders assigned to this staff member that are completed/cancelled
    my_orders = GuestOrder.objects.filter(
        assigned_staff=request.user,
        status__in=['DELIVERED', 'CANCELLED']
    ).order_by('-created_at')

    # Show all completed/cancelled orders (Global History)
    all_orders = GuestOrder.objects.filter(
        status__in=['DELIVERED', 'CANCELLED']
    ).order_by('-created_at')
    
    return render(request, 'services/staff_order_history.html', {
        'my_orders': my_orders,
        'all_orders': all_orders
    })

@login_required
def update_order_status(request, order_id):
    if not (request.user.is_staff or request.user.role in [User.Role.MANAGER, User.Role.ADMIN, User.Role.KITCHEN]):
         messages.error(request, "Access denied.")
         return redirect('home')

    order = get_object_or_404(GuestOrder, id=order_id)
    if request.method == 'POST':
        # Handle "Assign Me"
        if request.POST.get('assign_me') == 'true':
            order.assigned_staff = request.user
            # Optionally update status to IN_PROGRESS if it was PENDING
            if order.status == 'PENDING':
                order.status = 'IN_PROGRESS'
            order.save()
            messages.success(request, f"Order #{order.id} assigned to you.")
            return redirect('staff_order_list')

        status = request.POST.get('status')
        if status:
            order.status = status
            order.save()
            messages.success(request, f"Order status updated to {status}.")
            
            # Notify Guest
            Notification.objects.create(
                recipient=order.user,
                title="Order Update",
                message=f"Your order #{order.id} is now {order.get_status_display()}.",
                link=reverse('my_orders')
            )

            # If order is completed (Delivered/Cancelled), remove related notifications for staff
            if status in ['DELIVERED', 'CANCELLED']:
                # Find notifications about this order for the current user
                Notification.objects.filter(
                    recipient=request.user,
                    message__contains=f"Order #{order.id}"
                ).delete()
            
    return redirect('staff_order_list')

# --- Housekeeping Views ---

@login_required
def request_housekeeping(request):
    active_booking = Booking.objects.filter(
        user=request.user, 
        status='CHECKED_IN'
    ).first()
    
    # Allow staff to make requests too?
    # Logic from previous read:
    if not active_booking and not request.user.is_staff:
        # Optionally allow if staff
        pass

    service_types = HousekeepingServiceType.objects.filter(is_active=True)

    if request.method == 'POST':
        service_type_id = request.POST.get('service_type')
        note = request.POST.get('note')
        
        room_num = active_booking.room.room_number if active_booking else "Staff Request"

        service_type = get_object_or_404(HousekeepingServiceType, id=service_type_id)

        hk_request = HousekeepingRequest.objects.create(
            user=request.user,
            booking=active_booking,
            room_number=room_num,
            service_type=service_type,
            request_type='OTHER', 
            note=note
        )

        # Notify Staff
        staff_users = User.objects.filter(role__in=[User.Role.MANAGER, User.Role.RECEPTIONIST, User.Role.CLEANER])
        
        # Send Email
        for staff in staff_users:
            if staff.email:
                try:
                    send_tenant_email(
                        subject=f"New Housekeeping Request: {room_num}",
                        message=f"New housekeeping request for Room {room_num}.\n\nService: {service_type.name}\nNote: {note or 'N/A'}\n\nPlease attend to it.",
                        recipient_list=[staff.email],
                        tenant=request.tenant if hasattr(request, 'tenant') else None,
                        fail_silently=True
                    )
                except Exception:
                    pass

        for staff in staff_users:
            Notification.objects.create(
                recipient=staff,
                title="New Housekeeping Request",
                message=f"{service_type.name} requested for Room {room_num}.",
                notification_type=Notification.Type.WARNING,
                link=reverse('staff_housekeeping_list')
            )

        messages.success(request, "Housekeeping request sent successfully.")
        return redirect('my_requests')

    return render(request, 'services/request_housekeeping.html', {'service_types': service_types})

@login_required
def my_requests(request):
    requests = HousekeepingRequest.objects.filter(user=request.user).order_by('-created_at')
    return render(request, 'services/my_requests.html', {'requests': requests})

@login_required
def staff_housekeeping_list(request):
    if not (request.user.is_staff or request.user.role in [User.Role.MANAGER, User.Role.ADMIN, User.Role.RECEPTIONIST, User.Role.CLEANER]):
        messages.error(request, "Access denied.")
        return redirect('home')
    
    requests = HousekeepingRequest.objects.exclude(status__in=['COMPLETED', 'CANCELLED']).order_by('created_at')
    my_tasks = HousekeepingRequest.objects.filter(assigned_staff=request.user).exclude(status__in=['COMPLETED', 'CANCELLED'])

    return render(request, 'services/staff_housekeeping_list.html', {
        'requests': requests,
        'my_tasks': my_tasks,
        'status_choices': HousekeepingRequest.STATUS_CHOICES
    })

@login_required
def update_housekeeping_status(request, pk):
    if not (request.user.is_staff or request.user.role in [User.Role.MANAGER, User.Role.ADMIN, User.Role.RECEPTIONIST, User.Role.CLEANER]):
        messages.error(request, "Access denied.")
        return redirect('home')

    hk_request = get_object_or_404(HousekeepingRequest, pk=pk)

    if request.method == 'POST':
        if 'assign_me' in request.POST:
            hk_request.assigned_staff = request.user
            hk_request.status = 'IN_PROGRESS'
            hk_request.save()
            messages.success(request, "Task assigned to you.")
        
        status = request.POST.get('status')
        if status:
            hk_request.status = status
            hk_request.save()
            
            # Notify Guest
            Notification.objects.create(
                recipient=hk_request.user,
                title="Housekeeping Request Updated",
                message=f"Your request for {hk_request.service_type.name if hk_request.service_type else hk_request.get_request_type_display()} is now {hk_request.get_status_display()}.",
                notification_type=Notification.Type.INFO,
                link=reverse('my_requests')
            )
            
            # If request is completed (Completed/Cancelled), remove related notifications for staff
            if status in ['COMPLETED', 'CANCELLED']:
                # Find notifications about this request for the current user
                # Message pattern from creation: "{service_type.name} requested for Room {room_num}."
                # We can match by Room number and "requested"
                Notification.objects.filter(
                    recipient=request.user,
                    message__contains=f"Room {hk_request.room_number}"
                ).filter(
                    message__contains="requested"
                ).delete()

            messages.success(request, "Status updated.")

    return redirect('staff_housekeeping_list')

# --- Housekeeping Service Management Views ---

class HousekeepingManagementMixin(UserPassesTestMixin):
    def test_func(self):
        user = self.request.user
        return user.is_authenticated and (user.is_superuser or user.role in [User.Role.ADMIN, User.Role.MANAGER])

class HousekeepingServiceTypeListView(LoginRequiredMixin, HousekeepingManagementMixin, ListView):
    model = HousekeepingServiceType
    template_name = 'services/housekeeping_service_type_list.html'
    context_object_name = 'service_types'
    ordering = ['name']

class HousekeepingServiceTypeCreateView(LoginRequiredMixin, HousekeepingManagementMixin, CreateView):
    model = HousekeepingServiceType
    fields = ['name', 'description', 'icon', 'is_active']
    template_name = 'services/housekeeping_service_type_form.html'
    success_url = reverse_lazy('housekeeping_service_type_list')

    def form_valid(self, form):
        messages.success(self.request, "Service type created successfully.")
        return super().form_valid(form)

class HousekeepingServiceTypeUpdateView(LoginRequiredMixin, HousekeepingManagementMixin, UpdateView):
    model = HousekeepingServiceType
    fields = ['name', 'description', 'icon', 'is_active']
    template_name = 'services/housekeeping_service_type_form.html'
    success_url = reverse_lazy('housekeeping_service_type_list')

    def form_valid(self, form):
        messages.success(self.request, "Service type updated successfully.")
        return super().form_valid(form)

class HousekeepingServiceTypeDeleteView(LoginRequiredMixin, HousekeepingManagementMixin, DeleteView):
    model = HousekeepingServiceType
    template_name = 'services/housekeeping_service_type_confirm_delete.html'
    success_url = reverse_lazy('housekeeping_service_type_list')

    def delete(self, request, *args, **kwargs):
        messages.success(self.request, "Service type deleted successfully.")
        return super().delete(request, *args, **kwargs)

class HousekeepingSettingsView(LoginRequiredMixin, HousekeepingManagementMixin, UpdateView):
    model = TenantSetting
    form_class = HousekeepingSettingsForm
    template_name = 'services/housekeeping_settings.html'
    success_url = reverse_lazy('housekeeping_settings')

    def get_object(self, queryset=None):
        tenant = self.request.tenant
        if not tenant:
             # Should probably handle this better, but for now:
             return None
        obj, created = TenantSetting.objects.get_or_create(tenant=tenant)
        return obj

    def form_valid(self, form):
        messages.success(self.request, "Housekeeping information updated successfully.")
        return super().form_valid(form)
