from django.shortcuts import get_object_or_404, redirect
from django.db.models import F, Q
from .models import User, Entry, Comment, EntryLike, CommentLike, Follow, Liked
from django.contrib.auth import get_user_model
from django.http import JsonResponse, HttpResponseForbidden
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, AllowAny, IsAuthenticatedOrReadOnly
from rest_framework.authentication import SessionAuthentication
from rest_framework.renderers import TemplateHTMLRenderer, JSONRenderer
from rest_framework.response import Response
from .serializers import EntrySerializer, AuthorsSerializer, FollowRequestSerializer, FollowersSerializer, FollowingSerializer, LikeSerializer,LikesSerializer, CommentSerializer
from django.http import JsonResponse, HttpResponseNotAllowed, HttpResponseForbidden, HttpResponse, Http404

from .utils import helpers
from django.core.paginator import Paginator
from rest_framework.parsers import JSONParser, FormParser, MultiPartParser
from urllib.parse import urlparse, unquote
from .entries import entryView
import urllib.parse



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


# --- FQID helpers ---
from urllib.parse import urlparse, unquote
from django.http import Http404

def _normalize_local_id(s):
    """Return the last path segment (decoded), e.g. .../commented/ABC -> ABC."""
    return unquote(str(s or "")).strip().rstrip("/").split("/")[-1]

def _resolve_local_entry_from_fqid(entry_fqid):
    """
    Accepts a local FQID like:
      http://<host>/api/authors/<AUTHOR_ID>/entries/<ENTRY_ID>
    Returns the Entry or raises Http404.
    """
    u = urlparse(unquote(str(entry_fqid)))
    parts = u.path.strip("/").split("/")
    try:
        api_i = parts.index("api")
        authors_i = parts.index("authors", api_i + 1)
        entries_i = parts.index("entries", authors_i + 1)
        author_id = parts[authors_i + 1]
        entry_id = parts[entries_i + 1]
    except (ValueError, IndexError):
        raise Http404("Invalid entry FQID")
    from .models import Entry  # local import to avoid cycles
    return get_object_or_404(Entry, id=entry_id, author_id=author_id, is_deleted=False)

def _resolve_local_comment_from_fqid(comment_fqid):
    """
    Accepts a local comment FQID like:
      http://<host>/api/authors/<AUTHOR_ID>/commented/<COMMENT_ID>
    Returns the Comment or raises Http404.
    """
    u = urlparse(unquote(str(comment_fqid)))
    parts = u.path.strip("/").split("/")
    try:
        api_i = parts.index("api")
        authors_i = parts.index("authors", api_i + 1)
        # allow both 'commented/<id>' and 'comments/<id>'
        if "commented" in parts[authors_i + 2:]:
            commented_i = parts.index("commented", authors_i + 2)
            author_id = parts[authors_i + 1]
            comment_id = parts[commented_i + 1]
        elif "comments" in parts[authors_i + 2:]:
            comments_i = parts.index("comments", authors_i + 2)
            author_id = parts[authors_i + 1]
            comment_id = parts[comments_i + 1]
        else:
            raise ValueError
    except (ValueError, IndexError):
        # fallback: last segment
        comment_id = _normalize_local_id(comment_fqid)
        author_id = None  # unknown here
    from .models import Comment  # local import to avoid cycles
    if author_id:
        return get_object_or_404(Comment, id=comment_id, author_id=author_id)
    return get_object_or_404(Comment, id=comment_id)



# class EntryCommentsByFQIDView(APIView):
#     permission_classes = [AllowAny]
#     renderer_classes = [JSONRenderer]

#     def get(self, request, entry_fqid):
#         entry = Entry.objects.get(url= entry_fqid, is_deleted=False)
#         comments = Comment.objects.filter(entry=entry).order_by("created")

#         items = [helpers.comment_to_json(c) for c in comments]
#         data = {
#             "type": "comments",
#             "id": request.build_absolute_uri(),  # URL for this list
#             "page_number": 1,
#             "size": len(items),
#             "count": len(items),
#             "src": items,
#         }
#         return Response(data, status=200)

