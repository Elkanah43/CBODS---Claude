def unread_count(request):
    if request.user.is_authenticated:
        return {"unread_notifications": request.user.notifications.filter(is_read=False).count()}
    return {"unread_notifications": 0}
