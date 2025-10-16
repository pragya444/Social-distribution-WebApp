from django.contrib import admin
from .models import Entry, User

# Register your models here.
admin.site.register(Entry)
admin.site.register(User)