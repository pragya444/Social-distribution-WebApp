from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import Entry, Follow, Comment, EntryLike, CommentLike
from .utils import helpers
from .models import get_url 
User = get_user_model()
import base64

class AuthorSerializer(serializers.ModelSerializer):
    type = serializers.SerializerMethodField()
    id = serializers.CharField(source="url", read_only=True)
    host = serializers.CharField(read_only=True)
    displayName = serializers.CharField(source='name', allow_blank=False, required=False)
    description = serializers.CharField(allow_blank=True, required=False)
    github = serializers.CharField(allow_blank=True, required=False)
    profileImage = serializers.CharField(source='profile_picture', allow_blank=True, required=False)
    web = serializers.SerializerMethodField()
    #followers = serializers.SerializerMethodField()
    #following = serializers.SerializerMethodField()
    #friends = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["type","id","host","displayName","description","github","profileImage","web"]
        read_only_fields = ["type","id","host", "web"] #"created","followers","following","friends"]

    def get_web(self, obj):
        request = self.context.get('request')
        return f"{request.scheme}://{request.get_host()}/api/authors/{obj.id}"
    
    def get_type(self, obj):
        return "author"


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
    '''
    def _serialize_user_list(self, qs):
        """Return a lightweight list representation for a queryset of User objects."""
        return [{"id": u.id, "url": u.url, "username": u.username} for u in qs]

    def get_followers(self, obj):
        try:
            return self._serialize_user_list(helpers.followers_of(obj))
        except Exception:
            return []

    def get_following(self, obj):
        try:
            return self._serialize_user_list(helpers.users_i_follow(obj))
        except Exception:
            return []

    def get_friends(self, obj):
        try:
            return self._serialize_user_list(helpers.friends_of(obj))
        except Exception:
            return []
    '''
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

class AuthorsSerializer(serializers.Serializer):
    """Authors list serializer matching API spec"""
    type = serializers.CharField(default="authors", read_only=True)
    page_number = serializers.IntegerField(min_value=1)
    size = serializers.IntegerField(min_value=1)
    count = serializers.IntegerField(min_value=0)
    authors = AuthorSerializer(many=True)

class PaginatedSerializer(serializers.Serializer):
    """Base pagination serializer"""
    page_number = serializers.IntegerField(min_value=1)
    size = serializers.IntegerField(min_value=1)
    count = serializers.IntegerField(min_value=0)

class EntrySerializer(serializers.ModelSerializer):
    contentType = serializers.CharField(source='content_type', required=False)
    author = AuthorSerializer(read_only=True)
    comments = serializers.SerializerMethodField()
    likes = serializers.SerializerMethodField()

    class Meta:
        model = Entry
        fields = (
            'id', 'author', 'title', 'description',
            'content', 'contentType', 'visibility',
            'published', 'updated',
            'comments', 'likes')
        read_only_fields = ('published', 'updated')

    def get_id(self, obj):
        request = self.context.get('request')
        return f"{request.build_absolute_uri('/api/')}/authors/{obj.author.id}/entries/{obj.id}"

    def get_web(self, obj):
        request = self.context.get('request')
        return get_url().rstrip("/") + "/authors/" + obj.author.id + "/entries/" + obj.id

    def get_comments(self, obj):
        request = self.context.get('request')
        return {
            'type': 'comments',
            'id': f"{request.build_absolute_uri('/api/')}/authors/{obj.author.id}/entries/{obj.id}/comments",
            'web': self.get_web(obj),
            'page_number': 1,
            'size': 5,
            'count': obj.comment_count,
            'src': []
        }

    def get_likes(self, obj):
        request = self.context.get('request')
        return {
            'type': 'likes',
            'id': f"{request.build_absolute_uri('/api/')}/authors/{obj.author.id}/entries/{obj.id}/likes",
            'web': self.get_web(obj) + '/likes',
            'page_number': 1,
            'size': 50,
            'count': obj.like_count,
            'src': []
        }

    def validate(self, attrs):
        instance = getattr(self, 'instance', None)
        content_type = attrs.get('content_type')
        visibility = attrs.get('visibility')
        title = attrs.get('title')
        content = attrs.get('content')
        
        # Only validate required fields on CREATE (instance is None)
        if instance is None:
            # Check what's actually missing
            missing = []
            if not content_type:
                missing.append('contentType')
            if not visibility:
                missing.append('visibility')
            if not title:
                missing.append('title')
            if content is None or content == '':  # Allow empty string for now
                missing.append('content')
            
            if missing:
                raise serializers.ValidationError({
                    "error": f"Missing required fields: {', '.join(missing)}",
                    "format": {
                        "title": "string (required)",
                        "content": "string (required)",
                        "contentType": "text/plain | text/markdown | image/png;base64 | image/jpeg;base64 | application/base64",
                        "visibility": "PUBLIC | FRIENDS | UNLISTED | PRIVATE"
                    }
                })

        # Validate content type if provided
        if content_type:
            allowed = ['text/plain', 'text/markdown', 'image/png;base64', 'image/jpeg;base64', 'application/base64']
            if content_type not in allowed:
                raise serializers.ValidationError({
                    "contentType": f"Invalid content type. Must be one of {', '.join(allowed)}"
                })

        # Validate visibility if provided
        if visibility and visibility not in ["PUBLIC", "FRIENDS", "UNLISTED", "PRIVATE"]:
            raise serializers.ValidationError({
                "visibility": "Invalid visibility. Must be one of PUBLIC, FRIENDS, UNLISTED, PRIVATE."
            })

        # Validate base64 for images (only if content_type is image)
        if content_type and content_type in ['image/png;base64', 'image/jpeg;base64', 'application/base64']:
            if content:  # Only validate if content is provided
                try:
                    import base64
                    base64.b64decode(content, validate=True)
                except Exception:
                    raise serializers.ValidationError({
                        "content": "Invalid content. Image content must be valid base64."
                    })

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
        entry.description = validated_data.get('description', entry.description)
        entry.save()
        return entry

