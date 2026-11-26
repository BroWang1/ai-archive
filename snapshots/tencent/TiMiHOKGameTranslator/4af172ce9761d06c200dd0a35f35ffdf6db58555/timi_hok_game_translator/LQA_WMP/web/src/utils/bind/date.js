import dayjs from 'dayjs';

const dateRangeBind = {
  clearable: false,
  type: 'daterange',
  align: 'left',
  unlinkPanels: true,
  rangeSeparator: '至',
  startPlaceholder: '开始日期',
  endPlaceholder: '结束日期',
  valueFormat: 'YYYY-MM-DD',
  shortcuts: [
    {
      text: '最近一周',
      value: () => [
        dayjs().subtract(1, 'week')
          .format('YYYY-MM-DD'),
        dayjs().format('YYYY-MM-DD'),
      ],
    },
    {
      text: '最近一个月',
      value: () => [
        dayjs().subtract(1, 'month')
          .format('YYYY-MM-DD'),
        dayjs().format('YYYY-MM-DD'),
      ],
    },
    {
      text: '最近三个月',
      value: () => [
        dayjs().subtract(3, 'month')
          .format('YYYY-MM-DD'),
        dayjs().format('YYYY-MM-DD'),
      ],
    },
  ],
  disabledDate(time) {
    return time > dayjs();
  },
};

export { dateRangeBind };
