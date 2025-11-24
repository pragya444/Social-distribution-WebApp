from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from django.test import Client
from zoneinfo import ZoneInfo
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase, APIClient
from rest_framework import status
import json
import base64
import warnings
from api.models import Entry, Follow, Comment, EntryLike, CommentLike, Node

warnings.filterwarnings('ignore', category=Warning, message='.*Pagination may yield inconsistent results.*')
warnings.filterwarnings('ignore', category=UserWarning, message='.*No directory at.*staticfiles.*')

User = get_user_model()

class InboxAPITests(TestCase):
    """Test all inbox API endpoints - ONLY POST method as per requirements"""
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username="testuser", password="pass", is_active=True)
        self.other_user = User.objects.create_user(username="otheruser", password="pass", is_active=True)

    def test_inbox_follow_request_post_success(self):
        """Test posting a follow request to inbox - SUCCESS"""
        self.client.force_login(self.user)
        url = f"/api/authors/{self.user.id}/inbox/"
        data = {
            "type": "follow",
            "actor": {
                "type": "author",
                "id": self.other_user.url,
                "displayName": self.other_user.name
            },
            "object": {
                "type": "author",
                "id": self.user.url,
                "displayName": self.user.name
            }
        }
        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
    
    def test_inbox_follow_request_invalid_data_failure(self):
        """Test posting invalid follow request to inbox - FAILURE"""
        self.client.force_login(self.user)
        url = f"/api/authors/{self.user.id}/inbox/"
        data = {
            "type": "follow",
        }
        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_inbox_like_post_success(self):
        """Test posting a like to inbox - SUCCESS"""
        self.client.force_login(self.user)
        entry = Entry.objects.create(
            author=self.user,
            title="Test",
            content="Content",
            content_type="text/plain",
            visibility="PUBLIC"
        )
        url = f"/api/authors/{self.user.id}/inbox/"
        data = {
            "type": "like",
            "author": {
                "type": "author",
                "id": self.other_user.url,
                "displayName": self.other_user.name
            },
            "object": entry.url
        }
        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_inbox_like_post_invalid_entry_failure(self):
        """Test posting like for non-existent entry to inbox - FAILURE"""
        self.client.force_login(self.user)
        url = f"/api/authors/{self.user.id}/inbox/"
        data = {
            "type": "like",
            "author": {
                "type": "author",
                "id": self.other_user.url,
                "displayName": self.other_user.name
            },
            "object": "http://invalid-entry-url"
        }
        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

