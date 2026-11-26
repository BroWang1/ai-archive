from django.urls import path

from .views import *

urlpatterns = [
    path('', IndexView.as_view(), name='index'),
    path('api/health', view_health, name='health'),
    path('api/ticket', TicketView.as_view(), name='ticket'),
    path('api/disk_usage', DiskUsageView.as_view(), name='disk_usage'),
    path('api/upload_file', view_upload_file, name='upload_file'),
    path('api/test', view_test)
]
