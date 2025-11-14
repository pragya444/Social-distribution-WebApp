from django.shortcuts import render, get_object_or_404, redirect
from django.db.models import F, Q
from .models import User, Entry, Comment, EntryLike, CommentLike, Follow
from django.contrib.auth import get_user_model
from django.http import JsonResponse, HttpResponseNotAllowed, HttpResponseForbidden, HttpResponse, Http404
from django.views.decorators.http import require_POST, require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, AllowAny, IsAuthenticatedOrReadOnly
from rest_framework.authentication import SessionAuthentication
from rest_framework.renderers import TemplateHTMLRenderer, JSONRenderer
from rest_framework.response import Response
from .serializers import AuthorSerializer, EntrySerializer, AuthorsSerializer, FollowRequestSerializer, FollowersSerializer, LikeSerializer, CommentSerializer
from .utils import helpers
from django.db import IntegrityError, transaction
from django.core.paginator import Paginator
from rest_framework.parsers import JSONParser, FormParser, MultiPartParser
import base64
from urllib.parse import urlparse, unquote
from .entries import entryView


User = get_user_model()

try:
    import markdown as md 
    HAS_MD = True 
except Exception:
    HAS_MD = False


try:
    from PIL import Image, UnidentifiedImageError
    PIL_AVAILABLE = True
except Exception:
    # If Pillow isn't installed, attempts to handle images should be skipped
    PIL_AVAILABLE = False
    Image = None
    UnidentifiedImageError = Exception  # Fallback to a generic exception type





class ProfileView(APIView):
    renderer_classes = [TemplateHTMLRenderer, JSONRenderer]
    
    def get(self, request, author_id):
        if isinstance(request.accepted_renderer, TemplateHTMLRenderer):
            if not request.user.is_authenticated:
                return redirect('login')
        else:
            if not request.user.is_authenticated:
                return Response({"Message": "Forbidden"}, status=403)


        if (request.user.id != author_id):
            user = get_object_or_404(User, id=author_id)
            entries = Entry.objects.filter(author_id=author_id, visibility='PUBLIC', is_deleted=False).order_by('-updated')
        else:
            user = request.user
            entries = Entry.objects.filter(author_id=author_id, is_deleted=False).order_by('-updated')

# ======================================================================
# Developed with assistance from ChatGPT (GPT-5), October 2025
# ======================================================================


        # -------- counts + relationship status -------------------------
        # counts
        posts_count = Entry.objects.filter(author=user, is_deleted=False).count()
        from .models import Follow  # (safe if already imported above)
        followers_count = Follow.objects.filter(followee=user, status=Follow.Status.APPROVED).count()
        following_count = Follow.objects.filter(follower=user, status=Follow.Status.APPROVED).count()
        friends_count = len(helpers.friends_of(user))
        # relationship (viewer -> viewed)
        rel_status = "self"  # self / none / pending / approved / rejected
        can_approve = False  # whether viewed user has requested to follow me
        if request.user.is_authenticated and request.user.id != user.id:
            rel = Follow.objects.filter(follower=request.user, followee=user).first()
            rel_status = (rel.status if rel else "none")
            # incoming pending (user -> me): lets me show approve/deny if you want it here
            can_approve = Follow.objects.filter(
                follower=user, followee=request.user, status=Follow.Status.PENDING
            ).exists()
        # --------------------------------------------------------------------

        # Pre-render HTML for template
        if isinstance(request.accepted_renderer, TemplateHTMLRenderer):
            for e in entries:
                e.rendered = helpers.render_entry(e)

            return Response(
                {
                    "user": user,
                    "entries": entries,
                  
                    "posts_count": posts_count,
                    "followers_count": followers_count,
                    "following_count": following_count,
                    "friends_count": friends_count,
                    "rel_status": rel_status,
                    "can_approve": can_approve,
                },
                template_name="author/profile.html",
            )

        #  JSON shape if you keep the API path
        serializer = AuthorSerializer(user, context={"request": request})

        entries_data = EntrySerializer(entries, many=True, context={"request": request}).data
        return Response(
            {
                **serializer.data,
                "entries": entries_data,
                "posts_count": posts_count,
                "followers_count": followers_count,
                "following_count": following_count,
                "friends_count": friends_count,
                "rel_status": rel_status,
                "can_approve": can_approve,
            },
            status=200,
        )
    
    def post(self, request, author_id):
        return self.put(request, author_id)
    
    def put(self, request, author_id):
        if request.user.id != author_id:
            if isinstance(request.accepted_renderer, TemplateHTMLRenderer):
                return redirect('home')
            return Response({"errors": "Only the author can edit their profile"}, status=403)

        serializer = AuthorSerializer(request.user, data=request.data, partial=True, context={"request": request})
        if not serializer.is_valid():
            if isinstance(request.accepted_renderer, TemplateHTMLRenderer):
                return Response({"errors": serializer.errors, "user": request.user}, template_name="author/profileEdit.html", status=400)
            return Response({"errors": serializer.errors}, status=400)

        user = serializer.save()
        if isinstance(request.accepted_renderer, TemplateHTMLRenderer):
            return redirect('profile', author_id=user.id)
        return Response({ **serializer.data }, status=200)


