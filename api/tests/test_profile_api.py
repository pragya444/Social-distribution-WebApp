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

class ProfileAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username="testuser", password="pass", is_active=True)
        self.other_user = User.objects.create_user(username="otheruser", password="pass", is_active=True)
        self.client.force_login(self.user)

    def test_retrieve_profile_api_success(self):
        """Test user story: Consistent identity per node - SUCCESS"""
        url = reverse("profile", kwargs={"author_id": self.user.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Check API response structure, not HTML content
        self.assertIn("id", response.data)
        self.assertIn("displayName", response.data)
        self.assertIn("url", response.data)
        self.assertIn(str(self.user.id), response.data["id"])

    def test_edit_profile_api_success(self):
        """Test user story: Edit profile via API - SUCCESS"""
        url = reverse("profile", kwargs={"author_id": self.user.id})
        data = {
            "displayName": "New Name",
            "description": "Updated description",
            "github": "https://github.com/testuser",
            "profileImage": "https://example.com/pic.jpg"
        }
        response = self.client.put(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual(self.user.name, "New Name")
        self.assertEqual(self.user.description, "Updated description")
        self.assertEqual(self.user.github, "https://github.com/testuser")
        self.assertEqual(self.user.profile_picture, "https://example.com/pic.jpg")

    def test_edit_profile_api_invalid_data_failure(self):
        """Test user story: Edit profile with invalid data via API - FAILURE"""
        url = reverse("profile", kwargs={"author_id": self.user.id})
        data = {
            "displayName": "",  # Invalid empty name
            "github": "invalid-url"  # Invalid URL format
        }
        response = self.client.put(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_profile_edit_unauthenticated_failure(self):
        """Test user story: Prevent profile editing when not logged in - FAILURE"""
        self.client.logout()
        url = reverse("profile", kwargs={"author_id": self.user.id})
        response = self.client.put(url, {"displayName": "Hacked"}, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_profile_edit_unauthorized_user_failure(self):
        """Test user story: Prevent profile editing by other users - FAILURE"""
        self.client.force_login(self.other_user)
        url = reverse("profile", kwargs={"author_id": self.user.id})
        data = {
            "displayName": "New Name",
            "description": "Updated description",
            "github": "https://github.com/testuser",
            "profileImage": "https://example.com/pic.jpg"
        }
        response = self.client.put(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_retrieve_nonexistent_profile_failure(self):
        """Test user story: Handle non-existent users gracefully - FAILURE"""
        url = reverse("profile", kwargs={"author_id": "999999"})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_retrieve_other_user_profile_success(self):
        """Test user story: View other user profiles - SUCCESS"""
        url = reverse("profile", kwargs={"author_id": self.other_user.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("id", response.data)
        self.assertIn("displayName", response.data)
        self.assertIn(str(self.other_user.id), response.data["id"])

    def test_partial_profile_update_success(self):
        """Test user story: Partial profile updates via API - SUCCESS"""
        url = reverse("profile", kwargs={"author_id": self.user.id})
        data = {
            "displayName": "Partial Update Name"
        }
        response = self.client.put(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual(self.user.name, "Partial Update Name")

class AuthorListAPITests(TestCase):
    """Test author listing API functionality"""
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username="testuser", password="pass", is_active=True)
        self.other_user = User.objects.create_user(username="otheruser", password="pass", is_active=True)
        self.client.force_login(self.user)

    def test_get_author_list_success(self):
        """Test user story: Browse authors via API - SUCCESS"""
        url = reverse("author-list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("type", response.data)
        self.assertEqual(response.data["type"], "authors")

    def test_get_author_list_pagination_success(self):
        """Test user story: Paginated author list via API - SUCCESS"""
        url = reverse("author-list") + "?page=1&size=10"
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_get_author_list_unauthenticated_failure(self):
        """Test user story: Author list requires authentication - FAILURE"""
        self.client.logout()
        url = reverse("author-list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)