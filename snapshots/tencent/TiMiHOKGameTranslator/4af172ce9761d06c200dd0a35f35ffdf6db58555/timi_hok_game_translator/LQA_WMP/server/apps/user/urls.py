
from django.urls import path
from .views import *

urlpatterns = [
    path('auth_config', view_auth_config, name='auth-config'),
    path('login', UserLoginView.as_view(), name='login'),
    path('register', UserRegisterView.as_view(), name='register'),
    path('logout', UserLogoutView.as_view(), name='logout'),
    path('password', UserPasswordView.as_view(), name='password'),
    path('reset_password', view_reset_password, name='reset-password'),
    path('profile', UserProfileView.as_view(), name='profile'),

    path('entity', UserView.as_view(), name='users'),
    path('list', UserListView.as_view(), name='user-list'),

    path('permission', user_permission_view, name='user-permission'),

    path('access_token', UserToken.as_view(), name='access-token')
]
