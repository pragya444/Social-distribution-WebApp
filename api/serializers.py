from rest_framework import serializers
from django.contrib.auth import get_user_model
User = get_user_model()

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username", "github", "profile_picture", "url", "created"]
        read_only_fields = ['id', 'username', 'url', 'created']