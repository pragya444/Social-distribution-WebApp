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

    path("authors/<str:author_id>/", views.ProfileView.as_view(), name="profile"),

    path("authors/<str:author_id>/follow", views.send_follow_request, name="follow-send"),
    path("authors/<str:author_id>/unfollow", views.unfollow_post, name="follow-unfollow"),
    path("authors/<str:author_id>/requests", views.follow_requests_page, name="follow-requests-page"),
    path("authors/<str:author_id>/requests/<str:follower_id>/approve", views.approve_follow_request, name="follow-approve"),
    path("authors/<str:author_id>/requests/<str:follower_id>/deny", views.deny_follow_request, name="follow-deny"),
]