import { customRequest } from '@/utils/service.ts';
import { ElMessage } from 'element-plus';

export async function getBasicInfo(projectId, imageId, form) {
  await customRequest({
    url: '/api/bug/build_info',
    method: 'get',
    params: {
      project_id: projectId,
      image_id: imageId,
      bug_types: (form.bug_types || []).join(','),
    },
  })
    .then((res) => {
      if (res.code === 0) {
        /* eslint-disable */
        form.title = res.data.title;
        form.description = res.data.description;
        form.current_owner = res.data.current_owner;
        form.Key_in_bug = res.data.keyInBugDict || '';
        // 标题前缀
        if (res.data.title_pre) {
          form.fix_title = res.data.title_pre;
        }
        // 发现版本
        if (res.data.version_report) {
          form.version_report_value = res.data.version_report;
        }
        /* eslint-enable */
      } else {
        ElMessage.warning(res.msg);
        // this.show_bug_dialog_fail_show(row)
      }
    })
    .catch((err) => {
      ElMessage.error('请求失败,请联系管理员');
      console.log(`/api/bug/build_info?project_id=${projectId}&image_id=${imageId} 接口调用失败: ${err}`);
    });
}