class FollowRequestSerializer(serializers.ModelSerializer):
    """Serializer for follow request objects following API spec format"""
    type = serializers.CharField(default="follow", read_only=True)
    summary = serializers.SerializerMethodField()
    actor = AuthorSerializer(source='follower', read_only=True)
    object = AuthorSerializer(source='followee', read_only=True)
    # ://service/api/authors/{AUTHOR_SERIAL}/follow_requests
    # ://service/api/authors/{AUTHOR_SERIAL}/inbox
    ''' 
    { "type": "follow", 
    "summary":"actor wants to follow object",
    "actor":{
        "type":"author",
        // The rest of the author object for the author who wants to follow
    },
    "object":{
        "type":"author",
        // The rest of the author object for the author they want to follow
    }} 
    '''
    class Meta:
        model = Follow
        fields = ['type', 'summary', 'actor', 'object']

    def get_summary(self, obj):
        return f"{obj.follower.displayName} wants to follow {obj.followee.displayName}"

class CommentSerializer(serializers.ModelSerializer):
    """Comment serializer following API spec"""
    type = serializers.CharField(default="comment", read_only=True)
    author = AuthorSerializer(read_only=True)
    comment = serializers.CharField()
    contentType = serializers.CharField(default="text/markdown")
    published = serializers.DateTimeField(source='created', read_only=True)
    id = serializers.SerializerMethodField()
    entry = serializers.SerializerMethodField()
    web = serializers.SerializerMethodField()
    likes = serializers.SerializerMethodField()
    '''{
    "type":"comment",
    "author":{
        "type":"author",
        "id":"http://nodeaaaa/api/authors/111",
        "web":"http://nodeaaaa/authors/greg",
        "host":"http://nodeaaaa/api/",
        "displayName":"Greg Johnson",
        "github": "http://github.com/gjohnson",
        "profileImage": "https://i.imgur.com/k7XVwpB.jpeg"
    },
    "comment":"Sick Olde English",
    "contentType":"text/markdown",
    // ISO 8601 TIMESTAMP
    "published":"2015-03-09T13:07:04+00:00",
    // ID of the Comment
    "id": "http://nodeaaaa/api/authors/111/commented/130",
    "entry": "http://nodebbbb/api/authors/222/entries/249",
    }'''

    class Meta:
        model = Comment
        fields = ['type', 'author', 'comment', 'contentType', 'published', 'id', 'entry', 'web', 'likes']
    
    def get_likes(self, obj): 
        request = self.context.get('request')
        return {
            'type': 'likes',
            'id': f"{request.scheme}://{request.get_host()}/api/authors/{obj.author.id}/comments/{obj.id}/likes",
            'web': f"{request.scheme}://{request.get_host()}/authors/{obj.author.username}/comments/{obj.id}",
            'page_number': 1,
            'size': 50,
            'count': obj.like_count,
            'src': []  # Populated when needed
        }
    def get_id(self, obj):
        request = self.context.get('request')
        return f"{request.scheme}://{request.get_host()}/api/authors/{obj.author.id}/commented/{obj.id}"

    def get_entry(self, obj):
        request = self.context.get('request')
        return f"{request.scheme}://{request.get_host()}/api/authors/{obj.entry.author.id}/entries/{obj.entry.id}"
    
    def get_web(self, obj):
        request = self.context.get('request')
        return f"{request.scheme}://{request.get_host()}/authors/{obj.entry.author.username}/entries/{obj.entry.id}"

