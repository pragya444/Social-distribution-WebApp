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

class ProfileAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username="testuser", password="pass", is_active=True)
        self.other_user = User.objects.create_user(username="otheruser", password="pass", is_active=True)
        self.client.force_login(self.user)

    def test_retrieve_profile(self):
        """Test user story: Consistent identity per node, public profile page"""
        url = reverse("profile", kwargs={"author_id": self.user.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(
            self.user.username in response.content.decode() 
            or f"@{self.user.username.lower()}" in response.content.decode()
            or "Anonymous" in response.content.decode(),   # fallback if name empty
            f"Expected username or displayName in response, got:\n{response.content.decode()}"
        )
        self.assertIsNotNone(self.user.url)
        self.assertIn(str(self.user.id), self.user.url)

    def test_edit_profile(self):
        """Test user story: Edit profile (name, description, picture, GitHub), manage profile via browser"""
        self.client.force_login(self.user)  
        url = reverse("profile", kwargs={"author_id": self.user.id})
        csrf_response = self.client.get(url)        
        csrf_token = csrf_response.cookies.get('csrftoken', '') 
        data = {
            "displayName": "New Name",
            "description": "Updated description",
            "github": "https://github.com/testuser",
            "profileImage": "https://example.com/pic.jpg"
        }
        response = self.client.put(url, data, format='json', HTTP_X_CSRFTOKEN=csrf_token)
        self.user.refresh_from_db()
        self.assertEqual(self.user.name, "New Name")
        self.assertEqual(self.user.description, "Updated description")
        self.assertEqual(self.user.github, "https://github.com/testuser")
        self.assertEqual(self.user.profile_picture, "https://example.com/pic.jpg")
        
    
    def test_profile_edit_no_login(self):
        """Test user story: Prevent profile editing when not logged in"""
        self.client.logout()
        url = reverse("profile", kwargs={"author_id": self.user.id})
        response = self.client.put(url, {"displayName": "Hacked"}, format='json')
        self.assertIn(response.status_code, [status.HTTP_302_FOUND, status.HTTP_403_FORBIDDEN])

    def test_profile_edit_unauthorized_user(self):
        """Test user story: Prevent profile editing by other users"""
        self.client.force_login(self.other_user)
        url = reverse("profile", kwargs={"author_id": self.user.id})
        data = {
            "displayName": "New Name",
            "description": "Updated description",
            "github": "https://github.com/testuser",
            "profileImage": "https://example.com/pic.jpg"
        }
        response = self.client.put(url, data, format='json')
        self.assertIn(response.status_code, [status.HTTP_403_FORBIDDEN, status.HTTP_302_FOUND])

    def check_user_not_found(self):
        """Test user story: Handle non-existent users gracefully"""
        url = reverse("profile", kwargs={"author_id": "nonexistent"})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)