class ProfileEditView(APIView):
    permission_classes = [IsAuthenticated]
    renderer_classes = [TemplateHTMLRenderer, JSONRenderer]

    def get(self, request, author_id):
        if getattr(request, "user", None) and request.user.is_authenticated and request.user.id == author_id:
            return Response({"user": request.user }, template_name="author/profileEdit.html")
        else:
            return redirect('home')



class AuthorListView(APIView):
    renderer_classes = [TemplateHTMLRenderer, JSONRenderer]
    permission_classes = [AllowAny]

    def get(self, request):
        page = int(request.GET.get('page', 1))
        size = int(request.GET.get('size', 10))
        authors = User.objects.all()
        paginator = Paginator(authors, size)
        current_page = paginator.get_page(page)

        if request.accepted_renderer.format == 'html':
            return Response({
                'title': "All Authors",
                'users': current_page
            }, template_name='author/user_list.html')

        serializer = AuthorsSerializer({
            'type': 'authors',
            'page_number': page,
            'size': size,
            'count': paginator.count,
            'authors': current_page
        }, context={'request': request})
        return Response(serializer.data)

class AuthorStreamView(APIView):
    renderer_classes = [TemplateHTMLRenderer, JSONRenderer]
    permission_classes = [IsAuthenticated]

    def get(self, request, author_id):
        tab = request.GET.get('tab', 'all')
        me = request.user
        if str(me.id) != str(author_id):
            author_id = me.id

        if tab == 'following':
            followed_users = helpers.users_i_follow(me)
            friends = helpers.friends_of(me)
            following_nonfriends = followed_users.exclude(pk__in=friends.values("pk"))
            entries = (
                Entry.objects.filter(is_deleted=False)
                .exclude(author=me)
                .filter(
                    Q(author__in=friends, visibility__in=["FRIENDS", "PUBLIC", "UNLISTED"]) |
                    Q(author__in=following_nonfriends, visibility__in=["PUBLIC", "UNLISTED"])
                )
                .order_by("-updated")
            )
        elif tab == 'private':
            entries = Entry.objects.filter(author=request.user, is_deleted=False).order_by('-updated')
        elif tab == 'friends':
            friends = helpers.friends_of(me)
            entries = (
                Entry.objects
                .filter(author__in=friends, visibility__in=['FRIENDS', 'PUBLIC', 'UNLISTED'], is_deleted=False)
                .exclude(author=me)
                .order_by('-updated')
            )
        else:  # all tab
            followed_users = helpers.users_i_follow(me)
            friend_users = helpers.friends_of(me)
            public_entries = Entry.objects.filter(visibility='PUBLIC', is_deleted=False)
            my_entries = Entry.objects.filter(author=me, is_deleted=False)
            unlisted_from_followed = Entry.objects.filter(author__in=followed_users, visibility='UNLISTED', is_deleted=False)
            friends_only_from_friends = Entry.objects.filter(author__in=friend_users, visibility='FRIENDS', is_deleted=False)
            entries = (public_entries | my_entries | unlisted_from_followed | friends_only_from_friends).order_by('-updated')

        liked_ids = set()
        if request.user.is_authenticated and entries:
            liked_ids = set(EntryLike.objects.filter(user=request.user, entry__in=entries).values_list('entry_id', flat=True))

        for e in entries:
            e.user_liked = e.id in liked_ids
            e.rendered = helpers.render_entry(e)

        if request.accepted_renderer.format == 'html':
            return Response({
                'author': request.user,
                'entries': entries,
                'tab': tab,
            }, template_name='author_all_entries.html')

        serializer = EntrySerializer(entries, many=True, context={"request": request})
        return Response(serializer.data)


