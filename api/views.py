from django.shortcuts import render, get_object_or_404, redirect
from django.db.models import F, Q
from .models import User, Entry, Comment, EntryLike, CommentLike, Follow 
from django.contrib.auth import get_user_model
from django.http import JsonResponse, HttpResponseNotAllowed, HttpResponseForbidden, HttpResponse, Http404
from django.views.decorators.http import require_POST, require_http_methods
from django.views.decorators.csrf import csrf_exempt, csrf_protect
from django.contrib.auth.decorators import login_required
from django.utils.timezone import now
from .utils.images import handle_uploaded_image
import base64
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.renderers import TemplateHTMLRenderer, JSONRenderer
from rest_framework.response import Response
from .serializers import UserSerializer
from .utils import helpers





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
        serializer = UserSerializer(user)
        entries_data = (
            entries.annotate(author_username=F("author__username"))
            .values("id", "author_username", "title", "content_type", "visibility", "updated")
        )
        return Response(
            {
                "user": serializer.data,
                "entries": list(entries_data),
                # counts/rel also available in JSON if you want:
                "posts_count": posts_count,
                "followers_count": followers_count,
                "following_count": following_count,
                "friends_count": friends_count,
                "rel_status": rel_status,
                "can_approve": can_approve,
            },
            status=200,
        )


class ProfileEditView(APIView):
    permission_classes = [IsAuthenticated]
    renderer_classes = [TemplateHTMLRenderer, JSONRenderer]

    def get(self, request, author_id):
        if getattr(request, "user", None) and request.user.is_authenticated and request.user.id == author_id:
            return Response({"user": request.user }, template_name="author/profileEdit.html")
        else:
            return redirect('home')

    def post(self, request, author_id):
        if request.user.id != author_id:
            return redirect('home')
        
        serializer = UserSerializer(request.user, data=request.data, partial=True)

        if not serializer.is_valid():
            if isinstance(request.accepted_renderer, TemplateHTMLRenderer):
                return Response({"errors": serializer.errors, "user": request.user}, template_name="author/profileEdit.html", status=400)
            return Response({"errors": serializer.errors}, status=400)

        user = serializer.save()
        if isinstance(request.accepted_renderer, TemplateHTMLRenderer):
            return redirect('profile', author_id=user.id)
        return Response({"user": serializer.data}, status=200)


@login_required
def author_stream(request, author_id):
    # determine the selected tab (default to all)
    tab = request.GET.get('tab', 'all')
    me = request.user

    # If someone opens another author's stream URL, show their own stream
    if str(me.id) != str(author_id):
        author_id = me.id

    if tab == 'following':
        # fetch entries from authors the user follows, excluding the user's own entries
        followed_users = helpers.users_i_follow(me)
        friends = helpers.friends_of(me)

        # authors I follow who are NOT friends
        following_nonfriends = followed_users.exclude(pk__in=friends.values("pk"))

        entries = (
        Entry.objects.filter(is_deleted=False)
        .exclude(author=me)
        .filter(
            # friends: can see FRIENDS + PUBLIC + UNLISTED
            Q(author__in=friends, visibility__in=["FRIENDS", "PUBLIC", "UNLISTED"])
            |
            # followed but not friends: PUBLIC + UNLISTED only
            Q(author__in=following_nonfriends, visibility__in=["PUBLIC", "UNLISTED"])
        )
        .order_by("-updated")
    )
        
    elif tab == 'private':
        # fetch only the user's own private entries
        entries = Entry.objects.filter(
            author=request.user,
            is_deleted=False
        ).order_by('-updated')
       
    
    elif tab == 'friends':
        friends = helpers.friends_of(me)
        allowed_visibility = ['FRIENDS', 'PUBLIC', 'UNLISTED']

        entries = (
            Entry.objects
            .filter(author__in=friends, visibility__in=allowed_visibility, is_deleted=False)
            .exclude(author=me)
            .order_by('-updated')
        )
    else: #all tab
        
        followed_users = helpers.users_i_follow(me)
        friend_users   = helpers.friends_of(me)
           
        public_entries = Entry.objects.filter(
          visibility='PUBLIC', is_deleted=False)

        my_entries = Entry.objects.filter(
          author=me, is_deleted=False)
        
        unlisted_from_followed = Entry.objects.filter(
        author__in=followed_users, visibility='UNLISTED', is_deleted=False
    )
        friends_only_from_friends = Entry.objects.filter(
            author__in=friend_users, visibility='FRIENDS', is_deleted=False
        )
        entries = (
            public_entries
            | my_entries
            | unlisted_from_followed
            | friends_only_from_friends
        ).order_by('-updated')
    
    liked_ids = set()
    if request.user.is_authenticated and entries:
        liked_ids = set(
            EntryLike.objects
            .filter(user=request.user, entry__in=entries)
            .values_list('entry_id', flat=True)
        )

    # pre-rendered HTML for template
    for e in entries:
        e.user_liked = e.id in liked_ids
        
        e.rendered = helpers.render_entry(e)

    # render with author ID and the selected tab
    return render(request, 'author_all_entries.html', {
        'author_id': author_id,
        'entries': entries,
        'tab': tab,
    })


