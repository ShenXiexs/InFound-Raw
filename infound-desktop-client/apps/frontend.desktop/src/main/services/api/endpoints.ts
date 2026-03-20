export const API_ENDPOINTS = {
  auth: {
    login: '/account/login'
  },
  user: {
    current: '/user/current',
    checkToken: '/user/check-token'
  }
} as const
