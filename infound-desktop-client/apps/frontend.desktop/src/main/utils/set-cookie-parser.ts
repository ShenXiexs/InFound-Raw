export interface Cookie {
  name: string
  value: string
  expires?: Date
  maxAge?: number
  domain?: string
  path?: string
  secure?: boolean
  httpOnly?: boolean
  sameSite?: 'strict' | 'lax' | 'none'
}

export type CookieMap = Record<string, Cookie>

export interface ParseOptions {
  decodeValues?: boolean // 默认 true
  map?: boolean // 返回 Map 而不是数组
}

export function parseSetCookie(input: string | string[], options?: ParseOptions & { map?: false }): Cookie[]

export function parseSetCookie(input: string | string[], options: ParseOptions & { map: true }): CookieMap

export function parseSetCookie(input: string | string[], options: ParseOptions = {}): Cookie[] | CookieMap {
  const decode = options.decodeValues !== false

  const arr = Array.isArray(input) ? input : [input]

  const cookies: Cookie[] = arr.map((str) => {
    const parts = str.split(';').map((p) => p.trim())
    const [nameValue, ...attrs] = parts
    const [name, ...valParts] = nameValue.split('=')
    const value = valParts.join('=')

    const cookie: Cookie = {
      name,
      value: decode ? decodeURIComponent(value) : value
    }

    for (const attr of attrs) {
      const [attrName, attrValue] = attr.split('=')
      const lowerName = attrName.toLowerCase()

      switch (lowerName) {
        case 'expires':
          cookie.expires = new Date(attrValue)
          break
        case 'max-age':
          cookie.maxAge = Number(attrValue)
          break
        case 'domain':
          cookie.domain = attrValue
          break
        case 'path':
          cookie.path = attrValue
          break
        case 'secure':
          cookie.secure = true
          break
        case 'httponly':
          cookie.httpOnly = true
          break
        case 'samesite':
          cookie.sameSite = attrValue as Cookie['sameSite']
          break
      }
    }

    return cookie
  })

  if (options.map) {
    return cookies.reduce<CookieMap>((map, c) => {
      map[c.name] = c
      return map
    }, {})
  }

  return cookies
}
