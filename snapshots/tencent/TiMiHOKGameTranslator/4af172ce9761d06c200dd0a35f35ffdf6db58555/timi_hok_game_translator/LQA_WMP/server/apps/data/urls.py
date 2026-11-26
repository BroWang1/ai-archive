
from django.urls import path

from .views import *

urlpatterns = [
    path('entity', DataView.as_view(), name='data'),
    path('list', DataListView.as_view(), name='data-list'),
    path('resource_version/list', DataResourceVersionView.as_view(), name='data-resource-version-list'),
    path('image_resource', ImagerResourceView.as_view(), name='image-resource'),
    path('image_resource/merge', ImagerResourceMergeView.as_view(), name='image-resource-merge'),
]