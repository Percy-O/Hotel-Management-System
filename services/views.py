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
        # Check Module Limit
        if self.request.tenant and self.request.tenant.plan:
             if not self.request.tenant.plan.module_restaurant:
                 return False
                 
        user = self.request.user
        return user.can_manage_menu

class MenuItemListView(LoginRequiredMixin, MenuManagementMixin, ListView):
    model = MenuItem
    template_name = 'services/menu_item_list.html'
    context_object_name = 'menu_items'
    ordering = ['category', 'name']

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.tenant:
            return qs.filter(tenant=self.request.tenant)
        return qs.none()

class MenuItemCreateView(LoginRequiredMixin, MenuManagementMixin, CreateView):
    model = MenuItem
    fields = ['name', 'description', 'price', 'category', 'image', 'is_available']
    template_name = 'services/menu_item_form.html'
    success_url = reverse_lazy('menu_item_list')

    def form_valid(self, form):
        if self.request.tenant:
            form.instance.tenant = self.request.tenant
        else:
            messages.error(self.request, "Operation failed: No valid workspace found.")
            return self.form_invalid(form)
            
        messages.success(self.request, "Menu item created successfully.")
        return super().form_valid(form)

class MenuItemUpdateView(LoginRequiredMixin, MenuManagementMixin, UpdateView):
    model = MenuItem
    fields = ['name', 'description', 'price', 'category', 'image', 'is_available']
    template_name = 'services/menu_item_form.html'
    success_url = reverse_lazy('menu_item_list')

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.tenant:
            return qs.filter(tenant=self.request.tenant)
        return qs.none()

    def form_valid(self, form):
        messages.success(self.request, "Menu item updated successfully.")
        return super().form_valid(form)

class MenuItemDeleteView(LoginRequiredMixin, MenuManagementMixin, DeleteView):
    model = MenuItem
    template_name = 'services/menu_item_confirm_delete.html'
    success_url = reverse_lazy('menu_item_list')

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.tenant:
            return qs.filter(tenant=self.request.tenant)
        return qs.none()

    def delete(self, request, *args, **kwargs):
        messages.success(self.request, "Menu item deleted successfully.")
        return super().delete(request, *args, **kwargs)

