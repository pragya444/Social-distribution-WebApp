from django.urls import path
from . import views
from .auth.viewsets import LoginViewSet, RegistrationViewSet



urlpatterns = [
    path('auth/login', LoginViewSet.as_view({'post': "create"}), name='login_user'),
    path('auth/register', RegistrationViewSet.as_view({'post': 'create'}), name='register_user'),
    path('authors/<int:author_id>/stream', views.author_stream, name='author-all-entries'),
    path('authors/<int:author_id>/entries/', views.make_entries_public, name='make-entries-public'),
]