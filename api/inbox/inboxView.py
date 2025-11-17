from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.authentication import BasicAuthentication, SessionAuthentication
from api.serializers import EntrySerializer, FollowRequestSerializer, EntryLikeSerializer, CommentSerializer
from api.models import Entry, EntryLike, Follow, Comment, Nodes
from django.contrib.auth import get_user_model
from django.utils.text import slugify
from django.db.models import F
from django.utils.dateparse import parse_datetime
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
import requests
import pprint
from urllib.parse import urlparse


User = get_user_model()


def get_host_from_object(object_fqid: str) -> str:
    parsed = urlparse(object_fqid)  # parses protocol, host, path, etc.
    return f"{parsed.scheme}://{parsed.netloc}/"



class InboxView(APIView):
    authentication_classes = [BasicAuthentication, SessionAuthentication]
    permission_classes = [AllowAny]

    @method_decorator(csrf_exempt)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

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
            return self.handle_entry(is_local, request, data)

        elif item_type == 'follow':
            actor_obj = data.get("actor") or {}
            object_obj = data.get("object") or {}

            actor_id_fqid = actor_obj.get("id")
            object_id_fqid = object_obj.get("id")

            if not actor_id_fqid or not object_id_fqid:
                return Response({"error": "actor.id and object.id are required for follow"}, status=400)

            # object.id should be the FQID of the *local* author whose inbox this is
        
            cleaned_object = object_id_fqid.rstrip("/")
            cleaned_actor = actor_id_fqid.rstrip("/")

            try:
                # local followee (the author whose inbox we're addressing)
                followee = User.objects.get(url__in=[cleaned_object, cleaned_object + "/"])
            except User.DoesNotExist:
                return Response(
                    {"error": f"Unknown local author for object.id: {object_id_fqid}"},
                    status=404,
                )

            

            try:
                # follower (may be remote or local, but must already exist in our DB as a User with url)
                follower = User.objects.get(url__in=[cleaned_actor, cleaned_actor + "/"])
            except User.DoesNotExist:
                # we require the remote actor
                # to have a User row already.
                return Response(
                    {"error": f"Unknown follower for actor.id: {actor_id_fqid}"},
                    status=404,
                )
            
            # Ensure we have (or create) a local record for the remote follower
            follower = self.get_or_create_remote_user(actor_obj)
            follow, created = Follow.objects.get_or_create(
                follower=follower,
                followee=followee,
                defaults={"status": Follow.Status.PENDING},
            )

            # Represent it back in the standard follow-request shape
            resp_data = FollowRequestSerializer(follow, context={"request": request}).data
            return Response(resp_data, status=201 if created else 200)


            
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
        
    
    # def handle_like(self, request, author, data, is_local):
    #     entry_fqid = data.get('object', '')
    #     remote_host = data.get('remote_host', '')
    #     remote_author_id = data.get('remote_author_id', '')

    #     # print(data)

    #     try:
    #         entry = Entry.objects.get(url=entry_fqid)
    #     except Entry.DoesNotExist:
    #         return Response({"error": "Entry not found"}, status=404)
        
    #     if is_local:
    #         user = request.user
    #     else:
    #         user_data = data.get('author', {})
    #         if not user_data.get('id'):
    #             return Response({"error": "Author data missing in like"}, status=400)

    #         user = self.get_or_create_remote_user(user_data)

    #     like_qs = EntryLike.objects.filter(user=user, entry=entry)

    #     if like_qs.exists():
    #         delete_like = EntryLikeSerializer(like_qs.first(), context={'request': request})
    #         if is_local and remote_host and remote_author_id:
    #             self.send_like_to_remote(remote_host, remote_author_id, delete_like.data)

    #         like_qs.delete()
    #         entry.like_count = max(entry.like_count - 1, 0)
    #         like_count = max(entry.like_count - 1, 0)
    #         # entry.save(update_fields=['like_count'])
    #         Entry.objects.filter(id=entry.id).update(like_count=like_count)
    #         entry.refresh_from_db(fields=['like_count'])
    #         return Response({"ok": True, "message": "Like removed", "liked": False, "count": entry.like_count}, status=200)
        
    #     like = EntryLike.objects.create(user=user, entry=entry)
    #     Entry.objects.filter(id=entry.id).update(like_count=F('like_count') + 1)
    #     entry.refresh_from_db(fields=['like_count'])
    #     serializer = EntryLikeSerializer(like, context={'request': request})
    #     # print(serializer.data)

    #     if is_local and remote_host and remote_author_id:
    #         self.send_like_to_remote(remote_host, remote_author_id, serializer.data)

                
    #     return Response({**serializer.data, "liked": True, "count": entry.like_count}, status=201)


    def handle_like(self, request, author, data, is_local):
        entry_fqid = data.get('object', '')
        remote_host = data.get('remote_host', '')
        remote_author_id = data.get('remote_author_id', '')

        # e.g. "http://nodebbbb/" from "http://nodebbbb/api/authors/222/entries/249"
        remote_host_from_req = get_host_from_object(entry_fqid)

        try:
            entry = Entry.objects.get(url=entry_fqid)
        except Entry.DoesNotExist:
            return Response({"error": "Entry not found"}, status=404)
        
        # Who is liking?
        if is_local:
            user = request.user
        else:
            user_data = data.get('author', {})
            if not user_data.get('id'):
                return Response({"error": "Author data missing in like"}, status=400)
            user = self.get_or_create_remote_user(user_data)

        like_qs = EntryLike.objects.filter(user=user, entry=entry)

        # ---------- UNLIKE BRANCH ----------
        if like_qs.exists():
            delete_like = EntryLikeSerializer(
                like_qs.first(),
                context={'request': request}
            ).data

            # Delete locally
            like_qs.delete()
            like_count = max(entry.like_count - 1, 0)
            Entry.objects.filter(id=entry.id).update(like_count=like_count)
            entry.refresh_from_db(fields=['like_count'])

            # ✅ Federation for UNLIKE only for *local* requests
            if is_local:
                if remote_host and remote_author_id:
                    # local_author unliking remote entry → tell the remote origin
                    self.send_like_to_remote(remote_host, remote_author_id, delete_like)
                else:
                    # local_author unliking local entry → broadcast to all nodes
                    self.broadcast_like_to_all_nodes(delete_like)

            # ❌ if not is_local: remote node unliking → store only, no rebroadcast

            return Response(
                {
                    "ok": True,
                    "message": "Like removed",
                    "liked": False,
                    "count": entry.like_count,
                },
                status=200,
            )

        # ---------- NEW LIKE BRANCH ----------
        like = EntryLike.objects.create(user=user, entry=entry)
        Entry.objects.filter(id=entry.id).update(like_count=F('like_count') + 1)
        entry.refresh_from_db(fields=['like_count'])
        serializer = EntryLikeSerializer(like, context={'request': request})
        like_data = serializer.data  # this is what we'll send to other nodes (if needed)

        # ✅ Only act on federation for *local* likes
        if is_local:
            if remote_host and remote_author_id:
                # CASE 2: local_author likes remote entry → send to remote node
                self.send_like_to_remote(remote_host, remote_author_id, like_data)
            else:
                # CASE 1: local_author likes local entry → send to all nodes
                self.broadcast_like_to_all_nodes(like_data)

        # ❌ CASE 3: remote node sends like to me → save locally, no broadcast

        return Response({**serializer.data, "liked": True, "count": entry.like_count}, status=201)

    
    def handle_entry(self, is_local, request, data):
        if is_local:
            return
        else:
            remote_entry_id = data.get('id', '')
            author_data = data.get('author', {})

            if not remote_entry_id:
                return Response({"error": "Remote entry 'id' (fqid) is required"}, status=400)

            if not author_data.get("id"):
                return Response({"error": "Remote author 'id' is required"}, status=400)

            remote_author = self.get_or_create_remote_user(author_data)
            visibility = data.get('visibility', 'PUBLIC').upper()
            if visibility == "DELETED":
                is_deleted = True
                visibility = "PUBLIC"
            else:
                is_deleted = False
            
            published    = None
            if data.get("published"):
                published = parse_datetime(data["published"])  # safely parses ISO string; returns None if invalid
            

            defaults = {
                "author": remote_author,
                "title": data.get("title", ""),
                "description": data.get("description", ""),
                "content": data.get("content", ""),
                "content_type": data.get("contentType", "text/plain"),
                "visibility": visibility,
                "is_deleted": is_deleted,
                "like_count": data.get("likes", {}).get("count", 0),
                "comment_count": data.get("comments", {}).get("count", 0),
            }

            if published:
                defaults["created"] = published
                defaults["updated"] = published
            
            entry, created = Entry.objects.update_or_create(
                url=remote_entry_id,
                defaults=defaults,
            )

            likes = data.get("likes", {}).get("src", [])
            comments = data.get("comments", {}).get("src", [])


            for like_data in likes:
                self.create_like(like_data, entry)
            
            for comment_data in comments:
                self.create_comment(comment_data, entry)

            serializer = EntrySerializer(entry, context={"request": request})
            status_code = 201 if created else 200
            return Response(serializer.data, status=status_code)
        
    def create_like(self, like, entry):
        author_data = like.get('author', {})
        if not author_data.get('id'):
        # Can't attribute this like → skip
            return
        user = self.get_or_create_remote_user(author_data)
        EntryLike.objects.get_or_create(user=user, entry=entry)
    
    def create_comment(self, comment_data, entry):
        author_data = comment_data.get('author', {})
        if not author_data.get('id'):
            return  # skip bad comment
        user = self.get_or_create_remote_user(author_data)
        published = comment_data.get('published', None)
        if published:
            published = parse_datetime(published)
        Comment.objects.get_or_create(
            fqid=comment_data.get('id', ''),
            defaults = {
                "entry": entry,
                "author": user,
                "comment": comment_data.get('comment', ''),
                "content_type": comment_data.get('contentType', 'text/plain'),
                "created": published,
            }
        )
    
    def send_like_to_remote(self, remote_host, remote_author_id, entryLike):
            print()
            print("Received entryLike to send to remote:")
            pprint.pprint(entryLike)
            print()


            try:
                remote_author = User.objects.get(id=remote_author_id)
            except User.DoesNotExist:
                print(f"Remote author with id {remote_author_id} does not exist.")
                return
            
            formatted_host = remote_host.rstrip('api/') + '/'

            node = Nodes.objects.filter(host=formatted_host).first()

            if not node:
                print(f"No node configuration found for host: {formatted_host}")
                return
            
            if not node.is_connected:
                print(f"Node for host {formatted_host} is not connected.")
                return
            
            headers = {
                'Authorization': f"{node.token}",
                'Content-Type': 'application/json',
                'Accept': 'application/json',
            }

            remote_inbox_url = f"{remote_author.fqid.rstrip('/')}/inbox/"
            try:
                resp = requests.post(
                    url=remote_inbox_url, 
                    json=entryLike, 
                    headers=headers, 
                    timeout=5
                )
                if resp.status_code not in [200, 201]:
                    print(f"Failed to send like to remote inbox. Status code: {resp.status_code}, Response: {resp.text}")
                else:
                    print(f"Successfully sent like to remote inbox at {remote_inbox_url}")
                
            except Exception as e:
                print(f"Failed to send like to remote inbox: {e}")


    def broadcast_like_to_all_nodes(self, like_data, remote_host=None):
        nodes = Nodes.objects.filter(is_connected=True)

        if not nodes.exists():
            print("No connected nodes to broadcast like to.")
            return

        for node in nodes:

            if node.host == remote_host:
                print(f"Skipping broadcasting to origin node: {node.host}")
                continue

            headers = {
                "Authorization": f"{node.token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            }

            base = node.host.rstrip('/')

            try:
                authors_response = requests.get(
                    url=f"{base}/api/authors/",
                    headers=headers,
                    timeout=5,
                )
                if authors_response.status_code != 200:
                    print(f"Failed to fetch authors from node {node.host}: {authors_response.status_code}")
                    continue
                
                data = authors_response.json()
                authors = data.get("authors", [])

                for author in authors:
                    author_id = author.get("id")
                    if not author_id:
                        continue

                    inbox_url = f"{author_id.rstrip('/')}/inbox/"

                    response = requests.post(
                        url=inbox_url,
                        json=like_data,
                        headers=headers,
                        timeout=5,
                    )
                    if response.status_code not in [200, 201]:
                        print(f"Failed to send like to {inbox_url}: {response.status_code} {response.text}")
                    else:
                        print(f"Successfully sent like to {inbox_url}: {response.status_code} {response.text}")
            except Exception as e:
                print(f"Error sending like to node {node.host}: {str(e)}")