@login_required     # require login
@csrf_protect   # use csrf token in browser posts
@require_http_methods(['POST'])   # only allow post
def make_entries_public(request, entry_id):
    # only the owner can change visibility
    entry = get_object_or_404(Entry, id=entry_id, is_deleted=False)
    if entry.author_id != request.user.id:
        return HttpResponseForbidden("only the author can change visibility for this entry.")

    # set to public and save
    entry.visibility = 'PUBLIC'
    entry.updated = now()
    entry.save()

    return JsonResponse({'status': 'ok', 'entry_id': str(entry_id), 'visibility': entry.visibility}, status=200)


# -------- api: list + create --------------------------------------------------
@csrf_exempt  # kept for simple curl testing; ui paths use csrf_protect
def entries_list_create(request, author_id):
    # list entries for an author, newest first
    if request.method == 'GET':
        qs = Entry.objects.filter(
            author_id=author_id,     
            is_deleted=False            # exclude deleted
        ).order_by('-updated')       
        data = [helpers.entry_to_json(e, content_type_hint='text/markdown') for e in qs]
        return JsonResponse({"type": "entries", "count": len(data), "src": data}, status=200)

    # create a new entry locally for the same author
    if request.method == 'POST':
        # only the logged-in owner can create entries here
        if not request.user.is_authenticated or str(request.user.id) != str(author_id):
            return HttpResponseForbidden("only the author can create entries here.")
        payload = helpers.json_from_request(request)       # parse json body
        title       = (payload.get('title') or '').strip() or '(no title)'  # default title
        content     = payload.get('content') or ''  # allow empty body
        contentType = payload.get('contentType') or 'text/plain'            # markdown or plain
        visibility  = payload.get('visibility') or 'PUBLIC'                 # default public

        # fetch owner and insert the record
        author = get_object_or_404(User, id=author_id)  # ensure author exists
        e = Entry.objects.create(
            author=author,              
            title=title,                
            content=content,          
            visibility=visibility,        # enum value
            is_deleted=False,             # ensure visible
        )
        return JsonResponse(helpers.entry_to_json(e, content_type_hint=contentType), status=201)

    # method not allowed guard
    return HttpResponseNotAllowed(['GET', 'POST'])


