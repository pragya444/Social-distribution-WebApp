from django.shortcuts import get_object_or_404, redirect
from django.http import JsonResponse, HttpResponseForbidden
from django.contrib.auth import get_user_model
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.renderers import TemplateHTMLRenderer, JSONRenderer
from rest_framework.response import Response
from rest_framework.authentication import SessionAuthentication
import urllib.parse
from api.models import Follow  
from api.utils import helpers
from django.conf import settings          
import logging                           
import requests   
import json
import urllib.request
from django.views.decorators.csrf import csrf_exempt  
from requests.auth import HTTPBasicAuth
import os

from api.serializers import (
    FollowRequestSerializer,
    FollowersSerializer,
    FollowingSerializer,
    AuthorSerializer,
)


import logging
import requests
from urllib.parse import urlparse, urlunparse

log = logging.getLogger(__name__)

User = get_user_model()



# helper function
def is_local_user(user):
    """
    Return True if this user belongs to *our* node,
    by comparing their host to our LOCAL_API_BASE setting.
    """
    local_base = getattr(settings, "LOCAL_API_BASE", "").rstrip("/")  # e.g. "http://127.0.0.1:8000/api"
    user_host = (getattr(user, "host", "") or "").rstrip("/")
    return local_base and user_host == local_base


def build_inbox_url(author_url: str) -> str:
    """
    Canonical author URL → their inbox URL with a trailing slash.
    Example:
      https://peer.herokuapp.com/api/authors/<uuid>  ->  .../inbox/
    """
    u = urlparse(author_url or "")
    scheme = u.scheme or "http"
    path = u.path.rstrip("/") + "/inbox/"
    return urlunparse((scheme, u.netloc, path, "", "", ""))

def _remote_basic_auth_for(url: str):
    netloc = urlparse(url or "").netloc
    # Try settings-based mapping
    # user = os.getenv("REMOTE_NODE_B_USER") if os.getenv("REMOTE_NODE_B_HOST") == netloc else None
    # pwd  = os.getenv("REMOTE_NODE_B_PASS") if os.getenv("REMOTE_NODE_B_HOST") == netloc else None

    # if user and pwd:
    #     return HTTPBasicAuth(user, pwd)

    # Optional: resolve from Node model if you have one
    try:
        from api.models import Node  # if exists
        node = Node.objects.filter(host__icontains=netloc).first()
        if node and node.username and node.password:
            return HTTPBasicAuth(node.username, node.password)
    except Exception:
        print("No Node model available for auth lookup in followViews.py.")

    return None

def send_follow_to_remote(actor, target, request):
    actor_data  = AuthorSerializer(actor,  context={"request": request}).data
    object_data = AuthorSerializer(target, context={"request": request}).data
    payload = {
        "type": "follow",
        "summary": f"{actor_data.get('displayName', actor.username)} wants to follow "
                   f"{object_data.get('displayName', target.username)}",
        "actor":  {**actor_data,  "type": "author"},
        "object": {**object_data, "type": "author"},
    }
    inbox_url = build_inbox_url(target.url)
    auth = _remote_basic_auth_for(target.url)

    try:
        r = requests.post(
            inbox_url, json=payload,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            auth=auth, timeout=10, allow_redirects=False
        )
        # If their server still redirects, re-POST to the Location so we keep POST (not GET)
        if r.is_redirect and r.headers.get("Location"):
            r = requests.post(
                r.headers["Location"], json=payload,
                headers={"Content-Type": "application/json", "Accept": "application/json"},
                auth=auth, timeout=10, allow_redirects=False
            )
        #if r.status_code not in (200, 201, 202, 204):
            #log.warning("Remote inbox %s returned %s: %.200s", inbox_url, r.status_code, r.text)
    except Exception as e:
        log.exception("Failed to post follow to %s: %s", inbox_url, e)




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

#         if is_local_user(target):
#             # local → just create PENDING and redirect (your existing logic    

#             fr, created = Follow.objects.get_or_create(
#                 follower=request.user, followee=target,
#                 defaults={"status": Follow.Status.PENDING}
#            )
#             if not created and fr.status == Follow.Status.REJECTED:
#                 fr.status = Follow.Status.PENDING
#                 fr.save(update_fields=["status"])

#             return redirect("profile", author_id=target.id)
#         # REMOTE target → create/refresh local PENDING, then send to remote inbox
#         follow, created = Follow.objects.get_or_create(
#             follower=request.user,
#             followee=target,
#             defaults={"status": Follow.Status.PENDING},
#         )
#         if not created and follow.status == Follow.Status.REJECTED:
#             follow.status = Follow.Status.PENDING
#             follow.save(update_fields=["status"])

#         # Fire-and-forget to remote inbox (handled by helper)
#         send_follow_to_remote(actor=request.user, target=target, request=request)

