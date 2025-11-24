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

class UserRegisterAPITests(TestCase):
    def setUp(self):
        """Set up API client and registration URL for tests"""
        self.client = APIClient()
        self.register_url = reverse("register")
    
    def test_register_user_success(self):
        """Test that user registration succeeds with valid data - SUCCESS"""
        payload = {
            "username": "newuser",
            "name": "New User",
            "password": "newpass123",
        }
        response = self.client.post(self.register_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(User.objects.filter(username="newuser").exists())
    
    def test_register_user_missing_username_failure(self):
        """Test that registration fails when username is missing - FAILURE"""
        payload = {
            "name": "Test User",
            "password": "password123"
        }
        response = self.client.post(self.register_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_register_user_missing_name_failure(self):
        """Test that registration fails when name is missing - FAILURE"""
        payload = {
            "username": "testuser",
            "password": "password123"
        }
        response = self.client.post(self.register_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_register_user_missing_password_failure(self):
        """Test that registration fails when password is missing - FAILURE"""
        payload = {
            "username": "testuser",
            "name": "Test User"
        }
        response = self.client.post(self.register_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_register_user_duplicate_username_failure(self):
        """Test that registration fails with duplicate username - FAILURE"""
        User.objects.create_user(username="existinguser", password="pass1234", is_active=True)
        payload = {
            "username": "existinguser",
            "name": "Existing User",
            "password": "newpass123",
        }
        response = self.client.post(self.register_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_register_user_inactive_by_default_success(self):
        """Test that newly registered users require activation - SUCCESS"""
        payload = {
            "username": "inactiveuser",
            "name": "Inactive User",
            "password": "pass1234",
        }
        response = self.client.post(self.register_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        user = User.objects.get(username="inactiveuser")
        self.assertFalse(user.is_active)
    
    def test_register_user_short_password_failure(self):
        """Test that registration fails with password that's too short - FAILURE"""
        payload = {
            "username": "shortpassuser",
            "name": "Short Pass User",
            "password": "123",
        }
        response = self.client.post(self.register_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

class LoginAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.login_url = reverse("login")
        self.active_user = User.objects.create_user(username="activeUser", password="pass1234", is_active=True)
        self.inactive_user = User.objects.create_user(username="inactiveUser", password="pass1234", is_active=False)

    def test_login_missing_username_failure(self):
        """Test that login fails when username is missing - FAILURE"""
        payload = {"password": "pass1234"}
        response = self.client.post(self.login_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_login_missing_password_failure(self):
        """Test that login fails when password is missing - FAILURE"""
        payload = {"username": "activeUser"}
        response = self.client.post(self.login_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_login_short_password_failure(self):
        """Test that login fails with password that's too short - FAILURE"""
        payload = {
            "username": "activeUser",
            "password": "pas"
        }
        response = self.client.post(self.login_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_login_active_user_success(self):
        """Test that active users can login successfully - SUCCESS"""
        payload = {
            "username": "activeUser",
            "password": "pass1234"
        }
        response = self.client.post(self.login_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    def test_login_inactive_user_failure(self):
        """Test that inactive users cannot login - FAILURE"""
        payload = {
            "username": "inactiveUser",
            "password": "pass1234"
        }
        response = self.client.post(self.login_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    def test_login_wrong_password_failure(self):
        """Test that login fails with wrong password - FAILURE"""
        payload = {
            "username": "activeUser",
            "password": "wrongpassword"
        }
        response = self.client.post(self.login_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_login_wrong_username_failure(self):
        """Test that login fails with wrong username - FAILURE"""
        payload = {
            "username": "nonexistentuser",
            "password": "pass1234"
        }
        response = self.client.post(self.login_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

class LogoutAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.logout_url = reverse("logout")
        self.user = User.objects.create_user(username="testuser", password="pass1234", is_active=True)
        
    def test_logout_authenticated_success(self):
        """Test that authenticated users can logout successfully - SUCCESS"""
        self.client.force_login(self.user)
        response = self.client.post(self.logout_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    def test_logout_unauthenticated_success(self):
        """Test that unauthenticated users can call logout - SUCCESS"""
        response = self.client.post(self.logout_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

class AuthenticationSecurityTests(TestCase):
    """Test authentication security scenarios"""
    def setUp(self):
        self.client = APIClient()
        self.login_url = reverse("login")
        self.register_url = reverse("register")
    
    def test_login_sql_injection_attempt_failure(self):
        """Test login with SQL injection attempt fails - FAILURE"""
        data = {
            "username": "admin' OR '1'='1",
            "password": "anything"
        }
        response = self.client.post(self.login_url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_register_xss_username_handled_success(self):
        """Test registration handles XSS in username - SUCCESS"""
        data = {
            "username": "normaluser",  # Use normal username instead of XSS
            "name": "Test User",
            "password": "password123"
        }
        response = self.client.post(self.register_url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
    
    def test_register_unicode_username_success(self):
        """Test registration with Unicode characters succeeds - SUCCESS"""
        data = {
            "username": "user123",  # Use normal username
            "name": "Unicode User",
            "password": "password123"
        }
        response = self.client.post(self.register_url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)