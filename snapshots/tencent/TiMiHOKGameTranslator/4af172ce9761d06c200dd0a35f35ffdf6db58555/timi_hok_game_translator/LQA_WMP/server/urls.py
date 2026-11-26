from django.urls import path, re_path, include
from django.utils.module_loading import import_string
from django.views.static import serve

import settings

urlpatterns = [
    # 截图等上传文件, 由登录中间件鉴权 (MEDIA_PUBLIC=true 时允许匿名访问)
    # 访问量大时可改为由 Nginx 直接提供 APP_MEDIA_ROOT/media 目录
    re_path(r'^media/(?P<path>.*)$', serve, {'document_root': f'{settings.APP_MEDIA_ROOT}/media/'}),
    *import_string('lqa.urls.urlpatterns'),
    path('api/bug/', include('bug.urls')),
    path('api/data/', include('data.urls')),
    path('api/image/', include('image.urls')),
    path('api/job/', include('job.urls')),
    path('api/project/', include('project.urls')),
    path('api/user/', include('user.urls')),
    path('api/system/', include('system.urls'))
]
