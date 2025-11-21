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

'''
The following test cases (EntryModelTests, AuthorEntriesViewTests, EntrySharingTests) were written with the assistance of OpenAI, ChatGPT-5. 2025-10-19.
'''




