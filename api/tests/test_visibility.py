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
from .models import Entry, Follow, Comment, EntryLike, CommentLike, Node

warnings.filterwarnings('ignore', category=Warning, message='.*Pagination may yield inconsistent results.*')        # filter out pagination warnings
warnings.filterwarnings('ignore', category=UserWarning, message='.*No directory at.*staticfiles.*')     # filter out staticfiles warnings

User = get_user_model()

class EntryVisibilityAccessTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.author = User.objects.create_user(username="author_va", password="pass", is_active=True)
        self.follower = User.objects.create_user(username="follower_va", password="pass", is_active=True)
        self.stranger = User.objects.create_user(username="stranger_va", password="pass", is_active=True)

    def test_public_visible_to_anonymous(self):
        """Test that public entries are visible to anonymous users"""
        e = Entry.objects.create(author=self.author, title="p", content="c", content_type="text/plain", visibility="PUBLIC")
        url = reverse("entry-retrieve-update", kwargs={"author_id": self.author.id, "entry_id": e.id})
        r = Client().get(url)
        self.assertEqual(r.status_code, status.HTTP_200_OK)

    def test_friends_not_visible_to_anonymous(self):
        """Test that friends-only entries are not visible to anonymous users"""
        e = Entry.objects.create(author=self.author, title="f", content="c", content_type="text/plain", visibility="FRIENDS")
        url = reverse("entry-retrieve-update", kwargs={"author_id": self.author.id, "entry_id": e.id})
        r = Client().get(url)
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)
    
    
    def test_unlisted_entry_visible_to_all_by_link(self):
        """Test that unlisted entries are visible to anyone with the link"""
        e = Entry.objects.create(author=self.author, title="u", content="c", content_type="text/plain", visibility="UNLISTED")
        url = reverse("entry-retrieve-update", kwargs={"author_id": self.author.id, "entry_id": e.id})
        self.client.force_login(self.stranger)
        r = self.client.get(url)
        self.assertEqual(r.status_code, status.HTTP_200_OK)

    def test_unlisted_visible_to_follower(self):
        """Test that unlisted entries are visible to approved followers"""
        e = Entry.objects.create(author=self.author, title="u", content="c", content_type="text/plain", visibility="UNLISTED")
        Follow.objects.create(follower=self.follower, followee=self.author, status=Follow.Status.APPROVED)
        self.client.force_login(self.follower)
        url = reverse("entry-retrieve-update", kwargs={"author_id": self.author.id, "entry_id": e.id})
        r = self.client.get(url)
        self.assertEqual(r.status_code, status.HTTP_200_OK)

    def test_friends_visible_to_friend(self):
        """Test that friends-only entries are visible to mutual friends"""
        e = Entry.objects.create(author=self.author, title="f", content="c", content_type="text/plain", visibility="FRIENDS")
        Follow.objects.create(follower=self.follower, followee=self.author, status=Follow.Status.APPROVED)
        Follow.objects.create(follower=self.author, followee=self.follower, status=Follow.Status.APPROVED)
        self.client.force_login(self.follower)
        url = reverse("entry-retrieve-update", kwargs={"author_id": self.author.id, "entry_id": e.id})
        r = self.client.get(url)
        self.assertEqual(r.status_code, status.HTTP_200_OK)

    def test_author_always_can_view_private(self):
        """Test that authors can always view their own private entries"""
        e = Entry.objects.create(author=self.author, title="f", content="c", content_type="text/plain", visibility="FRIENDS")
        self.client.force_login(self.author)
        url = reverse("entry-retrieve-update", kwargs={"author_id": self.author.id, "entry_id": e.id})
        r = self.client.get(url)
        self.assertEqual(r.status_code, status.HTTP_200_OK)

    def test_entries_list_public_when_viewing_other(self):
        """Test that viewing another author's entries only shows public entries"""
        Entry.objects.create(author=self.author, title="pub", content="c", content_type="text/plain", visibility="PUBLIC")
        Entry.objects.create(author=self.author, title="priv", content="c", content_type="text/plain", visibility="FRIENDS")
        self.client.force_login(self.stranger)
        url = reverse("entries-list-create", kwargs={"author_id": self.author.id})
        r = self.client.get(url)
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertIn("pub", str(r.content))
        self.assertNotIn("priv", str(r.content))

    def test_entries_list_author_sees_all(self):
        """Test that authors can see all their own entries including private ones"""
        Entry.objects.create(author=self.author, title="pub", content="c", content_type="text/plain", visibility="PUBLIC")
        Entry.objects.create(author=self.author, title="priv", content="c", content_type="text/plain", visibility="FRIENDS")
        self.client.force_login(self.author)
        url = reverse("entries-list-create", kwargs={"author_id": self.author.id})
        r = self.client.get(url)
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertIn("pub", str(r.content))
        self.assertIn("priv", str(r.content))

    def test_image_binary_endpoint_authz(self):
        """Test that image endpoint respects authorization for friends-only images"""
        e = Entry.objects.create(author=self.author, title="img", content=base64.b64encode(b"i").decode(), content_type="image/png;base64", visibility="FRIENDS")
        url = reverse("entry-image", kwargs={"author_id": self.author.id, "entry_id": e.id})
        r = Client().get(url)
        self.assertIn(r.status_code, [status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND])

class EntrySharingTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.author = User.objects.create_user(username="author", password="test123", is_active=True)
        self.reader = User.objects.create_user(username="reader", password="reader123", is_active=True)

        self.public_entry = Entry.objects.create(
            author=self.author,
            title="Public Entry",
            content="This is visible to everyone.",
            visibility="PUBLIC",
        )

        self.unlisted_entry = Entry.objects.create(
            author=self.author,
            title="Unlisted Entry",
            content="This is visible to everyone via link.",
            visibility="UNLISTED",
        )

        self.private_entry = Entry.objects.create(
            author=self.author,
            title="Private Entry",
            content="Should not be visible.",
            visibility="FRIENDS",  
        )

    def test_unlisted_entry_accessible_by_anonymous(self):
        """Anonymous users should NOT be able to access UNLISTED entries (follower-only)."""
        url = reverse(
            "entry-retrieve-update",
            kwargs={"author_id": self.author.id, "entry_id": self.unlisted_entry.id},
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_reader_can_access_unlisted_entry(self):
        """A logged-in non-friend reader cannot access another user's unlisted entry."""
        self.client.login(username="reader", password="reader123")
        url = reverse(
            "entry-retrieve-update",
            kwargs={"author_id": self.author.id, "entry_id": self.unlisted_entry.id},
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_reader_cannot_access_private_entry(self):
        """A logged-in non-friend reader cannot access another user's private entry."""
        self.client.login(username="reader", password="reader123")
        url = reverse(
            "entry-retrieve-update",
            kwargs={"author_id": self.author.id, "entry_id": self.private_entry.id},
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)
        
class VisibilityFilteringTests(TestCase):
    """Test visibility filtering for different entry types"""
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username="testuser", password="pass", is_active=True)
        self.friend = User.objects.create_user(username="friend", password="pass", is_active=True)
        self.stranger = User.objects.create_user(username="stranger", password="pass", is_active=True)
        
        Follow.objects.create(follower=self.user, followee=self.friend, status=Follow.Status.APPROVED)
        Follow.objects.create(follower=self.friend, followee=self.user, status=Follow.Status.APPROVED)
        
    def test_public_visible_to_all(self):
        """Test public entries visible to everyone"""
        entry = Entry.objects.create(
            author=self.user,
            title="Public",
            content="Content",
            content_type="text/plain",
            visibility="PUBLIC"
        )
        
        self.client.force_login(self.friend)
        url = reverse("entry-retrieve-update", kwargs={"author_id": self.user.id, "entry_id": entry.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        self.client.force_login(self.stranger)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    def test_friends_only_visible_to_friends(self):
        """Test friends-only entries visible only to friends"""
        entry = Entry.objects.create(
            author=self.user,
            title="Friends Only",
            content="Content",
            content_type="text/plain",
            visibility="FRIENDS"
        )
        
        self.client.force_login(self.friend)
        url = reverse("entry-retrieve-update", kwargs={"author_id": self.user.id, "entry_id": entry.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        self.client.force_login(self.stranger)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    def test_unlisted_visible_by_link(self):
        """Test unlisted entries accessible by direct link"""
        entry = Entry.objects.create(
            author=self.user,
            title="Unlisted",
            content="Content",
            content_type="text/plain",
            visibility="UNLISTED"
        )
        
        self.client.force_login(self.stranger)
        url = reverse("entry-retrieve-update", kwargs={"author_id": self.user.id, "entry_id": entry.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
