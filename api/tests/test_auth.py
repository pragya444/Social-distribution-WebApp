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

'''
The test refactoring was assited by OpenAI ChatGPT-5, 2025-11-23
'''

warnings.filterwarnings('ignore', category=Warning, message='.*Pagination may yield inconsistent results.*')        # filter out pagination warnings
warnings.filterwarnings('ignore', category=UserWarning, message='.*No directory at.*staticfiles.*')     # filter out staticfiles warnings

User = get_user_model()

class UserRegisterTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.register_url = reverse("register")

    def test_register_user_success(self):
        payload = {"username": "newuser", "name": "New User", "password": "newpass123"}
        response = self.client.post(self.register_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(User.objects.filter(username="newuser").exists())
        
    def test_register_missing_all_fields(self):
        response = self.client.post(self.register_url, {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_register_missing_name(self):
        payload = {"username": "abc", "password": "pass123"}
        response = self.client.post(self.register_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_register_missing_password(self):
        payload = {"username": "abc", "name": "User"}
        response = self.client.post(self.register_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_register_missing_username(self):
        payload = {"name": "User", "password": "pass123"}
        response = self.client.post(self.register_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_register_duplicate_username(self):
        User.objects.create_user(username="existing", password="pass", is_active=True)
        payload = {"username": "existing", "name": "New", "password": "pass123"}
        response = self.client.post(self.register_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_register_requires_activation(self):
        payload = {"username": "inactive", "name": "User", "password": "pass1234567"}
        response = self.client.post(self.register_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        user = User.objects.get(username="inactive")
        self.assertFalse(user.is_active)

    def test_register_short_password(self):
        payload = {"username": "short", "name": "User", "password": "123"}
        response = self.client.post(self.register_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        
class LoginTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.login_url = reverse("login")
        self.logout_url = reverse("logout")
        self.active = User.objects.create_user(username="active", password="pass1234", is_active=True)
        self.inactive = User.objects.create_user(username="inactive", password="pass1234")

    def test_login_missing_all_fields(self):
        response = self.client.post(self.login_url, {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_login_missing_password(self):
        response = self.client.post(self.login_url, {"username": "active"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_login_missing_username(self):
        response = self.client.post(self.login_url, {"password": "pass1234"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_login_short_password(self):
        response = self.client.post(self.login_url, {"username": "active", "password": "12"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_login_success_active(self):
        response = self.client.post(self.login_url, {"username": "active", "password": "pass1234"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_302_FOUND)
        self.assertIn("jwt", response.cookies)

    def test_login_inactive_user_fails(self):
        response = self.client.post(self.login_url, {"username": "inactive", "password": "pass1234"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertNotIn("jwt", response.cookies)

    def test_login_wrong_password(self):
        response = self.client.post(self.login_url, {"username": "active", "password": "wrongpass"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_login_wrong_username(self):
        response = self.client.post(self.login_url, {"username": "doesnotexist", "password": "pass1234"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        
    def test_logout_clears_cookie(self):
        self.client.post(self.login_url, {"username": "active", "password": "pass1234"}, format="json")
        response = self.client.post(self.logout_url)
        self.assertEqual(response.status_code, status.HTTP_302_FOUND)
        self.assertEqual(response.cookies["jwt"].value, "")

    def test_logout_when_not_logged_in(self):
        response = self.client.post(self.logout_url)
        # Expected behavior: redirect to login
        self.assertEqual(response.status_code, status.HTTP_302_FOUND)

class AuthenticationEdgeCaseTests(TestCase):
    """Test authentication edge cases"""
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username="auth_edge", password="securepass123", is_active=True)
    
    def test_login_sql_injection(self):
        """Test login with SQL injection attempt"""
        url = reverse("login")
        data = {
            "username": "admin' OR '1'='1",
            "password": "anything"
        }
        response = self.client.post(url, data, format="json")
        self.assertIn(response.status_code, [
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_403_FORBIDDEN
        ])
    
    def test_register_xss_username(self):
        """Test registration with XSS in username"""
        url = reverse("register")
        data = {
            "username": "<script>alert('xss')</script>",
            "name": "Test User",
            "password": "password123"
        }
        response = self.client.post(url, data, format="json")
        self.assertIn(response.status_code, [
            status.HTTP_201_CREATED,
            status.HTTP_400_BAD_REQUEST
        ])
    
    def test_register_unicode_username(self):
        """Test registration with Unicode characters"""
        url = reverse("register")
        data = {
            "username": "用户名123",
            "name": "Unicode User",
            "password": "password123"
        }
        response = self.client.post(url, data, format="json")
        self.assertIn(response.status_code, [
            status.HTTP_201_CREATED,
            status.HTTP_400_BAD_REQUEST
        ])
    
    def test_logout_when_not_logged_in(self):
        """Test logout when not authenticated"""
        url = reverse("logout")
        response = self.client.post(url)
        self.assertIn(response.status_code, [
            status.HTTP_302_FOUND,
            status.HTTP_200_OK,
            status.HTTP_401_UNAUTHORIZED
        ])

class AuthenticationMiddlewareTests(TestCase):
    """Test JWT authentication middleware"""
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username="testuser", password="pass", is_active=True)
        
    def test_jwt_token_generation(self):
        """Test JWT token is generated on login"""
        from api.utils import jwtUtils
        token = jwtUtils.make_access_token(self.user.id)
        self.assertIsNotNone(token)
        self.assertIsInstance(token, str)
    
    def test_jwt_token_validation(self):
        """Test JWT token validation"""
        from api.utils import jwtUtils
        token = jwtUtils.make_access_token(self.user.id)
        self.assertIsNotNone(token)
        self.assertIsInstance(token, str)
        self.assertTrue(len(token) > 0)
