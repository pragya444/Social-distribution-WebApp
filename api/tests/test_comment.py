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
    
    def test_comment_on_deleted_entry_failure(self):
        """Test commenting on a deleted entry - FAILURE"""
        self.entry.is_deleted = True
        self.entry.save()
        url = reverse("comments-list-create", kwargs={
            "author_id": self.user.id,
            "entry_id": self.entry.id
        })
        data = {"comment": "Comment on deleted", "contentType": "text/plain"}
        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
    
    def test_comment_empty_text_failure(self):
        """Test creating comment with empty text - FAILURE"""
        url = reverse("comments-list-create", kwargs={
            "author_id": self.user.id,
            "entry_id": self.entry.id
        })
        data = {"comment": "", "contentType": "text/plain"}
        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_comment_whitespace_only_failure(self):
        """Test creating comment with only whitespace - FAILURE"""
        url = reverse("comments-list-create", kwargs={
            "author_id": self.user.id,
            "entry_id": self.entry.id
        })
        data = {"comment": "   ", "contentType": "text/plain"}
        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_comment_xss_attempt_success(self):
        """Test comment with XSS script - SUCCESS (should be sanitized)"""
        url = reverse("comments-list-create", kwargs={
            "author_id": self.user.id,
            "entry_id": self.entry.id
        })
        data = {"comment": "<script>alert('xss')</script>", "contentType": "text/plain"}
        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        comment = Comment.objects.latest('id')
        self.assertEqual(comment.comment, "<script>alert('xss')</script>")
    
    def test_comment_on_private_entry_unauthorized_failure(self):
        """Test commenting on private entry by non-friend - FAILURE"""
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
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

class LikesCommentsEdgeTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.alice = User.objects.create_user(username="alice_lc", password="pass", is_active=True)
        self.bob = User.objects.create_user(username="bob_lc", password="pass", is_active=True)
        self.entry = Entry.objects.create(author=self.alice, title="t", content="c", content_type="text/plain", visibility="PUBLIC")
        self.client.force_login(self.bob)

    def test_like_entry_success(self):
        """Test that entries can be liked - SUCCESS"""
        url = reverse("entry-likes", kwargs={"author_id": self.alice.id, "entry_id": self.entry.id})
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(EntryLike.objects.filter(user=self.bob, entry=self.entry).exists())

    def test_unlike_entry_success(self):
        """Test that entries can be unliked - SUCCESS"""
        EntryLike.objects.create(user=self.bob, entry=self.entry)
        url = reverse("entry-likes", kwargs={"author_id": self.alice.id, "entry_id": self.entry.id})
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(EntryLike.objects.filter(user=self.bob, entry=self.entry).exists())

    def test_like_requires_auth_failure(self):
        """Test that liking entries requires authentication - FAILURE"""
        url = reverse("entry-likes", kwargs={"author_id": self.alice.id, "entry_id": self.entry.id})
        anon_client = APIClient()  
        response = anon_client.post(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_comment_create_requires_auth_failure(self):
        """Test that creating comments requires authentication - FAILURE"""
        url = reverse("comments-list-create", kwargs={"author_id": self.alice.id, "entry_id": self.entry.id})
        anon_client = APIClient()
        response = anon_client.post(url, {"comment":"hi"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_get_comment_likes_success(self):
        """Test that comment likes can be retrieved - SUCCESS"""
        comment = Comment.objects.create(entry=self.entry, author=self.bob, comment="ok", content_type="text/plain")
        url = reverse("comment-likes", kwargs={"author_id": self.alice.id, "entry_id": self.entry.id, "comment_id": comment.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_like_comment_success(self):
        """Test that comments can be liked - SUCCESS"""
        comment = Comment.objects.create(entry=self.entry, author=self.bob, comment="ok", content_type="text/plain")
        url = reverse("comment-likes", kwargs={"author_id": self.alice.id, "entry_id": self.entry.id, "comment_id": comment.id})
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(CommentLike.objects.filter(user=self.bob, comment=comment).exists())

    def test_comment_like_requires_auth_failure(self):
        """Test that liking comments requires authentication - FAILURE"""
        comment = Comment.objects.create(entry=self.entry, author=self.bob, comment="ok", content_type="text/plain")
        url = reverse("comment-likes", kwargs={"author_id": self.alice.id, "entry_id": self.entry.id, "comment_id": comment.id})
        anon_client = APIClient()
        response = anon_client.post(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_like_counts_increase_success(self):
        """Test that like counts increase when entries are liked - SUCCESS"""
        initial_count = self.entry.like_count
        url = reverse("entry-likes", kwargs={"author_id": self.alice.id, "entry_id": self.entry.id})
        self.client.post(url)
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.like_count, initial_count + 1)

    def test_comment_list_get_success(self):
        """Test that comment lists can be retrieved - SUCCESS"""
        Comment.objects.create(entry=self.entry, author=self.bob, comment="ok", content_type="text/plain")
        url = reverse("comments-list-create", kwargs={"author_id": self.alice.id, "entry_id": self.entry.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_unlike_non_existent_like_success(self):
        """Test that deleting non-existent likes succeeds - SUCCESS"""
        url = reverse("entry-likes", kwargs={"author_id": self.alice.id, "entry_id": self.entry.id})
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)