@login_required
def menu_list(request):
    active_booking = Booking.objects.filter(
        user=request.user, 
        status='CHECKED_IN'
    ).first()

    # Base QuerySet: available items
    menu_items = MenuItem.objects.filter(is_available=True)
    
    # Filter by Tenant
    if request.tenant:
        menu_items = menu_items.filter(tenant=request.tenant)
    else:
        # If no tenant context (should not happen for logged in guests in SaaS),
        # try to infer from active booking
        if active_booking and active_booking.tenant:
            menu_items = menu_items.filter(tenant=active_booking.tenant)
        else:
            # Fallback: Don't show anything if we can't determine tenant
            # OR show everything if it's a superuser/platform admin (but this view is for guests)
            if not request.user.is_superuser:
                menu_items = MenuItem.objects.none()

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
        # Try to find an active booking, but don't strictly require it for the order itself
        active_booking = Booking.objects.filter(
            user=request.user, 
            status='CHECKED_IN'
        ).first()

        # If no active booking, we might want to check if the user is a guest in the tenant context
        # But for now, we'll allow the order if they are authenticated.
        # We'll use a provided room number or fallback to "Walk-in / Unknown"
        
        # Room number logic:
        # 1. Active booking room
        # 2. Staff provided (if staff order) - not implemented here yet
        # 3. User input (if we added a field, but for now fallback)
        
        room_num = "Unknown"
        if active_booking:
            room_num = active_booking.room.room_number
        elif request.user.is_staff:
            room_num = "Staff Order"
        else:
            # If no booking and not staff, maybe we shouldn't block?
            # User said "The room services orders is totally different from the room booking"
            # But they probably still need a room number for delivery if it's room service.
            # Assuming for now we allow it but mark as "No Room / Pickup" if no booking found.
            # Or better, we trust the user is a guest.
            room_num = "N/A" 

        # Note: Ideally we should ask the user for their room number if we can't find it automatically.
        # But to solve the "blocking" issue, we proceed.

        try:
            with transaction.atomic():
                # Create Order
                order = GuestOrder.objects.create(
                    user=request.user,
                    booking=active_booking, # Can be null
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
                        # Ensure item belongs to the current tenant if context is available
                        if request.tenant:
                            menu_item = get_object_or_404(MenuItem, id=item_id, tenant=request.tenant)
                        else:
                            menu_item = get_object_or_404(MenuItem, id=item_id)
                            
                        OrderItem.objects.create(
                            order=order,
                            menu_item=menu_item,
                            quantity=int(value)
                        )
                        has_items = True
                
                if not has_items:
                     raise ValueError("No items selected")

                order.calculate_total()
                
                # Create Invoice
                # Invoice usually requires a booking for billing aggregation, but we can make it standalone if model allows.
                # Billing model `Invoice` has `booking` as nullable.
                invoice = Invoice.objects.create(
                    booking=active_booking, # Can be null
                    tenant=request.tenant, # Ensure invoice is scoped to tenant
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
    # Staff/Kitchen/Bar/Admin/Manager
    if not (request.user.is_staff or request.user.role in [User.Role.MANAGER, User.Role.ADMIN, User.Role.KITCHEN, User.Role.BAR]):
         messages.error(request, "Access denied.")
         return redirect('home')

    orders = GuestOrder.objects.exclude(status__in=['DELIVERED', 'CANCELLED', 'AWAITING_PAYMENT'])
    
    # Filter by Tenant
    if request.tenant:
        orders = orders.filter(booking__tenant=request.tenant)

    # Filter by Role
    if request.user.role == User.Role.KITCHEN:
        orders = orders.filter(items__menu_item__category='FOOD').distinct()
    elif request.user.role == User.Role.BAR:
        orders = orders.filter(items__menu_item__category='DRINK').distinct()
        
    orders = orders.order_by('created_at')
    return render(request, 'services/staff_order_list.html', {'orders': orders})

@login_required
def staff_order_history(request):
    if not (request.user.is_staff or request.user.role in [User.Role.MANAGER, User.Role.ADMIN, User.Role.KITCHEN, User.Role.BAR]):
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
    )
    
    # Filter by Tenant
    if request.tenant:
        my_orders = my_orders.filter(booking__tenant=request.tenant)
        all_orders = all_orders.filter(booking__tenant=request.tenant)

    # Filter by Role for Global History
    if request.user.role == User.Role.KITCHEN:
        all_orders = all_orders.filter(items__menu_item__category='FOOD').distinct()
    elif request.user.role == User.Role.BAR:
        all_orders = all_orders.filter(items__menu_item__category='DRINK').distinct()
        
    all_orders = all_orders.order_by('-created_at')
    
    return render(request, 'services/staff_order_history.html', {
        'my_orders': my_orders,
        'all_orders': all_orders
    })

@login_required
def update_order_status(request, order_id):
    if not (request.user.is_staff or request.user.role in [User.Role.MANAGER, User.Role.ADMIN, User.Role.KITCHEN, User.Role.BAR]):
         messages.error(request, "Access denied.")
         return redirect('home')

    qs = GuestOrder.objects.all()
    if request.tenant:
        qs = qs.filter(booking__tenant=request.tenant)
        
    order = get_object_or_404(qs, id=order_id)
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
    # Check Module Limit
    if request.tenant and request.tenant.plan:
         if not request.tenant.plan.module_housekeeping:
             messages.error(request, "Housekeeping module is not enabled for this workspace.")
             return redirect('guest_dashboard')
             
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
    if request.tenant:
        service_types = service_types.filter(tenant=request.tenant)
    else:
        # If no tenant context, infer from booking or return none/defaults
        if active_booking and active_booking.tenant:
            service_types = service_types.filter(tenant=active_booking.tenant)
        else:
             # Fallback for staff without context or superuser
             if not request.user.is_superuser:
                 service_types = service_types.none()

    if request.method == 'POST':
        service_type_id = request.POST.get('service_type')
        note = request.POST.get('note')
        
        room_num = active_booking.room.room_number if active_booking else "Staff Request"

        service_type = get_object_or_404(service_types, id=service_type_id)

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
        if request.tenant:
             # Filter staff by tenant membership?
             # User model doesn't have tenant field directly, but we can assume role checks or use Membership
             # Or rely on User.tenant field if implemented.
             # Better: Use Membership
             from tenants.models import Membership
             staff_memberships = Membership.objects.filter(tenant=request.tenant, user__role__in=[User.Role.MANAGER, User.Role.RECEPTIONIST, User.Role.CLEANER])
             staff_users = [m.user for m in staff_memberships]
        
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
    
    requests = HousekeepingRequest.objects.exclude(status__in=['COMPLETED', 'CANCELLED'])
    my_tasks = HousekeepingRequest.objects.filter(assigned_staff=request.user).exclude(status__in=['COMPLETED', 'CANCELLED'])

    # Filter by Tenant
    if request.tenant:
        requests = requests.filter(booking__tenant=request.tenant)
        my_tasks = my_tasks.filter(booking__tenant=request.tenant)

    requests = requests.order_by('created_at')

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

    qs = HousekeepingRequest.objects.all()
    if request.tenant:
        qs = qs.filter(booking__tenant=request.tenant)
        
    hk_request = get_object_or_404(qs, pk=pk)

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

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.tenant:
            return qs.filter(tenant=self.request.tenant)
        return qs.none()

class HousekeepingServiceTypeCreateView(LoginRequiredMixin, HousekeepingManagementMixin, CreateView):
    model = HousekeepingServiceType
    fields = ['name', 'description', 'icon', 'is_active']
    template_name = 'services/housekeeping_service_type_form.html'
    success_url = reverse_lazy('housekeeping_service_type_list')

    def form_valid(self, form):
        if self.request.tenant:
            form.instance.tenant = self.request.tenant
        else:
            messages.error(self.request, "Operation failed: No valid workspace found.")
            return self.form_invalid(form)
            
        messages.success(self.request, "Service type created successfully.")
        return super().form_valid(form)

class HousekeepingServiceTypeUpdateView(LoginRequiredMixin, HousekeepingManagementMixin, UpdateView):
    model = HousekeepingServiceType
    fields = ['name', 'description', 'icon', 'is_active']
    template_name = 'services/housekeeping_service_type_form.html'
    success_url = reverse_lazy('housekeeping_service_type_list')

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.tenant:
            return qs.filter(tenant=self.request.tenant)
        return qs.none()

    def form_valid(self, form):
        messages.success(self.request, "Service type updated successfully.")
        return super().form_valid(form)

class HousekeepingServiceTypeDeleteView(LoginRequiredMixin, HousekeepingManagementMixin, DeleteView):
    model = HousekeepingServiceType
    template_name = 'services/housekeeping_service_type_confirm_delete.html'
    success_url = reverse_lazy('housekeeping_service_type_list')

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.tenant:
            return qs.filter(tenant=self.request.tenant)
        return qs.none()

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
