from django.shortcuts import get_object_or_404, redirect, render
from django.http import JsonResponse, HttpResponseNotAllowed, HttpResponseForbidden, HttpResponse, Http404
from django.core.paginator import Paginator
from rest_framework.renderers import TemplateHTMLRenderer, JSONRenderer
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.authentication import SessionAuthentication
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from django.conf import settings
from ..serializers import EntrySerializer
from ..models import Entry, EntryLike, Comment, CommentLike  
from ..utils import helpers, images
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.utils.timezone import is_naive
from django.utils.timezone import make_aware
from urllib.parse import urljoin
from api.utils import helpers
import base64


# Developed with assistance from ChatGPT (GPT-5), November 2025

def _site_root(request):
    # Ensures trailing slash
    root = getattr(settings, "SITE_URL", None)
    if not root:
        root = request.build_absolute_uri("/").rstrip("/") + "/"
    if not root.endswith("/"):
        root += "/"
    return root

def build_api_url(request, path):
    return urljoin(_site_root(request), path.lstrip("/"))

def build_web_url(request, path):
    return build_api_url(request, path)

def author_obj(request, author):
    base_api = f"api/authors/{author.id}"
    return {
        "type": "author",
        "id": build_api_url(request, base_api),
        "host": build_api_url(request, "api/"),
        "displayName": author.name,
        "github": author.github or "",
        "profileImage": author.profile_picture or "",
        "web": build_web_url(request, f"authors/{author.id}"),
    }

def like_page_obj(request, entry, page_number=1, size=50):
    qs = EntryLike.objects.filter(entry=entry).order_by("-created")[:size]  # changed from -published
    likes = []
    for l in qs:
        likes.append({
            "type": "like",
            "author": author_obj(request, l.user),
            "published": l.published.isoformat(),
            "id": build_api_url(request, f"api/authors/{l.user.id}/liked/{l.id}"),
            "object": build_api_url(request, f"api/authors/{entry.author_id}/entries/{entry.id}")
        })
    return {
        "type": "likes",
        "id": build_api_url(request, f"api/authors/{entry.author_id}/entries/{entry.id}/likes"),
        "web": build_web_url(request, f"authors/{entry.author_id}/entries/{entry.id}/likes"),
        "page_number": page_number,
        "size": size,
        "count": EntryLike.objects.filter(entry=entry).count(),
        "src": likes,
    }

def comment_page_obj(request, entry, page_number=1, size=5):
    qs = Comment.objects.filter(entry=entry).order_by("-created")[:size]  
    comments = []
    for c in qs:
        comments.append({
            "type": "comment",
            "author": author_obj(request, c.author),
            "comment": c.comment,
            "contentType": c.content_type,
            "published": c.published.isoformat(),
            "id": build_api_url(request, f"api/authors/{c.author.id}/commented/{c.id}"),
            "entry": build_api_url(request, f"api/authors/{entry.author_id}/entries/{entry.id}"),
            "web": build_web_url(request, f"authors/{entry.author_id}/entries/{entry.id}"),
            "likes": {
                "type": "likes",
                "id": build_api_url(request, f"api/authors/{c.author.id}/commented/{c.id}/likes"),
                "web": build_web_url(request, f"authors/{c.author.id}/comments/{c.id}/likes"),
                "page_number": 1,
                "size": 50,
                "count": CommentLike.objects.filter(comment=c).count(),
                "src": [],
            }
        })
    return {
        "type": "comments",
        "id": build_api_url(request, f"api/authors/{entry.author_id}/entries/{entry.id}/comments"),
        "web": build_web_url(request, f"authors/{entry.author_id}/entries/{entry.id}/comments"),
        "page_number": page_number,
        "size": size,
        "count": Comment.objects.filter(entry=entry).count(),
        "src": comments,
    }

def entry_obj(request, entry):
    published = entry.published
    if is_naive(published):
        published = make_aware(published)
    return {
        "type": "entry",
        "title": entry.title,
        "id": build_api_url(request, f"api/authors/{entry.author_id}/entries/{entry.id}"),
        "web": build_web_url(request, f"authors/{entry.author_id}/entries/{entry.id}"),
        "description": entry.description or "",
        "contentType": entry.content_type,
        "content": entry.content,
        "author": author_obj(request, entry.author),
        "comments": comment_page_obj(request, entry),
        "likes": like_page_obj(request, entry),
        "published": published.isoformat(),
        "visibility": entry.visibility,
    }

