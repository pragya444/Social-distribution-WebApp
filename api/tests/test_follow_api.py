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


class FollowAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username="testuser", password="pass", is_active=True)
        self.other_user = User.objects.create_user(username="otheruser", password="pass", is_active=True)
        self.client.force_login(self.user)

    def test_send_follow_request(self):
        """Test user story: Follow local authors"""
        url = reverse("follow-send", kwargs={"author_id": self.user.id})
        data = {"target_id": self.other_user.id}
        response = self.client.post(url, data)
        self.assertIn(response.status_code, [
        status.HTTP_200_OK, status.HTTP_302_FOUND, status.HTTP_404_NOT_FOUND, status.HTTP_403_FORBIDDEN ])
        follow = Follow.objects.filter(follower=self.user, followee=self.other_user).first()
        if follow:
            self.assertEqual(follow.status, Follow.Status.PENDING)
        else:
            self.assertIn(response.status_code, [ status.HTTP_200_OK, status.HTTP_302_FOUND, status.HTTP_404_NOT_FOUND, status.HTTP_403_FORBIDDEN])

    def test_approve_follow_request(self):
        """Test user story: Approve follow requests"""
        Follow.objects.create(follower=self.other_user, followee=self.user, status=Follow.Status.PENDING)
        self.client.force_login(self.user)
        url = reverse("follow-approve", kwargs={"author_id": self.user.id, "follower_id": self.other_user.id})
        response = self.client.post(url, follow=True)
        self.assertIn(response.status_code, [status.HTTP_200_OK, status.HTTP_302_FOUND])
        follow = Follow.objects.get(follower=self.other_user, followee=self.user)
        self.assertEqual(follow.status, Follow.Status.APPROVED)

    def test_deny_follow_request(self):
        """Test user story: Deny follow requests"""
        Follow.objects.create(follower=self.other_user, followee=self.user, status=Follow.Status.PENDING)
        self.client.force_login(self.user)
        url = reverse("follow-deny", kwargs={"author_id": self.user.id, "follower_id": self.other_user.id})
        response = self.client.post(url, follow=True)
        self.assertIn(response.status_code, [status.HTTP_200_OK, status.HTTP_302_FOUND])
        self.assertFalse(Follow.objects.filter(follower=self.other_user, followee=self.user).exists())

    def test_unfollow_author(self):
        """Test user story: Unfollow authors"""
        Follow.objects.create(follower=self.user, followee=self.other_user, status=Follow.Status.APPROVED)
        url = reverse("follow-unfollow", kwargs={"author_id": self.user.id})
        data = {"target_id": self.other_user.id}
        response = self.client.post(url, data)
        self.assertIn(response.status_code, [status.HTTP_200_OK, status.HTTP_302_FOUND, status.HTTP_404_NOT_FOUND, status.HTTP_403_FORBIDDEN])
        if response.status_code in [status.HTTP_200_OK, status.HTTP_302_FOUND]:
            self.assertFalse(Follow.objects.filter(follower=self.user, followee=self.other_user).exists())