#         return redirect("profile", author_id=target.id)    



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

        # Create/refresh local PENDING
        follow, created = Follow.objects.get_or_create(
            follower=request.user,
            followee=target,
            defaults={"status": Follow.Status.PENDING}
        )
        if not created and follow.status == Follow.Status.REJECTED:
            follow.status = Follow.Status.PENDING
            follow.save(update_fields=["status"])

        # If remote, send to their inbox
        if not is_local_user(target):
            send_follow_to_remote(actor=request.user, target=target, request=request)

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
        
        # NEW: Notify remote node if the follower is remote
        if not is_local_user(fr.follower):
            try:
                self._send_approval_to_remote(fr, request)
            except Exception as e:
                log.warning(f"Failed to notify remote node of approval: {e}")
        
        return redirect("follow-requests-page", author_id=author_id)
    
    def _send_approval_to_remote(self, follow, request):
        """
        Send the approved follow relationship to the remote follower's inbox.
        This updates their following list on their node.
        """
        from api.serializers import AuthorSerializer
        
        actor_data = AuthorSerializer(follow.follower, context={"request": request}).data
        object_data = AuthorSerializer(follow.followee, context={"request": request}).data
        
        payload = {
            "type": "follow",
            "summary": f"{object_data.get('displayName', follow.followee.username)} accepted your follow request",
            "actor": {**actor_data, "type": "author"},
            "object": {**object_data, "type": "author"},
            "approved": True  # Add this field to indicate approval
        }
        
        inbox_url = build_inbox_url(follow.follower.url)
        auth = _remote_basic_auth_for(follow.follower.url)
        
        try:
            r = requests.post(
                inbox_url, 
                json=payload,
                headers={"Content-Type": "application/json", "Accept": "application/json"},
                auth=auth, 
                timeout=10, 
                allow_redirects=False
            )
            #if r.status_code not in (200, 201, 202, 204): UNCOMMENT LATER
                #log.warning(f"Remote inbox {inbox_url} returned {r.status_code}: {r.text[:200]}")
        except Exception as e:
            log.exception(f"Failed to post approval to {inbox_url}: {e}")




class DenyFollowRequestView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [SessionAuthentication]

    def post(self, request, author_id, follower_id):
        if str(request.user.id) != str(author_id):
            return HttpResponseForbidden("Not your account")

        Follow.objects.filter(follower_id=follower_id, followee=request.user).delete()
        return redirect("follow-requests-page", author_id=author_id)




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

        serializer = FollowRequestSerializer(pendings, many=True, context={"request": request})
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

        serializer = FollowRequestSerializer(follow, context={"request": request})
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

        # JSON API 
        serializer = FollowersSerializer(
            {"type": "followers", "followers": followers},
            context={"request": request},
        )
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

        # JSON API
        serializer = FollowingSerializer(
            {"type": "following","following": following},
            context={"request": request},
        )
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






class FollowerDetailView(APIView):

    permission_classes = [IsAuthenticated]
    renderer_classes = [JSONRenderer]

    def _resolve_local_author(self, author_id, request):
        
        author = get_object_or_404(User, id=author_id)
        # Current user must be this author for PUT/DELETE
        return author

    def _resolve_foreign_user(self, foreign_author_fqid):
        # Decode percent-encoded FQID
        decoded = urllib.parse.unquote(foreign_author_fqid)
        cleaned = decoded.rstrip("/")
        return get_object_or_404(User, url__in=[cleaned, cleaned + "/"], )

    def get(self, request, author_id, foreign_author_fqid):
        owner = self._resolve_local_author(author_id, request)
        foreign_user = self._resolve_foreign_user(foreign_author_fqid)

        # Check if foreign_user is an APPROVED follower
        is_follower = Follow.objects.filter(
            follower=foreign_user,
            followee=owner,
            status=Follow.Status.APPROVED,
        ).exists()

        if not is_follower:
            return Response({"detail": "Not a follower"}, status=404)

        data = AuthorSerializer(foreign_user, context={"request": request}).data
        return Response(data, status=200)

    def put(self, request, author_id, foreign_author_fqid):
        owner = self._resolve_local_author(author_id, request)

        # Only the owner can accept their own followers
        if str(request.user.id) != str(owner.id):
            return Response({"detail": "Not authorized"}, status=403)

        foreign_user = self._resolve_foreign_user(foreign_author_fqid)

        # Accept only if there's a pending request
        follow = Follow.objects.filter(
            follower=foreign_user,
            followee=owner,
            status=Follow.Status.PENDING,
        ).first()

        if not follow:
            return Response({"detail": "No matching follow request"}, status=404)

        follow.status = Follow.Status.APPROVED
        follow.save(update_fields=["status"])

        data = AuthorSerializer(foreign_user, context={"request": request}).data
        return Response(data, status=200)

    def delete(self, request, author_id, foreign_author_fqid):
        owner = self._resolve_local_author(author_id, request)

        # Only the owner can remove/deny
        if str(request.user.id) != str(owner.id):
            return Response({"detail": "Not authorized"}, status=403)

        foreign_user = self._resolve_foreign_user(foreign_author_fqid)

        follow = Follow.objects.filter(
            follower=foreign_user,
            followee=owner,
        ).first()

        if not follow:
            return Response({"detail": "No matching follower"}, status=404)
        follow.delete()
        return Response(status=204)