# -------- api: retrieve + update ---------------------------------------------
@csrf_exempt  # for curl; the ui form uses csrf_protect
def entry_retrieve_update(request, author_id, entry_id):
    # find the entry or return 404
    e = get_object_or_404(Entry, id=entry_id, author_id=author_id, is_deleted=False)

    # return a single entry in json format
    if request.method == 'GET':
        return JsonResponse(helpers.entry_to_json(e, content_type_hint='text/markdown'), status=200)

    # update fields without delete-recreate
    if request.method in ['PUT', 'PATCH']:
        # only the owner can perform updates
        if not request.user.is_authenticated or str(request.user.id) != str(author_id):
            return HttpResponseForbidden("only the author can edit this entry.")
        payload = helpers.json_from_request(request)  # parse body

        # update only provided fields to support patch semantics
        if 'title' in payload:
            e.title = payload['title'] or e.title
        if 'content' in payload:
            e.content = payload['content'] or e.content
        if 'visibility' in payload:
            e.visibility = payload['visibility'] or e.visibility

        # update timestamp and save changes
        e.updated = now()
        e.save()

        # echo content type hint back to client
        contentType = payload.get('contentType') or 'text/plain'
        return JsonResponse(helpers.entry_to_json(e, content_type_hint=contentType), status=200)

    # method not allowed guard
    return HttpResponseNotAllowed(['GET', 'PUT', 'PATCH'])





# -------- pages: create (server-rendered form) --------------------------------
@login_required
@csrf_protect
def entry_create_page(request, author_id):
    #ToDO:Handle image being too large error
    # only the owner can open and submit this form
    if str(request.user.id) != str(author_id):
        return HttpResponseForbidden("only the author can create entries here.")

    # GET -> render empty form
    if request.method == 'GET':
        return render(request, 'entry_create.html', {'author_id': author_id})

    # POST -> create an entry
    title       = (request.POST.get('title') or '').strip() or '(no title)'
    visibility  = request.POST.get('visibility') or 'PUBLIC'
    contentType = request.POST.get('contentType') or 'text/plain'
    as_image    = request.POST.get('as_image') == 'on'  # checkbox "Upload as image entry"
    author      = get_object_or_404(User, id=author_id)

    # NOTE:
    # If as_image is checked, we read the uploaded file, validate with Pillow,
    # transcode when needed, and store base64 bytes as content with an image/*;base64 content_type.
    # Otherwise, we treat it as a text entry (markdown or plain) and store raw text.

    if as_image:
        # Ensure a file is provided
        file_obj = request.FILES.get('image')
        if not file_obj:
            # simple fallback: redirect back with a message, or raise 400
            return JsonResponse({"error": "no image file uploaded"}, status=400)

        # Validate and (optionally) transcode -> returns (content_type, base64_str)
        try:
            img_ct, b64_str = handle_uploaded_image(file_obj)
        except ValueError as exc:
            return JsonResponse({"error": str(exc)}, status=400)

        # Create the image entry
        e = Entry.objects.create(
            author=author,
            title=title,
            content=b64_str,          # store base64 string
            visibility=visibility,
            is_deleted=False,
        )
        # Persist the MIME type if your model has this field
        if hasattr(e, 'content_type'):
            e.content_type = img_ct          # e.g., "image/png;base64" or "image/jpeg;base64"
            e.save(update_fields=['content_type'])

    else:
        # Text entry (markdown/plain)
        text_content = request.POST.get('content') or ''
        e = Entry.objects.create(
            author=author,
            title=title,
            content=text_content,
            visibility=visibility,
            is_deleted=False,
        )
        # Save the text content type hint if the model has content_type
        if hasattr(e, 'content_type'):
            # "text/markdown" or "text/plain"
            e.content_type = contentType
            e.save(update_fields=['content_type'])

    # Done -> back to stream
    return redirect('author-all-entries', author_id=author_id)



