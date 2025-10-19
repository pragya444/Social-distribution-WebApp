from django.shortcuts import render, get_object_or_404, redirect
from django.db.models import F, Q
from .models import User, Entry, Comment, EntryLike, CommentLike, Follow 
from django.contrib.auth import get_user_model
from django.http import JsonResponse, HttpResponseNotAllowed, HttpResponseForbidden, HttpResponse, Http404
from django.views.decorators.http import require_POST, require_http_methods
from django.views.decorators.csrf import csrf_exempt, csrf_protect
from django.contrib.auth.decorators import login_required
from django.utils.timezone import now
from django.utils.html import escape
from django.utils.safestring import mark_safe
from django.template.defaultfilters import linebreaksbr
from django.urls import reverse
from .utils.images import handle_uploaded_image
import json
import base64
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.renderers import TemplateHTMLRenderer, JSONRenderer
from rest_framework.response import Response
from .serializers import UserSerializer
from .models import User, Entry, Comment, EntryLike, CommentLike


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



        # -------- counts + relationship status -------------------------
        # counts
        posts_count = Entry.objects.filter(author=user, is_deleted=False).count()
        from .models import Follow  # (safe if already imported above)
        followers_count = Follow.objects.filter(followee=user, status=Follow.Status.APPROVED).count()
        following_count = Follow.objects.filter(follower=user, status=Follow.Status.APPROVED).count()

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
                e.rendered = _render_entry(e)

            return Response(
                {
                    "user": user,
                    "entries": entries,
                  
                    "posts_count": posts_count,
                    "followers_count": followers_count,
                    "following_count": following_count,
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
                "rel_status": rel_status,
                "can_approve": can_approve,
            },
            status=200,
        )




        # serializer = UserSerializer(user)

        # if isinstance(request.accepted_renderer, TemplateHTMLRenderer):
        #     # attach pre-rendered html for template
        #     for e in entries:
        #         e.rendered = _render_entry(e)  # add a transient field for template use
        #     return Response({ "user": user, "entries": entries }, template_name="author/profile.html")
        
        # entries_data = (
        #     entries.annotate(author_username=F("author__username"))
        #     .values("id", "author_username", "title", "content_type", "visibility", "updated",)
        # )
        # return Response({"user": serializer.data, "entries": list(entries_data)}, status=200)



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
        followed_users = users_i_follow(me)
        entries = (
            Entry.objects
            .filter(author__in=followed_users, is_deleted=False)
            .exclude(author=me)
            .order_by('-updated')
        )
    elif tab == 'private':
        # fetch only the user's own private entries
        entries = Entry.objects.filter(
            author=request.user,
            is_deleted=False
        ).order_by('-updated')
       
    
    elif tab == 'friends':
        friends = friends_of(me)

        entries = (
            Entry.objects
            .filter(author__in=friends, visibility='FRIENDS', is_deleted=False)
            .exclude(author=me)
            .order_by('-updated')
        )
    else: #all tab
        
        followed_users = users_i_follow(me)
        friend_users   = friends_of(me)
           
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
    

    # else:  
    #     # fetch all public entries
    #     public_entries = Entry.objects.filter(visibility='PUBLIC', is_deleted=False)

    #     # fetch entries from authors the user follows
    #     followed_entries = Entry.objects.filter(
    #         Q(author__id=author_id) & Q(is_deleted=False)
    #     )

    #     # combine followed entries and public entries
    #     entries = public_entries.union(followed_entries).order_by('-updated')

    # pre-rendered HTML for template
    for e in entries:
        e.rendered = _render_entry(e)

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

# -------- helpers -------------------------------------------------------------
def _json_from_request(request):
    # parse json body safely, return empty dict on failure
    try:
        raw = request.body.decode('utf-8') or "{}"  # handle empty body
        return json.loads(raw)                      # convert to dict
    except Exception:
        return {}                                   # tolerate bad json


def _entry_to_json(e, content_type_hint='text/plain'):
    # produce a spec-like shape without touching database schema
    author_host = e.author.url.split('/authors/')[0] if e.author and e.author.url else ''
    # build a minimal, stable payload for clients and tests
    return {
        "type": "entry",                           
        "title": e.title,                        
        "id": f"{e.author.url}/entries/{e.id}" if e.author and e.author.url else str(e.id),  # fqid if available
        "web": f"/authors/{e.author_id}/entries/{e.id}",  # local web path
        "description": e.title or "",              
        "contentType": content_type_hint,           # passthrough hint
        "content": e.content or "",                
        "author": {                                 # embedded author
            "type": "author",
            "id": e.author.url if e.author else "",
            "host": f"{author_host}api/" if author_host else "",
            "displayName": e.author.username if e.author else "",
            "web": f"/authors/{e.author_id}",
            "github": e.author.github if e.author else "",
            "profileImage": e.author.profile_picture if e.author else "",
        },
        "likes": {                                  # placeholder list
            "type": "likes",
            "id": f"/api/authors/{e.author_id}/entries/{e.id}/likes",
            "page_number": 1, "size": 50, "count": 0, "src": [],
        },
        "comments": {                               # placeholder list
            "type": "comments",
            "id": f"/api/authors/{e.author_id}/entries/{e.id}/comments",
            "page_number": 1, "size": 5, "count": 0, "src": [],
        },
        "published": e.created.isoformat() if e.created else "",  # iso 8601 timestamp
        "visibility": e.visibility,                # enum string
    }

