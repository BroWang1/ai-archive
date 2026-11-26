from django.core.management.base import BaseCommand

from apps.user import service as user_svr


class Command(BaseCommand):

    def add_arguments(self, parser):
        parser.add_argument("-u", "--uid", type=int, required=True, help="请输入uid")
        parser.add_argument("-e", "--exp", type=int, default=864000*30, help="请输入过期时间单位秒，默认30天")

    def handle(self, *args, **options):
        uid = options['uid']
        exp = options['exp']
        access_token = user_svr.update_user_access_token(uid, exp)
        print(f'==> uid:{uid}, exp:{exp} access_token:{access_token}')
