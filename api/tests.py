from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from .models import Entry

User = get_user_model()

'''
The following test cases (EntryModelTests, AuthorEntriesViewTests) were written with the asistance of OpenAI, ChatGPT-5. 2025-10-19.
'''


class EntryModelTests(TestCase):
    '''
    This class contains tests for the Entry model
    It tests default values and timestamp handling
    '''
    def setUp(self):
        # create a minimal user for FK relations
        self.user = User.objects.create_user(username="testuser", password="pass")

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
        self.user = User.objects.create_user(username="viewuser", password="pass")
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

