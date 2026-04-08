import { AppConfig } from '@common/app-config'
import { globalState } from '../modules/state/global-state'
import { appStore } from '../modules/store/app-store'
import { credentialStore } from '../modules/store/credential-store'
import { CookieMap, parseSetCookie } from '../utils/set-cookie-parser'
import { logger } from '../utils/logger'

export async function getRuntimeAuthForEmbed(): Promise<{ token: string; tokenName: string; deviceId: string }> {
  const state = globalState.currentState
  const deviceId = state.appInfo?.deviceId?.trim() || ''
  let tokenName = state.currentUser?.tokenName?.trim() || 'xunda-token'
  let token = state.currentUser?.tokenValue?.trim() || ''

  const apiCookie = appStore.get<string | string[] | undefined>('apiCookie')
  if (apiCookie) {
    const cookieMap: CookieMap = parseSetCookie(apiCookie, { map: true })
    const cookieTokenName = cookieMap['xunda_token_name']?.value?.trim() || ''
    const cookieTokenValue = cookieMap['xunda_token_value']?.value?.trim() || ''
    if (cookieTokenName) {
      tokenName = cookieTokenName
    }
    if (cookieTokenValue) {
      token = cookieTokenValue
    }
  }

  if (!token) {
    token = (await credentialStore.getToken())?.trim() || ''
  }

  return {
    token,
    tokenName,
    deviceId
  }
}

/**
 * 拼接独立部署 embed 的完整 URL（与店铺标签内打开 embed 的规则一致）
 */
export async function buildEmbedPageUrl(hashPath: string, shopId?: string): Promise<string> {
  const normalizedHash = hashPath.startsWith('/') ? hashPath : `/${hashPath}`
  const shopIdValue = shopId?.trim()
  const embedBaseUrl = AppConfig.EMBED_BASE_URL?.trim()
  const auth = await getRuntimeAuthForEmbed()
  if (!embedBaseUrl) {
    const message = 'EMBED_BASE_URL 未配置，无法打开独立 embed 站点'
    logger.error(`[EmbedUrl] ${message}`)
    throw new Error(message)
  }

  try {
    const url = new URL(embedBaseUrl)
    if (shopIdValue) {
      url.searchParams.set('shopId', shopIdValue)
    }
    if (auth.token) {
      url.searchParams.set('xundaToken', auth.token)
      url.searchParams.set('xundaTokenName', auth.tokenName)
    }
    if (auth.deviceId) {
      url.searchParams.set('xundaDeviceId', auth.deviceId)
    }
    url.hash = normalizedHash
    const finalUrl = url.toString()
    logger.info(`[EmbedUrl] ${finalUrl}`)
    return finalUrl
  } catch (error) {
    logger.error(`[EmbedUrl] EMBED_BASE_URL 非法: ${embedBaseUrl}`, error)
    throw new Error(`EMBED_BASE_URL 非法: ${embedBaseUrl}`)
  }
}
