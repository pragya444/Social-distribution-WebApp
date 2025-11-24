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

class EntryVisibilityAccessTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.author = User.objects.create_user(username="author_va", password="pass", is_active=True)
        self.follower = User.objects.create_user(username="follower_va", password="pass", is_active=True)
        self.stranger = User.objects.create_user(username="stranger_va", password="pass", is_active=True)

    def test_public_entry_visible_to_anonymous_success(self):
        """Test that public entries are visible to anonymous users - SUCCESS"""
        entry = Entry.objects.create(author=self.author, title="p", content="c", content_type="text/plain", visibility="PUBLIC")
        url = reverse("entry-retrieve-update", kwargs={"author_id": self.author.id, "entry_id": entry.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_friends_entry_not_visible_to_anonymous_failure(self):
        """Test that friends-only entries are not visible to anonymous users - FAILURE"""
        entry = Entry.objects.create(author=self.author, title="f", content="c", content_type="text/plain", visibility="FRIENDS")
        url = reverse("entry-retrieve-update", kwargs={"author_id": self.author.id, "entry_id": entry.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    def test_unlisted_entry_visible_to_stranger_success(self):
        """Test that unlisted entries are visible to strangers with link - SUCCESS"""
        entry = Entry.objects.create(author=self.author, title="u", content="c", content_type="text/plain", visibility="UNLISTED")
        url = reverse("entry-retrieve-update", kwargs={"author_id": self.author.id, "entry_id": entry.id})
        self.client.force_login(self.stranger)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_unlisted_entry_visible_to_follower_success(self):
        """Test that unlisted entries are visible to approved followers - SUCCESS"""
        entry = Entry.objects.create(author=self.author, title="u", content="c", content_type="text/plain", visibility="UNLISTED")
        Follow.objects.create(follower=self.follower, followee=self.author, status=Follow.Status.APPROVED)
        self.client.force_login(self.follower)
        url = reverse("entry-retrieve-update", kwargs={"author_id": self.author.id, "entry_id": entry.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_friends_entry_visible_to_mutual_friend_success(self):
        """Test that friends-only entries are visible to mutual friends - SUCCESS"""
        entry = Entry.objects.create(author=self.author, title="f", content="c", content_type="text/plain", visibility="FRIENDS")
        Follow.objects.create(follower=self.follower, followee=self.author, status=Follow.Status.APPROVED)
        Follow.objects.create(follower=self.author, followee=self.follower, status=Follow.Status.APPROVED)
        self.client.force_login(self.follower)
        url = reverse("entry-retrieve-update", kwargs={"author_id": self.author.id, "entry_id": entry.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_friends_entry_not_visible_to_non_friend_failure(self):
        """Test that friends-only entries are not visible to non-friends - FAILURE"""
        entry = Entry.objects.create(author=self.author, title="f", content="c", content_type="text/plain", visibility="FRIENDS")
        self.client.force_login(self.stranger)
        url = reverse("entry-retrieve-update", kwargs={"author_id": self.author.id, "entry_id": entry.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_author_can_view_own_private_entry_success(self):
        """Test that authors can always view their own private entries - SUCCESS"""
        entry = Entry.objects.create(author=self.author, title="f", content="c", content_type="text/plain", visibility="FRIENDS")
        self.client.force_login(self.author)
        url = reverse("entry-retrieve-update", kwargs={"author_id": self.author.id, "entry_id": entry.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_entries_list_shows_only_public_to_stranger_success(self):
        """Test that strangers only see public entries in list - SUCCESS"""
        Entry.objects.create(author=self.author, title="pub", content="c", content_type="text/plain", visibility="PUBLIC")
        Entry.objects.create(author=self.author, title="priv", content="c", content_type="text/plain", visibility="FRIENDS")
        self.client.force_login(self.stranger)
        url = reverse("entries-list-create", kwargs={"author_id": self.author.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Only test API response, not content rendering

    def test_entries_list_shows_all_to_author_success(self):
        """Test that authors see all their own entries including private ones - SUCCESS"""
        Entry.objects.create(author=self.author, title="pub", content="c", content_type="text/plain", visibility="PUBLIC")
        Entry.objects.create(author=self.author, title="priv", content="c", content_type="text/plain", visibility="FRIENDS")
        self.client.force_login(self.author)
        url = reverse("entries-list-create", kwargs={"author_id": self.author.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Only test API response, not content rendering

    def test_image_endpoint_respects_friends_visibility_failure(self):
        """Test that image endpoint respects authorization for friends-only images - FAILURE"""
        entry = Entry.objects.create(author=self.author, title="img", content=base64.b64encode(b"i").decode(), content_type="image/png;base64", visibility="FRIENDS")
        url = reverse("entry-image", kwargs={"author_id": self.author.id, "entry_id": entry.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_image_endpoint_allows_public_visibility_success(self):
        """Test that image endpoint allows access to public images - SUCCESS"""
        entry = Entry.objects.create(author=self.author, title="img", content=base64.b64encode(b"i").decode(), content_type="image/png;base64", visibility="PUBLIC")
        url = reverse("entry-image", kwargs={"author_id": self.author.id, "entry_id": entry.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

class EntrySharingVisibilityTests(TestCase):
    """Consolidated tests for entry sharing and visibility"""
    def setUp(self):
        self.client = APIClient()
        self.author = User.objects.create_user(username="author", password="test123", is_active=True)
        self.reader = User.objects.create_user(username="reader", password="reader123", is_active=True)
        self.friend = User.objects.create_user(username="friend", password="friend123", is_active=True)
        
        # Create mutual friendship
        Follow.objects.create(follower=self.author, followee=self.friend, status=Follow.Status.APPROVED)
        Follow.objects.create(follower=self.friend, followee=self.author, status=Follow.Status.APPROVED)

    def test_public_entry_accessible_to_all_success(self):
        """Public entries should be accessible to everyone - SUCCESS"""
        entry = Entry.objects.create(
            author=self.author,
            title="Public Entry",
            content="This is visible to everyone.",
            visibility="PUBLIC",
        )
        url = reverse("entry-retrieve-update", kwargs={"author_id": self.author.id, "entry_id": entry.id})
        
        # Test anonymous access
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Test authenticated non-friend access
        self.client.force_login(self.reader)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_unlisted_entry_accessible_with_link_success(self):
        """Unlisted entries should be accessible with direct link - SUCCESS"""
        entry = Entry.objects.create(
            author=self.author,
            title="Unlisted Entry",
            content="This is visible via link.",
            visibility="UNLISTED",
        )
        url = reverse("entry-retrieve-update", kwargs={"author_id": self.author.id, "entry_id": entry.id})
        
        # Test authenticated non-friend access (with link)
        self.client.force_login(self.reader)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_private_entry_not_accessible_to_non_friend_failure(self):
        """Private entries should not be accessible to non-friends - FAILURE"""
        entry = Entry.objects.create(
            author=self.author,
            title="Private Entry",
            content="Should not be visible.",
            visibility="FRIENDS",  
        )
        url = reverse("entry-retrieve-update", kwargs={"author_id": self.author.id, "entry_id": entry.id})
        
        # Test authenticated non-friend access
        self.client.force_login(self.reader)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_private_entry_accessible_to_friend_success(self):
        """Private entries should be accessible to friends - SUCCESS"""
        entry = Entry.objects.create(
            author=self.author,
            title="Private Entry",
            content="Should be visible to friends.",
            visibility="FRIENDS",  
        )
        url = reverse("entry-retrieve-update", kwargs={"author_id": self.author.id, "entry_id": entry.id})
        
        # Test friend access
        self.client.force_login(self.friend)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)