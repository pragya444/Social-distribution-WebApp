from django.urls import path
from . import views
from .auth import authViews


urlpatterns = [   
    path('auth/login/', authViews.LoginView.as_view(), name="login"),
    path('auth/register/', authViews.RegisterView.as_view(), name="register"),
    path('auth/logout/', authViews.LogoutView.as_view(), name='logout'),
    path('authors/<str:author_id>/', views.ProfileView.as_view(), name="profile"),
    path("authors/<str:author_id>/edit/", views.ProfileEditView.as_view(), name="profile_edit"),
    # author stream, show public entries for a given author
    path('authors/<str:author_id>/stream/', views.author_stream, name='author-all-entries'),

    # pages: simple create and edit forms
    path('authors/<str:author_id>/entries/new/', views.entry_create_page, name='entry-create-page'),
 
    # edit page for a specific entry
    path('authors/<str:author_id>/entries/<str:entry_id>/edit/', views.entry_edit_page, name='entry-edit-page'),
    
    # api: list author entries and create a new entry
    path('authors/<str:author_id>/entries/', views.entries_list_create, name='entries-list-create'),
  
    # api: get and update a single entry by id
    path('authors/<str:author_id>/entries/<str:entry_id>/', views.entry_retrieve_update, name='entry-retrieve-update'),

    path('api/authors/<author_id>/entries/<entry_id>/image/', views.entry_image_binary, name='entry-image'),
    
    path('authors/<author_id>/entries/<entry_id>/delete/', views.entry_delete, name='entry-delete'),
    path('share/<uuid:token>/', views.entry_shared_view, name='entry-shared-view'),
    path('api/authors/<str:author_id>/entries/<str:entry_id>/comments', views.comments_list_create, name='comments-list-create'),
    path('api/authors/<str:author_id>/entries/<str:entry_id>/likes', views.entry_likes, name='entry-likes'),
    path('api/authors/<str:author_id>/entries/<str:entry_id>/comments/<str:comment_id>/likes',views.comment_likes, name='comment-likes'),
]