class EntryCommentsByFQIDView(APIView):
    permission_classes = [AllowAny]
    renderer_classes = [JSONRenderer]

    def get(self, request, entry_fqid):
        entry = Entry.objects.get(url= entry_fqid, is_deleted=False)

        # sort newest(first) → oldest(last)
        qs = Comment.objects.filter(entry=entry).order_by("-created")

        # pagination params (default ~5 comments)
        page_number = int(request.GET.get("page", 1))
        size = int(request.GET.get("size", 5))

        paginator = Paginator(qs, size)
        page = paginator.get_page(page_number)

        # serialize comments (each comment includes its likes wrapper)
        serializer = CommentSerializer(
            page.object_list,
            many=True,
            context={"request": request},
        )

        base = request.build_absolute_uri("/").rstrip("/")

        comments_id = f"{base}/api/authors/{entry.author.id}/entries/{entry.id}/comments"
        web = f"{base}/authors/{entry.author.id}/entries/{entry.id}"

        data = {
            "type": "comments",
            "id": comments_id,
            "web": web,
            "page_number": page.number,
            "size": size,
            "count": qs.count(),   # total across all pages
            "src": serializer.data,
        }

        return Response(data, status=200)        




class CommentedDetailView(APIView):
    """
    GET /api/authors/{AUTHOR_SERIAL}/commented/{COMMENT_SERIAL}
    """
    renderer_classes = [JSONRenderer]
    permission_classes = [AllowAny]

    def get(self, request, author_id, comment_id):
        comment = get_object_or_404(
            Comment,
            id=comment_id,
            author_id=author_id,
        )
        return Response(helpers.comment_to_json(comment), status=200)


class CommentedByFQIDView(APIView):
    """
    GET /api/commented/{COMMENT_FQID}
    where COMMENT_FQID is URL-encoded, e.g.
      http%3A%2F%2Fnodeaaaa%2Fapi%2Fauthors%2F111%2Fcommented%2F130
    """
    renderer_classes = [JSONRenderer]
    permission_classes = [AllowAny]

    def get(self, request, comment_fqid):
        comment = _resolve_local_comment_from_fqid(comment_fqid)
        data = helpers.comment_to_json(comment)
        return Response(data, status=200)
        

class CommentedListView(APIView):
    permission_classes = [AllowAny]
    renderer_classes = [JSONRenderer]

    def get(self, request, author_id):
        local_author_id = _normalize_local_id(author_id)
        author = get_object_or_404(User, id=local_author_id)

        qs = Comment.objects.filter(author=author).select_related("entry", "entry__author").order_by("created")

        items = [helpers.comment_to_json(c) for c in qs]
        data = {
            "type": "comments",
            "id": request.build_absolute_uri(),
            "page_number": 1,
            "size": len(items),
            "count": qs.count(),
            "src": items,
        }
        return Response(data, status=200)

    def post(self, request, author_id):
        # Local author POSTs a comment object here
        if not request.user.is_authenticated:
            return Response({"error": "Authentication required"}, status=401)
        if str(request.user.id) != str(author_id):
            return Response({"error": "Cannot post comments as another author"}, status=403)

        data = request.data
        if (data.get("type") or "").lower() != "comment":
            return Response({"error": "Payload 'type' must be 'comment'"}, status=400)

        entry_fqid = data.get("entry")
        if not entry_fqid:
            return Response({"error": "Missing 'entry' field"}, status=400)

        try:
            entry = _resolve_local_entry_from_fqid(entry_fqid)
        except Http404:
            return Response({"error": "Unknown entry FQID"}, status=404)

        if not helpers.can_view_entry(request.user, entry):
            return Response({"error": "Cannot comment on this entry"}, status=403)

        text = (data.get("comment") or "").strip()
        if not text:
            return Response({"error": "Comment cannot be empty"}, status=400)

        ctype = (
            data.get("contentType")
            or data.get("content_type")
            or "text/plain"
        )

        comment = Comment.objects.create(
            entry=entry,
            author=request.user,
            comment=text,
            content_type=ctype,
        )

        Entry.objects.filter(id=entry.id).update(comment_count=F("comment_count") + 1)
        entry.refresh_from_db(fields=["comment_count"])

        out = helpers.comment_to_json(comment)
        out["comment_count"] = entry.comment_count
        return Response(out, status=201)






