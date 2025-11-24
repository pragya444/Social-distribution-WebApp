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

class CommentByFQIDAPITests(TestCase):
    """Test comment operations by FQID"""
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username="testuser", password="pass", is_active=True)
        self.entry = Entry.objects.create(
            author=self.user,
            title="Test Entry",
            content="Content",
            content_type="text/plain",
            visibility="PUBLIC"
        )
        self.client.force_login(self.user)

class CommentedAPITests(TestCase):
    """Test the commented API endpoints"""
    def setUp(self):
        self.client = APIClient()
        self.author = User.objects.create_user(username="author_commented", password="pass", is_active=True)
        self.other_user = User.objects.create_user(username="commenter", password="pass", is_active=True)
        self.entry = Entry.objects.create(
            author=self.author,
            title="Test Entry",
            content="Content",
            content_type="text/plain",
            visibility="PUBLIC"
        )
        self.client.force_login(self.other_user)
    
    def test_commented_list_success(self):
        """Test listing all comments made by an author - SUCCESS"""
        comment = Comment.objects.create(
            entry=self.entry,
            author=self.other_user,
            comment="My comment",
            content_type="text/plain"
        )
        url = reverse("commented-list", kwargs={"author_id": self.other_user.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    def test_commented_list_empty_success(self):
        """Test commented list when author has no comments - SUCCESS"""
        url = reverse("commented-list", kwargs={"author_id": self.other_user.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    def test_commented_detail_success(self):
        """Test getting specific comment details - SUCCESS"""
        comment = Comment.objects.create(
            entry=self.entry,
            author=self.other_user,
            comment="Detailed comment",
            content_type="text/plain"
        )
        url = reverse("commented-detail", kwargs={"author_id": self.other_user.id, "comment_id": comment.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    def test_commented_detail_not_found_failure(self):
        """Test getting non-existent comment details - FAILURE"""
        url = reverse("commented-detail", kwargs={"author_id": self.other_user.id, "comment_id": 9999})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

class CommentsByFQIDTests(TestCase):
    """Test entry comments by FQID endpoints"""
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username="fqid_user", password="pass", is_active=True)
        self.entry = Entry.objects.create(
            author=self.user,
            title="FQID Entry",
            content="Content",
            content_type="text/plain",
            visibility="PUBLIC"
        )
        self.client.force_login(self.user)

class CommentAndLikeAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username="testuser", password="pass", is_active=True)
        self.other_user = User.objects.create_user(username="otheruser", password="pass", is_active=True)
        self.entry = Entry.objects.create(
            author=self.other_user,
            title="Test Entry",
            content="Content",
            content_type="text/plain",
            visibility="PUBLIC"
        )
        self.client.force_login(self.user)

    def test_like_entry_success(self):
        """Test user story: Like accessible entries - SUCCESS"""
        url = reverse("entry-likes", kwargs={"author_id": self.other_user.id, "entry_id": self.entry.id})
        csrf_response = self.client.get(url)
        csrf_token = csrf_response.cookies.get('csrftoken', '')
        response = self.client.post(url, HTTP_X_CSRFTOKEN=csrf_token)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        like = EntryLike.objects.get(user=self.user, entry=self.entry)
        self.assertEqual(like.user, self.user)

    def test_like_entry_already_liked_failure(self):
        """Test user story: Liking already liked entry returns success - SUCCESS"""
        EntryLike.objects.create(user=self.user, entry=self.entry)
        url = reverse("entry-likes", kwargs={"author_id": self.other_user.id, "entry_id": self.entry.id})
        csrf_response = self.client.get(url)
        csrf_token = csrf_response.cookies.get('csrftoken', '')
        response = self.client.post(url, HTTP_X_CSRFTOKEN=csrf_token)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_get_comment_likes_success(self):
        """Test endpoint: Get comment likes - SUCCESS"""
        comment = Comment.objects.create(
            entry=self.entry,
            author=self.other_user,
            comment="Nice post!",
            content_type="text/plain"
        )
        url = reverse("comment-likes", kwargs={
            "author_id": self.other_user.id,
            "entry_id": self.entry.id,
            "comment_id": comment.id
        })
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_like_comment_success(self):
        """Test endpoint: Like comments - SUCCESS"""
        comment = Comment.objects.create(
            entry=self.entry,
            author=self.other_user,
            comment="Nice post!",
            content_type="text/plain"
        )
        url = reverse("comment-likes", kwargs={
            "author_id": self.other_user.id,
            "entry_id": self.entry.id,
            "comment_id": comment.id
        })
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

class CommentLikesByFQIDTests(TestCase):
    """Test comment likes by FQID"""
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username="testuser", password="pass", is_active=True)
        self.entry = Entry.objects.create(
            author=self.user,
            title="Test Entry",
            content="Content",
            content_type="text/plain",
            visibility="PUBLIC"
        )
        self.comment = Comment.objects.create(
            entry=self.entry,
            author=self.user,
            comment="Test comment",
            content_type="text/plain"
        )
        self.client.force_login(self.user)
        
    def test_comment_likes_by_fqid_success(self):
        """Test getting comment likes by FQID - SUCCESS"""
        import urllib.parse
        comment_fqid = urllib.parse.quote(self.comment.fqid or self.comment.api_id(), safe='')
        url = reverse("comment-likes-fqid", kwargs={
            "author_id": self.user.id,
            "entry_id": self.entry.id,
            "comment_fqid": comment_fqid
        })
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    def test_post_comment_like_by_fqid_success(self):
        """Test posting comment like by FQID - SUCCESS"""
        import urllib.parse
        comment_fqid = urllib.parse.quote(self.comment.fqid or self.comment.api_id(), safe='')
        url = reverse("comment-likes-fqid", kwargs={
            "author_id": self.user.id,
            "entry_id": self.entry.id,
            "comment_fqid": comment_fqid
        })
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)