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


class FollowAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username="testuser", password="pass", is_active=True)
        self.other_user = User.objects.create_user(username="otheruser", password="pass", is_active=True)
        self.client.force_login(self.user)

    def test_send_follow_request_success(self):
        """Test user story: Follow local authors - SUCCESS"""
        url = reverse("follow-send", kwargs={"author_id": self.user.id})
        data = {"target_id": self.other_user.id}
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        follow = Follow.objects.filter(follower=self.user, followee=self.other_user).first()
        self.assertIsNotNone(follow)
        self.assertEqual(follow.status, Follow.Status.PENDING)

    def test_send_follow_request_self_failure(self):
        """Test user story: Cannot follow self - FAILURE"""
        url = reverse("follow-send", kwargs={"author_id": self.user.id})
        data = {"target_id": self.user.id}
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_approve_follow_request_success(self):
        """Test user story: Approve follow requests - SUCCESS"""
        Follow.objects.create(follower=self.other_user, followee=self.user, status=Follow.Status.PENDING)
        self.client.force_login(self.user)
        url = reverse("follow-approve", kwargs={"author_id": self.user.id, "follower_id": self.other_user.id})
        response = self.client.post(url, follow=True)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        follow = Follow.objects.get(follower=self.other_user, followee=self.user)
        self.assertEqual(follow.status, Follow.Status.APPROVED)

    def test_deny_follow_request_success(self):
        """Test user story: Deny follow requests - SUCCESS"""
        Follow.objects.create(follower=self.other_user, followee=self.user, status=Follow.Status.PENDING)
        self.client.force_login(self.user)
        url = reverse("follow-deny", kwargs={"author_id": self.user.id, "follower_id": self.other_user.id})
        response = self.client.post(url, follow=True)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(Follow.objects.filter(follower=self.other_user, followee=self.user).exists())

    def test_unfollow_author_success(self):
        """Test user story: Unfollow authors - SUCCESS"""
        Follow.objects.create(follower=self.user, followee=self.other_user, status=Follow.Status.APPROVED)
        url = reverse("follow-unfollow", kwargs={"author_id": self.user.id})
        data = {"target_id": self.other_user.id}
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(Follow.objects.filter(follower=self.user, followee=self.other_user).exists())

    def test_unfollow_not_following_failure(self):
        """Test user story: Unfollow when not following - FAILURE"""
        url = reverse("follow-unfollow", kwargs={"author_id": self.user.id})
        data = {"target_id": self.other_user.id}
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

class FollowEdgeTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.a = User.objects.create_user(username="a_fe", password="pass", is_active=True)
        self.b = User.objects.create_user(username="b_fe", password="pass", is_active=True)
        self.client.force_login(self.a)

    def test_cannot_follow_self_api_failure(self):
        """Test that users cannot follow themselves via API - FAILURE"""
        url = reverse("follow-send", kwargs={"author_id": self.a.id})
        data = {"target_id": self.a.id}
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_duplicate_follow_request_api_failure(self):
        """Test that duplicate follow requests fail via API - FAILURE"""
        Follow.objects.create(follower=self.a, followee=self.b, status=Follow.Status.PENDING)
        url = reverse("follow-send", kwargs={"author_id": self.a.id})
        data = {"target_id": self.b.id}
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)

    def test_approve_flow_success(self):
        """Test that approving a follow request changes status to approved - SUCCESS"""
        Follow.objects.create(follower=self.b, followee=self.a, status=Follow.Status.PENDING)
        url = reverse("follow-approve", kwargs={"author_id": self.a.id, "follower_id": self.b.id})
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        follow = Follow.objects.get(follower=self.b, followee=self.a)
        self.assertEqual(follow.status, Follow.Status.APPROVED)

    def test_deny_flow_success(self):
        """Test that denying a follow request removes it - SUCCESS"""
        Follow.objects.create(follower=self.b, followee=self.a, status=Follow.Status.PENDING)
        url = reverse("follow-deny", kwargs={"author_id": self.a.id, "follower_id": self.b.id})
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(Follow.objects.filter(follower=self.b, followee=self.a).exists())

    def test_follow_send_requires_login_failure(self):
        """Test that sending follow requests requires authentication - FAILURE"""
        self.client.logout()
        url = reverse("follow-send", kwargs={"author_id": self.a.id})
        data = {"target_id": self.b.id}
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

