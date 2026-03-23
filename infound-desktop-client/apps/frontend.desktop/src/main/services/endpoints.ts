export const API_ENDPOINTS = {
  auth: {
    login: '/account/login'
  },
  user: {
    current: '/user/current',
    checkToken: '/user/check-token'
  },
  tkShop: {
    entries: '/shop/entries',
    add: '/shop/add',
    list: '/shop/list',
    open: '/shop/open',
    update: '/shop/update',
    delete: '/shop/delete'
  },
  task: {
    claim: '/task/claim',
    heartbeat: '/task/{taskId}/heartbeat',
    report: '/task/{taskId}/report'
  }
} as const
