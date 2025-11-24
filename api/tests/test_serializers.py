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

class AuthorAPIValidationTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username="svt", password="pass", is_active=True)
        self.client.force_login(self.user)

    def test_update_profile_blank_name_rejected_failure(self):
        """Test that API rejects blank display names - FAILURE"""
        url = reverse("profile", kwargs={"author_id": self.user.id})
        data = {"displayName": "   "}
        response = self.client.put(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_update_profile_github_normalization_success(self):
        """Test that API normalizes GitHub usernames to full URLs - SUCCESS"""
        url = reverse("profile", kwargs={"author_id": self.user.id})
        data = {"github": "octocat"}
        response = self.client.put(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Verify normalization happened
        self.user.refresh_from_db()
        self.assertTrue(self.user.github.startswith("https://github.com/"))

    def test_update_profile_valid_data_success(self):
        """Test that API accepts valid profile updates - SUCCESS"""
        url = reverse("profile", kwargs={"author_id": self.user.id})
        data = {
            "displayName": "New Name",
            "description": "New description",
            "profileImage": "https://example.com/pic.jpg",
            "github": "https://github.com/testuser"
        }
        response = self.client.put(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual(self.user.name, "New Name")

    def test_get_author_includes_required_fields_success(self):
        """Test that author API includes required fields - SUCCESS"""
        url = reverse("profile", kwargs={"author_id": self.user.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("type", response.data)
        self.assertIn("id", response.data)
        self.assertIn("displayName", response.data)

class EntryAPIValidationTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username="svt", password="pass", is_active=True)
        self.client.force_login(self.user)

    def test_create_entry_missing_fields_failure(self):
        """Test that API rejects entries with missing required fields - FAILURE"""
        url = reverse("entries-list-create", kwargs={"author_id": self.user.id})
        data = {"title": "x"}  # Missing content, contentType, visibility
        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_entry_invalid_content_type_failure(self):
        """Test that API rejects invalid content types - FAILURE"""
        url = reverse("entries-list-create", kwargs={"author_id": self.user.id})
        data = {
            "title": "x",
            "content": "y", 
            "contentType": "bad",
            "visibility": "PUBLIC"
        }
        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_entry_image_valid_base64_success(self):
        """Test that API accepts valid base64 image content - SUCCESS"""
        url = reverse("entries-list-create", kwargs={"author_id": self.user.id})
        img_data = base64.b64encode(b"fake image data").decode()
        data = {
            "title": "Image Entry",
            "content": img_data,
            "contentType": "image/png;base64",
            "visibility": "PUBLIC"
        }
        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_create_entry_image_invalid_base64_failure(self):
        """Test that API rejects invalid base64 image content - FAILURE"""
        url = reverse("entries-list-create", kwargs={"author_id": self.user.id})
        data = {
            "title": "Image Entry",
            "content": "not-valid-base64",
            "contentType": "image/png;base64",
            "visibility": "PUBLIC"
        }
        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_update_entry_partial_success(self):
        """Test that API supports partial entry updates - SUCCESS"""
        entry = Entry.objects.create(
            author=self.user, 
            title="Original Title", 
            content="Content", 
            content_type="text/plain", 
            visibility="PUBLIC"
        )
        url = reverse("entry-retrieve-update", kwargs={"author_id": self.user.id, "entry_id": entry.id})
        data = {"title": "Updated Title"}
        response = self.client.put(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        entry.refresh_from_db()
        self.assertEqual(entry.title, "Updated Title")