def users_i_follow(me):
    """
    Users that 'me' follows with APPROVED status.
    """
    return User.objects.filter(
        followers__follower=me,
        followers__status=Follow.Status.APPROVED
    )

def followers_of(me):
    """
    Users that follow 'me' with APPROVED status.
    """
    return User.objects.filter(
        following__followee=me,
        following__status=Follow.Status.APPROVED
    )

def friends_of(me):
    """
    Mutual follow: both directions APPROVED.
    """
    from .models import Follow
    return [u for u in users_i_follow(me) if Follow.are_friends(me, u)]    


# -------- api: list + create --------------------------------------------------
@csrf_exempt  # kept for simple curl testing; ui paths use csrf_protect
def entries_list_create(request, author_id):
    # list entries for an author, newest first
    if request.method == 'GET':
        qs = Entry.objects.filter(
            author_id=author_id,     
            is_deleted=False            # exclude deleted
        ).order_by('-updated')       
        data = [_entry_to_json(e, content_type_hint='text/markdown') for e in qs]
        return JsonResponse({"type": "entries", "count": len(data), "src": data}, status=200)

    # create a new entry locally for the same author
    if request.method == 'POST':
        # only the logged-in owner can create entries here
        if not request.user.is_authenticated or str(request.user.id) != str(author_id):
            return HttpResponseForbidden("only the author can create entries here.")
        payload = _json_from_request(request)       # parse json body
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
        return JsonResponse(_entry_to_json(e, content_type_hint=contentType), status=201)

    # method not allowed guard
    return HttpResponseNotAllowed(['GET', 'POST'])


# -------- api: retrieve + update ---------------------------------------------
@csrf_exempt  # for curl; the ui form uses csrf_protect
def entry_retrieve_update(request, author_id, entry_id):
    # find the entry or return 404
    e = get_object_or_404(Entry, id=entry_id, author_id=author_id, is_deleted=False)

    # return a single entry in json format
    if request.method == 'GET':
        return JsonResponse(_entry_to_json(e, content_type_hint='text/markdown'), status=200)

    # update fields without delete-recreate
    if request.method in ['PUT', 'PATCH']:
        # only the owner can perform updates
        if not request.user.is_authenticated or str(request.user.id) != str(author_id):
            return HttpResponseForbidden("only the author can edit this entry.")
        payload = _json_from_request(request)  # parse body

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
        return JsonResponse(_entry_to_json(e, content_type_hint=contentType), status=200)

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
        entry.rendered = _render_entry(entry)  # Add a transient field for template use

    # render the entries in the existing browse_entries.html template
    return render(request, 'browse_entries.html', {
        'entries': all_public_entries,
    })


def _looks_like_markdown(t: str) -> bool:
    # normalize to empty string when none
    t = t or ""
    # quick heuristics for common markdown tokens
    tokens = ("# ", "**", "* ", "- ", "\n- ", "`", "[", "](", "> ", "\n> ", "___", "---")
    # return true if any token appears in the text
    return any(tok in t for tok in tokens)


def _render_entry(entry):
    # read content type and text from the model
    ct = (getattr(entry, "content_type", "") or "").lower()
    text = getattr(entry, "content", "") or ""

    if ct in ("image/png;base64", "image/jpeg;base64", "image/jpg;base64"):
        img_url = reverse("entry-image", args=[entry.author_id, entry.id])
        html = f'<img src="{img_url}" alt="{escape(entry.title or "")}" style="max-width:100%;height:auto;" />'
        return mark_safe(html)
    
    # auto-detect markdown when content type is missing
    if not ct:
        ct = "text/markdown" if _looks_like_markdown(text) else "text/plain"

    # markdown rendering branch
    if ct in ("text/markdown", "text/commonmark", "text/md"):
        try:
            from commonmark import commonmark 
            html = commonmark(text)   
            return mark_safe(html)  
        except Exception:
            # fallback: show raw text in a <pre> block on any error
            return mark_safe(f"<pre>{escape(text)}</pre>")

    # plain text branch: escape html and keep line breaks
    safe = escape(text)         # prevent html injection
    html = linebreaksbr(safe)     
    return mark_safe(html)       






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
    entry.rendered = _render_entry(entry)

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



    # check friends function for comments
