from django.contrib import admin
from .models import Entry, User, Follow, Comment, EntryLike
from django.contrib.admin.sites import NotRegistered, AlreadyRegistered


# Register your models here.
admin.site.register(Entry)
admin.site.register(User)

try:
    admin.site.unregister(Follow)
except NotRegistered:
    pass

@admin.register(Follow)
class FollowAdmin(admin.ModelAdmin):
    list_display = ("follower", "followee", "status", "created_at")
    list_filter  = ("status",)
    search_fields = ("follower__username", "followee__username")

admin.site.register(Comment)
admin.site.register(EntryLike)