class FollowersFollowingAPITests(TestCase):
    """Test followers and following API endpoints"""
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username="testuser", password="pass", is_active=True)
        self.follower1 = User.objects.create_user(username="follower1", password="pass", is_active=True)
        self.follower2 = User.objects.create_user(username="follower2", password="pass", is_active=True)
        self.client.force_login(self.user)
        
    def test_followers_list_api_success(self):
        """Test getting list of followers - SUCCESS"""
        Follow.objects.create(follower=self.follower1, followee=self.user, status=Follow.Status.APPROVED)
        Follow.objects.create(follower=self.follower2, followee=self.user, status=Follow.Status.APPROVED)
        
        url = reverse("followers-api", kwargs={"author_id": self.user.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
    def test_following_list_api_success(self):
        """Test getting list of users being followed - SUCCESS"""
        Follow.objects.create(follower=self.user, followee=self.follower1, status=Follow.Status.APPROVED)
        Follow.objects.create(follower=self.user, followee=self.follower2, status=Follow.Status.APPROVED)
        
        url = reverse("following-api", kwargs={"author_id": self.user.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    def test_follower_detail_api_success(self):
        """Test checking if specific user is a follower - SUCCESS"""
        Follow.objects.create(follower=self.follower1, followee=self.user, status=Follow.Status.APPROVED)
        
        import urllib.parse
        foreign_fqid = urllib.parse.quote(self.follower1.url, safe='')
        url = reverse("follower-detail-api", kwargs={"author_id": self.user.id, "foreign_author_fqid": foreign_fqid})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    def test_follower_detail_not_found_failure(self):
        """Test checking if specific user is not a follower - FAILURE"""
        import urllib.parse
        foreign_fqid = urllib.parse.quote(self.follower1.url, safe='')
        url = reverse("follower-detail-api", kwargs={"author_id": self.user.id, "foreign_author_fqid": foreign_fqid})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

class FollowerDetailEdgeCaseTests(TestCase):
    """Test follower/following detail endpoint edge cases"""
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username="fd_user", password="pass", is_active=True)
        self.follower = User.objects.create_user(username="fd_follower", password="pass", is_active=True)
        self.client.force_login(self.user)
    
    def test_delete_follower_success(self):
        """Test removing a follower via DELETE - SUCCESS"""
        Follow.objects.create(
            follower=self.follower,
            followee=self.user,
            status=Follow.Status.APPROVED
        )
        import urllib.parse
        follower_fqid = urllib.parse.quote(self.follower.url, safe='')
        url = reverse("follower-detail-api", kwargs={
            "author_id": self.user.id,
            "foreign_author_fqid": follower_fqid
        })
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Follow.objects.filter(follower=self.follower, followee=self.user).exists())
    
    def test_delete_non_existent_follower_failure(self):
        """Test deleting non-existent follower - FAILURE"""
        import urllib.parse
        fake_fqid = urllib.parse.quote("http://fake.com/authors/999", safe='')
        url = reverse("follower-detail-api", kwargs={
            "author_id": self.user.id,
            "foreign_author_fqid": fake_fqid
        })
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

class FollowRequestAPITests(TestCase):
    """Test follow request API endpoints"""
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username="user_fr", password="pass", is_active=True)
        self.other_user = User.objects.create_user(username="other_fr", password="pass", is_active=True)
        self.client.force_login(self.user)
    
    def test_list_follow_requests_success(self):
        """Test getting list of follow requests - SUCCESS"""
        Follow.objects.create(
            follower=self.other_user,
            followee=self.user,
            status=Follow.Status.PENDING
        )
        url = reverse("follow-requests-api", kwargs={"author_id": self.user.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    def test_list_follow_requests_empty_success(self):
        """Test follow requests list when empty - SUCCESS"""
        url = reverse("follow-requests-api", kwargs={"author_id": self.user.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    def test_create_follow_request_success(self):
        """Test creating a follow request via API - SUCCESS"""
        url = reverse("follow-request-create", kwargs={"author_id": self.user.id})
        data = {"target_id": self.other_user.id}
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        follow = Follow.objects.filter(follower=self.user, followee=self.other_user).first()
        self.assertIsNotNone(follow)
        self.assertEqual(follow.status, Follow.Status.PENDING)
    
    def test_create_duplicate_follow_request_failure(self):
        """Test creating duplicate follow request - FAILURE"""
        Follow.objects.create(
            follower=self.user,
            followee=self.other_user,
            status=Follow.Status.PENDING
        )
        url = reverse("follow-request-create", kwargs={"author_id": self.user.id})
        data = {"target_id": self.other_user.id}
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)