class CommentsSerializer(serializers.Serializer):
    """Comments list serializer matching API spec"""
    type = serializers.CharField(default="comments", read_only=True)
    id = serializers.SerializerMethodField()
    web = serializers.SerializerMethodField() 
    page_number = serializers.IntegerField()
    size = serializers.IntegerField()
    count = serializers.IntegerField()
    src = CommentSerializer(many=True)

    def get_id(self, obj):
        request = self.context.get('request')
        return f"{request.scheme}://{request.get_host()}/api/authors/{obj.author.id}/entries/{obj.id}/comments"

    def get_web(self, obj):
        request = self.context.get('request')
        return f"{request.scheme}://{request.get_host()}/authors/{obj.author.username}/entries/{obj.id}"

class CommentedSerializer(serializers.Serializer):
    """Serializer for list of comments following API spec"""
    type = serializers.CharField(default="comments", read_only=True)
    comments = serializers.ListField(child=serializers.DictField())

class FollowersSerializer(serializers.Serializer):
    """Serializer for list of followers following API spec"""
    type = serializers.CharField(default="followers", read_only=True)
    followers = AuthorSerializer(many=True)

class LikeSerializer(serializers.ModelSerializer):
    """Base serializer for likes following API spec"""
    type = serializers.CharField(default="Like", read_only=True)
    author = AuthorSerializer(read_only=True , source='user')
    published = serializers.DateTimeField(source='created', read_only=True)
    id = serializers.SerializerMethodField()
    object = serializers.SerializerMethodField()
    
    class Meta:
        model = EntryLike   # default
        fields = ['type', 'author', 'published', 'id', 'object']

    @classmethod
    def for_model(cls, amodel):
        class _DynamicLikeSerializer(cls):
            class Meta(cls.Meta):
                model = amodel
        return _DynamicLikeSerializer

    def get_id(self, obj):
        request = self.context.get('request')
        return f"{request.scheme}://{request.get_host()}/api/authors/{obj.user.id}/liked/{obj.id}"
    
    def get_object(self, obj):
        request = self.context.get('request')
        if hasattr(obj, 'entry'):
            return f"{request.scheme}://{request.get_host()}/api/authors/{obj.entry.author.id}/entries/{obj.entry.id}"
        else:
            return f"{request.scheme}://{request.get_host()}/api/authors/{obj.comment.author.id}/commented/{obj.comment.id}"


class LikesSerializer(serializers.Serializer):
    """Likes list serializer matching API spec"""
    type = serializers.CharField(default="likes", read_only=True) 
    id = serializers.SerializerMethodField()
    web = serializers.SerializerMethodField()
    page_number = serializers.IntegerField()
    size = serializers.IntegerField()
    count = serializers.IntegerField()
    src = LikeSerializer(many=True)

    def get_id(self, obj):
        request = self.context.get('request')
        return f"{request.scheme}://{request.get_host()}/api/authors/{obj.author.id}/entries/{obj.id}/likes"

    def get_web(self, obj):
        # For comment likes
        request = self.context.get('request')
        if hasattr(obj, 'comment'):
            return f"{request.scheme}://{request.get_host()}/authors/{obj.comment.author.username}/comments/{obj.comment.id}/likes"
        # For entry likes
        return f"{request.scheme}://{request.get_host()}/authors/{obj.author.username}/entries/{obj.id}/likes"
        
class LikedSerializer(serializers.Serializer):
    """Serializer for list of likes following API spec"""
    type = serializers.CharField(default="liked", read_only=True)
    items = serializers.ListField(child=serializers.DictField())