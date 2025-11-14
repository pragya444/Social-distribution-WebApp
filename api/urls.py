from django.urls import path
from . import views
from .auth import authViews
from .entries import entryView
from .follow import followViews


urlpatterns = [
    # Auth routes
    path('auth/login/', authViews.LoginView.as_view(), name="login"),
    path('auth/register/', authViews.RegisterView.as_view(), name="register"),
    path('auth/logout/', authViews.LogoutView.as_view(), name='logout'),

    # Author routes
    path('authors/', views.AuthorListView.as_view(), name='author-list'),  # paginated list of authors
    path('authors/<str:author_id>/', views.ProfileView.as_view(), name="profile"), #endpoint to get and update author profile
    path("authors/<str:author_id>/edit/", views.ProfileEditView.as_view(), name="profile_edit"), #endpoint to get edit page

    # author stream, show public entries for a given author
    path('authors/<str:author_id>/stream/', views.AuthorStreamView.as_view(), name='author-all-entries'),

    # Entry routes
    path('entries/<path:entry_fqid>', entryView.EntryByFQIDView.as_view(), name='entry-by-fqid'),
    # pages: simple create form
    path('authors/<str:author_id>/entries/new/', views.EntryCreateView.as_view(), name='entry-create-page'),
    # edit page for a specific entry
    path('authors/<str:author_id>/entries/<str:entry_id>/edit/', views.EntryEditView.as_view(), name='entry-edit-page'),
    # list author entries and create a new entry 
    path('authors/<str:author_id>/entries/', entryView.EntryView.as_view(), name='entries-list-create'),
    # get and update a single entry by id
    path('authors/<str:author_id>/entries/<str:entry_id>/', entryView.SingleEntryView.as_view(), name='entry-retrieve-update'),
    path('authors/<str:author_id>/entries/<str:entry_id>/image/', views.EntryImageView.as_view(), name='entry-image'),

    # Comment routes
    path('authors/<str:author_id>/entries/<str:entry_id>/comments', views.CommentListCreateView.as_view(), name='comments-list-create'),
    path('entries/<path:entry_id>/comments/', views.CommentListCreateView.as_view(), name='comments-list-fqid'),  # for FQID
    path('authors/<str:author_id>/entries/<str:entry_id>/comments/<path:comment_id>/', views.CommentDetailView.as_view(), name='comment-detail'),

    # Like routes
    path('authors/<str:author_id>/entries/<str:entry_id>/likes', views.EntryLikesView.as_view(), name='entry-likes'),
    path('authors/<str:author_id>/entries/<str:entry_id>/comments/<str:comment_id>/likes/', views.CommentLikesView.as_view(), name='comment-likes'),

    # Follow send/unfollow (POST actions)
    path("authors/<str:author_id>/follow", followViews.FollowRequestActionView.as_view(), name="follow-send"),
    path("authors/<str:author_id>/unfollow", followViews.UnfollowView.as_view(), name="follow-unfollow"),

    # Follow requests page (list incoming)
    path("authors/<str:author_id>/requests", followViews.FollowRequestsPageView.as_view(), name="follow-requests-page"),
    # Approve / Deny follow requests (POST)
    path("authors/<str:author_id>/requests/<str:follower_id>/approve", followViews.ApproveFollowRequestView.as_view(), name="follow-approve"),
    path("authors/<str:author_id>/requests/<str:follower_id>/deny", followViews.DenyFollowRequestView.as_view(), name="follow-deny"),

    # Follow / Following / Friends **HTML pages**
    path("authors/<str:author_id>/followers/", followViews.FollowersPageView.as_view(), name="followers-page"),
    path("authors/<str:author_id>/following/", followViews.FollowingPageView.as_view(), name="following-page"),
    path("authors/<str:author_id>/friends/", followViews.FriendsPageView.as_view(), name="friends-page"),

    # JSON API endpoints (no trailing slash)
    path("authors/<str:author_id>/followers", followViews.FollowersListView.as_view(), name="followers-api"),
    path("authors/<str:author_id>/following", followViews.FollowingListView.as_view(), name="following-api"),


    # NEW: follower detail (percent-encoded foreign author FQID)
    path("authors/<str:author_id>/followers/<path:foreign_author_fqid>", followViews.FollowerDetailView.as_view(), name="follower-detail-api" ),
    # JSON API – following detail
    path("authors/<str:author_id>/following/<path:foreign_author_fqid>", followViews.FollowingDetailView.as_view(), name="following-detail-api"),


    # Follow request list & create (API + HTML)
    path('authors/<str:author_id>/follow_requests/', followViews.FollowRequestListView.as_view(), name='follow-requests-api'),
    path('authors/<str:author_id>/follow_requests/send/', followViews.FollowRequestCreateView.as_view(), name='follow-request-create'),

    # New inbox endpoint
    path('authors/<str:author_id>/inbox/', views.InboxView.as_view(), name='inbox'),
]