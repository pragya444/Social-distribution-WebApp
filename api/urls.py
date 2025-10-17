from django.urls import path
from . import views
from .auth.viewsets import LoginViewSet, RegistrationViewSet



urlpatterns = [
    path('auth/login', LoginViewSet.as_view({'post': "create"}), name='login_user'),
    path('auth/register', RegistrationViewSet.as_view({'post': 'create'}), name='register_user'),
   
    # author stream, show public entries for a given author
    path('authors/<str:author_id>/stream', views.author_stream, name='author-all-entries'),

    # pages: simple create and edit forms
    path('authors/<str:author_id>/entries/new', views.entry_create_page, name='entry-create-page'),
 
    # edit page for a specific entry
    path('authors/<str:author_id>/entries/<str:entry_id>/edit', views.entry_edit_page, name='entry-edit-page'),
    
    # api: list author entries and create a new entry
    path('authors/<str:author_id>/entries', views.entries_list_create, name='entries-list-create'),
  
    # api: get and update a single entry by id
    path('authors/<str:author_id>/entries/<str:entry_id>', views.entry_retrieve_update, name='entry-retrieve-update'),

    path('api/authors/<author_id>/entries/<entry_id>/image', views.entry_image_binary, name='entry-image'),
    
    path('authors/<author_id>/entries/<entry_id>/delete', views.entry_delete, name='entry-delete'),



]