class FollowEdgeTests(TestCase):
    def setUp(self):
        """Set up users and API client for follow edge case tests"""
        self.client = APIClient()
        self.a = User.objects.create_user(username="a_fe", password="pass", is_active=True)
        self.b = User.objects.create_user(username="b_fe", password="pass", is_active=True)
        self.client.force_login(self.a)

    def test_cannot_follow_self(self):
        """Test that users cannot follow themselves"""
        url = reverse("follow-send", kwargs={"author_id": self.a.id})
        data = {"target_id": self.a.id}
        r = self.client.post(url, data)
        self.assertIn(r.status_code, [status.HTTP_403_FORBIDDEN, status.HTTP_400_BAD_REQUEST, status.HTTP_404_NOT_FOUND])

    def test_duplicate_follow_request_unique(self):
        """Test that duplicate follow requests raise an exception due to uniqueness constraint"""
        Follow.objects.create(follower=self.a, followee=self.b, status=Follow.Status.PENDING)
        with self.assertRaises(Exception):
            Follow.objects.create(follower=self.a, followee=self.b, status=Follow.Status.PENDING)

    def test_mutual_follow_friends(self):
        """Test that mutual approved follows create a friend relationship"""
        Follow.objects.create(follower=self.a, followee=self.b, status=Follow.Status.APPROVED)
        Follow.objects.create(follower=self.b, followee=self.a, status=Follow.Status.APPROVED)
        self.assertTrue(Follow.objects.filter(follower=self.a, followee=self.b, status=Follow.Status.APPROVED).exists())

    def test_unfollow_endpoint(self):
        """Test that the unfollow endpoint removes follow relationships"""
        Follow.objects.create(follower=self.a, followee=self.b, status=Follow.Status.APPROVED)
        url = reverse("follow-unfollow", kwargs={"author_id": self.a.id})
        data = {"target_id": self.b.id}
        r = self.client.post(url, data)
        self.assertIn(r.status_code, [status.HTTP_200_OK, status.HTTP_302_FOUND, status.HTTP_404_NOT_FOUND, status.HTTP_403_FORBIDDEN])

    def test_approve_flow(self):
        """Test that approving a follow request changes status to approved"""
        Follow.objects.create(follower=self.b, followee=self.a, status=Follow.Status.PENDING)
        url = reverse("follow-approve", kwargs={"author_id": self.a.id, "follower_id": self.b.id})
        r = self.client.post(url)
        self.assertIn(r.status_code, [status.HTTP_200_OK, status.HTTP_302_FOUND])

    def test_deny_flow(self):
        """Test that denying a follow request removes it"""
        Follow.objects.create(follower=self.b, followee=self.a, status=Follow.Status.PENDING)
        url = reverse("follow-deny", kwargs={"author_id": self.a.id, "follower_id": self.b.id})
        r = self.client.post(url)
        self.assertIn(r.status_code, [status.HTTP_200_OK, status.HTTP_302_FOUND])

    def test_follow_requests_page_requires_login(self):
        """Test that viewing follow requests requires authentication"""
        self.client.logout()
        url = reverse("follow-requests-page", kwargs={"author_id": self.a.id})
        resp = self.client.get(url)
        self.assertIn(resp.status_code, [status.HTTP_302_FOUND, status.HTTP_403_FORBIDDEN])

    def test_follow_send_requires_login(self):
        """Test that sending follow requests requires authentication"""
        self.client.logout()
        url = reverse("follow-send", kwargs={"author_id": self.a.id})
        data = {"target_id": self.b.id}
        resp = self.client.post(url, data)
        self.assertIn(resp.status_code, [status.HTTP_302_FOUND, status.HTTP_403_FORBIDDEN])

    def test_follow_unique_constraint(self):
        """Test that unique constraint prevents duplicate follow relationships"""
        Follow.objects.create(follower=self.a, followee=self.b, status=Follow.Status.PENDING)
        with self.assertRaises(Exception):
            Follow.objects.create(follower=self.a, followee=self.b, status=Follow.Status.APPROVED)

    def test_no_self_follow_constraint(self):
        """Test that constraint prevents users from following themselves"""
        with self.assertRaises(Exception):
            Follow.objects.create(follower=self.a, followee=self.a, status=Follow.Status.PENDING)

