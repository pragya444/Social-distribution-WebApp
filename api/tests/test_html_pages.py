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


class AuthorEntriesViewTests(TestCase):
    '''
    This class contains tests for the author all entries view
    It assumes the view is named "author-all-entries" in urls.py
    and that it takes an author_id parameter.
    '''
    def setUp(self):
        self.user = User.objects.create_user(username="viewuser", password="pass", is_active=True)
        self.client.force_login(self.user)

    def test_author_all_entries_page_renders(self):
        '''
        Test that the author stream page renders successfully
        '''
        url = reverse("author-all-entries", kwargs={"author_id": str(self.user.id)})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)

    def test_author_all_entries_page_shows_entries(self):
        '''
        Test that the author stream page shows the correct entries
        '''
        Entry.objects.create(
            author=self.user,
            title="Visible Entry",
            content="This entry should be visible",
            content_type="text/plain",
            is_deleted=False,
        )
        Entry.objects.create(
            author=self.user,
            title="Deleted Entry",
            content="This entry should NOT be visible",
            content_type="text/plain",
            is_deleted=True,
        )

        url = reverse("author-all-entries", kwargs={"author_id": str(self.user.id)})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Visible Entry")
        self.assertNotContains(resp, "Deleted Entry")

    def test_author_all_entries_page_requires_login(self):
        '''
        Test that the author stream page requires login
        '''
        self.client.logout()
        url = reverse("author-all-entries", kwargs={"author_id": str(self.user.id)})
        resp = self.client.get(url)
        self.assertIn(resp.status_code, [302, 403])

    def test_author_following_page_renders(self):
        '''
        Test that the author following page renders successfully
        '''
        url = reverse("follow-requests-page", kwargs={"author_id": str(self.user.id)})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)


class HTMLPageTests(TestCase):
    """Test HTML page rendering for UI views"""
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username="testuser", password="pass", is_active=True)
        self.client.force_login(self.user)
        
    def test_entry_create_page(self):
        """Test entry creation page renders"""
        url = reverse("entry-create-page", kwargs={"author_id": self.user.id})
        response = self.client.get(url)
        self.assertIn(response.status_code, [status.HTTP_200_OK, status.HTTP_302_FOUND])
    
    def test_entry_edit_page(self):
        """Test entry edit page renders"""
        entry = Entry.objects.create(
            author=self.user,
            title="Test",
            content="Content",
            content_type="text/plain",
            visibility="PUBLIC"
        )
        url = reverse("entry-edit-page", kwargs={"author_id": self.user.id, "entry_id": entry.id})
        response = self.client.get(url)
        self.assertIn(response.status_code, [status.HTTP_200_OK, status.HTTP_302_FOUND])
    
    def test_profile_edit_page(self):
        """Test profile edit page renders"""
        url = reverse("profile_edit", kwargs={"author_id": self.user.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    def test_followers_page(self):
        """Test followers HTML page"""
        url = reverse("followers-page", kwargs={"author_id": self.user.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    def test_following_page(self):
        """Test following HTML page"""
        url = reverse("following-page", kwargs={"author_id": self.user.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    def test_friends_page(self):
        """Test friends HTML page"""
        url = reverse("friends-page", kwargs={"author_id": self.user.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

class AdminSiteTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.superuser = User.objects.create_superuser(
            username="admin",
            password="pass",
        )

    def test_admin_login_page_loads_with_csrf(self):
        """Test that admin login page loads with CSRF token"""
        url = reverse("admin:login")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("csrfmiddlewaretoken", resp.content.decode())

    def test_admin_index_requires_login_redirects(self):
        """Test that accessing admin index without login redirects to login page"""
        url = reverse("admin:index")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/admin/login/?next=", resp.url)

    def test_admin_index_accessible_to_superuser(self):
        """Test that superusers can access admin index"""
        self.client.force_login(self.superuser)
        url = reverse("admin:index")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)

    def test_admin_index_accessible_to_staff(self):
        """Test that staff users can access admin index"""
        staff = User.objects.create_user(username="staff", password="pass", is_active=True)
        staff.is_staff = True
        staff.save()
        self.client.force_login(staff)
        url = reverse("admin:index")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)

    def test_admin_index_inactive_staff_redirects(self):
        """Test that inactive staff users are redirected from admin index"""
        inactive = User.objects.create_user(username="inactive", password="pass", is_active=False)
        inactive.is_staff = True
        inactive.save()
        self.client.force_login(inactive)
        url = reverse("admin:index")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/admin/login/?next=", resp.url)
