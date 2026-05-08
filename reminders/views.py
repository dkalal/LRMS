from django.shortcuts import redirect


def reminders_redirect(request):
    return redirect("latra:status_list", status_name="expiring")