# -------- pages: edit (server-rendered form) ----------------------------------
@login_required   # require session auth for ui usage
@csrf_protect     # protect post with csrf token
def entry_edit_page(request, author_id, entry_id):
    # only the owner can edit
    if str(request.user.id) != str(author_id):
        return HttpResponseForbidden("only the author can edit this entry.")

    # load target entry
    e = get_object_or_404(Entry, id=entry_id, author_id=author_id, is_deleted=False)

    # pre-fill form
    if request.method == 'GET':
        # keep your original default; template can still show text controls
        ctx = {
            'author_id': author_id,
            'entry': e,
            'contentType': getattr(e, 'content_type', '') or 'text/markdown',
        }
        return render(request, 'entry_edit.html', ctx)

    # POST: two paths
    # 1) "replace with image" path (checkbox + file)
    as_image = request.POST.get('as_image') == 'on'     # flag from form
    img_file = request.FILES.get('image')               # uploaded file

    # always allow updating common fields
    e.title = request.POST.get('title') or e.title
    e.visibility = request.POST.get('visibility') or e.visibility

    if as_image and img_file:
        #validate/transcode -> base64，  set content & content_type accordingly
        try:
            content_type, b64_str = handle_uploaded_image(img_file)
            e.content = b64_str
            e.content_type = content_type            # e.g. image/png;base64 or image/jpeg;base64
        except ValueError:
            #if the image is invalid, silently fall back to text update (keeps behavior simple)
            pass
    else:
        # 2) original text-edit path
        e.content = request.POST.get('content') or e.content
        ct_hint = request.POST.get('contentType') or ''
        if ct_hint:
            e.content_type = ct_hint

    e.updated = now()
    e.save()

    # back to stream
    return redirect('author-all-entries', author_id=author_id)


@login_required
def browse_public_entries(request):
    # querying for all public entries (local and received)
    all_public_entries = Entry.objects.filter(visibility='PUBLIC', is_deleted=False).order_by('-created')

    # pre-rendered HTML for each entry
    for entry in all_public_entries:
        entry.rendered = helpers.render_entry(entry)  # Add a transient field for template use

    # render the entries in the existing browse_entries.html template
    return render(request, 'browse_entries.html', {
        'entries': all_public_entries,
    })


    
@login_required
@require_http_methods(['GET'])
def entry_image_binary(request, author_id, entry_id):
    """
    Return the binary of an image entry (spec-compliant /image endpoint):
    - content_type must be image/*;base64
    - content stores the pure base64 body (without the "data:" prefix)
    """
    # grab the entry or 404 if it doesn't exist / isn't yours
    e = get_object_or_404(Entry, id=entry_id, author_id=author_id, is_deleted=False)

    # normalize and check the stored content_type, we only serve real image entries
    ct = (getattr(e, 'content_type', '') or '').lower()
    if not (ct.startswith('image/') and ct.endswith(';base64')):
        # not an image-type entry per our contract
        raise Http404('not an image entry')

    try:
        # decode the raw base64 string to bytes
        raw = base64.b64decode(e.content or '')
    except Exception:
        # data is corrupt or not base64 — treat as missing
        raise Http404('bad image data')

    # send bytes back with an actual image/* mime type (strip the ;base64 suffix)
    return HttpResponse(raw, content_type=ct.replace(';base64', ''))


def entry_shared_view(request, token):
    entry = get_object_or_404(Entry, share_token=token, is_deleted=False)
    
    if entry.visibility not in ['PUBLIC', 'UNLISTED']:
        return HttpResponseForbidden("This entry is not shareable.")

    # render the entry content
    entry.rendered = helpers.render_entry(entry)

    return render(request, "entry_shared.html", {"entry": entry})



@require_POST
@login_required
@csrf_protect
def entry_delete(request, author_id, entry_id):
    # only the author can delete
    if str(request.user.id) != str(author_id):
        return HttpResponseForbidden("Only the author can delete this entry.")

    # soft delete the entry because it says to delete my own entries locally
    e = get_object_or_404(Entry, id=entry_id, author_id=author_id, is_deleted=False)
    e.is_deleted = True
    e.updated = now()
    e.save(update_fields=['is_deleted', 'updated'])
    return redirect('author-all-entries', author_id=author_id)


