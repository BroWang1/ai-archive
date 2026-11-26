export const timeCols = {
  // 创建时间
  created_at: {
    title: '创建时间',
    type: 'datetime',
    form: { show: false },
  },
  // 更新时间
  updated_at: {
    title: '更新时间',
    type: 'datetime',
    form: { show: false },
    column: {
      // 空渲染
      conditionalRender: {
        match(scope: any) {
          return !scope.value;
        },
        render() {
          return '';
        },
      },
    },
  },
};
