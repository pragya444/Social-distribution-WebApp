from django.urls import path
from . import views
from .auth import authViews
from .entries import entryView
from .views import EntryImageView, EntryImageFQIDView
from .inbox import inboxView
from .authors import authorView
from .follow import followViews



urlpatterns = [
    # Auth routes
    path('auth/login/', authViews.LoginView.as_view(), name="login"),
    path('auth/register/', authViews.RegisterView.as_view(), name="register"),
    path('auth/logout/', authViews.LogoutView.as_view(), name='logout'),

    # Author routes
    path('authors/', authorView.AuthorListView.as_view(), name='author-list'),  # paginated list of authors
    path('authors/<str:author_id>/', authorView.ProfileView.as_view(), name="profile"), #endpoint to get and update author profile
    path("authors/<str:author_id>/edit/", authorView.ProfileEditView.as_view(), name="profile_edit"), #endpoint to get edit page

    # author stream, show public entries for a given author
    path('authors/<str:author_id>/stream/', views.AuthorStreamView.as_view(), name='author-all-entries'),


    
    path("entries/<path:entry_fqid>/image",EntryImageFQIDView.as_view(),name="entry-image-fqid",), #/entries/{ENTRY_FQID}/image
    # path('entries/<path:entry_fqid>', entryView.EntryByFQIDView.as_view(), name='entry-by-fqid'),# Entry FQID routes

    
    
    
    path('authors/<str:author_id>/entries/new/', views.EntryCreateView.as_view(), name='entry-create-page'), # pages: simple create form   
    path('authors/<str:author_id>/entries/<str:entry_id>/edit/', views.EntryEditView.as_view(), name='entry-edit-page'), # edit page for a specific entry    
    path('authors/<str:author_id>/entries/', entryView.EntryView.as_view(), name='entries-list-create'), # list author entries and create a new entry 
    path('authors/<str:author_id>/entries/<str:entry_id>/', entryView.SingleEntryView.as_view(), name='entry-retrieve-update'), # get and update a single entry by id 
    path('authors/<str:author_id>/entries/<str:entry_id>/image/', views.EntryImageView.as_view(), name='entry-image'),
    
    # #/authors/{AUTHOR_SERIAL}/entries/{ENTRY_SERIAL}/image
    # path("authors/<str:author_id>/entries/<str:entry_id>/image", EntryImageView.as_view(),name="entry-image-api",),




    # # Comment routes
    # path('authors/<str:author_id>/entries/<str:entry_id>/comments', views.CommentListCreateView.as_view(), name='comments-list-create'),
    # path('entries/<path:entry_id>/comments/', views.CommentListCreateView.as_view(), name='comments-list-fqid'),  # for FQID
    # path('authors/<str:author_id>/entries/<str:entry_id>/comments/<path:comment_id>/', views.CommentDetailView.as_view(), name='comment-detail'),

    # # Like routes


    path('authors/<str:author_id>/entries/<str:entry_id>/likes', views.EntryLikesView.as_view(), name='entry-likes'), # Local access
    path('entries/<path:entry_fqid>/likes', views.EntryLikesView.as_view(), name='entry-likes-fqid'),  # for FQID
    # TODO: The comment Section
    path('authors/<str:author_id>/entries/<str:entry_id>/comments/<path:comment_fqid>/likes', views.CommentLikesView.as_view(), name='comment-likes-fqid'),  # for FQID
    path('authors/<str:author_id>/entries/<str:entry_id>/comments/<str:comment_id>/likes/', views.CommentLikesView.as_view(), name='comment-likes'), # Local access
    
    
    
    # Liked routes
    path('authors/<str:author_id>/liked', views.LikedView.as_view(), name='liked-entries'),
    path('authors/<str:author_id>/liked/<str:like_id>', views.LikedView.as_view(), name='liked-entry-detail'),
    path('authors/<path:author_fqid>/liked', views.LikedView.as_view(), name='liked-entries-fqid'),  # for FQID
    path('liked/<path:liked_fqid>', views.LikedView.as_view(), name='liked-entry-detail-fqid'),  # for FQID

    # Follow send/unfollow (POST actions)
    path("authors/<str:author_id>/follow", followViews.FollowRequestActionView.as_view(), name="follow-send"),
    path("authors/<str:author_id>/unfollow", followViews.UnfollowView.as_view(), name="follow-unfollow"),

    # Follow requests page (list incoming)
    path("authors/<str:author_id>/requests", followViews.FollowRequestsPageView.as_view(), name="follow-requests-page"),
    # Approve / Deny follow requests (POST)
    path("authors/<str:author_id>/requests/<str:follower_id>/approve", followViews.ApproveFollowRequestView.as_view(), name="follow-approve"),
    path("authors/<str:author_id>/requests/<str:follower_id>/deny", followViews.DenyFollowRequestView.as_view(), name="follow-deny"),



    # Followers JSON endpoint (both versions)
    path("authors/<str:author_id>/followers", followViews.FollowersListView.as_view(), name="followers-api"),
    path("authors/<str:author_id>/followers/", followViews.FollowersListView.as_view(), name="followers-api-slash"),

    # Following JSON endpoint (both versions)
    path("authors/<str:author_id>/following", followViews.FollowingListView.as_view(), name="following-api"),
    path("authors/<str:author_id>/following/", followViews.FollowingListView.as_view(), name="following-api-slash"),


    # Follow / Following / Friends **HTML pages**
    path("authors/<str:author_id>/followers/page/", followViews.FollowersPageView.as_view(), name="followers-page"),    
    path("authors/<str:author_id>/following/page", followViews.FollowingPageView.as_view(), name="following-page"),
    path("authors/<str:author_id>/friends/", followViews.FriendsPageView.as_view(), name="friends-page"),



    # New follower detail (percent-encoded foreign author FQID)
    path("authors/<str:author_id>/followers/<path:foreign_author_fqid>", followViews.FollowerDetailView.as_view(), name="follower-detail-api" ),
    # JSON API – following detail
    path("authors/<str:author_id>/following/<path:foreign_author_fqid>", followViews.FollowingDetailView.as_view(), name="following-detail-api"),




    # Follow request list & create (API + HTML)
    path('authors/<str:author_id>/follow_requests/', followViews.FollowRequestListView.as_view(), name='follow-requests-api'),
    path('authors/<str:author_id>/follow_requests/send/', followViews.FollowRequestCreateView.as_view(), name='follow-request-create'),

    # New inbox endpoint
    path('authors/<str:author_id>/inbox', inboxView.InboxView.as_view(), name='inbox-api'),
    path('authors/<str:author_id>/inbox/', inboxView.InboxView.as_view(), name='inbox'),



    path('authors/<str:author_id>/entries/<str:entry_id>/comments',views.CommentListCreateView.as_view(),name='comments-list-create',),
    path('authors/<str:author_id>/entries/<str:entry_id>/likes',views.EntryLikesView.as_view(),name='entry-likes',),
    path('authors/<str:author_id>/entries/<str:entry_id>/comments/<str:comment_id>/likes/',views.CommentLikesView.as_view(),name='comment-likes',),

    # JSON API endpoints 
    path("api/authors/<str:author_id>/entries/<str:entry_id>/comments",views.CommentListCreateView.as_view(),name="api-comments-list-create",),
    path("api/authors/<str:author_id>/entries/<str:entry_id>/likes",views.EntryLikesView.as_view(),name="api-entry-likes",),
    path("api/authors/<str:author_id>/entries/<str:entry_id>/comments/<str:comment_id>/likes/",views.CommentLikesView.as_view(),name="api-comment-likes",),
    

     # === Comments API ===
     path(
     "authors/<str:author_id>/inbox/",
     inboxView.InboxView.as_view(),
     name="author-inbox",
     ),
     path("entries/<path:entry_fqid>/comments",
     views.EntryCommentsByFQIDView.as_view(),
     name="entry-comments-by-fqid"),


     path("authors/<str:author_id>/entries/<str:entry_id>/comments/<path:remote_comment_fqid>",
     views.EntryCommentByFQIDView.as_view(),
     name="entry-comment-by-fqid"),

     # === Commented API ===
     path("authors/<str:author_id>/commented",
     views.CommentedListView.as_view(),
     name="commented-list"),

     path("authors/<path:author_id>/commented",
     views.CommentedListView.as_view(),
     name="commented-list-fqid"),

     path("authors/<str:author_id>/commented/<str:comment_id>",
     views.CommentedDetailView.as_view(),
     name="commented-detail"),

     path("commented/<path:comment_fqid>",
     views.CommentedByFQIDView.as_view(),
     name="commented-by-fqid"),

    path('entries/<path:entry_fqid>', entryView.EntryByFQIDView.as_view(), name='entry-by-fqid'),
]