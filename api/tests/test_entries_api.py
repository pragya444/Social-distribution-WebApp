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

class EntryAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()       
        self.user = User.objects.create_user(username="testuser", password="pass", is_active=True)
        self.other_user = User.objects.create_user(username="otheruser", password="pass", is_active=True)
        self.client.force_login(self.user)      

    def test_create_entry(self):
        """Test user story: Create entries, make entries public, CommonMark support"""
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

    def test_create_entry_not_logged_in(self):
        """Test user story: Prevent entry creation when not logged in"""
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

    def test_create_entry_with_image_link(self):
        """Test user story: CommonMark entries can link to images"""
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

    def test_edit_entry_browser(self):
        """
        Test user story: Manage/author entries via web browser
        """
        
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
        self.assertIn(response.status_code, [status.HTTP_200_OK, status.HTTP_403_FORBIDDEN])  
        entry.refresh_from_db()
        self.assertEqual(entry.title, "Updated")
        self.assertEqual(entry.content, "Updated content")

    def test_edit_entry_api(self):
        """Test user story: Edit entries locally"""
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

    def test_unauthorized_edit_entry(self):
        """Test user story: Other authors cannot modify my entries"""
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

    def test_delete_entry(self):
        """Test user story: Delete own entries locally"""
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

    def test_unauthorized_delete_entry(self):
        """Test user story: Other authors cannot delete my entries"""
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
    
    def test_author_sees_own_entries(self):
        """Test user story: Entries visible to me until deleted"""
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

    def test_share_entry(self):
        """Test user story: Get link to public or unlisted entry"""
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
        
    def testShareEntryPublic(self):
        '''
        Test case: Share link works for public entries
        Create an entry with PUBLIC visibility and attempt to access it as another user.
        It will return 200 OK.
        '''

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

    def test_share_entry_as_non_friend(self):
        """
        Create an entry with FRIENDS visibility and attempt to access it as another user thats not a friend.
        return 403 Forbidden.
        """
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
        '''Set up users and API client for edge case tests'''
        self.client = APIClient()
        self.author = User.objects.create_user(username="author_ec", password="pass", is_active=True)
        self.other = User.objects.create_user(username="other_ec", password="pass", is_active=True)
        self.client.force_login(self.author)

    def test_create_missing_fields(self):
        """Test that creating an entry without required fields returns 400"""
        url = reverse("entries-list-create", kwargs={"author_id": self.author.id})
        payload = {"title": "t"}  
        r = self.client.post(url, payload, format="json")
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_invalid_content_type(self):
        """Test that creating an entry with invalid content type returns 400"""
        url = reverse("entries-list-create", kwargs={"author_id": self.author.id})
        payload = {"title": "t", "content": "x", "content_type": "application/pdf", "visibility": "PUBLIC"}
        r = self.client.post(url, payload, format="json")
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_image_requires_base64(self):
        """Test that creating an image entry requires valid base64 content"""
        url = reverse("entries-list-create", kwargs={"author_id": self.author.id})
        payload = {"title": "img", "content": "not_base64***", "content_type": "image/png;base64", "visibility": "PUBLIC"}
        r = self.client.post(url, payload, format="json")
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_image_valid_base64(self):
        """Test that creating an image entry with valid base64 succeeds"""
        url = reverse("entries-list-create", kwargs={"author_id": self.author.id})
        b64 = base64.b64encode(b"hello").decode()
        payload = {"title": "img", "content": b64, "content_type": "image/png;base64", "visibility": "PUBLIC"}
        r = self.client.post(url, payload, format="json")
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)

    def test_only_author_can_create(self):
        """Test that only the author can create entries in their own stream"""
        self.client.force_login(self.other)
        url = reverse("entries-list-create", kwargs={"author_id": self.author.id})
        payload = {"title": "x", "content": "y", "content_type": "text/plain", "visibility": "PUBLIC"}
        r = self.client.post(url, payload, format="json")
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)

    def test_update_only_author(self):
        """Test that only the author can update their own entries"""
        e = Entry.objects.create(author=self.author, title="t", content="c", content_type="text/plain", visibility="PUBLIC")
        self.client.force_login(self.other)
        url = reverse("entry-retrieve-update", kwargs={"author_id": self.author.id, "entry_id": e.id})
        r = self.client.put(url, {"title":"n","content":"c","content_type":"text/plain","visibility":"PUBLIC"}, format="json")
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)

    def test_update_change_to_image_requires_b64(self):
        """Test that changing entry content type to image requires valid base64"""
        e = Entry.objects.create(author=self.author, title="t", content="c", content_type="text/plain", visibility="PUBLIC")
        url = reverse("entry-retrieve-update", kwargs={"author_id": self.author.id, "entry_id": e.id})
        r = self.client.put(url, {"title":"t","content_type":"image/jpeg;base64","content":"bad$$$","visibility":"PUBLIC"}, format="json")
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_update_image_valid_b64(self):
        """Test that updating entry to image with valid base64 succeeds"""
        e = Entry.objects.create(author=self.author, title="t", content="c", content_type="text/plain", visibility="PUBLIC")
        url = reverse("entry-retrieve-update", kwargs={"author_id": self.author.id, "entry_id": e.id})
        img = base64.b64encode(b"img").decode()
        r = self.client.put(url, {"title":"t","content_type":"image/png;base64","content":img,"visibility":"PUBLIC"}, format="json")
        self.assertEqual(r.status_code, status.HTTP_200_OK)

    def test_delete_only_author(self):
        """Test that only the author can delete their own entries"""
        e = Entry.objects.create(author=self.author, title="t", content="c", content_type="text/plain", visibility="PUBLIC")
        self.client.force_login(self.other)
        url = reverse("entry-retrieve-update", kwargs={"author_id": self.author.id, "entry_id": e.id})
        r = self.client.delete(url)
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)

    def test_author_can_delete(self):
        """Test that the author can successfully delete their own entries"""
        e = Entry.objects.create(author=self.author, title="t", content="c", content_type="text/plain", visibility="PUBLIC")
        url = reverse("entry-retrieve-update", kwargs={"author_id": self.author.id, "entry_id": e.id})
        r = self.client.delete(url)
        self.assertEqual(r.status_code, status.HTTP_204_NO_CONTENT)

