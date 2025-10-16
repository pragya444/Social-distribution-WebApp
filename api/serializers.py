from .models import User
from rest_framework import serializers

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username", "github", "profile_picture", "url", "is_staff", "is_active", "created", "updated"]
        