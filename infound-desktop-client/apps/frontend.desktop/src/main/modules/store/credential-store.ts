import keytar from 'keytar'

const SERVICE_NAME = 'XunDa'
const ACCOUNT_NAME = 'user-token'

export const credentialStore = {
  async saveToken(token: string) {
    const normalizedToken = token?.trim() || ''
    if (!normalizedToken) {
      await keytar.deletePassword(SERVICE_NAME, ACCOUNT_NAME)
      return
    }

    // service 名称通常是你的应用名
    await keytar.setPassword(SERVICE_NAME, ACCOUNT_NAME, normalizedToken)
  },
  async getToken(): Promise<string | null> {
    return await keytar.getPassword(SERVICE_NAME, ACCOUNT_NAME)
  },
  async clearToken(): Promise<boolean> {
    return await keytar.deletePassword(SERVICE_NAME, ACCOUNT_NAME)
  }
}