class FollowingDetailView(APIView):
    """

    local author is the follower
    FOREIGN_AUTHOR_FQID is the author they want to follow/unfollow/check.
    """
    permission_classes = [IsAuthenticated]
    renderer_classes = [JSONRenderer]

    def _resolve_local_actor(self, author_id):
        # Local author who is doing the following
        return get_object_or_404(User, id=author_id)

    def _resolve_foreign_user(self, foreign_author_fqid):
        # Percent-decode the FQID and look up by User.url
        decoded = urllib.parse.unquote(foreign_author_fqid)
        cleaned = decoded.rstrip("/")
        return get_object_or_404(User, url__in=[cleaned, cleaned + "/"])

    def get(self, request, author_id, foreign_author_fqid):
        """
        GET: check if AUTHOR_SERIAL is following FOREIGN_AUTHOR_FQID.
        """
        actor = self._resolve_local_actor(author_id)
        foreign_user = self._resolve_foreign_user(foreign_author_fqid)

        is_following = Follow.objects.filter(
            follower=actor,
            followee=foreign_user,
            status=Follow.Status.APPROVED,
        ).exists()

        if not is_following:
            return Response({"detail": "Not following"}, status=404)

        data = AuthorSerializer(foreign_user, context={"request": request}).data
        return Response(data, status=200)

    def put(self, request, author_id, foreign_author_fqid):
        """
        AUTHOR_SERIAL generates a follow request for FOREIGN_AUTHOR_FQID.
      
        If foreign author is on a different node, author's node should generate a follow request and POST it to foreign author's inbox API endpoint.
        """
        actor = self._resolve_local_actor(author_id)

        # Only the logged-in user can change their own following list
        if str(request.user.id) != str(actor.id):
            return Response({"detail": "Not authorized"}, status=403)

        foreign_user = self._resolve_foreign_user(foreign_author_fqid)

        follow, created = Follow.objects.get_or_create(
            follower=actor,
            followee=foreign_user,
            defaults={"status": Follow.Status.PENDING},
        )

        if not created and follow.status == Follow.Status.APPROVED:
            # Already following
            data = AuthorSerializer(foreign_user, context={"request": request}).data
            return Response(data, status=200)

        if not created and follow.status == Follow.Status.PENDING:
            # Follow request already pending
            data = AuthorSerializer(foreign_user, context={"request": request}).data
            return Response(data, status=200)

        # send follow object to foreign_user's inbox
        try:
            # Build actor & object author objects as in the spec
            actor_data = AuthorSerializer(actor, context={"request": request}).data
            object_data = AuthorSerializer(foreign_user, context={"request": request}).data

            follow_payload = {
                "type": "follow",
                "summary": f"{actor_data.get('displayName', actor.username)} wants to follow {object_data.get('displayName', foreign_user.username)}",
                "actor": actor_data,
                "object": object_data,
            }

            # send follow object to foreign_user's inbox
            inbox_url = foreign_user.url.rstrip("/") + "/inbox"

            req = urllib.request.Request(
                inbox_url,
                data=json.dumps(follow_payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            # if it fails, we just log or ignore for now
            try:
                urllib.request.urlopen(req, timeout=5)
            except Exception:
                
                pass

        except Exception:
            # If anything goes wrong building/sending the remote request,
            # we still consider the local Follow row created.
            pass

        data = AuthorSerializer(foreign_user, context={"request": request}).data
        return Response(data, status=200)             






        # if not created and follow.status == Follow.Status.APPROVED:
        #     # Already following
        #     data = AuthorSerializer(foreign_user, context={"request": request}).data
        #     return Response(data, status=200)

        # if not created and follow.status == Follow.Status.PENDING:
        #     # Follow request already pending
        #     data = AuthorSerializer(foreign_user, context={"request": request}).data
        #     return Response(data, status=200)

        # # TODO send to remote inbox here
        # # build the "follow" object
        # # POST it to foreign_user.inbox URL

        # data = AuthorSerializer(foreign_user, context={"request": request}).data
        # return Response(data, status=200)

    def delete(self, request, author_id, foreign_author_fqid):
        """
        DELETE: 
        Removes the Follow row, whether PENDING or APPROVED.
        """
        actor = self._resolve_local_actor(author_id)

        if str(request.user.id) != str(actor.id):
            return Response({"detail": "Not authorized"}, status=403)

        foreign_user = self._resolve_foreign_user(foreign_author_fqid)

        follow = Follow.objects.filter(
            follower=actor,
            followee=foreign_user,
        ).first()

        if not follow:
            return Response({"detail": "No follow relationship"}, status=404)

        follow.delete()
        return Response(status=204)

