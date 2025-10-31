from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.conf import settings
from django.utils import timezone

import secrets
import uuid
from django.utils import timezone



def generate_id():
    return secrets.token_urlsafe(16)

def get_url():
    if hasattr(settings, 'DJANGO_ENV'):
        if settings.DJANGO_ENV == 'development':
            return "http://127.0.0.1:8000/"
        elif settings.DJANGO_ENV == 'production':
            return ""   # Have to replace with actual production URL
    return "http://127.0.0.1:8000/"



class UserManager(BaseUserManager):
    def create_user(self, username, password, **kwargs):
        if not username:
            raise ValueError("User must have a username")
        if not password:
            raise ValueError("User must have a password")
        is_active = kwargs.pop('is_active', False) 
        user = self.model(username=username,is_active=is_active, **kwargs)
        user.set_password(password)
        user.save(using=self._db)
        return user
    
    def create_superuser(self, username, password):
        if not username:
            raise ValueError("Superuser must have a username")
        if not password:
            raise ValueError("Superuser must have a password")
        
        user = self.create_user(username=username, password=password, is_active=True, is_staff=True, is_superuser=True)
        user.save(using=self._db)
        return user
    

class User(AbstractBaseUser, PermissionsMixin):
    id = models.CharField(primary_key=True, unique=True, max_length=50, db_index=True, default=generate_id)
    username = models.CharField(max_length=255, unique=True, db_index=True)
    name = models.CharField(max_length=255, default="Anonymous")
    github = models.CharField(max_length=255, default="")
    profile_picture = models.CharField(max_length=255, default="")
    description = models.CharField(max_length=500, default="")
    url = models.CharField(max_length=255, default="", db_index=True, unique=True)
    is_staff = models.BooleanField(default=False)
    is_active = models.BooleanField(default=False)
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
    # following = models.ManyToManyField('self', symmetrical=False, related_name='followers')
    # follwers = models.ManyToManyField('self', symmetrical=False, related_name='following_set')
    
    USERNAME_FIELD = 'username'
    objects = UserManager()

    def __str__(self):
        return self.username
    
    def save(self, *args, **kwargs):
        self.url = get_url() + "authors/" + self.id  # Creates a fixed URL for each user
        return super(User, self).save(*args, **kwargs)
    


'''
This model Entry was written with the assistance of OpenAI, ChatGPT-5. 2025-10-19.
'''

class Entry(models.Model):
    """
    This model represents a blog entry or post created by an author.
    Each entry has a title, content, visibility settings, and timestamps for creation and updates.
    The visibility can be set to 'PUBLIC', 'FRIENDS', 'PRIVATE', or 'UNLISTED'.
    The foreign key relationship to the User model indicates which author created the entry.
    """

    VISIBILITY_CHOICES = [
        ('PUBLIC', 'Public'),
        ('FRIENDS', 'Friends'),
        ('PRIVATE', 'Private'),
        ('UNLISTED', 'Unlisted'),
    ]

    id = models.CharField(primary_key=True, unique=True, max_length=50, db_index=True, default=generate_id)
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name='entries')
    title = models.CharField(max_length=255)

    content = models.TextField(blank=True, default="")  #stores text OR base64 image data
    content_type = models.CharField(max_length=60, blank=True, default="")  # e.g. text/markdown,  image/png;base64

    visibility = models.CharField(max_length=10, choices=VISIBILITY_CHOICES, default='PUBLIC')
    is_deleted = models.BooleanField(default=False)
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
    share_token = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    comment_count = models.IntegerField(default=0)
    like_count = models.IntegerField(default=0)

    
    @property
    def is_image(self) -> bool:
        """NEW: True if entry is an image entry encoded as base64 (e.g., image/png;base64)."""
        ct = (self.content_type or "").lower()
        return ct.startswith("image/") and ct.endswith(";base64")

    @property
    def is_markdown(self) -> bool:
        """NEW: True if entry should be rendered as Markdown."""
        return (self.content_type or "").lower() in {"text/markdown", "text/commonmark", "text/md"}

    def __str__(self):
        return self.title



class Follow(models.Model):
    class Status(models.TextChoices):
        PENDING  = "pending", "pending"
        APPROVED = "approved", "approved"
        REJECTED = "rejected", "rejected"

    follower = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="following", on_delete=models.CASCADE)
    followee = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="followers", on_delete=models.CASCADE)
    status   = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["follower", "followee"], name="uniq_follow"),
            models.CheckConstraint(check=~models.Q(follower=models.F("followee")), name="no_self_follow"),
        ]

    @staticmethod
    def is_follower(x, y) -> bool:
        return Follow.objects.filter(follower=x, followee=y, status="approved").exists()

    @staticmethod
    def are_friends(a, b) -> bool:
        return Follow.is_follower(a, b) and Follow.is_follower(b, a)       


class Comment(models.Model):
    id = models.CharField(primary_key=True, unique=True, max_length=50, db_index=True, default=generate_id)
    entry = models.ForeignKey(Entry, on_delete=models.CASCADE, related_name="comments")
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name="comments")
    comment = models.TextField()
    content_type = models.CharField(max_length=60, default="text/plain")
    created = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created"]

    def api_id(self) -> str:
        base = get_url().rstrip("/")
        # http://host/api/authors/<author>/entries/<entry>/comments/<comment>
        return f"{base}/api/authors/{self.entry.author_id}/entries/{self.entry.id}/comments/{self.id}"
    

class EntryLike(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="entry_likes")
    entry = models.ForeignKey(Entry, on_delete=models.CASCADE, related_name="likes")
    created = models.DateTimeField(default=timezone.now)

    class Meta:
        unique_together = ("user", "entry")

class CommentLike(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="comment_likes")
    comment = models.ForeignKey(Comment, on_delete=models.CASCADE, related_name="likes")
    created = models.DateTimeField(default=timezone.now)

    class Meta:
        unique_together = ("user", "comment")