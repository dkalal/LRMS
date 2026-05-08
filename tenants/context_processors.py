def tenant_context(request):
    tenant = getattr(request.user, "tenant", None) if request.user.is_authenticated else None
    return {"current_tenant": tenant}
