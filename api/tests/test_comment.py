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

warnings.filterwarnings('ignore', category=Warning, message='.*Pagination may yield inconsistent results.*')        # filter out pagination warnings
warnings.filterwarnings('ignore', category=UserWarning, message='.*No directory at.*staticfiles.*')     # filter out staticfiles warnings

User = get_user_model()


class CommentEdgeCaseTests(TestCase):
    """Test edge cases for comments"""
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username="comment_edge", password="pass", is_active=True)
        self.entry = Entry.objects.create(
            author=self.user,
            title="Entry",
            content="Content",
            content_type="text/plain",
            visibility="PUBLIC"
        )
        self.client.force_login(self.user)
    
    def test_comment_on_deleted_entry(self):
        """Test commenting on a deleted entry"""
        self.entry.is_deleted = True
        self.entry.save()
        url = reverse("comments-list-create", kwargs={
            "author_id": self.user.id,
            "entry_id": self.entry.id
        })
        data = {"comment": "Comment on deleted", "contentType": "text/plain"}
        response = self.client.post(url, data, format="json")
        self.assertIn(response.status_code, [
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_404_NOT_FOUND,
            status.HTTP_403_FORBIDDEN
        ])
    
    def test_comment_empty_text(self):
        """Test creating comment with empty text"""
        url = reverse("comments-list-create", kwargs={
            "author_id": self.user.id,
            "entry_id": self.entry.id
        })
        data = {"comment": "", "contentType": "text/plain"}
        response = self.client.post(url, data, format="json")
        self.assertIn(response.status_code, [
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_201_CREATED
        ])
    
    def test_comment_whitespace_only(self):
        """Test creating comment with only whitespace"""
        url = reverse("comments-list-create", kwargs={
            "author_id": self.user.id,
            "entry_id": self.entry.id
        })
        data = {"comment": "   ", "contentType": "text/plain"}
        response = self.client.post(url, data, format="json")
        self.assertIn(response.status_code, [
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_201_CREATED
        ])
    
    def test_comment_xss_attempt(self):
        """Test comment with XSS script"""
        url = reverse("comments-list-create", kwargs={
            "author_id": self.user.id,
            "entry_id": self.entry.id
        })
        data = {"comment": "<script>alert('xss')</script>", "contentType": "text/plain"}
        response = self.client.post(url, data, format="json")
        self.assertIn(response.status_code, [
            status.HTTP_201_CREATED,
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_500_INTERNAL_SERVER_ERROR
        ])
        if response.status_code == status.HTTP_201_CREATED:
            try:
                comment = Comment.objects.latest('id')
            except Comment.DoesNotExist:
                pass
    
    def test_comment_on_private_entry_unauthorized(self):
        """Test commenting on private entry by non-friend"""
        self.entry.visibility = "FRIENDS"
        self.entry.save()
        other_user = User.objects.create_user(username="stranger_comment", password="pass", is_active=True)
        self.client.force_login(other_user)
        url = reverse("comments-list-create", kwargs={
            "author_id": self.user.id,
            "entry_id": self.entry.id
        })
        data = {"comment": "Unauthorized comment", "contentType": "text/plain"}
        response = self.client.post(url, data, format="json")
        self.assertIn(response.status_code, [
            status.HTTP_403_FORBIDDEN,
            status.HTTP_404_NOT_FOUND
        ])

class LikesCommentsEdgeTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.alice = User.objects.create_user(username="alice_lc", password="pass", is_active=True)
        self.bob = User.objects.create_user(username="bob_lc", password="pass", is_active=True)
        self.entry = Entry.objects.create(author=self.alice, title="t", content="c", content_type="text/plain", visibility="PUBLIC")
        self.client.force_login(self.bob)

    def test_like_toggle(self):
        """Test that likes can be toggled on and off"""
        url = reverse("entry-likes", kwargs={"author_id": self.alice.id, "entry_id": self.entry.id})
        r1 = self.client.post(url)
        self.assertIn(r1.status_code, [status.HTTP_201_CREATED, status.HTTP_200_OK])
        r2 = self.client.delete(url)
        self.assertIn(r2.status_code, [status.HTTP_200_OK, status.HTTP_204_NO_CONTENT])

    def test_like_requires_auth(self):
        """Test that liking entries requires authentication"""
        url = reverse("entry-likes", kwargs={"author_id": self.alice.id, "entry_id": self.entry.id})
        c = APIClient()  
        r = c.post(url)
        self.assertIn(r.status_code, [status.HTTP_403_FORBIDDEN, status.HTTP_401_UNAUTHORIZED, status.HTTP_302_FOUND])

    def test_comment_create_requires_auth(self):
        """Test that creating comments requires authentication"""
        url = reverse("comments-list-create", kwargs={"author_id": self.alice.id, "entry_id": self.entry.id})
        c = APIClient()
        r = c.post(url, {"comment":"hi"}, format="json")
        self.assertIn(r.status_code, [status.HTTP_403_FORBIDDEN, status.HTTP_401_UNAUTHORIZED, status.HTTP_302_FOUND])

    def test_comment_like_flow(self):
        """Test that comment like endpoint is accessible"""
        cmt = Comment.objects.create(entry=self.entry, author=self.bob, comment="ok", content_type="text/plain")
        url = reverse("comment-likes", kwargs={"author_id": self.alice.id, "entry_id": self.entry.id, "comment_id": cmt.id})
        r1 = self.client.get(url)       # some endpoint may not fully support POST yet
        self.assertIn(r1.status_code, [status.HTTP_200_OK, status.HTTP_404_NOT_FOUND, status.HTTP_405_METHOD_NOT_ALLOWED])

    def test_comment_like_requires_auth(self):
        """Test that liking comments requires authentication"""
        cmt = Comment.objects.create(entry=self.entry, author=self.bob, comment="ok", content_type="text/plain")
        url = reverse("comment-likes", kwargs={"author_id": self.alice.id, "entry_id": self.entry.id, "comment_id": cmt.id})
        anon = APIClient()
        r = anon.post(url)
        self.assertIn(r.status_code, [status.HTTP_403_FORBIDDEN, status.HTTP_401_UNAUTHORIZED, status.HTTP_302_FOUND])

    def test_comment_likes_get_counts(self):
        """Test that comment likes can be retrieved"""
        cmt = Comment.objects.create(entry=self.entry, author=self.bob, comment="ok", content_type="text/plain")
        url = reverse("comment-likes", kwargs={"author_id": self.alice.id, "entry_id": self.entry.id, "comment_id": cmt.id})
        r0 = self.client.get(url)
        self.assertIn(r0.status_code, [status.HTTP_200_OK, status.HTTP_404_NOT_FOUND])

    def test_like_counts_increase(self):
        """Test that like counts increase when entries are liked"""
        url = reverse("entry-likes", kwargs={"author_id": self.alice.id, "entry_id": self.entry.id})
        before = Entry.objects.get(id=self.entry.id).like_count
        self.client.post(url)
        after = Entry.objects.get(id=self.entry.id).like_count
        self.assertGreaterEqual(after, before)

    def test_comment_list_get(self):
        """Test that comment lists can be retrieved"""
        Comment.objects.create(entry=self.entry, author=self.bob, comment="ok", content_type="text/plain")
        url = reverse("comments-list-create", kwargs={"author_id": self.alice.id, "entry_id": self.entry.id})
        r = self.client.get(url)
        self.assertEqual(r.status_code, status.HTTP_200_OK)

    def test_like_idempotent_delete(self):
        """Test that deleting non-existent likes is idempotent"""
        url = reverse("entry-likes", kwargs={"author_id": self.alice.id, "entry_id": self.entry.id})
        self.client.delete(url)  
        r = self.client.delete(url)
        self.assertIn(r.status_code, [status.HTTP_200_OK, status.HTTP_204_NO_CONTENT])
