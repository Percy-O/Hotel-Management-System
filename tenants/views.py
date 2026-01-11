from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from .forms import TenantForm
from .models import Tenant, Domain, Membership

@login_required
def create_tenant(request):
    if request.method == 'POST':
        form = TenantForm(request.POST)
        if form.is_valid():
            tenant = form.save(commit=False)
            tenant.owner = request.user
            tenant.save()
            
            # Create Domain
            Domain.objects.create(
                tenant=tenant,
                domain=form.cleaned_data['domain'],
                is_primary=True
            )
            
            # Create Membership
            Membership.objects.create(
                user=request.user,
                tenant=tenant,
                role='ADMIN'
            )
            
            # Redirect to new tenant dashboard
            # Assuming port 8000 for localhost development
            protocol = 'https' if request.is_secure() else 'http'
            domain = form.cleaned_data['domain']
            if 'localhost' in domain and ':' not in domain:
                domain += ':8000'
                
            return redirect(f"{protocol}://{domain}/dashboard/")
    else:
        form = TenantForm()
    
    return render(request, 'tenants/create_tenant.html', {'form': form})
