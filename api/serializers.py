from rest_framework import serializers
from django.contrib.auth import get_user_model
User = get_user_model()

class UserSerializer(serializers.ModelSerializer):
    name = serializers.CharField(allow_blank=False, required=False)
    description = serializers.CharField(allow_blank=True, required=False)
    github = serializers.CharField(allow_blank=True, required=False)
    profile_picture = serializers.CharField(allow_blank=True, required=False)

    class Meta:
        model = User
        fields = ["id","username","name","description","github","profile_picture","url","created"]
        read_only_fields = ["id","username","url","created"]

    def validate(self, attrs):
        """
        With partial=True, a field not present is ignored.
        But if the client *sent* `name` and it's empty/whitespace, raise an error.
        """
        raw_name = self.initial_data.get("name", None)
        if raw_name is not None and raw_name.strip() == "":
            raise serializers.ValidationError({"name": "Name cannot be blank."})
        return attrs

    def validate_github(self, value):
        v = (value or "").strip()
        if v == "":
            return ""  # allow clearing
        
        if not v.startswith("http"):
            v = f"https://github.com/{v}"
        return v

    def update(self, user, validated_data):
        if "name" in validated_data:
            user.name = validated_data["name"].strip()

        if "description" in validated_data:
            user.description = validated_data.get("description", "").strip()

        if "profile_picture" in validated_data:
            user.profile_picture = validated_data.get("profile_picture", "").strip()

        if "github" in validated_data:
            user.github = validated_data["github"]

        user.save()
        return user
