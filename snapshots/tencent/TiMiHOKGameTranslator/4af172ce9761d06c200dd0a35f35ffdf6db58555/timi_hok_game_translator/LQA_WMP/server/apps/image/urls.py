
from django.urls import path

from .views import *

urlpatterns = [
    path('entity', ImageView.as_view(), name='image'),
    path('list', ImageListView.as_view(), name='image-list'),
    path('ai_sign', ImageAiSignView.as_view(), name='image-ai-sign'),
    path('data_review', DataReviewView.as_view(), name='data-review'),
    # path('resource_version/list', ResourceVersionView.as_view(), name='resource-version-list')
]