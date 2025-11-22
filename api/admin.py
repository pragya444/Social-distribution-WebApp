from django.contrib import admin
from .models import Entry, User, Follow, Comment, EntryLike, Node, CommentLike
from django.contrib.admin.sites import NotRegistered, AlreadyRegistered


# Register your models here.
admin.site.register(Entry)


try:
    admin.site.unregister(Follow)
except NotRegistered:
    pass

@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ("username", "name", "is_active", "is_staff")
    list_filter = ("is_active", "is_staff")
    actions = ["approve_users"]

    def approve_users(self, request, queryset):
        queryset.update(is_active=True)
    approve_users.short_description = "Approve selected users"

@admin.register(Follow)
class FollowAdmin(admin.ModelAdmin):
    list_display = ("follower", "followee", "status", "created_at")
    list_filter  = ("status",)
    search_fields = ("follower__username", "followee__username")

admin.site.register(Comment)
admin.site.register(EntryLike)
admin.site.register(Node)
admin.site.register(CommentLike)