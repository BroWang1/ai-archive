import { dict, useCompute } from '@fast-crud/fast-crud';
// import basicApi from '@/api';
import { request } from '@/utils/service';

const { compute } = useCompute();

/**
 * 下拉框过滤创建，可根据 ;|, 批量创建
 */
function autoCreate(key) {
  return {
    multiple: true,
    allowCreate: true,
    defaultFirstOption: true,
    reserveKeyword: false,
    filterMethod: compute(({ form }) => {
      function userFilter(e) {
        if (e.search(',|;') !== -1) {
          e.split(/;|,/).map((item) => {
            const properValue = item.trim();
            if (properValue && !form[key].includes(properValue)) {
              form[key].push(properValue);
            }
          });
        }
      }

      return userFilter;
    }),
  };
}

// function userFormatDict(projectId) {
// 	return dict({
// 		url: () => {
// 			const params = { current: 1, limit: 10000 };
// 			if (projectId) {
// 				params.project_id = projectId;
// 			}
// 			const queryParams = new URLSearchParams(params);
// 			return `${basicApi.basics.user.url}?${queryParams}`;
// 		},
// 		getData: async ({ url }) => {
// 			const { records } = await http.get(url);
// 			records.forEach((item) => {
// 				// eslint-disable-next-line no-param-reassign
// 				item.userFormatName = `${item.user_name}(${item.user_chn_name})`;
// 			});
// 			return records;
// 		},
// 		value: 'user_name',
// 		label: 'userFormatName',
// 		cache: false,
// 	});
// }

export {
  // userFormatDict,
  autoCreate,
};