class EntryCreateView(APIView):
    permission_classes = [IsAuthenticated]
    renderer_classes = [TemplateHTMLRenderer, JSONRenderer]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    authentication_classes = [SessionAuthentication]  # Enforces CSRF for HTML forms

    def get(self, request, author_id):
        if str(request.user.id) != str(author_id):
            if request.accepted_renderer.format == 'html':
                return HttpResponseForbidden("only the author can create entries here.")
            return Response({"error": "Not authorized"}, status=403)

        if request.accepted_renderer.format == 'html':
            return Response({'author_id': author_id}, template_name='entry/entry_create.html')
        return Response({"type": "entry", "author_id": author_id})

    def post(self, request, author_id):
        if str(request.user.id) != str(author_id):
            return Response({"error": "Not authorized"}, status=403)

        serializer = EntrySerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            entry = serializer.save(author=request.user)
            if request.accepted_renderer.format == 'html':
                return redirect('author-all-entries', author_id=author_id)
            return Response(serializer.data, status=201)

        if request.accepted_renderer.format == 'html':
            return Response({
                'author_id': author_id,
                'errors': serializer.errors
            }, template_name='entry/entry_create.html')
        return Response(serializer.errors, status=400)


class EntryEditView(APIView):
    permission_classes = [IsAuthenticated]
    renderer_classes = [TemplateHTMLRenderer, JSONRenderer]
    authentication_classes = [SessionAuthentication]

    def get(self, request, author_id, entry_id):
        if str(request.user.id) != str(author_id):
            if request.accepted_renderer.format == 'html':
                return HttpResponseForbidden("only the author can edit this entry.")
            return Response({"error": "Not authorized"}, status=403)

        entry = get_object_or_404(Entry, id=entry_id, author_id=author_id, is_deleted=False)
        if request.accepted_renderer.format == 'html':
            return Response({
                'author_id': author_id,
                'entry': entry,
                'contentType': getattr(entry, 'content_type', '') or 'text/markdown',
            }, template_name='entry/entry_edit.html')
        serializer = EntrySerializer(entry)
        return Response(serializer.data)



class EntryImageView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, author_id, entry_id):
        # Fetch the entry by author and id, ensure it is not deleted
        entry = get_object_or_404(
            Entry,
            id=entry_id,
            author_id=author_id,
            is_deleted=False,
        )
        return entryView._serve_entry_image(request, entry)


class EntryImageFQIDView(APIView):
    """
    GET /api/entries/{ENTRY_FQID}/image

    ENTRY_FQID is the full URL of the entry (usually percent-encoded).
    Steps:
      1. Decode the FQID.
      2. Parse its path to extract authors/{author_id}/entries/{entry_id}.
      3. Fetch the local Entry and serve it as an image.
    """
    permission_classes = [AllowAny]

    def get(self, request, entry_fqid):
        # 1) Decode percent-encoding (e.g. http%3A%2F%2F... -> http://...)
        decoded = unquote(entry_fqid)

        # 2) Parse URL and get the path, e.g. "/api/authors/222/entries/249"
        parsed = urlparse(decoded)
        path = parsed.path

        parts = path.strip("/").split("/")  # e.g. ["api", "authors", "222", "entries", "249"]

        try:
            # Find "authors" and "entries" segments and read the IDs after them
            idx_auth = parts.index("authors")
            author_id = parts[idx_auth + 1]

            idx_entry = parts.index("entries")
            entry_id = parts[idx_entry + 1]
        except (ValueError, IndexError):
            # Path does not look like .../authors/{id}/entries/{id}
            raise Http404("invalid entry FQID format")

        # 3) Fetch the entry and reuse the same image-serving helper
        entry = get_object_or_404(
            Entry,
            id=entry_id,
            author_id=author_id,
            is_deleted=False,
        )
        return _serve_entry_image(request, entry)





