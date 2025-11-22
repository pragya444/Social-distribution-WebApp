from django.shortcuts import get_object_or_404, redirect, render
from django.http import JsonResponse, HttpResponseNotAllowed, HttpResponseForbidden, HttpResponse, Http404
from django.core.paginator import Paginator
from rest_framework.renderers import TemplateHTMLRenderer, JSONRenderer
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.authentication import SessionAuthentication, BasicAuthentication
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from django.conf import settings
from ..serializers import EntrySerializer
from ..models import Entry, EntryLike, Comment, CommentLike, User, Node, Follow
from ..utils import helpers, images
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.utils.timezone import is_naive
from django.utils.timezone import make_aware
from urllib.parse import urljoin, urlparse
from api.utils import helpers
import base64
import requests
from requests.auth import HTTPBasicAuth


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
    # First check if the current user has permission to view this entry
    if not helpers.can_view_entry(request.user, entry):
        return HttpResponseForbidden("no access to this image")

    # Normalize / read the content_type, default to empty string if missing
    ct = (getattr(entry, "content_type", "") or "").lower()

    # Only handle entries where content_type looks like "image/*;base64"
    if not (ct.startswith("image/") and ct.endswith(";base64")):
        # If it's not an image entry, respond with 404 to match the spec
        raise Http404("not an image entry")

    try:
        # Decode the base64-encoded image data from entry.content
        raw_bytes = base64.b64decode(entry.content or "")
    except Exception:
        # If decoding fails, treat it as invalid image data and return 404
        raise Http404("invalid image data")

    # Remove the ";base64" suffix to get the real MIME type, e.g. "image/png"
    mime_type = ct.replace(";base64", "")

    # Return the raw bytes as an HTTP response with the correct content type
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
        entry_data = entry_obj(request, updated_entry)
        connected_nodes = Node.objects.filter(is_connected=True)
        if connected_nodes.exists():
            for node in connected_nodes:
                send_entry_to_node(node, entry_data, request)

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
        entry_data = entry_obj(request, entry)
        entry_data['visibility'] = 'DELETED'  # Indicate deletion in the data sent to nodes
        connected_nodes = Node.objects.filter(is_connected=True)
        if connected_nodes.exists():
            for node in connected_nodes:
                send_entry_to_node(node, entry_data, request)

        # Redirect on delete for browser
        if isinstance(request.accepted_renderer, TemplateHTMLRenderer):
            return redirect('author-all-entries', author_id=author_id)
        
        return Response({"msg": "Entry deleted successfully."}, status=204)




