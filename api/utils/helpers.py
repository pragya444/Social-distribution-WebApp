import json
from ..models import User, Entry, Comment, EntryLike, CommentLike, Follow
from django.utils.html import escape
from django.utils.safestring import mark_safe
from django.template.defaultfilters import linebreaksbr
from django.urls import reverse


def json_from_request(request):
    # parse json body safely, return empty dict on failure
    try:
        raw = request.body.decode('utf-8') or "{}"  # handle empty body
        return json.loads(raw)                      # convert to dict
    except Exception:
        return {}                                   # tolerate bad json


def entry_to_json(e, content_type_hint='text/plain'):
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
        "likes": {
            "type": "likes",
            "id": f"/api/authors/{e.author_id}/entries/{e.id}/likes",
            "page_number": 1, "size": 50,
            "count": e.likes.count(),
            "src": [],
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
    return [u for u in users_i_follow(me) if Follow.are_friends(me, u)]   



def is_friends(viewer: User, owner: User) -> bool:
    if not (viewer and owner):
        return False
    # Mutual follow counts as "friends"
    try:
        return owner.followers.filter(id=viewer.id).exists() and viewer.followers.filter(id=owner.id).exists()
    except Exception:
        return False


def can_view_entry(current_user, entry: Entry) -> bool:
    # normalize whatever is in the DB/form
    vis = (entry.visibility or "PUBLIC").upper()

    if vis in ("PUBLIC", "UNLISTED"):
        return True

    if not current_user or not getattr(current_user, "is_authenticated", False):
        return False

    # owner can always see
    if str(current_user.id) == str(entry.author_id):
        return True

    if vis == "FRIENDS":
        # replace with  actual friend check
        return is_friends(current_user, entry.author)

    if vis == "PRIVATE":
        return str(current_user.id) == str(entry.author_id)

    return False


def comment_to_json(c):
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


def _looks_like_markdown(t: str) -> bool:
    # normalize to empty string when none
    t = t or ""
    # quick heuristics for common markdown tokens
    tokens = ("# ", "**", "* ", "- ", "\n- ", "`", "[", "](", "> ", "\n> ", "___", "---")
    # return true if any token appears in the text
    return any(tok in t for tok in tokens)


def render_entry(entry):
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