class FollowRequestActionView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [SessionAuthentication]

    def post(self, request, author_id):
        if str(request.user.id) != str(author_id):
            return HttpResponseForbidden("Not your account")

        target_id = request.POST.get("target_id")
        target = get_object_or_404(User, id=target_id)
        if target == request.user:
            return JsonResponse({"error": "cannot follow yourself"}, status=400)

        fr, created = Follow.objects.get_or_create(
            follower=request.user, followee=target,
            defaults={"status": Follow.Status.PENDING}
        )
        if not created and fr.status == Follow.Status.REJECTED:
            fr.status = Follow.Status.PENDING
            fr.save(update_fields=["status"])

        return redirect("profile", author_id=target.id)


class UnfollowView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [SessionAuthentication]

    def post(self, request, author_id):
        if str(request.user.id) != str(author_id):
            return HttpResponseForbidden("Not your account")

        target_id = request.POST.get("target_id")
        target = get_object_or_404(User, id=target_id)
        Follow.objects.filter(follower=request.user, followee=target).delete()
        return redirect("profile", author_id=target.id)


class FollowRequestsPageView(APIView):
    permission_classes = [IsAuthenticated]
    renderer_classes = [TemplateHTMLRenderer]

    def get(self, request, author_id):
        if str(request.user.id) != str(author_id):
            return HttpResponseForbidden("Not your account")

        pendings = Follow.objects.filter(followee=request.user, status=Follow.Status.PENDING) \
            .select_related("follower").order_by("-created_at")
        return Response({"requests": pendings}, template_name="follow_requests.html")


class ApproveFollowRequestView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [SessionAuthentication]

    def post(self, request, author_id, follower_id):
        if str(request.user.id) != str(author_id):
            return HttpResponseForbidden("Not your account")

        fr = get_object_or_404(Follow, follower_id=follower_id, followee=request.user)
        fr.status = Follow.Status.APPROVED
        fr.save(update_fields=["status"])
        return redirect("follow-requests-page", author_id=author_id)


class DenyFollowRequestView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [SessionAuthentication]

    def post(self, request, author_id, follower_id):
        if str(request.user.id) != str(author_id):
            return HttpResponseForbidden("Not your account")

        Follow.objects.filter(follower_id=follower_id, followee=request.user).delete()
        return redirect("follow-requests-page", author_id=author_id)


class CommentDetailView(APIView):
    permission_classes = [IsAuthenticatedOrReadOnly]

    def get(self, request, author_id, entry_id, comment_id):
        comment = get_object_or_404(Comment, id=comment_id, entry__id=entry_id, entry__author_id=author_id)
        return Response(helpers.comment_to_json(comment))

    def put(self, request, author_id, entry_id, comment_id):
        comment = get_object_or_404(Comment, id=comment_id, author=request.user)
        data = helpers.json_from_request(request)
        text = (data.get("comment") or "").strip()
        if not text:
            return Response({"error": "comment text is required"}, status=400)
        comment.comment = text
        comment.save(update_fields=["comment"])
        return Response(helpers.comment_to_json(comment))

    def delete(self, request, author_id, entry_id, comment_id):
        comment = get_object_or_404(Comment, id=comment_id, author=request.user)
        comment.delete()
        return Response({"ok": True}, status=204)