class EntryCommentByFQIDView(APIView):
    """
    GET /api/authors/{AUTHOR_SERIAL}/entries/{ENTRY_SERIAL}/comment/{REMOTE_COMMENT_FQID}

    REMOTE_COMMENT_FQID is URL-encoded. For local comments we support:
      - the encoded FQID of this node's comment
      - or just the local numeric id.
    """
    renderer_classes = [JSONRenderer]
    permission_classes = [AllowAny]

    def get(self, request, author_id, entry_id, remote_comment_fqid):
        # make sure the entry itself exists and is visible
        entry = get_object_or_404(
            Entry,
            id=entry_id,
            author_id=author_id,
            is_deleted=False,
        )
        if not helpers.can_view_entry(request.user, entry):
            return Response({"error": "no access"}, status=403)

        decoded = unquote(str(remote_comment_fqid))

        # Try local id 
        comment = Comment.objects.filter(fqid=remote_comment_fqid, entry=entry).first()
        if not comment:
            # Try resolving as our own FQID form
            try:
                comment = _resolve_local_comment_from_fqid(decoded)
            except Http404:
                comment = None

        if not comment or comment.entry_id != entry.id:
            raise Http404("comment not found")

        return Response(helpers.comment_to_json(comment), status=200)


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
        return Response(serializer.data, status=200)


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

    {ENTRY_FQID} is the *full* URL of an entry, for example:

        http://127.0.0.1:8000/api/authors/<AUTHOR_ID>/entries/<ENTRY_ID>

    This view only handles local entries. It parses the FQID to get
    author_id and entry_id, then reuses the same image-serving helper
    used by the /authors/{AUTHOR_SERIAL}/entries/{ENTRY_SERIAL}/image endpoint.
    """
    permission_classes = [AllowAny]

    def get(self, request, entry_fqid):
        # Parse the FQID into its components
        parsed = urlparse(entry_fqid)

        # Expected local path format:
        #   /api/authors/<author_id>/entries/<entry_id>
        path_parts = parsed.path.strip("/").split("/")

        try:
            # Example path_parts:
            # ['api', 'authors', '<author_id>', 'entries', '<entry_id>']
            api_index = path_parts.index("api")
            authors_index = path_parts.index("authors", api_index + 1)
            entries_index = path_parts.index("entries", authors_index + 1)

            author_id = path_parts[authors_index + 1]
            entry_id = path_parts[entries_index + 1]
        except (ValueError, IndexError):
            # FQID doesn't look like a valid local entry URL
            return Response(
                {"error": "Invalid FQID format for local entry"},
                status=400,
            )

        # Look up the Entry using the parsed IDs
        entry = get_object_or_404(
            Entry,
            id=entry_id,
            author_id=author_id,
            is_deleted=False,
        )

        # Reuse the existing helper to serve the image bytes
        return entryView._serve_entry_image(request, entry)






# class FollowRequestActionView(APIView):
#     permission_classes = [IsAuthenticated]
#     authentication_classes = [SessionAuthentication]

#     def post(self, request, author_id):
#         if str(request.user.id) != str(author_id):
#             return HttpResponseForbidden("Not your account")

#         target_id = request.POST.get("target_id")
#         target = get_object_or_404(User, id=target_id)
#         if target == request.user:
#             return JsonResponse({"error": "cannot follow yourself"}, status=400)

#         fr, created = Follow.objects.get_or_create(
#             follower=request.user, followee=target,
#             defaults={"status": Follow.Status.PENDING}
#         )
#         if not created and fr.status == Follow.Status.REJECTED:
#             fr.status = Follow.Status.PENDING
#             fr.save(update_fields=["status"])

#         return redirect("profile", author_id=target.id)


# class UnfollowView(APIView):
#     permission_classes = [IsAuthenticated]
#     authentication_classes = [SessionAuthentication]

#     def post(self, request, author_id):
#         if str(request.user.id) != str(author_id):
#             return HttpResponseForbidden("Not your account")

#         target_id = request.POST.get("target_id")
#         target = get_object_or_404(User, id=target_id)
#         Follow.objects.filter(follower=request.user, followee=target).delete()
#         return redirect("profile", author_id=target.id)


# class FollowRequestsPageView(APIView):
#     permission_classes = [IsAuthenticated]
#     renderer_classes = [TemplateHTMLRenderer]

#     def get(self, request, author_id):
#         if str(request.user.id) != str(author_id):
#             return HttpResponseForbidden("Not your account")

#         pendings = Follow.objects.filter(followee=request.user, status=Follow.Status.PENDING) \
#             .select_related("follower").order_by("-created_at")
#         return Response({"requests": pendings}, template_name="follow_requests.html")


# class ApproveFollowRequestView(APIView):
#     permission_classes = [IsAuthenticated]
#     authentication_classes = [SessionAuthentication]

#     def post(self, request, author_id, follower_id):
#         if str(request.user.id) != str(author_id):
#             return HttpResponseForbidden("Not your account")

#         fr = get_object_or_404(Follow, follower_id=follower_id, followee=request.user)
#         fr.status = Follow.Status.APPROVED
#         fr.save(update_fields=["status"])
#         return redirect("follow-requests-page", author_id=author_id)


# class DenyFollowRequestView(APIView):
#     permission_classes = [IsAuthenticated]
#     authentication_classes = [SessionAuthentication]

#     def post(self, request, author_id, follower_id):
#         if str(request.user.id) != str(author_id):
#             return HttpResponseForbidden("Not your account")

#         Follow.objects.filter(follower_id=follower_id, followee=request.user).delete()
#         return redirect("follow-requests-page", author_id=author_id)


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

        # sort newest(first) → oldest(last)
        qs = Comment.objects.filter(entry=entry).order_by("-created")

        # pagination params (default ~5 comments)
        page_number = int(request.GET.get("page", 1))
        size = int(request.GET.get("size", 5))

        paginator = Paginator(qs, size)
        page = paginator.get_page(page_number)
         # serialize comments (each comment includes its likes wrapper)
        serializer = CommentSerializer(
            page.object_list,
            many=True,
            context={"request": request},
        )

        base = request.build_absolute_uri('/api')
        comments_id = f"{base}/authors/{entry.author.id}/entries/{entry.id}/comments"
        web = f"{base}/authors/{entry.author.id}/entries/{entry.id}"

        data = {
            "type": "comments",
            "id": comments_id,
            "web": web,
            "page_number": page.number,
            "size": size,
            "count": qs.count(),   # total across all pages
            "src": serializer.data,
        }

        return Response(data, status=200)        




    

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

        return Response(helpers.comment_to_json(comment), status=201)

class EntryLikesView(APIView):
    '''
    This view handles:
    - GET /api/authors/{author_id}/entries/{entry_id}/likes
        returns a paginated list of likes for the specified entry. (likes object)
        
    - GET /api/entries/{entry_fqid}/likes
        returns a paginated list of likes for the specified entry by fqid. (likes object)
        
    - POST /api/authors/{author_id}/entries/{entry_id}/likes
        returns the like count and the liked status after liking the entry.
        
    - DELETE /api/authors/{author_id}/entries/{entry_id}/likes
        returns the like count and the liked status after unliking the entry.

    '''
    
    permission_classes = [IsAuthenticatedOrReadOnly]
    authentication_classes = [SessionAuthentication]
    renderer_classes = [JSONRenderer]

    def get(self, request, entry_fqid=None, author_id=None, entry_id=None):
        '''
        This handles a get request to retrieve the list of likes for a specific entry.
        it returns a paginated list of likes along with metadata about the entry and pagination.
        '''
        if author_id:
            entry = get_object_or_404(Entry, id=entry_id, author_id=author_id, is_deleted=False)
        elif entry_fqid:
            entry = get_object_or_404(Entry, fqid=entry_fqid, is_deleted=False)
        else:
            return Response({"error": "Invalid request"}, status=400)

        if not helpers.can_view_entry(request.user, entry):
            return HttpResponseForbidden("no access")
        
        page_number = int(request.GET.get("page", 1))  # default to page 1
        size = int(request.GET.get("size", 50)) # default to 50 items per page
        liked = EntryLike.objects.filter(entry=entry).order_by("-created")
        paginator = Paginator(liked, size)
        page = paginator.get_page(page_number)

        # Use an object, not a dict to avoid DRF treating 'src' as a field
        class LikeListObject:
            def __init__(self, author, id, page_number, size, count, src):
                self.author = author
                self.id = id
                self.page_number = page_number
                self.size = size
                self.count = count
                self.src = src

        data = LikeListObject(
            author=entry.author,
            id=entry.id,
            page_number=page_number,
            size=len(liked),
            count=paginator.count,
            src=page.object_list
        )

        serializer = LikesSerializer(data, context={'request': request})
        return Response(serializer.data, status=200)
    
    def post(self, request, author_id, entry_id):
        entry = get_object_or_404(
            Entry, id=entry_id, author_id=author_id, is_deleted=False
        )

        if not helpers.can_view_entry(request.user, entry):
            return HttpResponseForbidden("no access")

        # 1. Create EntryLike (primary like model)
        entry_like, created = EntryLike.objects.get_or_create(
            user=request.user,
            entry=entry
        )

        if created:
            # 2. Add to Liked table for user-liked list
            Liked.objects.get_or_create(
                user=request.user,
                entry=entry,
                defaults={"comment": None}
            )

            # 3. Increment entry like_count
            Entry.objects.filter(id=entry.id).update(like_count=F('like_count') + 1)

        entry.refresh_from_db(fields=['like_count'])

        return JsonResponse({
            "ok": True,
            "liked": True,
            "count": entry.like_count
        }, status=200 if not created else 201)

    def delete(self, request, author_id, entry_id):
        entry = get_object_or_404(
            Entry, id=entry_id, author_id=author_id, is_deleted=False
        )

        if not helpers.can_view_entry(request.user, entry):
            return HttpResponseForbidden("no access")

        # 1. Remove EntryLike
        deleted, _ = EntryLike.objects.filter(
            user=request.user,
            entry=entry
        ).delete()

        if deleted:
            # 2. Remove from Liked model
            Liked.objects.filter(
                user=request.user,
                entry=entry
            ).delete()

            # 3. Decrement like_count
            entry.like_count = max(entry.like_count - 1, 0)
            entry.save(update_fields=['like_count'])

        entry.refresh_from_db(fields=['like_count'])

        return JsonResponse({
            "ok": True,
            "liked": False,
            "count": entry.like_count
        })

class LikedView(APIView):
    """
    Handles:
    - GET /api/authors/{author_id}/liked
        returns a paginated list of all likes (entries + comments) by the specified author.
        
    - GET /api/authors/{author_id}/liked/{like_id}
        returns a single like by this author.
        
    - GET /api/authors/{author_fqid}/liked
        returns a paginated list of all likes (entries + comments) by the specified remote author identified by FQID.
    
    - GET /api/liked/{liked_fqid}
        returns a single like identified by FQID.
    """
    permission_classes = [IsAuthenticatedOrReadOnly]
    renderer_classes = [JSONRenderer]

    def get(self, request, author_id=None, like_id=None, author_fqid=None, liked_fqid=None):

        # Case 1: /authors/{author_id}/liked — all likes (entries + comments)
        if author_id and not like_id:
            user = get_object_or_404(User, id=author_id)
            likes = Liked.objects.filter(user=user).order_by("-created")

            # Pagination
            page_number = int(request.GET.get("page", 1))
            size = int(request.GET.get("size", 5))
            paginator = Paginator(likes, size)
            page = paginator.get_page(page_number)

            # Wrapper
            class LikeListObject:
                def __init__(self, author, id, page_number, size, count, src):
                    self.author = author
                    self.id = id
                    self.page_number = page_number
                    self.size = size
                    self.count = count
                    self.src = src

            data = LikeListObject(
                author=user,
                id=user.id,
                page_number=page_number,
                size=len(likes),
                count=paginator.count,
                src=page.object_list
            )

            serializer = LikesSerializer(data, context={'request': request})
            return Response(serializer.data, status=200)

        # Case 2: single like by this author
        elif author_id and like_id:
            like = get_object_or_404(Liked, id=like_id, user__id=author_id)
            serializer = LikeSerializer(like, context={'request': request})
            return Response(serializer.data, status=200)

        # Case 3: /authors/{author_fqid}/liked — remote author’s likes by FQID
        elif author_fqid:
            user = get_object_or_404(User, fqid=author_fqid)
            likes = Liked.objects.filter(user=user).order_by("-created")

            # Pagination (same logic)
            page_number = int(request.GET.get("page", 1))
            size = int(request.GET.get("size", 5))
            paginator = Paginator(likes, size)
            page = paginator.get_page(page_number)

            class LikeListObject:
                def __init__(self, author, id, page_number, size, count, src):
                    self.author = author
                    self.id = id
                    self.page_number = page_number
                    self.size = size
                    self.count = count
                    self.src = src

            data = LikeListObject(
                author=user,
                id=user.id,
                page_number=page_number,
                size=len(likes),
                count=paginator.count,
                src=page.object_list
            )

            serializer = LikesSerializer(data, context={'request': request})
            return Response(serializer.data, status=200)

        # Case 4: single like by FQID
        elif liked_fqid:
            like = get_object_or_404(Liked, fqid=liked_fqid)
            serializer = LikeSerializer(like, context={'request': request})
            return Response(serializer.data, status=200)

        else:
            return Response({"error": "Invalid request"}, status=400)


# class CommentLikesView(APIView):
#     permission_classes = [IsAuthenticatedOrReadOnly]
#     authentication_classes = [SessionAuthentication]
#     renderer_classes = [JSONRenderer]

#     def get(self, request, author_id, entry_id, comment_id):
#         entry = get_object_or_404(Entry, id=entry_id, author_id=author_id, is_deleted=False)
#         if not helpers.can_view_entry(request.user, entry):
#             return HttpResponseForbidden("no access")

#         comment = get_object_or_404(Comment, id=comment_id, entry=entry)
#         user_liked = request.user.is_authenticated and CommentLike.objects.filter(user=request.user, comment=comment).exists()
#         data = [{
#             "type": "author",
#             "id": like.user.url,
#             "displayName": like.user.username,
#             "web": f"/authors/{like.user.id}",
#         } for like in comment.likes.select_related("user").all()]

#         return JsonResponse({
#             "type": "likes",
#             "count": len(data),
#             "liked": user_liked,
#             "src": data,
#         }, status=200)

#     def post(self, request, author_id, entry_id, comment_id):
#         """
#         Handles liking a comment using the unified Liked model.
#         """
#         # 1. Validate the entry and comment
#         entry = get_object_or_404(Entry, id=entry_id, author_id=author_id, is_deleted=False)
#         if not helpers.can_view_entry(request.user, entry):
#             return HttpResponseForbidden("no access")