class InboxExtendedTests(TestCase):
    """Extended tests for inbox endpoint - ONLY POST method"""
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username="inbox_user", password="pass", is_active=True)
        self.other_user = User.objects.create_user(username="sender", password="pass", is_active=True)
        self.client.force_login(self.user)
    
    def test_inbox_get_method_not_allowed_failure(self):
        """Test GET method on inbox should fail - FAILURE"""
        url = reverse("inbox", kwargs={"author_id": self.user.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
    
    def test_inbox_comment_post_success(self):
        """Test posting a comment to inbox - SUCCESS"""
        entry = Entry.objects.create(
            author=self.user,
            title="Entry",
            content="Content",
            content_type="text/plain",
            visibility="PUBLIC"
        )
        url = reverse("inbox", kwargs={"author_id": self.user.id})
        data = {
            "type": "comment",
            "comment": "Inbox comment",
            "contentType": "text/plain",
            "author": {
                "type": "author",
                "id": self.other_user.url,
                "displayName": self.other_user.name
            },
            "entry": entry.url 
        }
        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
    
    def test_inbox_comment_post_invalid_entry_failure(self):
        """Test posting comment for non-existent entry to inbox - FAILURE"""
        url = reverse("inbox", kwargs={"author_id": self.user.id})
        data = {
            "type": "comment",
            "comment": "Inbox comment",
            "contentType": "text/plain",
            "author": {
                "type": "author",
                "id": self.other_user.url,
                "displayName": self.other_user.name
            },
            "object": "http://invalid-entry-url"
        }
        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
    
    def test_inbox_post_malformed_data_failure(self):
        """Test posting malformed data to inbox - FAILURE"""
        url = reverse("inbox", kwargs={"author_id": self.user.id})
        data = {"type": "invalid", "bad": "data"}
        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_inbox_delete_method_not_allowed_failure(self):
        """Test DELETE method on inbox should fail - FAILURE"""
        url = reverse("inbox", kwargs={"author_id": self.user.id})
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
    
    def test_inbox_post_unauthenticated_failure(self):
        """Test posting to inbox without authentication - FAILURE"""
        self.client.logout()
        url = reverse("inbox", kwargs={"author_id": self.user.id})
        data = {
            "type": "entry",
            "title": "Test Entry",
            "content": "Content",
            "contentType": "text/plain"
        }
        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class RemoteInboxTests(TestCase):
    """Tests that exercise remote (BasicAuth) branches of the InboxView."""
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username="remote_target", password="pass", is_active=True)
        self.other_user = User.objects.create_user(username="remote_actor", password="pass", is_active=True)

    def _basic_auth(self, username, password):
        creds = base64.b64encode(f"{username}:{password}".encode()).decode()
        return {"HTTP_AUTHORIZATION": f"Basic {creds}"}
    def test_follow_approval_updates_follow(self):
        """Posting a follow with approved=true should set status to APPROVED"""
        pending = Follow.objects.create(follower=self.other_user, followee=self.user, status=Follow.Status.PENDING)
        url = reverse("inbox", kwargs={"author_id": self.user.id})
        data = {
            "type": "follow",
            "approved": True,
            "actor": {"type": "author", "id": self.other_user.url, "displayName": self.other_user.name},
            "object": {"type": "author", "id": self.user.url, "displayName": self.user.name}
        }
        headers = self._basic_auth(self.other_user.username, "pass")
        response = self.client.post(url, data, format="json", **headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        follow = Follow.objects.get(id=pending.id)
        self.assertEqual(follow.status, Follow.Status.APPROVED)

    def test_comment_like_success_and_not_found(self):
        """Like a comment (create) and fail when comment not found"""
        entry = Entry.objects.create(author=self.user, title="E", content="c", content_type="text/plain", visibility="PUBLIC")
        comment = Comment.objects.create(entry=entry, author=self.other_user, comment="hi", content_type="text/plain")

        url = reverse("inbox", kwargs={"author_id": self.user.id})
        self.client.force_login(self.user)
        data = {"type": "like", "object": comment.fqid}
        resp = self.client.post(url, data, format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertTrue(resp.data.get("liked", True))

        self.client.logout()
        headers = self._basic_auth(self.other_user.username, "pass")
        data2 = {"type": "like", "object": "http://invalid/comment/999"}
        resp2 = self.client.post(url, data2, format="json", **headers)
        self.assertEqual(resp2.status_code, status.HTTP_404_NOT_FOUND)

    def test_like_toggle_and_remote_like_missing_author(self):
        """Test liking an entry twice toggles like; remote like missing author.id returns 400"""
        entry = Entry.objects.create(author=self.user, title="Toggle", content="x", content_type="text/plain", visibility="PUBLIC")
        url = reverse("inbox", kwargs={"author_id": self.user.id})

        self.client.force_login(self.user)
        data = {"type": "like", "object": entry.url}
        r1 = self.client.post(url, data, format="json")
        self.assertEqual(r1.status_code, status.HTTP_201_CREATED)
        self.assertTrue(r1.data.get("liked", False))

        r2 = self.client.post(url, data, format="json")
        self.assertEqual(r2.status_code, status.HTTP_200_OK)
        self.assertFalse(r2.data.get("liked", True))

        self.client.logout()
        headers = self._basic_auth(self.other_user.username, "pass")
        bad = {"type": "like", "object": entry.url, "author": {}}
        resp = self.client.post(url, bad, format="json", **headers)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)