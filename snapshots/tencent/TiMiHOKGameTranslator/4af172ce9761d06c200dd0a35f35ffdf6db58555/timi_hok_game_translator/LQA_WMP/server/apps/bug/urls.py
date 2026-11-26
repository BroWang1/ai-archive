
from django.urls import path

from .views import *

urlpatterns = [
    path('entity', BugView.as_view(), name='bug'),
    path('list', BugListView.as_view(), name='bug-list'),

    path('build_info', view_bug_build_info, name='bug_build_info'),
    path('tracker_meta', view_tracker_meta, name='tracker_meta'),
    path('tracker_fields', view_tracker_fields, name='tracker_fields'),
    path('tracker_test', view_tracker_test, name='tracker_test'),
    path('export_excel', view_bug_export_excel, name='bug_export_excel'),
]