class CommentListCreateView(APIView):
    renderer_classes = [JSONRenderer]  
    permission_classes = [AllowAny]
    authentication_classes = [SessionAuthentication]
    parser_classes = [JSONParser, FormParser, MultiPartParser]

    def get(self, request, author_id=None, entry_id=None):
        # Support two patterns:
        # 1. /authors/<author_id>/entries/<entry_id>/comments
        # 2. /entries/<path:entry_id>/comments/ - FQID like http://node.com/authors/xyz/entries/123
        # Resolve entry (local or FQID)
        if author_id and entry_id:
            entry = get_object_or_404(Entry, id=entry_id, author_id=author_id, is_deleted=False)
        else:
            fqid = entry_id or request.path.split('/comments')[0]
            try:
                parts = fqid.strip('/').split('/')
                entry_id_local = parts[-1]
                author_id_local = parts[-3]
                entry = get_object_or_404(Entry, id=entry_id_local, author_id=author_id_local, is_deleted=False)
            except Exception:
                return Response({"error": "Invalid entry ID format"}, status=400)

        if not helpers.can_view_entry(request.user, entry):
            return Response({"error": "You do not have permission to view comments on this entry"}, status=403)

        # Paging
        try:
            page = int(request.GET.get("page", 1))
            size = int(request.GET.get("size", 10))
        except ValueError:
            page, size = 1, 10
        start = (page - 1) * size
        end = start + size

        qs = entry.comments.all().order_by("-created")
        items = [helpers.comment_to_json(c) for c in qs[start:end]]  

        base_url = request.build_absolute_uri('/api/')
        return Response({
            "type": "comments",
            "id": f"{base_url}authors/{entry.author.id}/entries/{entry.id}/comments",
            "page_number": page,
            "size": size,
            "count": entry.comment_count,
            "src": items
        })

    def post(self, request, author_id=None, entry_id=None):
        if not request.user.is_authenticated:
            return Response({"error": "Authentication required"}, status=401)

        # Resolve entry (same as GET)
        if author_id and entry_id:
            entry = get_object_or_404(Entry, id=entry_id, author_id=author_id, is_deleted=False)
        else:
            fqid = entry_id or request.data.get("id", "") or request.POST.get("id", "")
            try:
                parts = fqid.strip('/').split('/')
                entry_id_local = parts[-1]
                author_id_local = parts[-3]
                entry = get_object_or_404(Entry, id=entry_id_local, author_id=author_id_local, is_deleted=False)
            except Exception:
                return Response({"error": "Invalid entry ID"}, status=400)

        if not helpers.can_view_entry(request.user, entry):
            return Response({"error": "Cannot comment on this entry"}, status=403)

        text = (request.data.get("comment") or request.POST.get("comment", "")).strip()
        if not text:
            return Response({"error": "Comment cannot be empty"}, status=400)

        ctype = request.data.get("contentType", "text/plain") or request.POST.get("contentType", "text/plain")

        comment = Comment.objects.create(
            entry=entry,
            author=request.user,
            comment=text,
            content_type=ctype
        )

        Entry.objects.filter(id=entry.id).update(comment_count=F('comment_count') + 1)
        entry.refresh_from_db()

        return Response(helpers.comment_to_json(comment, request), status=201)

class EntryLikesView(APIView):
    permission_classes = [IsAuthenticatedOrReadOnly]
    authentication_classes = [SessionAuthentication]
    renderer_classes = [JSONRenderer]

    def get(self, request, author_id, entry_id):
        entry = get_object_or_404(Entry, id=entry_id, author_id=author_id, is_deleted=False)
        if not helpers.can_view_entry(request.user, entry):
            return HttpResponseForbidden("no access")

        user_liked = request.user.is_authenticated and EntryLike.objects.filter(entry=entry, user=request.user).exists()
        data = [{
            "type": "author",
            "id": like.user.url,
            "displayName": like.user.username,
            "web": f"/authors/{like.user.id}",
        } for like in EntryLike.objects.select_related("user").filter(entry=entry)]

        return JsonResponse({
            "type": "likes",
            "count": entry.like_count,
            "liked": user_liked,
            "src": data
        }, status=200)

    def post(self, request, author_id, entry_id):
        entry = get_object_or_404(Entry, id=entry_id, author_id=author_id, is_deleted=False)
        if not helpers.can_view_entry(request.user, entry):
            return HttpResponseForbidden("no access")

        like, created = EntryLike.objects.get_or_create(user=request.user, entry=entry)
        if created:
            Entry.objects.filter(id=entry.id).update(like_count=F('like_count') + 1)
        entry.refresh_from_db(fields=['like_count'])
        return JsonResponse({"ok": True, "liked": True, "count": entry.like_count}, status=201)

    def delete(self, request, author_id, entry_id):
        entry = get_object_or_404(Entry, id=entry_id, author_id=author_id, is_deleted=False)
        if not helpers.can_view_entry(request.user, entry):
            return HttpResponseForbidden("no access")

        deleted, _ = EntryLike.objects.filter(user=request.user, entry=entry).delete()
        if deleted:
            entry.like_count = max(entry.like_count - 1, 0)
            entry.save(update_fields=['like_count'])
        entry.refresh_from_db(fields=['like_count'])
        return JsonResponse({"ok": True, "liked": False, "count": entry.like_count}, status=200)


