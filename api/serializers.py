from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import Entry
User = get_user_model()
import base64

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


class EntrySerializer(serializers.ModelSerializer):
    author_username = serializers.CharField(source="author.username", read_only=True)
    class Meta:
        model = Entry
        fields = ['id', 'author', 'author_username', 'title', 'content', 'content_type', 'visibility', 'comment_count', 'like_count', 'updated']
        read_only_fields = ['id', 'author', 'author_username', 'comment_count', 'like_count', 'updated']
        extra_kwargs = {
            'title': {'required': True, 'allow_blank': False},
            'content': {'required': True, 'allow_blank': False},
            'content_type': {'required': True},
            'visibility': {'required': True}
        }
    
    def validate(self, attrs):
        # If updating, pull missing values from the existing instance
        instance = getattr(self, 'instance', None)

        content_type = attrs.get('content_type', getattr(instance, 'content_type', None))
        visibility = attrs.get('visibility', getattr(instance, 'visibility', None))
        title = attrs.get('title', getattr(instance, 'title', None))
        content = attrs.get('content', getattr(instance, 'content', ""))

        # On CREATE (no instance), enforce all required fields.
        if instance is None:
            if not all([content_type, visibility, title, content]):
                raise serializers.ValidationError({
                    "error": "Missing required fields.",
                    "format": {
                        "title": "string (required)",
                        "content": "string (required)",
                        "content_type": "text/plain | text/markdown | image/png;base64 | image/jpeg;base64",
                        "visibility": "PUBLIC | FRIENDS | UNLISTED"
                    }
                })

        # Common checks (apply to both create & update once values are resolved)
        if content_type not in ['text/plain', 'text/markdown', 'image/png;base64', 'image/jpeg;base64']:
            raise serializers.ValidationError({"error": "Invalid content type. Must be one of text/plain, text/markdown, image/png;base64, image/jpeg;base64."})

        if visibility not in ["PUBLIC", "FRIENDS", "UNLISTED"]:
            raise serializers.ValidationError({"error": "Invalid visibility. Visibility must be one of PUBLIC, FRIENDS, UNLISTED."})

        # Validate base64 only when image content is relevant to this request
        # i.e., on create, or when content is being changed, or content_type is changing to an image.
        is_image_type = content_type in ['image/png;base64', 'image/jpeg;base64']
        if is_image_type and (instance is None or 'content' in attrs or 'content_type' in attrs):
            try:
                base64.b64decode(content, validate=True)
            except Exception:
                raise serializers.ValidationError({"error": "Invalid content. Image content must be valid base64."})

        return attrs
    
    def create(self, validated_data):
        request = self.context.get('request')
        user = request.user
        try:
            entry = Entry.objects.create(author=user, **validated_data)
        except Exception as e:
            raise serializers.ValidationError({"error": str(e)})

        return entry
    
    def update(self, entry, validated_data):
        entry.title = validated_data.get('title', entry.title)
        entry.content = validated_data.get('content', entry.content)
        entry.content_type = validated_data.get('content_type', entry.content_type)
        entry.visibility = validated_data.get('visibility', entry.visibility)
        entry.save()
        return entry