@login_required
@require_POST
def send_follow_request(request, author_id):
    # author_id == the viewer (me) sending request
    if str(request.user.id) != str(author_id):
        return HttpResponseForbidden("Not your account")
    target_id = request.POST.get("target_id")
    target = get_object_or_404(User, id=target_id)
    if target == request.user:
        return JsonResponse({"error":"cannot follow yourself"}, status=400)

    fr, created = Follow.objects.get_or_create(
        follower=request.user, followee=target,
        defaults={"status": Follow.Status.PENDING}
    )
    if not created and fr.status == Follow.Status.REJECTED:
        fr.status = Follow.Status.PENDING
        fr.save(update_fields=["status"])
    return redirect("profile", author_id=target.id)


@login_required
@require_POST
def unfollow_post(request, author_id):
    if str(request.user.id) != str(author_id):
        return HttpResponseForbidden("Not your account")
    target_id = request.POST.get("target_id")
    target = get_object_or_404(User, id=target_id)
    Follow.objects.filter(follower=request.user, followee=target).delete()
    return redirect("profile", author_id=target.id)


@login_required
def follow_requests_page(request, author_id):
    # show incoming pending requests to ME
    if str(request.user.id) != str(author_id):
        return HttpResponseForbidden("Not your account")
    pendings = Follow.objects.filter(followee=request.user, status=Follow.Status.PENDING).select_related("follower").order_by("-created_at")
    return render(request, "follow_requests.html", {"requests": pendings})


@login_required
@require_POST
def approve_follow_request(request, author_id, follower_id):
    if str(request.user.id) != str(author_id):
        return HttpResponseForbidden("Not your account")
    fr = get_object_or_404(Follow, follower_id=follower_id, followee=request.user)
    fr.status = Follow.Status.APPROVED
    fr.save(update_fields=["status"])
    return redirect("follow-requests-page", author_id=author_id)


@login_required
@require_POST
def deny_follow_request(request, author_id, follower_id):
    if str(request.user.id) != str(author_id):
        return HttpResponseForbidden("Not your account")
    Follow.objects.filter(follower_id=follower_id, followee=request.user).delete()
    return redirect("follow-requests-page", author_id=author_id)


@csrf_exempt
@require_http_methods(["GET", "POST"])
def comments_list_create(request, author_id, entry_id):
    """
    GET  /api/authors/<author_id>/entries/<entry_id>/comments
    POST /api/authors/<author_id>/entries/<entry_id>/comments
    """
    entry = get_object_or_404(Entry, id=entry_id, author_id=author_id, is_deleted=False)

    # visibility guard (public/unlisted ok; friends/private need auth/relationship)
    if not helpers.can_view_entry(request.user, entry):
        return HttpResponseForbidden("no access to this entry")

    if request.method == "GET":
        # simple paging
        try:
            page = int(request.GET.get("page", 1))
            size = int(request.GET.get("size", 10))
        except ValueError:
            page, size = 1, 10
        start, end = (page - 1) * size, (page - 1) * size + size

        qs = entry.comments.all().order_by("-created")
        items = [helpers.comment_to_json(c) for c in qs[start:end]]

        base = entry.author.url.split('/authors/')[0] if entry.author and entry.author.url else ''
        return JsonResponse({
            "type": "comments",
            "id": f"{base}/api/authors/{author_id}/entries/{entry_id}/comments",
            "page_number": page,
            "size": size,
            "count": entry.comment_count,
            "src": items
        }, status=200)

    # POST: create a comment (must be logged in)
    if not request.user.is_authenticated:
        return HttpResponseForbidden("login required")

    data = helpers.json_from_request(request)
    text = (data.get("comment") or "").strip()
    if not text:
        return JsonResponse({"error": "comment text is required"}, status=400)
    ctype = (data.get("contentType") or "text/plain").strip() or "text/plain"

    c = Comment.objects.create(entry=entry, author=request.user, comment=text, content_type=ctype)
    Entry.objects.filter(id=entry.id).update(comment_count=F('comment_count') + 1)
    entry.refresh_from_db(fields=['comment_count'])
    return JsonResponse(helpers.comment_to_json(c), status=201)