@method_decorator(csrf_exempt, name='dispatch')
class EntryView(APIView):
    """
    GET [local, remote] get the recent entries from author AUTHOR_SERIAL (paginated)
    POST [local] create a new entry but generate a new ID
    
    URL: ://service/api/authors/{AUTHOR_SERIAL}/entries/
    
    GET Returns:
        - 200: Entries object with pagination
        {
            "type": "entries",
            "page_number": 1,
            "size": 10,
            "count": 100,
            "src": [/* array of entry objects */]
        }
    
    GET Authentication:
        - Not authenticated: only public entries
        - Authenticated locally as author: all entries
        - Authenticated locally as follower of author: public + unlisted entries
        - Authenticated locally as friend of author: all entries
    
    POST Returns:
        - 201: Entry object (created)
        - 400: Invalid data
        - 403: Not authorized (must be the author)
    
    POST Authentication:
        - Must be authenticated locally as the author
    
    When first creating the entry, there's no likes or comments since it doesn't exist yet.
    """
    renderer_classes = [JSONRenderer, TemplateHTMLRenderer]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    authentication_classes = [BasicAuthentication, SessionAuthentication]

    def get(self, request, author_id):
        page_num = int(request.GET.get('page', 1))
        page_size = int(request.GET.get('size', 10))
        
        author = get_object_or_404(User, id=author_id)
        
        # Determine what entries the requester can see
        if not request.user.is_authenticated:
            # Not authenticated: only public entries
            qs = Entry.objects.filter(
                author_id=author_id, 
                visibility="PUBLIC", 
                is_deleted=False
            ).order_by('-updated')
        elif str(request.user.id) == str(author_id):
            # Authenticated as author: all entries
            qs = Entry.objects.filter(
                author_id=author_id, 
                is_deleted=False
            ).order_by('-updated')
        else:
            # Authenticated as someone else: check relationship using helpers
            friends = helpers.friends_of(request.user)
            is_friend = author in friends
            
            followers = helpers.users_i_follow(request.user)
            is_follower = author in followers
            
            if is_friend:
                # Friend: all entries
                qs = Entry.objects.filter(
                    author_id=author_id,
                    is_deleted=False
                ).order_by('-updated')
            elif is_follower:
                # Follower: public + unlisted entries
                qs = Entry.objects.filter(
                    author_id=author_id,
                    visibility__in=["PUBLIC", "UNLISTED"],
                    is_deleted=False
                ).order_by('-updated')
            else:
                # Not following: only public entries
                qs = Entry.objects.filter(
                    author_id=author_id,
                    visibility="PUBLIC",
                    is_deleted=False
                ).order_by('-updated')
        
        paginator = Paginator(qs, page_size)
        page_obj = paginator.get_page(page_num)
        
        # For HTML rendering, set user_liked attribute
        if isinstance(request.accepted_renderer, TemplateHTMLRenderer):
            # Get liked entry IDs for the current user
            liked_ids = set()
            if request.user.is_authenticated and page_obj.object_list:
                liked_ids = set(EntryLike.objects.filter(
                    user=request.user, 
                    entry__in=page_obj.object_list
                ).values_list('entry_id', flat=True))
            
            # Set user_liked and render content for each entry
            for e in page_obj.object_list:
                e.user_liked = e.id in liked_ids
                e.rendered = helpers.render_entry(e)
            
            return Response({
                'author': author,
                'entries': page_obj.object_list,
                'tab': 'all',
            }, template_name='author_all_entries.html')
        
        # JSON response
        data = entries_page_obj(request, page_obj.object_list, page_obj, page_size)
        return Response(data, status=200)
    
    def post(self, request, author_id):
        if str(request.user.id) != str(author_id):
            return Response({"error": "Unauthorized"}, status=403)
        
        payload = create_payload(request)
        payload['author'] = author_id
        serializer = EntrySerializer(data=payload, context={'request': request})
        
        if not serializer.is_valid():
            if isinstance(request.accepted_renderer, TemplateHTMLRenderer):
                return Response(
                    {"errors": serializer.errors, "author_id": author_id},
                    template_name="entry/entry_create.html",
                    status=400
                )
            return Response({"errors": serializer.errors}, status=400)

        entry = serializer.save()
        entry_data = entry_obj(request, entry)
        connected_nodes = Node.objects.filter(is_connected=True)
        if connected_nodes.exists():
            for node in connected_nodes:
                send_entry_to_node(node, entry_data, request)
        
        # Redirect for browser/HTML requests
        if isinstance(request.accepted_renderer, TemplateHTMLRenderer):
            return redirect('author-all-entries', author_id=author_id)
        
        # JSON response for API clients
        return Response(entry_data, status=201)
        