#         comment = get_object_or_404(Comment, id=comment_id, entry=entry)

#         # 2. Create (or reuse) the like
#         like, created = Liked.objects.get_or_create(user=request.user, comment=comment, defaults={"entry": entry})

#         if created:
#             # Optional: update comment like count if you track it
#             Comment.objects.filter(id=comment.id).update(like_count=F('like_count') + 1)

#         # 3. Return the total count
#         count = Liked.objects.filter(comment=comment).count()
#         return JsonResponse({"ok": True, "liked": True, "count": count}, status=201)

#     def delete(self, request, author_id, entry_id, comment_id):
#         """
#         Handles unliking a comment using the unified Liked model.
#         """
#         entry = get_object_or_404(Entry, id=entry_id, author_id=author_id, is_deleted=False)
#         if not helpers.can_view_entry(request.user, entry):
#             return HttpResponseForbidden("no access")

#         comment = get_object_or_404(Comment, id=comment_id, entry=entry)

#         # 1. Delete the like
#         deleted, _ = Liked.objects.filter(user=request.user, comment=comment).delete()

#         if deleted:
#             # Optional: decrement comment like count (never below 0)
#             comment.like_count = max(comment.like_count - 1, 0)
#             comment.save(update_fields=["like_count"])

#         # 2. Return the updated count
#         count = Liked.objects.filter(comment=comment).count()
#         return JsonResponse({"ok": True, "liked": False, "count": count}, status=200)