# ======================================================================
# Developed with assistance from ChatGPT (GPT-5), October 2025
# ======================================================================
@csrf_exempt
@require_http_methods(["GET", "POST", "DELETE"])
def entry_likes(request, author_id, entry_id):
    """
    GET     /api/authors/<author_id>/entries/<entry_id>/likes
            -> { type:"likes", count:<int>, liked:<bool>, src:[...] }
    POST    like (idempotent) -> { ok:true, liked:true, count:<int> }
    DELETE  unlike            -> { ok:true, liked:false, count:<int> }
    """
    entry = get_object_or_404(Entry, id=entry_id, author_id=author_id, is_deleted=False)
    if not helpers.can_view_entry(request.user, entry):
        return HttpResponseForbidden("no access")

    # compute count fast and whether THIS user liked it
    # count = EntryLike.objects.filter(entry=entry).count()
    user_liked = False
    if request.user.is_authenticated:
        user_liked = EntryLike.objects.filter(entry=entry, user=request.user).exists()

    if request.method == "GET":
        data = [{
            "type": "author",
            "id": like.user.url,
            "displayName": like.user.username,
            "web": f"/authors/{like.user.id}",
        } for like in EntryLike.objects.select_related("user").filter(entry=entry)]
        return JsonResponse(
            {"type": "likes", "count": entry.like_count, "liked": user_liked, "src": data},
            status=200
        )

    if not request.user.is_authenticated:
        return HttpResponseForbidden("login required")

    if request.method == "POST":
        like, created = EntryLike.objects.get_or_create(user=request.user, entry=entry)
        if created:
            Entry.objects.filter(id=entry.id).update(like_count=F('like_count') + 1)
        entry.refresh_from_db(fields=['like_count'])
        return JsonResponse({"ok": True, "liked": True, "count": entry.like_count}, status=201)

    # DELETE (unlike)
    deleted, _ = EntryLike.objects.filter(user=request.user, entry=entry).delete()
    if deleted:
        entry.like_count = max(entry.like_count - 1, 0)
        entry.save(update_fields=['like_count'])
    entry.refresh_from_db(fields=['like_count'])
    return JsonResponse({"ok": True, "liked": False, "count": entry.like_count}, status=200)


@csrf_exempt
@require_http_methods(["GET", "POST", "DELETE"])
def comment_likes(request, author_id, entry_id, comment_id):
    """
    GET     /api/authors/<author_id>/entries/<entry_id>/comments/<comment_id>/likes
    POST    /api/authors/<author_id>/entries/<entry_id>/comments/<comment_id>/likes
    DELETE  /api/authors/<author_id>/entries/<entry_id>/comments/<comment_id>/likes
    """
    entry = get_object_or_404(Entry, id=entry_id, author_id=author_id, is_deleted=False)
    if not helpers.can_view_entry(request.user, entry):
        return HttpResponseForbidden("no access")

    comment = get_object_or_404(Comment, id=comment_id, entry=entry)

    if request.method == "GET":
        data = [{
            "type": "author",
            "id": like.user.url,
            "displayName": like.user.username,
            "web": f"/authors/{like.user.id}",
        } for like in comment.likes.select_related("user").all()]
        return JsonResponse({"type": "likes", "count": len(data), "src": data}, status=200)

    if not request.user.is_authenticated:
        return HttpResponseForbidden("login required")

    if request.method == "POST":
        CommentLike.objects.get_or_create(user=request.user, comment=comment)
        return JsonResponse({"ok": True}, status=201)

    # DELETE
    CommentLike.objects.filter(user=request.user, comment=comment).delete()
    return JsonResponse({"ok": True}, status=200)