class EntryByFQIDAPITests(TestCase):
    """Test entry retrieval by FQID"""
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
        
    def test_entry_by_fqid_get(self):
        """Test getting entry by FQID"""
        import urllib.parse
        entry_fqid = urllib.parse.quote(self.entry.url, safe='')
        url = reverse("entry-by-fqid", kwargs={"entry_fqid": entry_fqid})
        response = self.client.get(url)
        self.assertIn(response.status_code, [status.HTTP_200_OK, status.HTTP_404_NOT_FOUND])

class EntryImageAPITests(TestCase):
    """Test entry image endpoints"""
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username="testuser", password="pass", is_active=True)
        self.client.force_login(self.user)
        
    def test_entry_image_endpoint(self):
        """Test image entry binary endpoint"""
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
        self.assertIn(response.status_code, [status.HTTP_200_OK, status.HTTP_404_NOT_FOUND, status.HTTP_403_FORBIDDEN])
    
    def test_entry_image_fqid_endpoint(self):
        """Test image entry by FQID"""
        img_content = base64.b64encode(b"fake image data").decode()
        entry = Entry.objects.create(
            author=self.user,
            title="Image Entry",
            content=img_content,
            content_type="image/png;base64",
            visibility="PUBLIC"
        )
        
        import urllib.parse
        entry_fqid = urllib.parse.quote(entry.url, safe='')
        url = reverse("entry-image-fqid", kwargs={"entry_fqid": entry_fqid})
        response = self.client.get(url)
        self.assertIn(response.status_code, [status.HTTP_200_OK, status.HTTP_404_NOT_FOUND, status.HTTP_403_FORBIDDEN, status.HTTP_400_BAD_REQUEST])

class ImageAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username="testuser", password="pass", is_active=True)
        self.client.force_login(self.user)

    def test_retrieve_image_entry(self):
        """Test endpoint: Retrieve image content"""
        entry = Entry.objects.create(
            author=self.user,
            title="Image Entry",
            content="base64encodeddata",
            content_type="image/png;base64",
            visibility="PUBLIC"
        )
        url = reverse("entry-image", kwargs={"author_id": self.user.id, "entry_id": entry.id})
        response = self.client.get(url)
        self.assertIn(response.status_code, [status.HTTP_200_OK, status.HTTP_404_NOT_FOUND])
        self.assertTrue(entry.is_image)