def entries_page_obj(request, entries, page_obj, size):
    return {
        "type": "entries",
        "page_number": page_obj.number,
        "size": size,
        "count": page_obj.paginator.count,
        "src": [entry_obj(request, e) for e in entries],
    }


def _serve_entry_image(request, entry):
    """
    Serve an Entry whose content is an image (base64) as a binary HTTP response.
    """
    # 1) Permission check: does the current user have access to this entry
    #    (PUBLIC / FRIENDS etc. logic is handled in helpers)
    if not helpers.can_view_entry(request.user, entry):
        return Response({"error": "no access to this image"}, status=403)

    # 2) Ensure this is a base64-encoded image type, e.g. image/png;base64
    ct = (getattr(entry, "content_type", "") or "").lower()
    if not (ct.startswith("image/") and ct.endswith(";base64")):
        raise Http404("not an image entry")

    # 3) Decode the base64 string stored in the content field into raw bytes
    try:
        raw_bytes = base64.b64decode(entry.content or "")
    except Exception:
        raise Http404("invalid image data")

    # 4) Strip the trailing ;base64 to get the actual MIME type,
    #    then return a binary image response
    mime_type = ct.replace(";base64", "")
    return HttpResponse(raw_bytes, content_type=mime_type)



def create_payload(request):
    data = request.data
    payload = {}
    
    title = data.get('title')
    description = data.get('description', '')
    content_type = data.get('contentType') or data.get('content_type')
    visibility = data.get('visibility')
    content = data.get('content', '')
    
    if title:
        payload['title'] = title
    if description:
        payload['description'] = description
    if visibility:
        payload['visibility'] = visibility

    # Use 'contentType' key for serializer (not 'content_type')
    if content_type:
        payload['contentType'] = content_type  # Changed from 'content_type'
    
    # handle images
    if content_type in ['image/png;base64', 'image/jpeg;base64', 'application/base64']:
        img_file = request.FILES.get('image')
        if img_file:
            img_ct, b64_str = images.handle_uploaded_image(img_file)
            payload['contentType'] = img_ct  # Changed from 'content_type'
            payload['content'] = b64_str
        elif content:
            payload['content'] = content
    else:
        # Text content
        if content:
            payload['content'] = content
    
    return payload



