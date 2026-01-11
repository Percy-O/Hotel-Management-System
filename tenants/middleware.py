from django.utils.deprecation import MiddlewareMixin
from django.http import Http404
from .models import Tenant, Domain
from .utils import set_current_tenant

class TenantMiddleware(MiddlewareMixin):
    def process_request(self, request):
        host = request.get_host().split(':')[0]
        
        # Check for custom domain
        try:
            domain_obj = Domain.objects.select_related('tenant').get(domain=host)
            request.tenant = domain_obj.tenant
            set_current_tenant(request.tenant)
            return
        except Domain.DoesNotExist:
            pass

        # Check for subdomain
        # Assumes format: tenant.domain.com
        # For localhost (e.g., tenant.localhost), parts[0] is tenant
        parts = host.split('.')
        
        # Logic to distinguish between www.saas.com and tenant.saas.com
        # For development on localhost, we might treat "localhost" as the main domain
        # If parts[0] is not 'localhost' and not '127.0.0.1' and not 'www'
        
        if len(parts) > 1 or (len(parts) == 1 and parts[0] != 'localhost'):
            subdomain = parts[0]
            if subdomain not in ['www', 'localhost', '127']: 
                try:
                    tenant = Tenant.objects.get(subdomain=subdomain)
                    request.tenant = tenant
                    set_current_tenant(tenant)
                    return
                except Tenant.DoesNotExist:
                    pass
        
        # Fallback: Check if user is logged in and has a last_active_tenant or similar
        # For now, public site
        request.tenant = None
        set_current_tenant(None)