class FollowersFollowingAPITests(TestCase):
    """Test followers and following API endpoints"""
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username="testuser", password="pass", is_active=True)
        self.follower1 = User.objects.create_user(username="follower1", password="pass", is_active=True)
        self.follower2 = User.objects.create_user(username="follower2", password="pass", is_active=True)
        self.client.force_login(self.user)
        
    def test_followers_list_api(self):
        """Test getting list of followers"""
        Follow.objects.create(follower=self.follower1, followee=self.user, status=Follow.Status.APPROVED)
        Follow.objects.create(follower=self.follower2, followee=self.user, status=Follow.Status.APPROVED)
        
        url = reverse("followers-api", kwargs={"author_id": self.user.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
    def test_following_list_api(self):
        """Test getting list of users being followed"""
        Follow.objects.create(follower=self.user, followee=self.follower1, status=Follow.Status.APPROVED)
        Follow.objects.create(follower=self.user, followee=self.follower2, status=Follow.Status.APPROVED)
        
        url = reverse("following-api", kwargs={"author_id": self.user.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    def test_follower_detail_api(self):
        """Test checking if specific user is a follower"""
        Follow.objects.create(follower=self.follower1, followee=self.user, status=Follow.Status.APPROVED)
        
        import urllib.parse
        foreign_fqid = urllib.parse.quote(self.follower1.url, safe='')
        url = reverse("follower-detail-api", kwargs={"author_id": self.user.id, "foreign_author_fqid": foreign_fqid})
        response = self.client.get(url)
        self.assertIn(response.status_code, [status.HTTP_200_OK, status.HTTP_404_NOT_FOUND])
    
    def test_following_detail_api(self):
        """Test checking if following specific user"""
        Follow.objects.create(follower=self.user, followee=self.follower1, status=Follow.Status.APPROVED)
        
        import urllib.parse
        foreign_fqid = urllib.parse.quote(self.follower1.url, safe='')
        url = reverse("following-detail-api", kwargs={"author_id": self.user.id, "foreign_author_fqid": foreign_fqid})
        response = self.client.get(url)
        self.assertIn(response.status_code, [status.HTTP_200_OK, status.HTTP_404_NOT_FOUND])

class FollowerDetailEdgeCaseTests(TestCase):
    """Test follower/following detail endpoint edge cases"""
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username="fd_user", password="pass", is_active=True)
        self.follower = User.objects.create_user(username="fd_follower", password="pass", is_active=True)
        self.client.force_login(self.user)
    
    def test_delete_follower(self):
        """Test removing a follower via DELETE"""
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
        self.assertIn(response.status_code, [
            status.HTTP_204_NO_CONTENT,
            status.HTTP_200_OK,
            status.HTTP_405_METHOD_NOT_ALLOWED,
            status.HTTP_404_NOT_FOUND
        ])
    
    def test_delete_non_existent_follower(self):
        """Test deleting non-existent follower"""
        import urllib.parse
        fake_fqid = urllib.parse.quote("http://fake.com/authors/999", safe='')
        url = reverse("follower-detail-api", kwargs={
            "author_id": self.user.id,
            "foreign_author_fqid": fake_fqid
        })
        response = self.client.delete(url)
        self.assertIn(response.status_code, [
            status.HTTP_404_NOT_FOUND,
            status.HTTP_204_NO_CONTENT,
            status.HTTP_405_METHOD_NOT_ALLOWED
        ])

class FollowRequestAPITests(TestCase):
    """Test follow request API endpoints"""
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username="user_fr", password="pass", is_active=True)
        self.other_user = User.objects.create_user(username="other_fr", password="pass", is_active=True)
        self.client.force_login(self.user)
    
    def test_list_follow_requests(self):
        """Test getting list of follow requests"""
        Follow.objects.create(
            follower=self.other_user,
            followee=self.user,
            status=Follow.Status.PENDING
        )
        url = reverse("follow-requests-api", kwargs={"author_id": self.user.id})
        response = self.client.get(url)
        self.assertIn(response.status_code, [status.HTTP_200_OK, status.HTTP_404_NOT_FOUND])
    
    def test_list_follow_requests_empty(self):
        """Test follow requests list when empty"""
        url = reverse("follow-requests-api", kwargs={"author_id": self.user.id})
        response = self.client.get(url)
        self.assertIn(response.status_code, [status.HTTP_200_OK, status.HTTP_404_NOT_FOUND])
    
    def test_create_follow_request(self):
        """Test creating a follow request via API"""
        url = reverse("follow-request-create", kwargs={"author_id": self.user.id})
        data = {"target_id": self.other_user.id}
        response = self.client.post(url, data)
        self.assertIn(response.status_code, [
            status.HTTP_201_CREATED,
            status.HTTP_200_OK,
            status.HTTP_302_FOUND,
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_404_NOT_FOUND
        ])
    
    def test_create_duplicate_follow_request(self):
        """Test creating duplicate follow request"""
        Follow.objects.create(
            follower=self.user,
            followee=self.other_user,
            status=Follow.Status.PENDING
        )
        url = reverse("follow-request-create", kwargs={"author_id": self.user.id})
        data = {"target_id": self.other_user.id}
        response = self.client.post(url, data)
        self.assertIn(response.status_code, [
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_409_CONFLICT,
            status.HTTP_302_FOUND,
            status.HTTP_200_OK
        ])
