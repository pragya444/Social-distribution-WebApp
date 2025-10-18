from django.shortcuts import render, get_object_or_404, redirect
from .models import Entry, User
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



@login_required
def author_stream(request, author_id):
    # self stream
    if str(request.user.id) == str(author_id):
        entries = (
            Entry.objects
            .filter(author_id=author_id, is_deleted=False) # entries that hasnt been deleted
            .order_by('-updated')
        )
        
    # attach pre-rendered html for template
    for e in entries:
        e.rendered = _render_entry(e)  # add a transient field for template use


    # render with author id and a markdown availability flag
    return render(request, 'author_all_entries.html', {
        'author_id': author_id,
        'entries': entries,
    })

def show_public_entries(request ):
    #TODO: As an author, I want my stream page to show me all the public entries my node knows about, so I can find new people to follow.

    pass


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
    # TODO: Handle image being too large error
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



@require_POST
@login_required
@csrf_protect
def entry_delete(request, author_id, entry_id):
    # hard delete only， make sure the caller is the owner
    if str(request.user.id) != str(author_id):
        return HttpResponseForbidden("only the author can delete this entry.")

    # fetch the entry (no soft-delete filter here since we're hard-deleting anyway
    e = get_object_or_404(Entry, id=entry_id, author_id=author_id)

    # remove it from the database for real
    e.delete()

    # bounce back to the author's stream
    return redirect('author-all-entries', author_id=author_id)



'''
1. Entry delettion: Keep in database, but not show in streams or api results.
'''