def _is_friends(viewer: User, owner: User) -> bool:
    if not (viewer and owner):
        return False
    # Mutual follow counts as "friends"
    try:
        return owner.followers.filter(id=viewer.id).exists() and viewer.followers.filter(id=owner.id).exists()
    except Exception:
        return False
    
    # visibility to others
def _can_view_entry(current_user, entry: Entry) -> bool:
    vis = (entry.visibility or "PUBLIC").upper()
    if vis == "PUBLIC" or vis == "UNLISTED":
        return True
    if not current_user or not current_user.is_authenticated:
        return False
    if str(current_user.id) == str(entry.author_id):
        return True
    if vis == "FRIENDS":
        return _is_friends(current_user, entry.author)
    if vis == "PRIVATE":
        return str(current_user.id) == str(entry.author_id)
    return False


def _comment_to_json(c):
    a = c.author
    e = c.entry
    base = a.url.split('/authors/')[0] if a and a.url else ''
    return {
        "type": "comment",
        "id": f"{base}/api/authors/{e.author_id}/entries/{e.id}/comments/{c.id}",
        "entry": f"{base}/api/authors/{e.author_id}/entries/{e.id}",
        "comment": c.comment,
        "contentType": c.content_type or "text/plain",
        "published": c.created.isoformat(),
        "author": {
            "type": "author",
            "id": a.url if a else "",
            "host": f"{base}api/" if base else "",
            "displayName": a.username if a else "",
            "web": f"/authors/{a.id}" if a else "",
            "github": a.github if a else "",
            "profileImage": a.profile_picture if a else "",
        },
    }

@csrf_exempt
@require_http_methods(["GET", "POST"])
def comments_list_create(request, author_id, entry_id):
    """
    GET  /api/authors/<author_id>/entries/<entry_id>/comments
    POST /api/authors/<author_id>/entries/<entry_id>/comments
    """
    entry = get_object_or_404(Entry, id=entry_id, author_id=author_id, is_deleted=False)

    # visibility guard (public/unlisted ok; friends/private need auth/relationship)
    if not _can_view_entry(request.user, entry):
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
        items = [_comment_to_json(c) for c in qs[start:end]]

        base = entry.author.url.split('/authors/')[0] if entry.author and entry.author.url else ''
        return JsonResponse({
            "type": "comments",
            "id": f"{base}/api/authors/{author_id}/entries/{entry_id}/comments",
            "page_number": page,
            "size": size,
            "count": qs.count(),
            "src": items
        }, status=200)

    # POST: create a comment (must be logged in)
    if not request.user.is_authenticated:
        return HttpResponseForbidden("login required")

    data = _json_from_request(request)
    text = (data.get("comment") or "").strip()
    if not text:
        return JsonResponse({"error": "comment text is required"}, status=400)
    ctype = (data.get("contentType") or "text/plain").strip() or "text/plain"

    c = Comment.objects.create(entry=entry, author=request.user, comment=text, content_type=ctype)
    return JsonResponse(_comment_to_json(c), status=201)

@csrf_exempt
@require_http_methods(["GET", "POST", "DELETE"])
def entry_likes(request, author_id, entry_id):
    """
    GET     /api/authors/<author_id>/entries/<entry_id>/likes
    POST    /api/authors/<author_id>/entries/<entry_id>/likes   (like)
    DELETE  /api/authors/<author_id>/entries/<entry_id>/likes   (unlike)
    """
    entry = get_object_or_404(Entry, id=entry_id, author_id=author_id, is_deleted=False)
    if not _can_view_entry(request.user, entry):
        return HttpResponseForbidden("no access")

    if request.method == "GET":
        data = [{
            "type": "author",
            "id": like.user.url,
            "displayName": like.user.username,
            "web": f"/authors/{like.user.id}",
        } for like in entry.likes.select_related("user").all()]
        return JsonResponse({"type": "likes", "count": len(data), "src": data}, status=200)

    if not request.user.is_authenticated:
        return HttpResponseForbidden("login required")

    if request.method == "POST":
        EntryLike.objects.get_or_create(user=request.user, entry=entry)
        return JsonResponse({"ok": True}, status=201)

    # DELETE
    EntryLike.objects.filter(user=request.user, entry=entry).delete()
    return JsonResponse({"ok": True}, status=200)

@csrf_exempt
@require_http_methods(["GET", "POST", "DELETE"])
def comment_likes(request, author_id, entry_id, comment_id):
    """
    GET     /api/authors/<author_id>/entries/<entry_id>/comments/<comment_id>/likes
    POST    /api/authors/<author_id>/entries/<entry_id>/comments/<comment_id>/likes
    DELETE  /api/authors/<author_id>/entries/<entry_id>/comments/<comment_id>/likes
    """
    entry = get_object_or_404(Entry, id=entry_id, author_id=author_id, is_deleted=False)
    if not _can_view_entry(request.user, entry):
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