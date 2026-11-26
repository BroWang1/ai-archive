"""
MySQL 数据库后端 (在 Django 官方后端基础上) 允许主键/外键值为 0

系统模板项目使用 id=0 (libs.defs.QCC_PROJECT_ID), 其下的缺陷类型、语言配置的 project_id 为 0,
Django 官方 MySQL 后端会拒绝 0 作为 AutoField 的值, 这里放开该限制,
并在连接上启用 NO_AUTO_VALUE_ON_ZERO, 使显式写入的 0 不会被当作 “生成下一个自增ID”
"""
from django.db.backends.mysql import base, operations


class DatabaseOperations(operations.DatabaseOperations):
    def validate_autopk_value(self, value):
        return value


class DatabaseWrapper(base.DatabaseWrapper):
    ops_class = DatabaseOperations

    def init_connection_state(self):
        super().init_connection_state()
        with self.cursor() as cursor:
            cursor.execute("SET SESSION sql_mode = CONCAT(@@sql_mode, ',NO_AUTO_VALUE_ON_ZERO')")