from urllib.parse import unquote
from django.shortcuts import get_object_or_404
from django.http import JsonResponse
from rest_framework.permissions import IsAuthenticatedOrReadOnly
from rest_framework.renderers import JSONRenderer
from rest_framework.views import APIView
from django.db import IntegrityError

# assumes you already have:
# - helpers.can_view_entry(user, entry)
# - _normalize_local_id(s)
# - models: Entry, Comment, CommentLike

class CommentLikesView(APIView):
    """
    Supports BOTH:
      /api/authors/<author_id>/entries/<entry_id>/comments/<str:comment_id>/likes
      /api/authors/<author_id>/entries/<entry_id>/comments/<path:comment_fqid>/likes
    """
    permission_classes = [IsAuthenticatedOrReadOnly]

    renderer_classes = [JSONRenderer]

    def _get_entry(self, author_id, entry_id, user):
        entry = get_object_or_404(Entry, id=entry_id, author_id=author_id, is_deleted=False)





        if not helpers.can_view_entry(user, entry):
            return None, JsonResponse({"error": "no access"}, status=403)
        return entry, None


    def _resolve_comment(self, entry, comment_ref):

  
        if not comment_ref:
            return None

        # 1) exact local id
        c = Comment.objects.filter(id=comment_ref, entry=entry).first()
        if c:
            return c

        # 2) decoded + last segment
        decoded = unquote(str(comment_ref)).strip()
        last = _normalize_local_id(decoded)

        c = Comment.objects.filter(id=last, entry=entry).first()
        if c:
            return c

        # 3) exact fqid
        if hasattr(Comment, "fqid"):
            c = Comment.objects.filter(fqid=decoded, entry=entry).first()
            if c:
                return c
            # 4) endswith '/<id>'
            c = Comment.objects.filter(fqid__endswith="/" + last, entry=entry).first()
            if c:
                return c

        return None

    def get(self, request, author_id, entry_id, **kwargs):
        
        comment_ref = kwargs.get("comment_id") or kwargs.get("comment_fqid")

        entry, err = self._get_entry(author_id, entry_id, request.user)
        if err:
            return err

        comment = self._resolve_comment(entry, comment_ref)
        if not comment:
            return JsonResponse({"error": "comment not found"}, status=404)

        user_liked = (
            request.user.is_authenticated
            and CommentLike.objects.filter(user=request.user, comment=comment).exists()
        )

        src = [
            {
                "type": "author",
                "id": like.user.url,
                "displayName": like.user.username,
                "web": f"/authors/{like.user.id}",
            }
            for like in comment.likes.select_related("user").all()
        ]

        return JsonResponse({"type": "likes", "count": len(src), "liked": user_liked, "src": src}, status=200)









    def post(self, request, author_id, entry_id, **kwargs):



        if not request.user.is_authenticated:
            return JsonResponse({"error": "login required"}, status=403)

        comment_ref = kwargs.get("comment_id") or kwargs.get("comment_fqid")

        entry, err = self._get_entry(author_id, entry_id, request.user)
        if err:
            return err

        comment = self._resolve_comment(entry, comment_ref)
        if not comment:
            return JsonResponse({"error": "comment not found"}, status=404)

        try:
            _, created = CommentLike.objects.get_or_create(user=request.user, comment=comment)



        except IntegrityError:

            created = False

        count = CommentLike.objects.filter(comment=comment).count()
        return JsonResponse({"ok": True, "liked": True, "count": count}, status=201 if created else 200)

    def delete(self, request, author_id, entry_id, **kwargs):








        if not request.user.is_authenticated:
            return JsonResponse({"error": "login required"}, status=403)

        comment_ref = kwargs.get("comment_id") or kwargs.get("comment_fqid")

        entry, err = self._get_entry(author_id, entry_id, request.user)
        if err:
            return err


        comment = self._resolve_comment(entry, comment_ref)
        if not comment:
            return JsonResponse({"error": "comment not found"}, status=404)

        CommentLike.objects.filter(user=request.user, comment=comment).delete()
        count = CommentLike.objects.filter(comment=comment).count()
        return JsonResponse({"ok": True, "liked": False, "count": count}, status=200)


     