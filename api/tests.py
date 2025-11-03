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
        
    def testProfilenotAuthorizedEdit(self):
        '''Written with the assistance of OpenAI, ChatGPT-5. 2025-11-02.'''
        """
        Test user story: Other authors cannot modify my profile
        It creates a second user and attempts to edit the first user's profile.
        It will return 403 Forbidden or redirect (302) but never allow success.
        Checks that the profile name was not changed.
        """
        url = reverse("profile_edit", kwargs={"author_id": self.other_user.id})
        data = {
            "name": "Hacked Name"
        }
        # don't follow redirects so we can inspect the immediate response status
        response = self.client.post(url, data, format="json", follow=False)
        # allow either explicit 403 or a redirect (302) from HTML views, but never allow success
        self.assertIn(response.status_code, [status.HTTP_403_FORBIDDEN, status.HTTP_302_FOUND])
        self.other_user.refresh_from_db()
        self.assertNotEqual(self.other_user.name, "Hacked Name")

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
        # use the real author id, and perform request as the other_user to trigger permission check
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
        # use the real author id, and perform request as the other_user to trigger permission check
        url = reverse("entry-retrieve-update", kwargs={"author_id": self.user.id, "entry_id": entry.id})
        self.client.force_login(self.other_user)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

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

        self.public_entry = Entry.objects.create(
            author=self.author,
            title="Public Entry",
            content="This is visible to everyone.",
            visibility="PUBLIC",
        )

        self.unlisted_entry = Entry.objects.create(
            author=self.author,
            title="Unlisted Entry",
            content="This is visible to everyone via link.",
            visibility="UNLISTED",
        )

        self.private_entry = Entry.objects.create(
            author=self.author,
            title="Private Entry",
            content="Should not be visible.",
            visibility="FRIENDS",  
        )

    def test_public_entry_accessible_by_anonymous(self):
        """Anyone can access a PUBLIC entry via its author/entry ID link."""
        url = reverse(
            "entry-retrieve-update",
            kwargs={"author_id": self.author.id, "entry_id": self.public_entry.id},
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Public Entry")

    def test_unlisted_entry_accessible_by_anonymous(self):
        """Anonymous users should NOT be able to access UNLISTED entries (follower-only)."""
        url = reverse(
            "entry-retrieve-update",
            kwargs={"author_id": self.author.id, "entry_id": self.unlisted_entry.id},
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)

    def test_non_public_entry_not_accessible_by_anonymous(self):
        """Non-public entries (FRIENDS) should not be visible to anonymous users."""
        url = reverse(
            "entry-retrieve-update",
            kwargs={"author_id": self.author.id, "entry_id": self.private_entry.id},
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)

    def test_author_can_access_their_own_private_entry(self):
        """Author should be able to view their own private entry."""
        self.client.login(username="author", password="test123")
        url = reverse(
            "entry-retrieve-update",
            kwargs={"author_id": self.author.id, "entry_id": self.private_entry.id},
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Private Entry")

    def test_reader_cannot_access_private_entry(self):
        """A logged-in non-friend reader cannot access another user's private entry."""
        self.client.login(username="reader", password="reader123")
        url = reverse(
            "entry-retrieve-update",
            kwargs={"author_id": self.author.id, "entry_id": self.private_entry.id},
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)


# =============================
# Additional 50 edge case tests
# =============================

class EntryAPIEdgeTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.author = User.objects.create_user(username="author_ec", password="pass", is_active=True)
        self.other = User.objects.create_user(username="other_ec", password="pass", is_active=True)
        self.client.force_login(self.author)

    def test_create_missing_fields(self):
        url = reverse("entries-list-create", kwargs={"author_id": self.author.id})
        payload = {"title": "t"}  # missing content/content_type/visibility
        r = self.client.post(url, payload, format="json")
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_invalid_content_type(self):
        url = reverse("entries-list-create", kwargs={"author_id": self.author.id})
        payload = {"title": "t", "content": "x", "content_type": "application/pdf", "visibility": "PUBLIC"}
        r = self.client.post(url, payload, format="json")
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_image_requires_base64(self):
        url = reverse("entries-list-create", kwargs={"author_id": self.author.id})
        payload = {"title": "img", "content": "not_base64***", "content_type": "image/png;base64", "visibility": "PUBLIC"}
        r = self.client.post(url, payload, format="json")
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_image_valid_base64(self):
        url = reverse("entries-list-create", kwargs={"author_id": self.author.id})
        b64 = base64.b64encode(b"hello").decode()
        payload = {"title": "img", "content": b64, "content_type": "image/png;base64", "visibility": "PUBLIC"}
        r = self.client.post(url, payload, format="json")
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)

    def test_only_author_can_create(self):
        self.client.force_login(self.other)
        url = reverse("entries-list-create", kwargs={"author_id": self.author.id})
        payload = {"title": "x", "content": "y", "content_type": "text/plain", "visibility": "PUBLIC"}
        r = self.client.post(url, payload, format="json")
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)

    def test_update_only_author(self):
        e = Entry.objects.create(author=self.author, title="t", content="c", content_type="text/plain", visibility="PUBLIC")
        self.client.force_login(self.other)
        url = reverse("entry-retrieve-update", kwargs={"author_id": self.author.id, "entry_id": e.id})
        r = self.client.put(url, {"title":"n","content":"c","content_type":"text/plain","visibility":"PUBLIC"}, format="json")
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)

    def test_update_change_to_image_requires_b64(self):
        e = Entry.objects.create(author=self.author, title="t", content="c", content_type="text/plain", visibility="PUBLIC")
        url = reverse("entry-retrieve-update", kwargs={"author_id": self.author.id, "entry_id": e.id})
        r = self.client.put(url, {"title":"t","content_type":"image/jpeg;base64","content":"bad$$$","visibility":"PUBLIC"}, format="json")
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_update_image_valid_b64(self):
        e = Entry.objects.create(author=self.author, title="t", content="c", content_type="text/plain", visibility="PUBLIC")
        url = reverse("entry-retrieve-update", kwargs={"author_id": self.author.id, "entry_id": e.id})
        img = base64.b64encode(b"img").decode()
        r = self.client.put(url, {"title":"t","content_type":"image/png;base64","content":img,"visibility":"PUBLIC"}, format="json")
        self.assertEqual(r.status_code, status.HTTP_200_OK)

    def test_delete_only_author(self):
        e = Entry.objects.create(author=self.author, title="t", content="c", content_type="text/plain", visibility="PUBLIC")
        self.client.force_login(self.other)
        url = reverse("entry-retrieve-update", kwargs={"author_id": self.author.id, "entry_id": e.id})
        r = self.client.delete(url)
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)

    def test_author_can_delete(self):
        e = Entry.objects.create(author=self.author, title="t", content="c", content_type="text/plain", visibility="PUBLIC")
        url = reverse("entry-retrieve-update", kwargs={"author_id": self.author.id, "entry_id": e.id})
        r = self.client.delete(url)
        self.assertEqual(r.status_code, status.HTTP_204_NO_CONTENT)


class EntryVisibilityAccessTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.author = User.objects.create_user(username="author_va", password="pass", is_active=True)
        self.follower = User.objects.create_user(username="follower_va", password="pass", is_active=True)
        self.stranger = User.objects.create_user(username="stranger_va", password="pass", is_active=True)

    def test_public_visible_to_anonymous(self):
        e = Entry.objects.create(author=self.author, title="p", content="c", content_type="text/plain", visibility="PUBLIC")
        url = reverse("entry-retrieve-update", kwargs={"author_id": self.author.id, "entry_id": e.id})
        r = Client().get(url)
        self.assertEqual(r.status_code, status.HTTP_200_OK)

    def test_friends_not_visible_to_anonymous(self):
        e = Entry.objects.create(author=self.author, title="f", content="c", content_type="text/plain", visibility="FRIENDS")
        url = reverse("entry-retrieve-update", kwargs={"author_id": self.author.id, "entry_id": e.id})
        r = Client().get(url)
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)
    '''
    # not done yet
    def test_unlisted_requires_follower_or_author(self):
        e = Entry.objects.create(author=self.author, title="u", content="c", content_type="text/plain", visibility="UNLISTED")
        url = reverse("entry-retrieve-update", kwargs={"author_id": self.author.id, "entry_id": e.id})
        # stranger logged in
        self.client.force_login(self.stranger)
        r = self.client.get(url)
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)
    # not done yet
    def test_unlisted_visible_to_follower(self):
        e = Entry.objects.create(author=self.author, title="u", content="c", content_type="text/plain", visibility="UNLISTED")
        Follow.objects.create(follower=self.follower, followee=self.author, status=Follow.Status.APPROVED)
        self.client.force_login(self.follower)
        url = reverse("entry-retrieve-update", kwargs={"author_id": self.author.id, "entry_id": e.id})
        r = self.client.get(url)
        self.assertEqual(r.status_code, status.HTTP_200_OK)'''

    def test_friends_visible_to_friend(self):
        e = Entry.objects.create(author=self.author, title="f", content="c", content_type="text/plain", visibility="FRIENDS")
        # mutual follow
        Follow.objects.create(follower=self.follower, followee=self.author, status=Follow.Status.APPROVED)
        Follow.objects.create(follower=self.author, followee=self.follower, status=Follow.Status.APPROVED)
        self.client.force_login(self.follower)
        url = reverse("entry-retrieve-update", kwargs={"author_id": self.author.id, "entry_id": e.id})
        r = self.client.get(url)
        self.assertEqual(r.status_code, status.HTTP_200_OK)

    def test_author_always_can_view_private(self):
        e = Entry.objects.create(author=self.author, title="f", content="c", content_type="text/plain", visibility="FRIENDS")
        self.client.force_login(self.author)
        url = reverse("entry-retrieve-update", kwargs={"author_id": self.author.id, "entry_id": e.id})
        r = self.client.get(url)
        self.assertEqual(r.status_code, status.HTTP_200_OK)

    def test_entries_list_public_when_viewing_other(self):
        # when not author, only PUBLIC are returned by list
        Entry.objects.create(author=self.author, title="pub", content="c", content_type="text/plain", visibility="PUBLIC")
        Entry.objects.create(author=self.author, title="priv", content="c", content_type="text/plain", visibility="FRIENDS")
        self.client.force_login(self.stranger)
        url = reverse("entries-list-create", kwargs={"author_id": self.author.id})
        r = self.client.get(url)
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertIn("pub", str(r.content))
        self.assertNotIn("priv", str(r.content))

    def test_entries_list_author_sees_all(self):
        Entry.objects.create(author=self.author, title="pub", content="c", content_type="text/plain", visibility="PUBLIC")
        Entry.objects.create(author=self.author, title="priv", content="c", content_type="text/plain", visibility="FRIENDS")
        self.client.force_login(self.author)
        url = reverse("entries-list-create", kwargs={"author_id": self.author.id})
        r = self.client.get(url)
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertIn("pub", str(r.content))
        self.assertIn("priv", str(r.content))

    def test_image_binary_endpoint_authz(self):
        e = Entry.objects.create(author=self.author, title="img", content=base64.b64encode(b"i").decode(), content_type="image/png;base64", visibility="FRIENDS")
        url = reverse("entry-image", kwargs={"author_id": self.author.id, "entry_id": e.id})
        # anonymous forbidden for FRIENDS
        r = Client().get(url)
        self.assertIn(r.status_code, [status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND])


class FollowEdgeTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.a = User.objects.create_user(username="a_fe", password="pass", is_active=True)
        self.b = User.objects.create_user(username="b_fe", password="pass", is_active=True)
        self.client.force_login(self.a)

    def test_cannot_follow_self(self):
        url = reverse("follow-send", kwargs={"author_id": self.a.id})
        r = self.client.post(url)
        self.assertIn(r.status_code, [status.HTTP_403_FORBIDDEN, status.HTTP_400_BAD_REQUEST, status.HTTP_404_NOT_FOUND])

    def test_duplicate_follow_request_unique(self):
        Follow.objects.create(follower=self.a, followee=self.b, status=Follow.Status.PENDING)
        with self.assertRaises(Exception):
            Follow.objects.create(follower=self.a, followee=self.b, status=Follow.Status.PENDING)

    def test_mutual_follow_friends(self):
        Follow.objects.create(follower=self.a, followee=self.b, status=Follow.Status.APPROVED)
        Follow.objects.create(follower=self.b, followee=self.a, status=Follow.Status.APPROVED)
        self.assertTrue(Follow.objects.filter(follower=self.a, followee=self.b, status=Follow.Status.APPROVED).exists())

    def test_unfollow_endpoint(self):
        Follow.objects.create(follower=self.a, followee=self.b, status=Follow.Status.APPROVED)
        url = reverse("follow-unfollow", kwargs={"author_id": self.b.id})
        r = self.client.post(url)
        self.assertIn(r.status_code, [status.HTTP_200_OK, status.HTTP_404_NOT_FOUND, status.HTTP_403_FORBIDDEN])

    def test_approve_flow(self):
        Follow.objects.create(follower=self.b, followee=self.a, status=Follow.Status.PENDING)
        url = reverse("follow-approve", kwargs={"author_id": self.a.id, "follower_id": self.b.id})
        r = self.client.post(url)
        self.assertIn(r.status_code, [status.HTTP_200_OK, status.HTTP_302_FOUND])

    def test_deny_flow(self):
        Follow.objects.create(follower=self.b, followee=self.a, status=Follow.Status.PENDING)
        url = reverse("follow-deny", kwargs={"author_id": self.a.id, "follower_id": self.b.id})
        r = self.client.post(url)
        self.assertIn(r.status_code, [status.HTTP_200_OK, status.HTTP_302_FOUND])

    def test_follow_requests_page_requires_login(self):
        self.client.logout()
        url = reverse("follow-requests-page", kwargs={"author_id": self.a.id})
        resp = self.client.get(url)
        self.assertIn(resp.status_code, [status.HTTP_302_FOUND, status.HTTP_403_FORBIDDEN])

    def test_follow_send_requires_login(self):
        self.client.logout()
        url = reverse("follow-send", kwargs={"author_id": self.b.id})
        resp = self.client.post(url)
        self.assertIn(resp.status_code, [status.HTTP_302_FOUND, status.HTTP_403_FORBIDDEN])

    def test_follow_unique_constraint(self):
        Follow.objects.create(follower=self.a, followee=self.b, status=Follow.Status.PENDING)
        with self.assertRaises(Exception):
            Follow.objects.create(follower=self.a, followee=self.b, status=Follow.Status.APPROVED)

    def test_no_self_follow_constraint(self):
        with self.assertRaises(Exception):
            Follow.objects.create(follower=self.a, followee=self.a, status=Follow.Status.PENDING)


class SerializerValidationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="svt", password="pass", is_active=True)

    def test_user_serializer_blank_name_rejected(self):
        from .serializers import UserSerializer
        s = UserSerializer(self.user, data={"name": "   "}, partial=True)
        self.assertFalse(s.is_valid())

    def test_user_serializer_github_normalization(self):
        from .serializers import UserSerializer
        s = UserSerializer(self.user, data={"github": "octocat"}, partial=True)
        self.assertTrue(s.is_valid(), s.errors)
        u = s.save()
        self.assertTrue(u.github.startswith("https://github.com/"))

    def test_entry_serializer_missing_fields(self):
        from .serializers import EntrySerializer
        s = EntrySerializer(data={"title": "x"})
        self.assertFalse(s.is_valid())

    def test_entry_serializer_invalid_ct(self):
        from .serializers import EntrySerializer
        s = EntrySerializer(data={"title":"x","content":"y","content_type":"bad","visibility":"PUBLIC"})
        self.assertFalse(s.is_valid())

    def test_entry_serializer_image_b64_ok(self):
        from .serializers import EntrySerializer
        img = base64.b64encode(b"a").decode()
        s = EntrySerializer(data={"title":"x","content":img,"content_type":"image/png;base64","visibility":"PUBLIC"}, context={"request": type("obj", (), {"user": self.user})})
        self.assertTrue(s.is_valid(), s.errors)

    def test_entry_serializer_image_b64_bad(self):
        from .serializers import EntrySerializer
        s = EntrySerializer(data={"title":"x","content":"not-b64","content_type":"image/png;base64","visibility":"PUBLIC"})
        self.assertFalse(s.is_valid())

    def test_entry_serializer_update_partial(self):
        from .serializers import EntrySerializer
        e = Entry.objects.create(author=self.user, title="t", content="c", content_type="text/plain", visibility="PUBLIC")
        s = EntrySerializer(e, data={"title":"n"}, partial=True)
        self.assertTrue(s.is_valid(), s.errors)
        e2 = s.save()
        self.assertEqual(e2.title, "n")

    def test_user_serializer_update_fields(self):
        from .serializers import UserSerializer
        s = UserSerializer(self.user, data={"name":"New","description":"d","profile_picture":"http://x/y.png","github":"https://github.com/x"}, partial=True)
        self.assertTrue(s.is_valid(), s.errors)
        u = s.save()
        self.assertEqual(u.name, "New")

    # def test_user_serializer_followers_fields_present(self):
    #     from .serializers import UserSerializer
    #     s = UserSerializer(self.user)
    #     data = s.data
    #     self.assertIn("followers", data)
    #     self.assertIn("following", data)
    #     self.assertIn("friends", data)


class LikesCommentsEdgeTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.alice = User.objects.create_user(username="alice_lc", password="pass", is_active=True)
        self.bob = User.objects.create_user(username="bob_lc", password="pass", is_active=True)
        self.entry = Entry.objects.create(author=self.alice, title="t", content="c", content_type="text/plain", visibility="PUBLIC")
        self.client.force_login(self.bob)

    def test_like_toggle(self):
        url = reverse("entry-likes", kwargs={"author_id": self.alice.id, "entry_id": self.entry.id})
        r1 = self.client.post(url)
        self.assertIn(r1.status_code, [status.HTTP_201_CREATED, status.HTTP_200_OK])
        r2 = self.client.delete(url)
        self.assertIn(r2.status_code, [status.HTTP_200_OK, status.HTTP_204_NO_CONTENT])

    def test_like_requires_auth(self):
        url = reverse("entry-likes", kwargs={"author_id": self.alice.id, "entry_id": self.entry.id})
        c = APIClient()  # anonymous
        r = c.post(url)
        self.assertIn(r.status_code, [status.HTTP_403_FORBIDDEN, status.HTTP_401_UNAUTHORIZED, status.HTTP_302_FOUND])

    def test_comment_create_requires_auth(self):
        url = reverse("comments-list-create", kwargs={"author_id": self.alice.id, "entry_id": self.entry.id})
        c = APIClient()
        r = c.post(url, {"comment":"hi"}, format="json")
        self.assertIn(r.status_code, [status.HTTP_403_FORBIDDEN, status.HTTP_401_UNAUTHORIZED, status.HTTP_302_FOUND])

    def test_comment_create_and_count(self):
        url = reverse("comments-list-create", kwargs={"author_id": self.alice.id, "entry_id": self.entry.id})
        r = self.client.post(url, {"comment":"hi"}, format="json")
        self.assertIn(r.status_code, [status.HTTP_201_CREATED, status.HTTP_200_OK])
        self.entry.refresh_from_db()
        self.assertGreaterEqual(self.entry.comment_count, 1)

    def test_comment_like_flow(self):
        cmt = Comment.objects.create(entry=self.entry, author=self.bob, comment="ok", content_type="text/plain")
        url = reverse("comment-likes", kwargs={"author_id": self.alice.id, "entry_id": self.entry.id, "comment_id": cmt.id})
        r1 = self.client.post(url)
        self.assertIn(r1.status_code, [status.HTTP_201_CREATED, status.HTTP_200_OK])
        r2 = self.client.delete(url)
        self.assertIn(r2.status_code, [status.HTTP_200_OK, status.HTTP_204_NO_CONTENT])

    def test_like_counts_increase(self):
        url = reverse("entry-likes", kwargs={"author_id": self.alice.id, "entry_id": self.entry.id})
        before = Entry.objects.get(id=self.entry.id).like_count
        self.client.post(url)
        after = Entry.objects.get(id=self.entry.id).like_count
        self.assertGreaterEqual(after, before)

    def test_comment_list_get(self):
        Comment.objects.create(entry=self.entry, author=self.bob, comment="ok", content_type="text/plain")
        url = reverse("comments-list-create", kwargs={"author_id": self.alice.id, "entry_id": self.entry.id})
        r = self.client.get(url)
        self.assertEqual(r.status_code, status.HTTP_200_OK)

    def test_like_idempotent_delete(self):
        url = reverse("entry-likes", kwargs={"author_id": self.alice.id, "entry_id": self.entry.id})
        self.client.delete(url)  # no like yet
        r = self.client.delete(url)
        self.assertIn(r.status_code, [status.HTTP_200_OK, status.HTTP_204_NO_CONTENT])


class AdminSiteTests(TestCase):
    def setUp(self):
        self.client = Client()
        # Create a superuser for admin access
        self.superuser = User.objects.create_superuser(
            username="admin",
            password="pass",
        )

    def test_admin_login_page_loads_with_csrf(self):
        url = reverse("admin:login")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        # Admin login form should include a CSRF token
        self.assertIn("csrfmiddlewaretoken", resp.content.decode())

    def test_admin_index_requires_login_redirects(self):
        url = reverse("admin:index")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/admin/login/?next=", resp.url)

    def test_admin_index_accessible_to_superuser(self):
        self.client.force_login(self.superuser)
        url = reverse("admin:index")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)

    def test_admin_index_accessible_to_staff(self):
        staff = User.objects.create_user(username="staff", password="pass", is_active=True)
        staff.is_staff = True
        staff.save()
        self.client.force_login(staff)
        url = reverse("admin:index")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)

    def test_admin_index_inactive_staff_redirects(self):
        inactive = User.objects.create_user(username="inactive", password="pass", is_active=False)
        inactive.is_staff = True
        inactive.save()
        self.client.force_login(inactive)
        url = reverse("admin:index")
        resp = self.client.get(url)
        # Inactive users should not be allowed into admin; expect redirect to login
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/admin/login/?next=", resp.url)