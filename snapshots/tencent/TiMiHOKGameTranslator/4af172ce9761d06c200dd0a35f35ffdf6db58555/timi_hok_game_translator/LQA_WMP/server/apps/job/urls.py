
from django.urls import path

from .views import *

urlpatterns = [
    path('list', JobListView.as_view(), name='job-list'),
    path('entity', JobView.as_view(), name='job'),
    path('bug_regress', JobBugRegressView.as_view(), name='job-bug-gegress'),
    # path('retry', JobRetryView.as_view(), name='job-retry'),
    path('datas', JobDatasView.as_view(), name='job-datas'),
    path('device', JobDeviceView.as_view(), name='job-device'),
    path('action', JobActionView.as_view(), name='job-action'),
    path('progress', view_job_progress, name='job-progress')
]
