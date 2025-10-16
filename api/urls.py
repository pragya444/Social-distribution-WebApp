from django.urls import path
from . import views

urlpatterns = [
    path('author_all_entries/in/<int:author_id>/', views.author_stream, name='author-all-entries'),
    path('make_entries_public/<str:entry_id>/', views.make_entries_public, name='make-entries-public'),
    
]