class EntryByFQIDView(APIView):
    """
    GET [local] get the public entry whose URL is ENTRY_FQID
    
    URL: ://service/api/entries/{ENTRY_FQID}
    
    Example: GET /api/entries/http://localhost:8000/api/authors/123/entries/456/
    
    The ENTRY_FQID is the full URL of the entry (the 'url' field in the entry object).
    
    Returns:
        - 200: Entry object
        - 400: Invalid FQID format
        - 403: Not authorized to view friends-only entry
        - 404: Entry not found
    
    Authentication:
        - Public/unlisted entries: no authentication required
        - Friends-only entries: must be authenticated
    """
    renderer_classes = [JSONRenderer]
    parser_classes = [JSONParser]

    def get(self, request, entry_fqid):
        try:
            # The FQID might have a trailing slash or not, normalize it
            fqid_normalized = entry_fqid.rstrip('/')
            
            # Try exact match first on the url field
            entry = Entry.objects.filter(
                url=entry_fqid, 
                is_deleted=False
            ).first()
            
            # If not found, try without trailing slash
            if not entry:
                entry = Entry.objects.filter(
                    url=fqid_normalized,
                    is_deleted=False
                ).first()
            
            # If still not found, try with trailing slash added
            if not entry:
                entry = Entry.objects.filter(
                    url=fqid_normalized + '/',
                    is_deleted=False
                ).first()
            
            if not entry:
                return Response(
                    {"error": "Entry not found with the given FQID"},
                    status=404
                )
                
        except Exception as e:
            return Response(
                {"error": f"Invalid FQID: {str(e)}"},
                status=400
            )
        
        # Check visibility permissions
        if entry.visibility not in ['PUBLIC', 'UNLISTED']:
            if not request.user.is_authenticated:
                return Response(
                    {"error": "Authentication required for friends-only entries"},
                    status=401
                )
            if not helpers.can_view_entry(request.user, entry):
                return Response(
                    {"error": "Not authorized to view this entry"},
                    status=403
                )
        
        return Response(entry_obj(request, entry), status=200)
    


def normalize_host(host):
    if not host:
        return ""
    parsed = urlparse(host)
    return f"{parsed.scheme}://{parsed.netloc}/"

def node_has_follower_from_this_node(node):
    all_follows = Follow.objects.filter(status=Follow.Status.APPROVED)

    for follow in all_follows:
        follower_host = normalize_host(follow.follower.host)
        node_host = normalize_host(node.host)
        if follower_host == node_host:
            return True
    return False


def send_entry_to_node(node, entry_data, request):
    auth = HTTPBasicAuth(node.username, node.password)

    # user = request.user
    # followers = Follow.objects.filter(followee=user, status=Follow.Status.APPROVED)

    # remote_followers = [f for f in followers if normalize_host(f.follower.host) == normalize_host(node.host)]
    
    if not node_has_follower_from_this_node(node):
        print(f"No followers on node {node.host}, skipping send.")
        return

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    base = node.host.rstrip('/')

    try:
        authors_response = requests.get(
            url=f"{base}/api/authors/",
            headers=headers,
            auth=auth,
            timeout=10,
        )
        if authors_response.status_code != 200:
            print(f"Failed to fetch authors from node {node.host}: {authors_response.status_code}")
            return
        
        data = authors_response.json()
        authors = data.get("authors", [])

        target_author = None
        for author in authors:
            if normalize_host(author.get("id", "")) == node.host:
                target_author = author
                break

        # for author in authors:
        author_id = target_author.get("id")
        if not author_id:
            print(f"No matching author found on node {node.host} for broadcasting entry.")
            return
        inbox_url = f"{author_id.rstrip('/')}/inbox/"

        response = requests.post(
            url=inbox_url,
            json=entry_data,
            headers=headers,
            auth=auth,
            timeout=10,
        )
        if response.status_code not in [200, 201]:
            print(f"Failed to send entry to {inbox_url}: {response.status_code}")
        else:
            print(f"Successfully sent entry to {inbox_url}")

        # for follower in remote_followers:
        #     remote_user = follower.follower
        #     author_fqid = remote_user.fqid
        #     if not author_fqid:
        #         print(f"Remote user {remote_user.id} has no FQID, skipping.")

        #     inbox_url = f"{author_fqid.rstrip('/')}/inbox/"

        #     response = requests.post(
        #         url=inbox_url,
        #         json=entry_data,
        #         headers=headers,
        #         auth=auth,
        #         timeout=10,
        #     )
        #     if response.status_code not in [200, 201]:
        #         print(f"Failed to send entry to {inbox_url}: {response.status_code}")
        #     else:
        #         print(f"Successfully sent entry to {inbox_url}")

    except Exception as e:
        print(f"Error sending entry to node {node.host}: {str(e)}")

    
