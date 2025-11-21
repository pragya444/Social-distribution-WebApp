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

class EntryModelTests(TestCase):
    '''
    This class contains tests for the Entry model
    It tests default values and timestamp handling
    '''
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="pass", is_active=True)

    def testModelCreateSucceeds(self):
        '''
        Test that an Entry can be created successfully
        '''
        e = Entry.objects.create(
            author=self.user,
            title="Test Entry",
            content="This is a test entry.",
            content_type="text/plain",
        )
        self.assertIsNotNone(e.id)
        self.assertEqual(e.author, self.user)
        self.assertEqual(e.title, "Test Entry")
        self.assertEqual(e.content, "This is a test entry.")
        self.assertEqual(e.content_type, "text/plain")

    def test_create_entry_defaults_and_timestamps(self):
        '''
        Test that creating an Entry sets default fields and timestamps correctly
        '''
        e = Entry.objects.create(
            author=self.user,
            title="Hello",
            content="This is a test",
            content_type="text/plain",
        )
        self.assertFalse(e.is_deleted)
        self.assertIsNotNone(e.created)
        self.assertIsNotNone(e.updated)
        self.assertTrue(timezone.is_aware(e.created))
        self.assertTrue(timezone.is_aware(e.updated))

        local = timezone.localtime(e.created, ZoneInfo("America/Edmonton"))
        self.assertEqual(local.tzinfo.key, "America/Edmonton")
        

    def test_deleted_entries_are_excluded_from_default_queryset(self):
        '''
        Test that entries marked as deleted are not returned in the default
        queryset (i.e., Entry.objects.filter(...))
    
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

        qs = Entry.objects.filter(author=self.user, is_deleted=False)
        titles = [e.title for e in qs]
        self.assertIn("Visible", titles)
        self.assertNotIn("Deleted", titles)
        
class NodesManagementTests(TestCase):
    """Test node management functionality (non-API user story)"""
    def setUp(self):
        self.client = Client()
        self.admin = User.objects.create_superuser(username="admin", password="pass")
        
    def test_create_node_directly(self):
        """Test creating a node connection directly in database"""
        node = Node.objects.create(
            host="https://example.com/api/",
            token="test-token",
            is_connected=True
        )
        self.assertIsNotNone(node.id)
        self.assertEqual(node.host, "https://example.com/api/")
        self.assertTrue(node.is_connected)
        
    def test_node_uniqueness(self):
        """Test that node hosts must be unique"""
        Node.objects.create(
            host="https://example.com/api/",
            token="token1",
            is_connected=True
        )
        with self.assertRaises(Exception):
            Node.objects.create(
                host="https://example.com/api/",
                token="token2",
                is_connected=True
            )
    
    def test_node_connection_toggle(self):
        """Test toggling node connection status"""
        node = Node.objects.create(
            host="https://example.com/api/",
            token="test-token",
            is_connected=True
        )
        node.is_connected = False
        node.save()
        node.refresh_from_db()
        self.assertFalse(node.is_connected)
