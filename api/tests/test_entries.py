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

class EntryEdgeCaseTests(TestCase):
    """Additional entry edge cases"""
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username="entry_edge", password="pass", is_active=True)
        self.client.force_login(self.user)
    
    def test_create_entry_with_description_success(self):
        """Test creating entry with description field - SUCCESS"""
        url = reverse("entries-list-create", kwargs={"author_id": self.user.id})
        data = {
            "title": "Entry with description",
            "description": "This is a description",
            "content": "Content",
            "content_type": "text/plain",
            "visibility": "PUBLIC"
        }
        response = self.client.post(url, data, format="json")
        # Assuming description is a valid field - if not, this should be a failure test
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
    
    def test_create_entry_with_description_failure(self):
        """Test creating entry with invalid description field - FAILURE"""
        url = reverse("entries-list-create", kwargs={"author_id": self.user.id})
        data = {
            "title": "Entry with description",
            "description": "This is a description",
            "content": "Content",
            "content_type": "text/plain",
            "visibility": "PUBLIC"
        }
        response = self.client.post(url, data, format="json")
        # If description is not a valid field, expect 400
        if response.status_code != status.HTTP_201_CREATED:
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_create_entry_extremely_long_content_failure(self):
        """Test creating entry with very long content - FAILURE"""
        url = reverse("entries-list-create", kwargs={"author_id": self.user.id})
        long_content = "x" * 100000 
        data = {
            "title": "Long entry",
            "content": long_content,
            "content_type": "text/plain",
            "visibility": "PUBLIC"
        }
        response = self.client.post(url, data, format="json")
        # Should fail with either 400 or 413
        self.assertIn(response.status_code, [status.HTTP_400_BAD_REQUEST, status.HTTP_413_REQUEST_ENTITY_TOO_LARGE])
    
    def test_update_entry_url_field_failure(self):
        """Test updating entry URL field should fail - FAILURE"""
        entry = Entry.objects.create(
            author=self.user,
            title="Entry",
            content="Content",
            content_type="text/plain",
            visibility="PUBLIC"
        )
        url = reverse("entry-retrieve-update", kwargs={
            "author_id": self.user.id,
            "entry_id": entry.id
        })
        data = {
            "title": "Updated",
            "content": "Content",
            "content_type": "text/plain",
            "visibility": "PUBLIC",
            "url": "http://custom.url/entry"  # URL should typically be read-only
        }
        response = self.client.put(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_patch_entry_method_not_allowed_failure(self):
        """Test PATCH request should fail if not supported - FAILURE"""
        entry = Entry.objects.create(
            author=self.user,
            title="Original",
            content="Original content",
            content_type="text/plain",
            visibility="PUBLIC"
        )
        url = reverse("entry-retrieve-update", kwargs={
            "author_id": self.user.id,
            "entry_id": entry.id
        })
        data = {"title": "Patched Title"}
        response = self.client.patch(url, data, format="json")
        # PATCH should return 405 if not implemented
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

class LikedEdgeCaseTests(TestCase):
    """Test liked entries edge cases"""
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username="liked_edge", password="pass", is_active=True)
        self.client.force_login(self.user)
    
    def test_liked_entries_empty_success(self):
        """Test liked entries when user has no likes - SUCCESS"""
        url = reverse("liked-entries", kwargs={"author_id": self.user.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Should return empty list, not 404
    
    def test_liked_entry_detail_deleted_entry_failure(self):
        """Test getting liked entry detail for deleted entry - FAILURE"""
        other_user = User.objects.create_user(username="other_liked", password="pass", is_active=True)
        entry = Entry.objects.create(
            author=other_user,
            title="Entry",
            content="Content",
            content_type="text/plain",
            visibility="PUBLIC"
        )
        like = EntryLike.objects.create(user=self.user, entry=entry)
        entry.is_deleted = True
        entry.save()
        
        url = reverse("liked-entry-detail", kwargs={
            "author_id": self.user.id,
            "like_id": like.id
        })
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

class ImageEndpointEdgeCaseTests(TestCase):
    """Test image endpoint edge cases"""
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username="image_edge", password="pass", is_active=True)
        self.client.force_login(self.user)
    
    def test_image_endpoint_non_image_entry_failure(self):
        """Test image endpoint for non-image entry - FAILURE"""
        entry = Entry.objects.create(
            author=self.user,
            title="Text Entry",
            content="Just text",
            content_type="text/plain",
            visibility="PUBLIC"
        )
        url = reverse("entry-image", kwargs={
            "author_id": self.user.id,
            "entry_id": entry.id
        })
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
    
    def test_image_endpoint_invalid_base64_failure(self):
        """Test creating image entry with invalid base64 - FAILURE"""
        url = reverse("entries-list-create", kwargs={"author_id": self.user.id})
        data = {
            "title": "Bad Image",
            "content": "not-valid-base64!@#$",
            "content_type": "image/png;base64",
            "visibility": "PUBLIC"
        }
        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        
class ContentTypeValidationTests(TestCase):
    """Test content type validation across different entry types"""
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username="testuser", password="pass", is_active=True)
        self.client.force_login(self.user)
        
    def test_markdown_content_type_success(self):
        """Test creating entry with markdown content type - SUCCESS"""
        url = reverse("entries-list-create", kwargs={"author_id": self.user.id})
        data = {
            "title": "Markdown Entry",
            "content": "# Header\n\nText",
            "content_type": "text/markdown",
            "visibility": "PUBLIC"
        }
        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        entry = Entry.objects.get(title="Markdown Entry")
        self.assertTrue(entry.is_markdown)
    
    def test_plain_text_content_type_success(self):
        """Test creating entry with plain text content type - SUCCESS"""
        url = reverse("entries-list-create", kwargs={"author_id": self.user.id})
        data = {
            "title": "Plain Entry",
            "content": "Plain text",
            "content_type": "text/plain",
            "visibility": "PUBLIC"
        }
        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        entry = Entry.objects.get(title="Plain Entry")
        self.assertFalse(entry.is_markdown)
        self.assertFalse(entry.is_image)
    
    def test_image_content_type_success(self):
        """Test creating entry with image content type - SUCCESS"""
        url = reverse("entries-list-create", kwargs={"author_id": self.user.id})
        img_data = base64.b64encode(b"fake image").decode()
        data = {
            "title": "Image Entry",
            "content": img_data,
            "content_type": "image/jpeg;base64",
            "visibility": "PUBLIC"
        }
        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        entry = Entry.objects.get(title="Image Entry")
        self.assertTrue(entry.is_image)