class SingleEntryView(APIView):

    # The same view can respond with either JSON or HTML depending on Accept header
    renderer_classes = [JSONRenderer, TemplateHTMLRenderer]

    # Allow JSON body, form-data (for typical forms), and multipart (for file uploads)
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get(self, request, author_id, entry_id):
        """
        GET /authors/<author_id>/entries/<entry_id>/

        - If the client requests HTML: render a "shared entry" page.
        - If the client requests JSON: return serialized entry data.
        """

        # Look up the entry or return 404 if it doesn't exist
        entry = get_object_or_404(
            Entry,
            id=entry_id,
            author_id=author_id,
            is_deleted=False,  # soft-delete flag
        )

        # Only PUBLIC / UNLISTED entries are shareable to everyone.
        # For other visibility types, enforce permission checks.
        if entry.visibility not in ["PUBLIC", "UNLISTED"]:
            # helpers.can_view_entry encapsulates all permission logic
            # (ownership, friends-only, private, etc.)
            if not helpers.can_view_entry(request.user, entry):
                return Response(
                    {"error": "This entry is not shareable."},
                    status=403,
                )

        # If the client wants HTML, render the shared entry page
        if isinstance(request.accepted_renderer, TemplateHTMLRenderer):
            entry.rendered = helpers.render_entry(entry)

            # Default: not liked
            like = False

            # If the user is logged in, check whether they have liked this entry
            if request.user.is_authenticated:
                like = EntryLike.objects.filter(
                    entry=entry,
                    user=request.user,
                ).exists()

            # Render the HTML template with extra context:
            # - entry: the current entry object
            # - author_id: used in the template / links
            # - like: whether the current user has liked this entry
            return Response(
                {
                    "entry": entry,
                    "author_id": author_id,
                    "like": like,
                },
                template_name="entry/entry_shared.html",
            )

        # If the client expects JSON (e.g., a frontend SPA or mobile app),
        # return the serialized representation of this entry.
        # `entry_obj` should be a helper that converts the model to a dict.
        return Response(entry_obj(request, entry), status=200)

    
    
    def put(self, request, author_id, entry_id):
        # Only the owner (author_id) can update this entry
        if not request.user or str(request.user.id) != str(author_id):
            if isinstance(request.accepted_renderer, TemplateHTMLRenderer):
                return HttpResponseForbidden("Only the author can edit this entry.")
            return Response({"error": "Only the author can edit this entry"}, status=403)

        # Fetch the target entry (must not be deleted)
        entry = get_object_or_404(Entry, id=entry_id, author_id=author_id, is_deleted=False)

        # Normalize incoming data (text vs image, contentType, base64, etc.)
        payload = create_payload(request)

        serializer = EntrySerializer(entry, data=payload, partial=True, context={"request": request})

        if not serializer.is_valid():
            # HTML: re-render edit page with errors; JSON: return 400 with errors
            if isinstance(request.accepted_renderer, TemplateHTMLRenderer):
                return Response(
                    {
                        "author_id": author_id,
                        "entry": entry,
                        "errors": serializer.errors,
                        "contentType": getattr(entry, "content_type", "") or "text/markdown",
                    },
                    template_name="entry/entry_edit.html",
                    status=400,
                )
            return Response({"errors": serializer.errors}, status=400)

        updated_entry = serializer.save()

        # HTML: redirect back to entries list; JSON: return updated entry object
        if isinstance(request.accepted_renderer, TemplateHTMLRenderer):
            return redirect("author-all-entries", author_id=author_id)

        return Response(entry_obj(request, updated_entry), status=200)




    def post(self, request, author_id, entry_id):
        method = request.data.get('_method', '').upper()
        if method == 'DELETE':
            return self.delete(request, author_id, entry_id)
        return self.put(request, author_id, entry_id)
    
    
    def delete(self, request, author_id, entry_id):
        if not request.user or str(request.user.id) != str(author_id):
            if isinstance(request.accepted_renderer, TemplateHTMLRenderer):
                return HttpResponseForbidden("Only the author can delete this entry.")
            return Response({"error": "Only the author can delete this entry"}, status=403)

        entry = get_object_or_404(Entry, id=entry_id, author_id=author_id, is_deleted=False)
        entry.is_deleted = True
        entry.save()

        # Redirect on delete for browser
        if isinstance(request.accepted_renderer, TemplateHTMLRenderer):
            return redirect('author-all-entries', author_id=author_id)
        
        return Response({"msg": "Entry deleted successfully."}, status=204)




@method_decorator(csrf_exempt, name='dispatch')
class EntryView(APIView):
    renderer_classes = [JSONRenderer, TemplateHTMLRenderer]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    authentication_classes = [SessionAuthentication] 

    def get(self, request, author_id):
        page_num = int(request.GET.get('page', 1))
        page_size = int(request.GET.get('size', 10))
        
        if str(request.user.id) == str(author_id):
            qs = Entry.objects.filter(author_id=author_id, is_deleted=False).order_by('-updated')
        else:
            qs = Entry.objects.filter(author_id=author_id, visibility="PUBLIC", is_deleted=False).order_by('-updated')
        paginator = Paginator(qs, page_size)
        page_obj = paginator.get_page(page_num)
        data = entries_page_obj(request, page_obj.object_list, page_obj, page_size)

        return Response(data, status=200)
    
    
    def post(self, request, author_id):
        if str(request.user.id) != str(author_id):
            return Response({"error": "Unauthorized"}, status=403)
        
        payload = create_payload(request)
        payload['author'] = author_id
        serializer = EntrySerializer(data=payload, context={'request': request})
        
        if serializer.is_valid():
            entry = serializer.save()
            
            # Redirect for browser/HTML requests
            if isinstance(request.accepted_renderer, TemplateHTMLRenderer):
                return redirect('author-all-entries', author_id=author_id)
            
            # JSON response for API clients
            return Response(entry_obj(request, entry), status=201)
        
        # Handle validation errors
        if isinstance(request.accepted_renderer, TemplateHTMLRenderer):
            return Response(
                {"errors": serializer.errors, "author_id": author_id},
                template_name="entry/entry_create.html",
                status=400
            )
        return Response({"errors": serializer.errors}, status=400)