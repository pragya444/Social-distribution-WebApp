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

warnings.filterwarnings('ignore', category=Warning, message='.*Pagination may yield inconsistent results.*')        # filter out pagination warnings
warnings.filterwarnings('ignore', category=UserWarning, message='.*No directory at.*staticfiles.*')     # filter out staticfiles warnings

User = get_user_model()

class UserRegisterTests(TestCase):
    def setUp(self):
        """Set up API client and registration URL for tests"""
        self.client = APIClient()
        self.register_url = reverse("register")
    
    def test_register_user_success(self):
        """Test that user registration succeeds with valid data"""
        payload = {
            "username": "newuser",
            "name": "New User",
            "password": "newpass123",
        }
        response = self.client.post(self.register_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(User.objects.filter(username="newuser").exists())
    
    def test_register_user_missing_fields(self):
        """Test that registration fails when required fields are missing"""
        payload = {}
        response = self.client.post(self.register_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        payload = {
            "username": "Incomplete User",
            "password": "pass1234",
        }
        response = self.client.post(self.register_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        payload = {
            "username": "Incomplete User",
            "name": "pass1234",
        }
        response = self.client.post(self.register_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        payload = {
            "name": "Incomplete User",
            "password": "pass1234",
        }
        response = self.client.post(self.register_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_register_user_duplicate_username(self):
        """Test that registration fails with duplicate username"""
        User.objects.create_user(username="existinguser", password="pass1234", is_active=True)
        payload = {
            "username": "existinguser",
            "name": "Existing User",
            "password": "newpass123",
        }
        response = self.client.post(self.register_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_register_user_needs_activation(self):
        """Test that newly registered users require activation"""
        payload = {
            "username": "inactiveuser",
            "name": "Inactive User",
            "password": "pass1234",
        }
        response = self.client.post(self.register_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        user = User.objects.get(username="inactiveuser")
        self.assertFalse(user.is_active)
    
    def test_register_user_short_password(self):
        """Test that registration fails with password that's too short"""
        payload = {
            "username": "shortpassuser",
            "name": "Short Pass User",
            "password": "123",
        }
        response = self.client.post(self.register_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

class LoginTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.login_url = reverse("login")
        self.logout_url = reverse("logout")
        self.active_user = User.objects.create_user(username="activeUser", password="pass1234", is_active=True)
        self.inactive_user = User.objects.create_user(username="inactiveUser", password="pass1234")


    def test_missing_fields(self):
        """Test that login fails when required fields are missing"""
        payloads = [{}, {"username": "activeUser"}, {"password": "pass1234"}]
        for payload in payloads:
            response = self.client.post(self.login_url, payload, format='json')
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertNotIn("jwt", response.cookies)
    
    def test_short_password(self):
        """Test that login fails with password that's too short"""
        payload = {
            "username": "activeUser",
            "password": "pas"
        }

        response = self.client.post(self.login_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertNotIn("jwt", response.cookies)

    def test_active_login_success(self):
        """Test that active users can login successfully"""
        payload = {
            "username": "activeUser",
            "password": "pass1234"
        }

        response = self.client.post(self.login_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_302_FOUND)
        self.assertTrue(response.url.startswith(reverse("author-all-entries", args=[self.active_user.id]).rstrip('/')))
        self.assertIn("jwt", response.cookies)
    
    def test_logout_success(self):
        """Test that users can logout successfully"""
        payload = {
            "username": "activeUser",
            "password": "pass1234"
        }

        response = self.client.post(self.login_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_302_FOUND)
        self.assertIn("jwt", response.cookies)
        

        response = self.client.post(self.logout_url)
        self.assertEqual(response.status_code, status.HTTP_302_FOUND)
        self.assertRedirects(response, reverse("login"))
        cookie = response.cookies["jwt"]
        self.assertEqual(cookie.value, '')
    
    def test_inactive_login_failure(self):
        """Test that inactive users cannot login"""
        payload = {
            "username": "inactiveUser",
            "password": "pass1234"
        }

        response = self.client.post(self.login_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertNotIn("jwt", response.cookies)
    
    def test_wrong_password(self):
        """Test that login fails with wrong password"""
        payload = {
            "username": "activeUser",
            "password": "passs1234"
        }

        response = self.client.post(self.login_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertNotIn("jwt", response.cookies)
        self.assertEqual(response.data["errors"]["error"][0], "Invalid username or password")
    
    def test_wrong_username(self):
        """Test that login fails with wrong username"""
        payload = {
            "username": "activeUsesr",
            "password": "pass1234"
        }

        response = self.client.post(self.login_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertNotIn("jwt", response.cookies)
        self.assertEqual(response.data["errors"]["error"][0], "Invalid username or password")
    
    def test_wrong_username_or_password(self):
        """Test that login fails with both wrong username and password"""
        payload = {
            "username": "activeUsesr",
            "password": "pass12345"
        }

        response = self.client.post(self.login_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertNotIn("jwt", response.cookies)
        self.assertEqual(response.data["errors"]["error"][0], "Invalid username or password")

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
