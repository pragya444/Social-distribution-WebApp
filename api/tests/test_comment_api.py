from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status
import json
import warnings

from api.models import Entry, Follow, Comment, EntryLike, CommentLike  # EntryLike only used indirectly in DB queries

warnings.filterwarnings('ignore', category=Warning, message='.*Pagination may yield inconsistent results.*')
warnings.filterwarnings('ignore', category=UserWarning, message='.*No directory at.*staticfiles.*')

User = get_user_model()

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
        """List all comments made by an author - SUCCESS"""
        Comment.objects.create(
            entry=self.entry,
            author=self.other_user,
            comment="My comment",
            content_type="text/plain"
        )
        url = reverse("commented-list", kwargs={"author_id": self.other_user.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    def test_commented_list_empty_success(self):
        """Commented list when author has no comments - SUCCESS"""
        url = reverse("commented-list", kwargs={"author_id": self.other_user.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    def test_commented_detail_success(self):
        """Get specific comment details - SUCCESS"""
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
        """Get non-existent comment details - 404"""
        url = reverse("commented-detail", kwargs={"author_id": self.other_user.id, "comment_id": "does-not-exist"})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class CommentLikesByFQIDTests(TestCase):
    """Test comment likes by FQID route"""
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
        # ensure fqid exists
        if not self.comment.fqid:
            self.comment.save()
        self.client.force_login(self.user)
        
    def test_comment_likes_by_fqid_success(self):
        """Get comment likes by FQID - 200"""
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
        """Post comment like by FQID - 201"""
        import urllib.parse
        comment_fqid = urllib.parse.quote(self.comment.fqid or self.comment.api_id(), safe='')
        url = reverse("comment-likes-fqid", kwargs={
            "author_id": self.user.id,
            "entry_id": self.entry.id,
            "comment_fqid": comment_fqid
        })
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)


def make_user(username, friends=None):
    u = User.objects.create_user(username=username, password="pw123")
    u.is_active = True
    u.save()
    if friends:
        for f in friends:
            Follow.objects.create(follower=u, followee=f, status=Follow.Status.APPROVED)
            Follow.objects.create(follower=f, followee=u, status=Follow.Status.APPROVED)
    return u

def make_entry(author, visibility="PUBLIC", title="t", content="c"):
    return Entry.objects.create(author=author, visibility=visibility, title=title, content=content, content_type="text/plain")

class CommentAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.author = make_user("author")
        self.other = make_user("other")
        self.friend = make_user("friend", friends=[self.author])

        self.public_entry = make_entry(self.author, "PUBLIC")
        self.friends_entry = make_entry(self.author, "FRIENDS")
        self.private_entry = make_entry(self.author, "PRIVATE")
        self.unlisted_entry = make_entry(self.author, "UNLISTED")

        # one existing comment (public)
        self.comment_public = Comment.objects.create(
            entry=self.public_entry,
            author=self.author,
            comment="hello",
            content_type="text/plain"
        )

    def _comments_url(self, entry):
        return reverse("comments-list-create", kwargs={"author_id": entry.author.id, "entry_id": entry.id})

    def _comment_likes_url(self, entry, comment):
        return reverse("comment-likes", kwargs={
            "author_id": entry.author.id,
            "entry_id": entry.id,
            "comment_id": comment.id
        })

    # --- LIST ---

    def test_list_comments_public_unauthenticated_200(self):
        url = self._comments_url(self.public_entry)
        r = self.client.get(url)
        self.assertEqual(r.status_code, 200)
        self.assertIn("src", r.json())

    def test_list_comments_friends_entry_non_friend_403(self):
        url = self._comments_url(self.friends_entry)
        r = self.client.get(url)  # unauth
        self.assertEqual(r.status_code, 403)

        self.client.login(username="other", password="pw123")
        r2 = self.client.get(url)
        self.assertEqual(r2.status_code, 403)

    def test_list_comments_friends_entry_friend_200(self):
        url = self._comments_url(self.friends_entry)
        self.client.login(username="friend", password="pw123")
        r = self.client.get(url)
        self.assertEqual(r.status_code, 200)

    def test_list_comments_private_entry_non_owner_403(self):
        url = self._comments_url(self.private_entry)
        self.client.login(username="other", password="pw123")
        r = self.client.get(url)
        self.assertEqual(r.status_code, 403)

    def test_list_comments_private_entry_owner_200(self):
        url = self._comments_url(self.private_entry)
        self.client.login(username="author", password="pw123")
        r = self.client.get(url)
        self.assertEqual(r.status_code, 200)

    def test_list_comments_deleted_entry_404(self):
        self.public_entry.is_deleted = True
        self.public_entry.save()
        url = self._comments_url(self.public_entry)
        r = self.client.get(url)
        self.assertEqual(r.status_code, 404)

    # --- CREATE ---

    def test_create_comment_public_entry_authenticated_201(self):
        url = self._comments_url(self.public_entry)
        self.client.login(username="other", password="pw123")
        r = self.client.post(url, data=json.dumps({"comment": "new"}), content_type="application/json")
        self.assertEqual(r.status_code, 201)
        self.assertEqual(Comment.objects.filter(entry=self.public_entry).count(), 2)

    def test_create_comment_missing_field_400(self):
        url = self._comments_url(self.public_entry)
        self.client.login(username="other", password="pw123")
        r = self.client.post(url, data=json.dumps({}), content_type="application/json")
        self.assertEqual(r.status_code, 400)

    def test_create_comment_friends_entry_non_friend_403(self):
        url = self._comments_url(self.friends_entry)
        self.client.login(username="other", password="pw123")
        r = self.client.post(url, data=json.dumps({"comment": "x"}), content_type="application/json")
        self.assertEqual(r.status_code, 403)

    def test_create_comment_friends_entry_friend_201(self):
        url = self._comments_url(self.friends_entry)
        self.client.login(username="friend", password="pw123")
        r = self.client.post(url, data=json.dumps({"comment": "x"}), content_type="application/json")
        self.assertEqual(r.status_code, 201)

    def test_create_comment_private_entry_non_owner_403(self):
        url = self._comments_url(self.private_entry)
        self.client.login(username="other", password="pw123")
        r = self.client.post(url, data=json.dumps({"comment": "x"}), content_type="application/json")
        self.assertEqual(r.status_code, 403)

    def test_create_comment_private_entry_owner_201(self):
        url = self._comments_url(self.private_entry)
        self.client.login(username="author", password="pw123")
        r = self.client.post(url, data=json.dumps({"comment": "x"}), content_type="application/json")
        self.assertEqual(r.status_code, 201)

    def test_create_comment_deleted_entry_404(self):
        self.public_entry.is_deleted = True
        self.public_entry.save()
        url = self._comments_url(self.public_entry)
        self.client.login(username="other", password="pw123")
        r = self.client.post(url, data=json.dumps({"comment": "x"}), content_type="application/json")
        self.assertEqual(r.status_code, 404)

    # --- LIKE COMMENT ---

    def test_like_comment_unauthenticated_403(self):
        url = self._comment_likes_url(self.public_entry, self.comment_public)
        r = self.client.post(url, content_type="application/json")
        self.assertEqual(r.status_code, 403)

    def test_like_comment_public_authenticated_201_or_200(self):
        url = self._comment_likes_url(self.public_entry, self.comment_public)
        self.client.login(username="other", password="pw123")
        r = self.client.post(url, content_type="application/json")
        self.assertIn(r.status_code, (200, 201))
        data = r.json()
        self.assertTrue(data.get("liked"))

    def test_unlike_comment(self):
        url = self._comment_likes_url(self.public_entry, self.comment_public)
        self.client.login(username="other", password="pw123")
        self.client.post(url, content_type="application/json")
        r = self.client.delete(url, content_type="application/json")
        self.assertIn(r.status_code, (200, 204))
        data = r.json() if r.status_code == 200 else {}
        if r.status_code == 200:
            self.assertFalse(data.get("liked"))

    def test_unlike_comment_not_liked_404_or_idempotent(self):
        url = self._comment_likes_url(self.public_entry, self.comment_public)
        self.client.login(username="other", password="pw123")
        r = self.client.delete(url, content_type="application/json")
        self.assertIn(r.status_code, (200, 204, 404))

    def test_like_comment_private_entry_non_owner_403(self):
        private_comment = Comment.objects.create(entry=self.private_entry, author=self.author, comment="p", content_type="text/plain")
        url = self._comment_likes_url(self.private_entry, private_comment)
        self.client.login(username="other", password="pw123")
        r = self.client.post(url, content_type="application/json")
        self.assertEqual(r.status_code, 403)

    def test_like_comment_friends_entry_non_friend_403(self):
        friends_comment = Comment.objects.create(entry=self.friends_entry, author=self.author, comment="f", content_type="text/plain")
        url = self._comment_likes_url(self.friends_entry, friends_comment)
        self.client.login(username="other", password="pw123")
        r = self.client.post(url, content_type="application/json")
        self.assertEqual(r.status_code, 403)

    def test_like_comment_friends_entry_friend_200_or_201(self):
        friends_comment = Comment.objects.create(entry=self.friends_entry, author=self.author, comment="f", content_type="text/plain")
        url = self._comment_likes_url(self.friends_entry, friends_comment)
        self.client.login(username="friend", password="pw123")
        r = self.client.post(url, content_type="application/json")
        self.assertIn(r.status_code, (200, 201))

    # --- COMMENT FQID RETRIEVAL  ---

    def test_get_comment_by_fqid_public_200(self):
        if not self.comment_public.fqid:
            self.comment_public.save()
        url = reverse("entry-comment-by-fqid", kwargs={
            "author_id": self.public_entry.author.id,
            "entry_id": self.public_entry.id,
            "remote_comment_fqid": self.comment_public.fqid
        })
        r = self.client.get(url)
        self.assertEqual(r.status_code, 200)

    def test_get_comment_by_fqid_nonexistent_404(self):
        fake_fqid = "http://example.com/api/authors/{}/entries/{}/comments/doesnotexist".format(
            self.public_entry.author.id,
            self.public_entry.id
        )
        url = reverse("entry-comment-by-fqid", kwargs={
            "author_id": self.public_entry.author.id,
            "entry_id": self.public_entry.id,
            "remote_comment_fqid": fake_fqid
        })
        r = self.client.get(url)
        self.assertEqual(r.status_code, 404)