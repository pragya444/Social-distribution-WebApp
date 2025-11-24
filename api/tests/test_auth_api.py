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

class AuthorListAPITests(TestCase):
    """Test author list API endpoint"""
    def setUp(self):
        self.client = APIClient()
        self.user1 = User.objects.create_user(username="user1", password="pass", is_active=True)
        self.user2 = User.objects.create_user(username="user2", password="pass", is_active=True)
        self.user3 = User.objects.create_user(username="user3", password="pass", is_active=True)
    
    def test_author_list_get_success(self):
        """Test getting paginated author list - SUCCESS"""
        url = reverse("author-list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
    def test_author_list_pagination_success(self):
        """Test author list pagination parameters - SUCCESS"""
        url = reverse("author-list") + "?page=1&size=2"
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
    def test_author_list_response_structure_success(self):
        """Test author list response structure - SUCCESS"""
        url = reverse("author-list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data
        self.assertIn("type", data)
        self.assertEqual(data.get("type"), "authors")
        
    def test_author_list_pagination_response_structure_success(self):
        """Test paginated author list response structure - SUCCESS"""
        url = reverse("author-list") + "?page=1&size=2"
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data
        self.assertIn("type", data)
        self.assertEqual(data.get("type"), "authors")
        
    def test_author_list_unauthenticated_access_failure(self):
        """Test author list requires authentication - FAILURE"""
        self.client.logout()
        url = reverse("author-list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        
    def test_author_list_invalid_page_parameter_failure(self):
        """Test author list with invalid page parameter - FAILURE"""
        url = reverse("author-list") + "?page=invalid&size=2"
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        
    def test_author_list_invalid_size_parameter_failure(self):
        """Test author list with invalid size parameter - FAILURE"""
        url = reverse("author-list") + "?page=1&size=invalid"
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)