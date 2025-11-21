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

class AuthorListAPITests(TestCase):
    """Test author list API endpoint"""
    def setUp(self):
        self.client = APIClient()
        self.user1 = User.objects.create_user(username="user1", password="pass", is_active=True)
        self.user2 = User.objects.create_user(username="user2", password="pass", is_active=True)
        self.user3 = User.objects.create_user(username="user3", password="pass", is_active=True)
    
    def test_author_list_get(self):
        """Test getting paginated author list"""
        url = reverse("author-list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
    def test_author_list_pagination(self):
        """Test author list pagination parameters"""
        url = reverse("author-list") + "?page=1&size=2"
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        if response.accepted_renderer.format == 'json':
            data = response.data
            self.assertIn("type", data)
            self.assertEqual(data.get("type"), "authors")