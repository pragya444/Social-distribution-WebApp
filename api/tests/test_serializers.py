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

class SerializerValidationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="svt", password="pass", is_active=True)

    def test_user_serializer_blank_name_rejected(self):
        """Test that user serializer rejects blank display names"""
        from .serializers import AuthorSerializer
        s = AuthorSerializer(self.user, data={"displayName": "   "}, partial=True)
        self.assertFalse(s.is_valid())

    def test_user_serializer_github_normalization(self):
        """Test that user serializer normalizes GitHub usernames to full URLs"""
        from .serializers import AuthorSerializer
        s = AuthorSerializer(self.user, data={"github": "octocat"}, partial=True, context={"request": type("obj", (), {"scheme": "http", "get_host": lambda: "testserver"})})
        self.assertTrue(s.is_valid(), s.errors)
        u = s.save()
        self.assertTrue(u.github.startswith("https://github.com/"))

    def test_entry_serializer_missing_fields(self):
        """Test that entry serializer rejects entries with missing required fields"""
        from .serializers import EntrySerializer
        s = EntrySerializer(data={"title": "x"})
        self.assertFalse(s.is_valid())

    def test_entry_serializer_invalid_ct(self):
        """Test that entry serializer rejects invalid content types"""
        from .serializers import EntrySerializer
        s = EntrySerializer(data={"title":"x","content":"y","contentType":"bad","visibility":"PUBLIC"})
        self.assertFalse(s.is_valid())

    def test_entry_serializer_image_b64_ok(self):
        """Test that entry serializer accepts valid base64 image content"""
        from .serializers import EntrySerializer
        img = base64.b64encode(b"a").decode()
        s = EntrySerializer(data={"title":"x","content":img,"contentType":"image/png;base64","visibility":"PUBLIC"}, context={"request": type("obj", (), {"user": self.user, "build_absolute_uri": lambda x: "http://test" + x})})
        self.assertTrue(s.is_valid(), s.errors)

    def test_entry_serializer_image_b64_bad(self):
        """Test that entry serializer rejects invalid base64 image content"""
        from .serializers import EntrySerializer
        s = EntrySerializer(data={"title":"x","content":"not-b64","contentType":"image/png;base64","visibility":"PUBLIC"})
        self.assertFalse(s.is_valid())

    def test_entry_serializer_update_partial(self):
        """Test that entry serializer supports partial updates"""
        from .serializers import EntrySerializer
        e = Entry.objects.create(author=self.user, title="t", content="c", content_type="text/plain", visibility="PUBLIC")
        s = EntrySerializer(e, data={"title":"n"}, partial=True)
        self.assertTrue(s.is_valid(), s.errors)
        e2 = s.save()
        self.assertEqual(e2.title, "n")

    def test_user_serializer_update_fields(self):
        """Test that user serializer can update profile fields"""
        from .serializers import AuthorSerializer
        s = AuthorSerializer(self.user, data={"displayName":"New","description":"d","profileImage":"http://x/y.png","github":"https://github.com/x"}, partial=True, context={"request": type("obj", (), {"scheme": "http", "get_host": lambda: "testserver"})})
        self.assertTrue(s.is_valid(), s.errors)
        u = s.save()
        self.assertEqual(u.name, "New")

    def test_user_serializer_followers_fields_present(self):
        """Test that user serializer includes required author fields"""
        from .serializers import AuthorSerializer
        s = AuthorSerializer(self.user, context={"request": type("obj", (), {"scheme": "http", "get_host": lambda: "testserver"})})
        data = s.data
        self.assertIn("type", data)
        self.assertIn("id", data)
        self.assertIn("displayName", data)
