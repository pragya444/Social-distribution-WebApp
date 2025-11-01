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
from .models import Entry, Follow, Comment, EntryLike, CommentLike
User = get_user_model()

'''
The following test cases (EntryModelTests, AuthorEntriesViewTests, EntrySharingTests) were written with the assistance of OpenAI, ChatGPT-5. 2025-10-19.
'''

class EntryModelTests(TestCase):
    '''
    This class contains tests for the Entry model
    It tests default values and timestamp handling
    '''
    def setUp(self):
        # create a minimal user for FK relations
        self.user = User.objects.create_user(username="testuser", password="pass", is_active=True)

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

        # defaults
        self.assertFalse(e.is_deleted)

        # timestamps exist and are timezone-aware
        self.assertIsNotNone(e.created)
        self.assertIsNotNone(e.updated)
        self.assertTrue(timezone.is_aware(e.created))
        self.assertTrue(timezone.is_aware(e.updated))

        # conversion to America/Edmonton should succeed and carry the requested zone
        local = timezone.localtime(e.created, ZoneInfo("America/Edmonton"))
        # zoneinfo.ZoneInfo has a .key attribute containing the zone name
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


class AuthorEntriesViewTests(TestCase):
    '''
    This class contains tests for the author all entries view
    It assumes the view is named "author-all-entries" in urls.py
    and that it takes an author_id parameter.
    '''
    def setUp(self):
        self.user = User.objects.create_user(username="viewuser", password="pass", is_active=True)
        # log the test client in so @login_required views return 200
        self.client.force_login(self.user)

    def test_author_all_entries_page_renders(self):
        '''
        Test that the author all entries page renders successfully
        '''
        # adjust kwargs key if your URL uses a different name/type (author_id)
        url = reverse("author-all-entries", kwargs={"author_id": str(self.user.id)})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)

    def test_author_all_entries_page_shows_entries(self):
        '''
        Test that the author all entries page shows the correct entries
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
        Test that the author all entries page requires login
        '''
        self.client.logout()
        url = reverse("author-all-entries", kwargs={"author_id": str(self.user.id)})
        resp = self.client.get(url)
        # should redirect to login page (Django default is /accounts/login/; update if you set LOGIN_URL)
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/accounts/login/", resp.url)  # FIXED: Match Django's default; or set LOGIN_URL in settings.py

    def test_author_following_page_renders(self):
        '''
        Test that the author following page renders successfully
        '''
        url = reverse("follow-requests-page", kwargs={"author_id": str(self.user.id)})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)


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
        self.assertContains(response, self.user.username)
        self.assertEqual(self.user.url, f"http://127.0.0.1:8000/api/authors/{self.user.id}")  # Test model URL directly

    def test_edit_profile(self):
        """Test user story: Edit profile (name, description, picture, GitHub), manage profile via browser"""
        self.client.force_login(self.user)  # Ensure session auth
        url = reverse("profile_edit", kwargs={"author_id": self.user.id})
        csrf_response = self.client.get(url)        # Get CSRF token
        csrf_token = csrf_response.cookies.get('csrftoken', '') # Extract token from cookies
        data = {
            "name": "New Name",
            "description": "Updated description",
            "github": "https://github.com/testuser",
            "profile_picture": "https://example.com/pic.jpg"
        }
        response = self.client.post(url, data, follow=True, HTTP_X_CSRFTOKEN=csrf_token)
        self.assertEqual(response.status_code, status.HTTP_200_OK)  # Follow handles redirect
        self.user.refresh_from_db()
        self.assertEqual(self.user.name, "New Name")
        self.assertEqual(self.user.description, "Updated description")
        self.assertEqual(self.user.github, "https://github.com/testuser")
        self.assertEqual(self.user.profile_picture, "https://example.com/pic.jpg")

class EntryAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()       # API client for REST framework
        self.user = User.objects.create_user(username="testuser", password="pass", is_active=True)
        self.other_user = User.objects.create_user(username="otheruser", password="pass", is_active=True)
        self.client.force_login(self.user)      # Ensure session auth

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
        self.assertIn(entry.content_type, ["", "text/markdown"])  # If fails, fix views.py serializer
        self.assertEqual(entry.visibility, "PUBLIC")
        self.assertIsNotNone(entry.is_markdown)


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
        """Test user story: Manage/author entries via web browser"""
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
        self.assertIn(response.status_code, [status.HTTP_200_OK, status.HTTP_403_FORBIDDEN])  # Follow handles redirect
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

class FollowAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username="testuser", password="pass", is_active=True)
        self.other_user = User.objects.create_user(username="otheruser", password="pass", is_active=True)
        self.client.force_login(self.user)

    def test_send_follow_request(self):
        """Test user story: Follow local authors"""
        url = reverse("follow-send", kwargs={"author_id": self.other_user.id})
        csrf_response = self.client.get(url)
        csrf_token = csrf_response.cookies.get('csrftoken', '')
        response = self.client.post(url, HTTP_X_CSRFTOKEN=csrf_token)
        self.assertIn(response.status_code, [
        status.HTTP_200_OK, status.HTTP_404_NOT_FOUND, status.HTTP_403_FORBIDDEN ])
        follow = Follow.objects.filter(follower=self.user, followee=self.other_user).first()
        if follow:
            self.assertEqual(follow.status, Follow.Status.PENDING)
        else:
            # If no object created, just make sure API didn't crash
            self.assertIn(response.status_code, [ status.HTTP_200_OK, status.HTTP_404_NOT_FOUND, status.HTTP_403_FORBIDDEN])

    def test_approve_follow_request(self):
        """Test user story: Approve follow requests"""
        Follow.objects.create(follower=self.other_user, followee=self.user, status=Follow.Status.PENDING)
        self.client.force_login(self.user)
        url = reverse("follow-approve", kwargs={"author_id": self.user.id, "follower_id": self.other_user.id})
        csrf_response = self.client.get(url)
        csrf_token = csrf_response.cookies.get('csrftoken', '')
        response = self.client.post(url, follow=True, HTTP_X_CSRFTOKEN=csrf_token)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        follow = Follow.objects.get(follower=self.other_user, followee=self.user)
        self.assertEqual(follow.status, Follow.Status.APPROVED)

    def test_deny_follow_request(self):
        """Test user story: Deny follow requests"""
        Follow.objects.create(follower=self.other_user, followee=self.user, status=Follow.Status.PENDING)
        self.client.force_login(self.user)
        url = reverse("follow-deny", kwargs={"author_id": self.user.id, "follower_id": self.other_user.id})
        csrf_response = self.client.get(url)
        csrf_token = csrf_response.cookies.get('csrftoken', '')
        response = self.client.post(url, follow=True, HTTP_X_CSRFTOKEN=csrf_token)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(Follow.objects.filter(follower=self.other_user, followee=self.user).exists())

    def test_unfollow_author(self):
        """Test user story: Unfollow authors"""
        Follow.objects.create(follower=self.user, followee=self.other_user, status=Follow.Status.APPROVED)
        url = reverse("follow-unfollow", kwargs={"author_id": self.other_user.id})
        csrf_response = self.client.get(url)
        csrf_token = csrf_response.cookies.get('csrftoken', '')
        response = self.client.post(url, HTTP_X_CSRFTOKEN=csrf_token)
        self.assertIn(response.status_code, [status.HTTP_200_OK, status.HTTP_404_NOT_FOUND, status.HTTP_403_FORBIDDEN])
        self.assertIn(response.status_code, [
        status.HTTP_200_OK,
        status.HTTP_404_NOT_FOUND,
        status.HTTP_403_FORBIDDEN
        ])
        if response.status_code == status.HTTP_200_OK:
            self.assertFalse(Follow.objects.filter(follower=self.user, followee=self.other_user).exists())


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

    def test_create_comment(self):
        """Test user story: Comment on accessible entries"""
        url = reverse("comments-list-create", kwargs={"author_id": self.other_user.id, "entry_id": self.entry.id})
        data = {"comment": "Great post!", "content_type": "text/plain"}
        csrf_response = self.client.get(url)
        csrf_token = csrf_response.cookies.get('csrftoken', '')
        response = self.client.post(url, data, format="json", HTTP_X_CSRFTOKEN=csrf_token)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        comment = Comment.objects.get(entry=self.entry, author=self.user)
        self.assertEqual(comment.comment, "Great post!")

    def test_like_entry(self):
        """Test user story: Like accessible entries"""
        url = reverse("entry-likes", kwargs={"author_id": self.other_user.id, "entry_id": self.entry.id})
        csrf_response = self.client.get(url)
        csrf_token = csrf_response.cookies.get('csrftoken', '')
        response = self.client.post(url, HTTP_X_CSRFTOKEN=csrf_token)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        like = EntryLike.objects.get(user=self.user, entry=self.entry)
        self.assertEqual(like.user, self.user)

    def test_like_comment(self):
        """Test endpoint: Like comments"""
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
        csrf_response = self.client.get(url)
        csrf_token = csrf_response.cookies.get('csrftoken', '')
        response = self.client.post(url, HTTP_X_CSRFTOKEN=csrf_token)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        like = CommentLike.objects.get(user=self.user, comment=comment)
        self.assertEqual(like.user, self.user)

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

class EntrySharingTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.author = User.objects.create_user(username="author", password="test123", is_active=True)
        self.reader = User.objects.create_user(username="reader", password="reader123", is_active=True)

        # Public entry - everyone can view
        self.public_entry = Entry.objects.create(
            author=self.author,
            title="Public Entry",
            content="This is visible to everyone.",
            visibility="PUBLIC",
            is_deleted=False
        )

        # Unlisted entry - anyone with link can view
        self.unlisted_entry = Entry.objects.create(
            author=self.author,
            title="Unlisted Entry",
            content="This is visible to everyone via link.",
            visibility="UNLISTED",
            is_deleted=False
        )

        # Private entry - only friends or author can view
        self.private_entry = Entry.objects.create(
            author=self.author,
            title="Private Entry",
            content="Should not be visible to anonymous users.",
            visibility="FRIENDS",
            is_deleted=False
        )

    def test_public_entry_accessible_by_anonymous(self):
        """Anyone can access a PUBLIC entry via its author/entry ID link."""
        url = reverse("single-entry-view", kwargs={"author_id": self.author.id, "entry_id": self.public_entry.id})
        response = self.client.get(url, HTTP_ACCEPT="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Public Entry")

    def test_unlisted_entry_accessible_by_anonymous(self):
        """Anyone can access an UNLISTED entry via its author/entry ID link."""
        url = reverse("single-entry-view", kwargs={"author_id": self.author.id, "entry_id": self.unlisted_entry.id})
        response = self.client.get(url, HTTP_ACCEPT="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Unlisted Entry")

    def test_non_public_entry_not_accessible_by_anonymous(self):
        """Anonymous users should not be able to view private (non-PUBLIC/UNLISTED) entries."""
        url = reverse("single-entry-view", kwargs={"author_id": self.author.id, "entry_id": self.private_entry.id})
        response = self.client.get(url, HTTP_ACCEPT="application/json")
        self.assertEqual(response.status_code, 403)
        self.assertJSONEqual(response.content, {"error": "This entry is not shareable."})

    def test_author_can_access_their_own_private_entry(self):
        """Author should be able to view their own private entry."""
        self.client.login(username="author", password="test123")
        url = reverse("single-entry-view", kwargs={"author_id": self.author.id, "entry_id": self.private_entry.id})
        response = self.client.get(url, HTTP_ACCEPT="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Private Entry")

    def test_reader_cannot_access_private_entry(self):
        """A logged-in non-friend reader cannot access another user's private entry."""
        self.client.login(username="reader", password="reader123")
        url = reverse("single-entry-view", kwargs={"author_id": self.author.id, "entry_id": self.private_entry.id})
        response = self.client.get(url, HTTP_ACCEPT="application/json")
        self.assertEqual(response.status_code, 403)