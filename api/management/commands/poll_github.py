from django.core.management.base import BaseCommand
import time
from dotenv import load_dotenv
import os
import requests
import pprint

from ...models import Entry
from django.contrib.auth import get_user_model

User = get_user_model()

load_dotenv()
GITHUB_PAT = os.getenv("GITHUB_PAT")


class Command(BaseCommand):
    help = "Poll GitHub for updates"

    def handle(self, *args, **options):
        self.stdout.write("Starting GitHub Poller...")
        while True:
            self.stdout.write("Polling GitHub...")

            try:
                users = User.objects.exclude(github__isnull=True).exclude(github="")
                for user in users:
                    github_url = user.github
                    github_username = github_url.rstrip("/").split("/")[-1]
                    github_etag = user.github_etag
                    last_seen_github_id = user.latest_github_event_id

                    headers = {
                        "Authorization": f"Bearer {GITHUB_PAT}",
                        "If-None-Match": github_etag,
                    }

                    response = requests.get(f"https://api.github.com/users/{github_username}/events", headers=headers)
                    if response.status_code == 200:
                        print("Success for user: ", user.username)
                        print(response.headers.get("ETag"))
                        data = response.json()
                        if len(data) != 0:
                            latest_event_id = data[0].get('id')
                        else:
                            continue

                        if last_seen_github_id and latest_event_id != last_seen_github_id:
                            create_events(data, last_seen_github_id, user)

                        user.github_etag = response.headers.get("ETag")
                        user.latest_github_event_id = latest_event_id
                        user.save()
                    elif response.status_code == 304:
                        print("No change in github for: ", user.username)
                    else:
                        print("Error in API call, ", response.status_code)

            except KeyboardInterrupt:
                self.stdout.write("Stopping GitHub Poller...")
                break


            time.sleep(60)  # Poll every minute


def create_events(data, last_seen, user):
    to_create = []
    
    for d in data:
        if d.get('id') == last_seen:
            break
        to_create.append(d)
    
    to_create.reverse()

    for entry in to_create:
        title = "New GitHub Entry"
        visibility = "PUBLIC"
        content = f"I just did a Github {entry.get('type')} on {entry.get('repo').get('name')}!"

        e = Entry.objects.create(
            author=user,              
            title=title,                
            content=content,          
            visibility=visibility,        # enum value
            content_type="text/plain",
            is_deleted=False,             # ensure visible
        )

        print(f"Created GitHub entry for user {user.username}: {e.content}")