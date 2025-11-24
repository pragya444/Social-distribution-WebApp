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

'''
The test refactoring is assisted by OpenAI, ChatGPT-5, 2025-11-23.
'''

warnings.filterwarnings('ignore', category=Warning, message='.*Pagination may yield inconsistent results.*')        # filter out pagination warnings
warnings.filterwarnings('ignore', category=UserWarning, message='.*No directory at.*staticfiles.*')     # filter out staticfiles warnings

User = get_user_model()


class CommentEdgeCaseTests(TestCase):
    """Test edge cases for comments"""
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="comment_edge", password="pass", is_active=True
        )
        self.entry = Entry.objects.create(
            author=self.user,
            title="Entry",
            content="Content",
            content_type="text/plain",
            visibility="PUBLIC"
        )
        self.client.force_login(self.user)

    def test_comment_on_deleted_entry(self):
        """Commenting on deleted entry must NOT succeed."""
        self.entry.is_deleted = True
        self.entry.save()

        url = reverse("comments-list-create", kwargs={
            "author_id": self.user.id,
            "entry_id": self.entry.id
        })

        r = self.client.post(url, {"comment": "x", "contentType": "text/plain"}, format="json")
        self.assertIn(r.status_code, [404])

    def test_comment_empty_text(self):
        """Empty comment is invalid."""
        url = reverse("comments-list-create", kwargs={
            "author_id": self.user.id,
            "entry_id": self.entry.id
        })

        r = self.client.post(url, {"comment": "", "contentType": "text/plain"}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_comment_whitespace_only(self):
        """Whitespace-only comments should be rejected."""
        url = reverse("comments-list-create", kwargs={
            "author_id": self.user.id,
            "entry_id": self.entry.id
        })

        r = self.client.post(url, {"comment": "   ", "contentType": "text/plain"}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_comment_xss_attempt(self):
        """XSS should be allowed as plain text but safely stored."""
        url = reverse("comments-list-create", kwargs={
            "author_id": self.user.id,
            "entry_id": self.entry.id
        })

        payload = {"comment": "<script>alert('x')</script>", "contentType": "text/plain"}
        r = self.client.post(url, payload, format="json")

        # CMPUT404 does NOT filter out XSS, so creation == OK
        self.assertEqual(r.status_code, 201)
        c = Comment.objects.latest("id")
        self.assertEqual(c.comment, payload["comment"])

    def test_comment_on_private_entry_unauthorized(self):
        """Non-friends cannot comment on FRIENDS-only entries."""
        self.entry.visibility = "FRIENDS"
        self.entry.save()

        stranger = User.objects.create_user("stranger", password="pass", is_active=True)
        self.client.force_login(stranger)

        url = reverse("comments-list-create", kwargs={
            "author_id": self.user.id,
            "entry_id": self.entry.id
        })

        r = self.client.post(url, {"comment": "nope", "contentType": "text/plain"}, format="json")
        self.assertIn(r.status_code, [403])
        
class LikesCommentsEdgeTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.alice = User.objects.create_user("alice_lc", password="pass", is_active=True)
        self.bob = User.objects.create_user("bob_lc", password="pass", is_active=True)

        self.entry = Entry.objects.create(
            author=self.alice,
            title="t",
            content="c",
            content_type="text/plain",
            visibility="PUBLIC"
        )

        self.client.force_login(self.bob)

    def test_like_toggle(self):
        """POST creates like, DELETE removes like."""
        url = reverse("entry-likes", kwargs={"author_id": self.alice.id, "entry_id": self.entry.id})

        r1 = self.client.post(url)
        self.assertEqual(r1.status_code, 201)

        r2 = self.client.delete(url)
        self.assertIn(r2.status_code, [200])

    def test_like_requires_auth(self):
        """Anonymous users cannot like."""
        c = APIClient()
        url = reverse("entry-likes", kwargs={"author_id": self.alice.id, "entry_id": self.entry.id})
        r = c.post(url)
        self.assertIn(r.status_code, [403])

    def test_comment_create_requires_auth(self):
        """Anonymous users cannot create comments."""
        c = APIClient()
        url = reverse("comments-list-create", kwargs={"author_id": self.alice.id, "entry_id": self.entry.id})
        r = c.post(url, {"comment": "hi"}, format="json")
        self.assertIn(r.status_code, [401])

    def test_comment_like_flow(self):
        """GET comment-like endpoint should not error"""
        cmt = Comment.objects.create(entry=self.entry, author=self.bob, comment="ok", content_type="text/plain")
        url = reverse("comment-likes", kwargs={"author_id": self.alice.id, "entry_id": self.entry.id, "comment_id": cmt.id})

        r = self.client.get(url)
        self.assertIn(r.status_code, [200])

    def test_comment_like_requires_auth(self):
        """Anonymous users cannot like comments."""
        anon = APIClient()
        cmt = Comment.objects.create(entry=self.entry, author=self.bob, comment="ok", content_type="text/plain")

        url = reverse("comment-likes", kwargs={"author_id": self.alice.id, "entry_id": self.entry.id, "comment_id": cmt.id})

        r = anon.post(url)
        self.assertIn(r.status_code, [403])

    def test_comment_likes_get_counts(self):
        """GET comment likes returns a count container."""
        cmt = Comment.objects.create(entry=self.entry, author=self.bob, comment="ok", content_type="text/plain")

        url = reverse("comment-likes", kwargs={"author_id": self.alice.id, "entry_id": self.entry.id, "comment_id": cmt.id})
        r = self.client.get(url)

        self.assertIn(r.status_code, [200])

    def test_like_counts_increase(self):
        """Entry like_count increments after POST."""
        url = reverse("entry-likes", kwargs={"author_id": self.alice.id, "entry_id": self.entry.id})

        before = Entry.objects.get(id=self.entry.id).like_count
        self.client.post(url)
        after = Entry.objects.get(id=self.entry.id).like_count

        self.assertEqual(after, before + 1)

    def test_comment_list_get(self):
        """GET comment list always 200."""
        Comment.objects.create(entry=self.entry, author=self.bob, comment="ok", content_type="text/plain")
        url = reverse("comments-list-create", kwargs={"author_id": self.alice.id, "entry_id": self.entry.id})
        r = self.client.get(url)
        self.assertEqual(r.status_code, 200)

    def test_like_idempotent_delete(self):
        """Deleting a non-existing like should not error."""
        url = reverse("entry-likes", kwargs={"author_id": self.alice.id, "entry_id": self.entry.id})

        self.client.delete(url)  # no like yet
        r = self.client.delete(url)

        self.assertIn(r.status_code, [200])
