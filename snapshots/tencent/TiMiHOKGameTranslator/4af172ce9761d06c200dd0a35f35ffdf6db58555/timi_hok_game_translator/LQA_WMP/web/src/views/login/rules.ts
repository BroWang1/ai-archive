import type { FormItemRule } from 'element-plus';

/** 与后端 apps/user/schemas.py 保持一致 */
export const USERNAME_RULE: FormItemRule = {
  pattern: /^[A-Za-z][A-Za-z0-9_.-]{2,31}$/,
  message: '以字母开头，3~32位，只能包含字母、数字、下划线、点、中划线',
  trigger: 'blur',
};

export const passwordRules = (required = true): FormItemRule[] => [
  { required, message: '请输入密码', trigger: 'blur' },
  { min: 8, max: 64, message: '密码长度需为 8~64 位', trigger: 'blur' },
  {
    validator: (_r, value, cb) => (!value || (/[A-Za-z]/.test(value) && /\d/.test(value))
      ? cb()
      : cb(new Error('密码需同时包含字母和数字'))),
    trigger: 'blur',
  },
];
