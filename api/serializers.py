from rest_framework import serializers
from django.contrib.auth import get_user_model
User = get_user_model()

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username", "name", "github", "profile_picture", "url", "created"]
        read_only_fields = ['id', 'username', 'url', 'created']
    
    def update(self, user, validated_data):
        name = validated_data.get('name', None)
        github = validated_data.get('github', None)
        profile_picture = validated_data.get('profile_picture', None)

        if name:
            user.name = name.strip()       
        if github:
            github = github.strip()
            if github.startswith("https://"):
                pass
            else:
                github = f"https://github.com/{github}"
            user.github = github
        if profile_picture:
            user.profile_picture = profile_picture.strip()
        
        user.save()
        return user
