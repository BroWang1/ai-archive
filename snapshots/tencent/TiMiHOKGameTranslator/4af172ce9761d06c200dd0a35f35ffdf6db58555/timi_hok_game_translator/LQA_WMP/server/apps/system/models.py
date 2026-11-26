from django.db import models

class SystemLanguage(models.Model):
    id = models.IntegerField(primary_key=True)
    language = models.CharField(max_length=45, verbose_name='语言')
    language_code = models.CharField(max_length=45, verbose_name='语言编码')
    is_delete = models.IntegerField(default=0, verbose_name='逻辑删除')

    class Meta:
        db_table = 'lqa_system_language'