class CommentLikesView(APIView):
    permission_classes = [IsAuthenticatedOrReadOnly]
    authentication_classes = [SessionAuthentication]
    renderer_classes = [JSONRenderer]

    def get(self, request, author_id, entry_id, comment_id):
        entry = get_object_or_404(Entry, id=entry_id, author_id=author_id, is_deleted=False)
        if not helpers.can_view_entry(request.user, entry):
            return HttpResponseForbidden("no access")

        comment = get_object_or_404(Comment, id=comment_id, entry=entry)
        user_liked = request.user.is_authenticated and CommentLike.objects.filter(user=request.user, comment=comment).exists()
        data = [{
            "type": "author",
            "id": like.user.url,
            "displayName": like.user.username,
            "web": f"/authors/{like.user.id}",
        } for like in comment.likes.select_related("user").all()]

        return JsonResponse({
            "type": "likes",
            "count": len(data),
            "liked": user_liked,
            "src": data,
        }, status=200)

    def post(self, request, author_id, entry_id, comment_id):
        entry = get_object_or_404(Entry, id=entry_id, author_id=author_id, is_deleted=False)
        if not helpers.can_view_entry(request.user, entry):
            return HttpResponseForbidden("no access")

        comment = get_object_or_404(Comment, id=comment_id, entry=entry)
        CommentLike.objects.get_or_create(user=request.user, comment=comment)
        count = CommentLike.objects.filter(comment=comment).count()
        return JsonResponse({"ok": True, "liked": True, "count": count}, status=201)

    def delete(self, request, author_id, entry_id, comment_id):
        entry = get_object_or_404(Entry, id=entry_id, author_id=author_id, is_deleted=False)
        if not helpers.can_view_entry(request.user, entry):
            return HttpResponseForbidden("no access")

        comment = get_object_or_404(Comment, id=comment_id, entry=entry)
        CommentLike.objects.filter(user=request.user, comment=comment).delete()
        count = CommentLike.objects.filter(comment=comment).count()
        return JsonResponse({"ok": True, "liked": False, "count": count}, status=200)


class FollowersPageView(APIView):
    permission_classes = [IsAuthenticated]
    renderer_classes = [TemplateHTMLRenderer]

    def get(self, request, author_id):
        owner = get_object_or_404(User, id=author_id)
        qs = helpers.followers_of(owner).order_by("name", "username")
        return Response({
            "title": f"Followers of {owner.username}",
            "owner": owner,
            "users": qs,
        }, template_name="author/user_list.html")


class FollowingPageView(APIView):
    permission_classes = [IsAuthenticated]
    renderer_classes = [TemplateHTMLRenderer]

    def get(self, request, author_id):
        owner = get_object_or_404(User, id=author_id)
        qs = helpers.users_i_follow(owner).order_by("name", "username")
        return Response({
            "title": f"{owner.username} is Following",
            "owner": owner,
            "users": qs,
        }, template_name="author/user_list.html")


class FriendsPageView(APIView):
    permission_classes = [IsAuthenticated]
    renderer_classes = [TemplateHTMLRenderer]

    def get(self, request, author_id):
        owner = get_object_or_404(User, id=author_id)
        qs = helpers.friends_of(owner).order_by("name", "username")
        return Response({
            "title": f"Friends of {owner.username}",
            "owner": owner,
            "users": qs,
        }, template_name="author/user_list.html")


