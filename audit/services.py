from .models import AuditLog


def log_audit_event(user, action, instance=None, message="", reason=""):
    if user is None or not getattr(user, "tenant", None):
        return None
    return AuditLog.objects.create(
        tenant=user.tenant,
        actor=user,
        action=action,
        message=message or action,
        reason=reason,
        content_type=instance.__class__.__name__ if instance else "",
        object_id=getattr(instance, "pk", None),
    )
