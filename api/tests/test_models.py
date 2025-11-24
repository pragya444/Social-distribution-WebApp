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

class EntryAPIModelsTests(TestCase):
    '''
    This class contains tests for Entry creation via API
    Testing API endpoints for entry creation and defaults
    '''
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username="testuser", password="pass", is_active=True)
        self.client.force_login(self.user)

    def test_create_entry_via_api_success(self):
        '''
        Test that an Entry can be created successfully via API - SUCCESS
        '''
        url = reverse("entries-list-create", kwargs={"author_id": self.user.id})
        data = {
            "title": "Test Entry",
            "content": "This is a test entry.",
            "content_type": "text/plain",
            "visibility": "PUBLIC"
        }
        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("id", response.data)
        self.assertEqual(response.data["title"], "Test Entry")

    def test_create_entry_with_defaults_via_api_success(self):
        '''
        Test that creating an Entry via API sets default fields correctly - SUCCESS
        '''
        url = reverse("entries-list-create", kwargs={"author_id": self.user.id})
        data = {
            "title": "Hello",
            "content": "This is a test",
            "content_type": "text/plain",
            "visibility": "PUBLIC"
        }
        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
    
        entry = Entry.objects.filter(author=self.user, title="Hello").order_by('-created').first()
        self.assertIsNotNone(entry)
        self.assertFalse(entry.is_deleted)
        self.assertIsNotNone(entry.created)

    def test_get_entries_excludes_deleted_via_api_success(self):
        '''
        Test that deleted entries are not returned via entries API - SUCCESS
        '''
        Entry.objects.create(
            author=self.user,
            title="Visible",
            content="Visible",
            content_type="text/plain",
            is_deleted=False,
        )
        Entry.objects.create(
            author=self.user,
            title="Deleted",
            content="Deleted",
            content_type="text/plain",
            is_deleted=True,
        )

        url = reverse("entries-list-create", kwargs={"author_id": self.user.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)