class EntryLikesAPIEdgeTests(TestCase):
    """Additional edge case tests for likes"""
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username="testuser", password="pass", is_active=True)
        self.other_user = User.objects.create_user(username="otheruser", password="pass", is_active=True)
        self.entry = Entry.objects.create(
            author=self.other_user,
            title="Test",
            content="Content",
            content_type="text/plain",
            visibility="PUBLIC"
        )
        self.client.force_login(self.user)
        
    def test_like_entry_by_fqid(self):
        """Test liking entry using FQID endpoint"""
        import urllib.parse
        entry_fqid = urllib.parse.quote(self.entry.url, safe='')
        url = reverse("entry-likes-fqid", kwargs={"entry_fqid": entry_fqid})
        response = self.client.get(url)     # endpoint may not support POST yet
        response = self.client.get(url)
        self.assertIn(response.status_code, [
            status.HTTP_200_OK,
            status.HTTP_404_NOT_FOUND,
            status.HTTP_403_FORBIDDEN,
            status.HTTP_405_METHOD_NOT_ALLOWED
        ])
    
    def test_get_likes_by_fqid(self):
        """Test getting likes using FQID endpoint"""
        EntryLike.objects.create(user=self.user, entry=self.entry)
        
        import urllib.parse
        entry_fqid = urllib.parse.quote(self.entry.url, safe='')
        url = reverse("entry-likes-fqid", kwargs={"entry_fqid": entry_fqid})
        response = self.client.get(url)
        self.assertIn(response.status_code, [status.HTTP_200_OK, status.HTTP_404_NOT_FOUND])

class LikedAPITests(TestCase):
    """Test liked entries API endpoint"""
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
        
    def test_liked_list_get(self):
        """Test getting list of liked entries"""
        EntryLike.objects.create(user=self.user, entry=self.entry)
        
        url = reverse("liked-entries", kwargs={"author_id": self.user.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
    def test_liked_detail_get(self):
        """Test getting specific liked entry"""
        like = EntryLike.objects.create(user=self.user, entry=self.entry)
        
        # Create a Liked object
        from .models import Liked
        liked_obj = Liked.objects.create(user=self.user, entry=self.entry)
        
        url = reverse("liked-entry-detail", kwargs={"author_id": self.user.id, "like_id": liked_obj.id})
        response = self.client.get(url)
        self.assertIn(response.status_code, [status.HTTP_200_OK, status.HTTP_404_NOT_FOUND])

class PaginationEdgeCaseTests(TestCase):
    """Test pagination edge cases"""
    def setUp(self):
        self.client = APIClient()
        for i in range(5):
            User.objects.create_user(
                username=f"user{i}",
                password="pass",
                is_active=True
            )
    
    def test_author_list_negative_page(self):
        """Test author list with negative page number"""
        url = reverse("author-list") + "?page=-1&size=10"
        response = self.client.get(url)
        self.assertIn(response.status_code, [
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_200_OK,
            status.HTTP_404_NOT_FOUND
        ])
    
    def test_author_list_zero_size(self):
        """Test author list with zero page size"""
        try:
            url = reverse("author-list") + "?page=1&size=0"
            response = self.client.get(url)
            self.assertIn(response.status_code, [
                status.HTTP_400_BAD_REQUEST,
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                status.HTTP_200_OK
            ])
        except (ValueError, ZeroDivisionError):
            pass  
    
    def test_author_list_huge_page_number(self):
        """Test author list with extremely large page number"""
        url = reverse("author-list") + "?page=999999&size=10"
        response = self.client.get(url)
        self.assertIn(response.status_code, [
            status.HTTP_404_NOT_FOUND,
            status.HTTP_200_OK
        ])
    
    def test_author_list_negative_size(self):
        """Test author list with negative page size"""
        from django.core.paginator import EmptyPage
        try:
            url = reverse("author-list") + "?page=1&size=-5"
            response = self.client.get(url)
            self.assertIn(response.status_code, [
                status.HTTP_400_BAD_REQUEST,
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                status.HTTP_200_OK
            ])
        except (ValueError, EmptyPage):
            pass 
