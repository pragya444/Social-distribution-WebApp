from django.test import TestCase
from django.urls import reverse
from django.test import Client
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

class EntryAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()       
        self.user = User.objects.create_user(username="testuser", password="pass", is_active=True)
        self.other_user = User.objects.create_user(username="otheruser", password="pass", is_active=True)
        self.client.force_login(self.user)      

    def test_create_entry_success(self):
        """Test user story: Create entries, make entries public, CommonMark support - SUCCESS"""
        url = reverse("entries-list-create", kwargs={"author_id": self.user.id})
        data = {
            "title": "Test Entry",
            "content": "# Hello\nThis is a *test*",
            "content_type": "text/markdown",
            "visibility": "PUBLIC"
        }
        csrf_response = self.client.get(url)
        csrf_token = csrf_response.cookies.get('csrftoken', '')
        response = self.client.post(url, data, format="json", HTTP_X_CSRFTOKEN=csrf_token)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        entry = Entry.objects.get(title="Test Entry")
        self.assertEqual(entry.author, self.user)
        self.assertIn(entry.content_type, ["", "text/markdown"])  
        self.assertEqual(entry.visibility, "PUBLIC")
        self.assertIsNotNone(entry.is_markdown)

    def test_create_entry_not_logged_in_failure(self):
        """Test user story: Prevent entry creation when not logged in - FAILURE"""
        self.client.logout()
        url = reverse("entries-list-create", kwargs={"author_id": self.user.id})
        data = {
            "title": "Test Entry",
            "content": "Content",
            "content_type": "text/plain",
            "visibility": "PUBLIC"
        }
        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_create_entry_with_image_link_success(self):
        """Test user story: CommonMark entries can link to images - SUCCESS"""
        url = reverse("entries-list-create", kwargs={"author_id": self.user.id})
        data = {
            "title": "Image Entry",
            "content": "![Image](https://example.com/image.jpg)",
            "content_type": "text/markdown",
            "visibility": "PUBLIC"
        }
        csrf_response = self.client.get(url)
        csrf_token = csrf_response.cookies.get('csrftoken', '')
        response = self.client.post(url, data, format="json", HTTP_X_CSRFTOKEN=csrf_token)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        entry = Entry.objects.get(title="Image Entry")
        self.assertIn("https://example.com/image.jpg", entry.content)

    def test_edit_entry_browser_success(self):
        """Test user story: Manage/author entries via web browser - SUCCESS"""
        entry = Entry.objects.create(
            author=self.user,
            title="Original",
            content="Original content",
            content_type="text/plain",
            visibility="PUBLIC"
        )
        url = reverse("entry-retrieve-update", kwargs={"author_id": self.user.id, "entry_id": entry.id})
        csrf_response = self.client.get(url)
        csrf_token = csrf_response.cookies.get('csrftoken', '')
        data = {
            "title": "Updated",
            "content": "Updated content",
            "content_type": "text/plain",
            "visibility": "PUBLIC"
        }
        response = self.client.post(url, data, follow=True, HTTP_X_CSRFTOKEN=csrf_token)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        entry.refresh_from_db()
        self.assertEqual(entry.title, "Updated")
        self.assertEqual(entry.content, "Updated content")

    def test_edit_entry_api_success(self):
        """Test user story: Edit entries locally - SUCCESS"""
        entry = Entry.objects.create(
            author=self.user,
            title="Original",
            content="Original content",
            content_type="text/plain",
            visibility="PUBLIC"
        )
        url = reverse("entry-retrieve-update", kwargs={"author_id": self.user.id, "entry_id": entry.id})
        data = {
            "title": "Updated",
            "content": "Updated content",
            "content_type": "text/plain",
            "visibility": "PUBLIC"
        }
        csrf_response = self.client.get(url)
        csrf_token = csrf_response.cookies.get('csrftoken', '')
        response = self.client.put(url, data, format="json", HTTP_X_CSRFTOKEN=csrf_token)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        entry.refresh_from_db()
        self.assertEqual(entry.title, "Updated")
        self.assertEqual(entry.content, "Updated content")

    def test_unauthorized_edit_entry_failure(self):
        """Test user story: Other authors cannot modify my entries - FAILURE"""
        entry = Entry.objects.create(
            author=self.user,
            title="Test Entry",
            content="Content",
            content_type="text/plain",
            visibility="PUBLIC"
        )
        self.client.force_login(self.other_user)
        url = reverse("entry-retrieve-update", kwargs={"author_id": self.user.id, "entry_id": entry.id})
        data = {"title": "Hacked"}
        response = self.client.put(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        entry.refresh_from_db()
        self.assertEqual(entry.title, "Test Entry")

    def test_delete_entry_success(self):
        """Test user story: Delete own entries locally - SUCCESS"""
        entry = Entry.objects.create(
            author=self.user,
            title="Test Entry",
            content="Content",
            content_type="text/plain",
            visibility="PUBLIC"
        )
        url = reverse("entry-retrieve-update", kwargs={"author_id": self.user.id, "entry_id": entry.id})
        csrf_response = self.client.get(url)
        csrf_token = csrf_response.cookies.get('csrftoken', '')
        response = self.client.delete(url, follow=True, HTTP_X_CSRFTOKEN=csrf_token)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        entry.refresh_from_db()
        self.assertTrue(entry.is_deleted)

    def test_unauthorized_delete_entry_failure(self):
        """Test user story: Other authors cannot delete my entries - FAILURE"""
        entry = Entry.objects.create(
            author=self.user,
            title="Test Entry",
            content="Content",
            content_type="text/plain",
            visibility="PUBLIC"
        )
        self.client.force_login(self.other_user)
        url = reverse("entry-retrieve-update", kwargs={"author_id": self.user.id, "entry_id": entry.id})
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        entry.refresh_from_db()
        self.assertFalse(entry.is_deleted)
    
    def test_author_sees_own_entries_success(self):
        """Test user story: Entries visible to me until deleted - SUCCESS"""
        entry = Entry.objects.create(
            author=self.user,
            title="Test Entry",
            content="Content",
            content_type="text/plain",
            visibility="PUBLIC"
        )
        url = reverse("entries-list-create", kwargs={"author_id": self.user.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertContains(response, "Test Entry")

class ShareAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username="testuser", password="pass", is_active=True)
        self.client.force_login(self.user)
        self.other_user = User.objects.create_user(username="otheruser", password="pass", is_active=True)

    def test_share_unlisted_entry_success(self):
        """Test user story: Get link to unlisted entry - SUCCESS"""
        entry = Entry.objects.create(
            author=self.user,
            title="Shared Entry",
            content="Content",
            content_type="text/plain",
            visibility="UNLISTED"
        )
        url = reverse("entry-retrieve-update", kwargs={"author_id": self.user.id, "entry_id": entry.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertContains(response, "Shared Entry")
        
    def test_share_public_entry_as_other_user_success(self):
        """Test user story: Share link works for public entries - SUCCESS"""
        entry = Entry.objects.create(
            author=self.user,
            title="Private Entry",
            content="Content",
            content_type="text/plain",
            visibility="PUBLIC"
        )
        url = reverse("entry-retrieve-update", kwargs={"author_id": self.user.id, "entry_id": entry.id})
        self.client.force_login(self.other_user)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_share_friends_entry_as_non_friend_failure(self):
        """Test user story: Friends-only entries not accessible to non-friends - FAILURE"""
        entry = Entry.objects.create(
            author=self.user,
            title="Private Entry",
            content="Content",
            content_type="text/plain",
            visibility="FRIENDS"
        )
        url = reverse("entry-retrieve-update", kwargs={"author_id": self.user.id, "entry_id": entry.id})
        self.client.force_login(self.other_user)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

class EntryAPIEdgeTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.author = User.objects.create_user(username="author_ec", password="pass", is_active=True)
        self.other = User.objects.create_user(username="other_ec", password="pass", is_active=True)
        self.client.force_login(self.author)

    def test_create_entry_missing_fields_failure(self):
        """Test that creating an entry without required fields returns 400 - FAILURE"""
        url = reverse("entries-list-create", kwargs={"author_id": self.author.id})
        payload = {"title": "t"}  
        response = self.client.post(url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_entry_invalid_content_type_failure(self):
        """Test that creating an entry with invalid content type returns 400 - FAILURE"""
        url = reverse("entries-list-create", kwargs={"author_id": self.author.id})
        payload = {"title": "t", "content": "x", "content_type": "application/pdf", "visibility": "PUBLIC"}
        response = self.client.post(url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_image_entry_invalid_base64_failure(self):
        """Test that creating an image entry requires valid base64 content - FAILURE"""
        url = reverse("entries-list-create", kwargs={"author_id": self.author.id})
        payload = {"title": "img", "content": "not_base64***", "content_type": "image/png;base64", "visibility": "PUBLIC"}
        response = self.client.post(url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_image_entry_valid_base64_success(self):
        """Test that creating an image entry with valid base64 succeeds - SUCCESS"""
        url = reverse("entries-list-create", kwargs={"author_id": self.author.id})
        b64 = base64.b64encode(b"hello").decode()
        payload = {"title": "img", "content": b64, "content_type": "image/png;base64", "visibility": "PUBLIC"}
        response = self.client.post(url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_create_entry_as_other_user_failure(self):
        """Test that only the author can create entries in their own stream - FAILURE"""
        self.client.force_login(self.other)
        url = reverse("entries-list-create", kwargs={"author_id": self.author.id})
        payload = {"title": "x", "content": "y", "content_type": "text/plain", "visibility": "PUBLIC"}
        response = self.client.post(url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_update_entry_as_other_user_failure(self):
        """Test that only the author can update their own entries - FAILURE"""
        entry = Entry.objects.create(author=self.author, title="t", content="c", content_type="text/plain", visibility="PUBLIC")
        self.client.force_login(self.other)
        url = reverse("entry-retrieve-update", kwargs={"author_id": self.author.id, "entry_id": entry.id})
        response = self.client.put(url, {"title":"n","content":"c","content_type":"text/plain","visibility":"PUBLIC"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_update_entry_to_image_invalid_base64_failure(self):
        """Test that changing entry content type to image requires valid base64 - FAILURE"""
        entry = Entry.objects.create(author=self.author, title="t", content="c", content_type="text/plain", visibility="PUBLIC")
        url = reverse("entry-retrieve-update", kwargs={"author_id": self.author.id, "entry_id": entry.id})
        response = self.client.put(url, {"title":"t","content_type":"image/jpeg;base64","content":"bad$$$","visibility":"PUBLIC"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_update_entry_to_image_valid_base64_success(self):
        """Test that updating entry to image with valid base64 succeeds - SUCCESS"""
        entry = Entry.objects.create(author=self.author, title="t", content="c", content_type="text/plain", visibility="PUBLIC")
        url = reverse("entry-retrieve-update", kwargs={"author_id": self.author.id, "entry_id": entry.id})
        img = base64.b64encode(b"img").decode()
        response = self.client.put(url, {"title":"t","content_type":"image/png;base64","content":img,"visibility":"PUBLIC"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_delete_entry_as_other_user_failure(self):
        """Test that only the author can delete their own entries - FAILURE"""
        entry = Entry.objects.create(author=self.author, title="t", content="c", content_type="text/plain", visibility="PUBLIC")
        self.client.force_login(self.other)
        url = reverse("entry-retrieve-update", kwargs={"author_id": self.author.id, "entry_id": entry.id})
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_delete_entry_as_author_success(self):
        """Test that the author can successfully delete their own entries - SUCCESS"""
        entry = Entry.objects.create(author=self.author, title="t", content="c", content_type="text/plain", visibility="PUBLIC")
        url = reverse("entry-retrieve-update", kwargs={"author_id": self.author.id, "entry_id": entry.id})
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

class EntryByFQIDAPITests(TestCase):
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
        
    def test_get_entry_by_fqid_success(self):
        """Test getting entry by FQID - SUCCESS"""
        import urllib.parse
        entry_fqid = urllib.parse.quote(self.entry.url, safe='')
        url = reverse("entry-by-fqid", kwargs={"entry_fqid": entry_fqid})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

class EntryImageAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username="testuser", password="pass", is_active=True)
        self.client.force_login(self.user)
        
    def test_get_entry_image_success(self):
        """Test image entry binary endpoint - SUCCESS"""
        img_content = base64.b64encode(b"fake image data").decode()
        entry = Entry.objects.create(
            author=self.user,
            title="Image Entry",
            content=img_content,
            content_type="image/png;base64",
            visibility="PUBLIC"
        )
        
        url = reverse("entry-image", kwargs={"author_id": self.user.id, "entry_id": entry.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

class ImageAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username="testuser", password="pass", is_active=True)
        self.client.force_login(self.user)

    def test_retrieve_image_entry_success(self):
        """Test endpoint: Retrieve image content - SUCCESS"""
        entry = Entry.objects.create(
            author=self.user,
            title="Image Entry",
            content="base64encodeddata",
            content_type="image/png;base64",
            visibility="PUBLIC"
        )
        url = reverse("entry-image", kwargs={"author_id": self.user.id, "entry_id": entry.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

class LikedAPITests(TestCase):
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
        
    def test_get_liked_entries_list_success(self):
        """Test getting list of liked entries - SUCCESS"""
        EntryLike.objects.create(user=self.user, entry=self.entry)
        
        url = reverse("liked-entries", kwargs={"author_id": self.user.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)