class FollowRequestListView(APIView):
    permission_classes = [IsAuthenticated]
    renderer_classes = [TemplateHTMLRenderer, JSONRenderer]

    def get(self, request, author_id):
        if str(request.user.id) != str(author_id):
            return Response({"error": "Not authorized"}, status=403)

        pendings = Follow.objects.filter(followee=request.user, status=Follow.Status.PENDING) \
            .select_related("follower").order_by("-created_at")

        if request.accepted_renderer.format == 'html':
            return Response({"requests": pendings}, template_name="follow_requests.html")

        serializer = FollowRequestSerializer(pendings, many=True)
        return Response(serializer.data)


class FollowRequestCreateView(APIView):
    permission_classes = [IsAuthenticated]
    renderer_classes = [TemplateHTMLRenderer, JSONRenderer]
    authentication_classes = [SessionAuthentication]

    def post(self, request, author_id):
        if str(request.user.id) != str(author_id):
            return Response({"error": "Not authorized"}, status=403)

        target = get_object_or_404(User, id=request.data.get("target_id"))
        if target == request.user:
            return Response({"error": "Cannot follow yourself"}, status=400)

        follow, created = Follow.objects.get_or_create(
            follower=request.user,
            followee=target,
            defaults={"status": Follow.Status.PENDING}
        )
        if not created and follow.status == Follow.Status.REJECTED:
            follow.status = Follow.Status.PENDING
            follow.save()

        if request.accepted_renderer.format == 'html':
            return redirect('profile', author_id=target.id)

        serializer = FollowRequestSerializer(follow)
        return Response(serializer.data, status=201)


class FollowersListView(APIView):
    permission_classes = [IsAuthenticated]
    renderer_classes = [TemplateHTMLRenderer, JSONRenderer]

    def get(self, request, author_id):
        owner = get_object_or_404(User, id=author_id)
        followers = helpers.followers_of(owner).order_by("name", "username")

        if request.accepted_renderer.format == 'html':
            return Response({
                "title": f"Followers of {owner.username}",
                "owner": owner,
                "users": followers,
            }, template_name="author/user_list.html")

        serializer = FollowersSerializer({"type": "followers", "followers": followers})
        return Response(serializer.data)


class FollowingListView(APIView):
    permission_classes = [IsAuthenticated]
    renderer_classes = [TemplateHTMLRenderer, JSONRenderer]

    def get(self, request, author_id):
        owner = get_object_or_404(User, id=author_id)
        following = helpers.users_i_follow(owner).order_by("name", "username")

        if request.accepted_renderer.format == 'html':
            return Response({
                "title": f"{owner.username} is Following",
                "owner": owner,
                "users": following,
            }, template_name="author/user_list.html")

        serializer = AuthorsSerializer({"type": "authors", "authors": following})
        return Response(serializer.data)


class FriendsListView(APIView):
    permission_classes = [IsAuthenticated]
    renderer_classes = [TemplateHTMLRenderer, JSONRenderer]

    def get(self, request, author_id):
        owner = get_object_or_404(User, id=author_id)
        friends = helpers.friends_of(owner).order_by("name", "username")

        if request.accepted_renderer.format == 'html':
            return Response({
                "title": f"Friends of {owner.username}",
                "owner": owner,
                "users": friends,
            }, template_name="author/user_list.html")

        serializer = AuthorsSerializer({"type": "authors", "authors": friends})
        return Response(serializer.data)


class InboxView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [SessionAuthentication]

    def post(self, request, author_id):
        if str(request.user.id) != str(author_id):
            return Response({"error": "Not authorized"}, status=403)

        data = request.data
        item_type = data.get('type', '').lower()

        if item_type == 'entry':
            serializer = EntrySerializer(data=data)
        elif item_type == 'follow':
            serializer = FollowRequestSerializer(data=data)
        elif item_type == 'like':
            serializer = LikeSerializer(data=data)
        elif item_type == 'comment':
            serializer = CommentSerializer(data=data)
        else:
            return Response({"error": f"Invalid item type: {item_type}"}, status=400)

        if serializer.is_valid():
            obj = serializer.save()
            return Response(serializer.data, status=201)

        return Response(serializer.errors, status=400)