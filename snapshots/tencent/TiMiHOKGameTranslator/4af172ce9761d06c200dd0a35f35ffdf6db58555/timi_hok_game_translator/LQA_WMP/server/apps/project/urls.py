
from django.urls import path

from .views import *

urlpatterns = [
    path('config', ProjectConfigView.as_view(), name='project-config'),

    path('module', ProjectModuleView.as_view(), name='project-module'),
    path('module/list', ProjectModuleListView.as_view(), name='project-module-list'),

    path('entity', ProjectView.as_view(), name='project'),
    path('roles', ProjectRolesView.as_view(), name='project-roles'),
    path('list', ProjectListView.as_view(), name='project-list'),
]