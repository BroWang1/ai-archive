
from django.urls import path

from . import views

urlpatterns = [
    path('enums/<str:cate>', views.EnumsView.as_view(), name='enum_cate')
]