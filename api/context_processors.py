from .models import Follow

def pending_follow_counts(request):
    if request.user.is_authenticated:
        return {
            "pending_follow_count": Follow.objects.filter(
                followee=request.user,
                status=Follow.Status.PENDING,
            ).count()
        }
    return {"pending_follow_count": 0}
