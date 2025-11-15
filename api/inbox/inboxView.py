from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.authentication import SessionAuthentication, BasicAuthentication
from api.serializers import EntrySerializer, FollowRequestSerializer, EntryLikeSerializer, CommentSerializer
from api.models import Entry, EntryLike
from django.contrib.auth import get_user_model
from django.utils.text import slugify
from django.db.models import F



User = get_user_model()

class InboxView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = [SessionAuthentication]

    def post(self, request, author_id):
        if request.user.is_authenticated:
            is_local = True
        else:
            # auth = request.headers.get('Authorization', '')
            # if auth != "SecretToken":
            #     return Response({"error": "Invalid or missing authorization token."}, status=401)
            is_local = False
        

        data = request.data
        item_type = data.get('type', '').lower()

        if item_type == 'entry':
            serializer = EntrySerializer(data=data)
        elif item_type == 'follow':
            serializer = FollowRequestSerializer(data=data)
        elif item_type == 'like':
            return self.handle_like(request, author_id, data, is_local)
        elif item_type == 'comment':
            serializer = CommentSerializer(data=data)
        else:
            return Response({"error": f"Invalid item type: {item_type}"}, status=400)

        if serializer.is_valid():
            obj = serializer.save()
            return Response(serializer.data, status=201)

        return Response(serializer.errors, status=400)
    

    def get_or_create_remote_user(self, user_data):
        def make_remote_username(fqid):
            slug = slugify(fqid)
            return f"remote_{slug}"[:150]  # Limit to 150 chars

        user_fqid = user_data.get('id', '')

        user, created = User.objects.get_or_create(
            fqid=user_fqid,
            defaults={
                'username': make_remote_username(user_fqid),
                'name': user_data.get('displayName', 'Remote User'),
                'host': user_data.get('host', ''),
                'github': user_data.get('github', ''),
                'profile_picture': user_data.get('profilePicture', ''),
            }
        )

        if created:
            user.set_unusable_password()
            user.save()
        
        return user
        
    
    def handle_like(self, request, author, data, is_local):
        entry_fqid = data.get('object', '')

        try:
            entry = Entry.objects.get(url=entry_fqid)
        except Entry.DoesNotExist:
            return Response({"error": "Entry not found"}, status=404)
        
        if is_local:
            user = request.user
        else:
            user_data = data.get('author', {})
            if not user_data.get('id'):
                return Response({"error": "Author data missing in like"}, status=400)

            user = self.get_or_create_remote_user(user_data)

        like_qs = EntryLike.objects.filter(user=user, entry=entry)

        if like_qs.exists():
            like_qs.delete()
            entry.like_count = max(entry.like_count - 1, 0)
            entry.save()
            entry.refresh_from_db(fields=['like_count'])
            return Response({"ok": True, "message": "Like removed", "liked": False, "count": entry.like_count}, status=200)
        like = EntryLike.objects.create(user=user, entry=entry)
        Entry.objects.filter(id=entry.id).update(like_count=F('like_count') + 1)
        entry.refresh_from_db(fields=['like_count'])
        serializer = EntryLikeSerializer(like, context={'request': request})
        return Response({**serializer.data, "liked": True, "count": entry.like_count}, status=201)

