import { mkdirSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import type { SellerCreatorDetailData } from '@common/types/rpa-creator-detail'

const buildLocalTimestamp = (): string => {
  const now = new Date()
  const year = now.getFullYear()
  const month = String(now.getMonth() + 1).padStart(2, '0')
  const day = String(now.getDate()).padStart(2, '0')
  const hour = String(now.getHours()).padStart(2, '0')
  const minute = String(now.getMinutes()).padStart(2, '0')
  const second = String(now.getSeconds()).padStart(2, '0')
  return `${year}${month}${day}_${hour}${minute}${second}`
}

const sanitizeFileToken = (value: string): string => {
  const cleaned = String(value || '')
    .trim()
    .replace(/[^a-zA-Z0-9_-]+/g, '_')
    .replace(/^_+|_+$/g, '')
  return cleaned || 'unknown'
}

const toJsonString = (value: unknown): string => JSON.stringify(value ?? null)

const escapeCsvValue = (value: unknown): string => {
  const text = String(value ?? '')
  if (!/[",\n\r]/.test(text)) return text
  return `"${text.replace(/"/g, '""')}"`
}

const buildCreatorDetailCsvRow = (detail: SellerCreatorDetailData): Record<string, string> => ({
  creator_id: detail.creator_id,
  region: detail.region,
  target_url: detail.target_url,
  collected_at_utc: detail.collected_at_utc,
  creator_name: detail.creator_name,
  creator_rating: detail.creator_rating,
  creator_review_count: detail.creator_review_count,
  creator_followers_count: detail.creator_followers_count,
  creator_mcn: detail.creator_mcn,
  creator_intro: detail.creator_intro,
  gmv: detail.gmv,
  items_sold: detail.items_sold,
  gpm: detail.gpm,
  gmv_per_customer: detail.gmv_per_customer,
  est_post_rate: detail.est_post_rate,
  avg_commission_rate: detail.avg_commission_rate,
  products: detail.products,
  brand_collaborations: detail.brand_collaborations,
  brands_list: Array.isArray(detail.brands_list) ? toJsonString(detail.brands_list) : detail.brands_list,
  product_price: detail.product_price,
  video_gpm: detail.video_gpm,
  videos_count: detail.videos_count,
  avg_video_views: detail.avg_video_views,
  avg_video_engagement: detail.avg_video_engagement,
  avg_video_likes: detail.avg_video_likes,
  avg_video_comments: detail.avg_video_comments,
  avg_video_shares: detail.avg_video_shares,
  live_gpm: detail.live_gpm,
  live_streams: detail.live_streams,
  avg_live_views: detail.avg_live_views,
  avg_live_engagement: detail.avg_live_engagement,
  avg_live_likes: detail.avg_live_likes,
  avg_live_comments: detail.avg_live_comments,
  avg_live_shares: detail.avg_live_shares,
  gmv_per_sales_channel: toJsonString(detail.gmv_per_sales_channel),
  gmv_by_product_category: toJsonString(detail.gmv_by_product_category),
  follower_gender: toJsonString(detail.follower_gender),
  follower_age: toJsonString(detail.follower_age),
  videos_list: toJsonString(detail.videos_list),
  videos_with_product: toJsonString(detail.videos_with_product),
  relative_creators: toJsonString(detail.relative_creators)
})

const toSingleRowCsv = (row: Record<string, string>): string => {
  const headers = Object.keys(row)
  const headerLine = headers.map((header) => escapeCsvValue(header)).join(',')
  const valueLine = headers.map((header) => escapeCsvValue(row[header])).join(',')
  return `${headerLine}\n${valueLine}\n`
}

export const buildSellerCreatorDetailExtractionScript = (): string => String.raw`
(async () => {
  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

  const normalizeText = (value) =>
    String(value ?? '')
      .replace(/\u00a0/g, ' ')
      .replace(/\s+/g, ' ')
      .trim()

  const normalizeMultilineText = (value) =>
    String(value ?? '')
      .replace(/\u00a0/g, ' ')
      .replace(/\r\n/g, '\n')
      .split('\n')
      .map((line) => line.replace(/[\t ]+/g, ' ').trim())
      .filter((line) => line.length > 0)
      .join('\n')

  const isVisible = (element) => {
    if (!(element instanceof HTMLElement)) return false
    const style = window.getComputedStyle(element)
    if (style.display === 'none' || style.visibility === 'hidden') return false
    return element.offsetParent !== null || style.position === 'fixed'
  }

  const getVisibleElements = (selector, root = document) =>
    Array.from(root.querySelectorAll(selector)).filter((node) => isVisible(node))

  const getText = (node, multiline = false) => {
    if (!(node instanceof HTMLElement)) return ''
    const rawValue = multiline ? node.innerText || node.textContent || '' : node.textContent || ''
    return multiline ? normalizeMultilineText(rawValue) : normalizeText(rawValue)
  }

  const getDirectText = (node) => {
    if (!(node instanceof HTMLElement)) return ''
    const direct = Array.from(node.childNodes)
      .filter((child) => child.nodeType === Node.TEXT_NODE)
      .map((child) => child.textContent || '')
      .join(' ')
    const normalized = normalizeText(direct)
    return normalized || getText(node)
  }

  const waitUntil = async (predicate, timeoutMs = 15000, intervalMs = 200) => {
    const startedAt = Date.now()
    while (Date.now() - startedAt < timeoutMs) {
      try {
        if (predicate()) return true
      } catch (_error) {}
      await sleep(intervalMs)
    }
    return false
  }

  const clickNode = (node) => {
    if (!(node instanceof HTMLElement)) return false
    if (typeof node.scrollIntoView === 'function') {
      node.scrollIntoView({ block: 'nearest', inline: 'nearest' })
    }
    if (typeof node.click === 'function') {
      node.click()
      return true
    }
    node.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }))
    return true
  }

  const strongClickNode = async (node) => {
    if (!(node instanceof HTMLElement)) return false
    if (typeof node.scrollIntoView === 'function') {
      node.scrollIntoView({ block: 'center', inline: 'center' })
    }
    node.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true, cancelable: true, pointerType: 'mouse' }))
    node.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true }))
    node.dispatchEvent(new PointerEvent('pointerup', { bubbles: true, cancelable: true, pointerType: 'mouse' }))
    node.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, cancelable: true }))
    const clicked = clickNode(node)
    await sleep(180)
    return clicked
  }

  const resolveScrollContainer = () => {
    const preferred = document.querySelector('#modern_sub_app_container_connection')
    if (preferred instanceof HTMLElement) return preferred

    const candidates = Array.from(document.querySelectorAll('div')).filter((node) => {
      if (!(node instanceof HTMLElement)) return false
      if (!isVisible(node)) return false
      return node.scrollHeight - node.clientHeight > 240
    })

    const sorted = candidates.sort((left, right) => right.clientHeight - left.clientHeight)
    return sorted[0] || document.scrollingElement || document.documentElement || document.body
  }

  const scrollForLazyContent = async () => {
    const container = resolveScrollContainer()
    if (!(container instanceof HTMLElement) && !(container instanceof Element)) return

    const target = container
    const maxRounds = 8
    for (let round = 0; round < maxRounds; round += 1) {
      const previousTop = target.scrollTop || 0
      const step = Math.max(target.clientHeight || 0, 600)
      const nextTop = Math.min(previousTop + step, Math.max(0, (target.scrollHeight || 0) - (target.clientHeight || 0)))
      target.scrollTop = nextTop
      target.dispatchEvent(new Event('scroll', { bubbles: true }))
      await sleep(250)
      if (nextTop === previousTop) break
    }

    target.scrollTop = 0
    target.dispatchEvent(new Event('scroll', { bubbles: true }))
    await sleep(150)
  }

  const findMetricCard = (label) => {
    const expected = normalizeText(label).toLowerCase()
    const preferredLabelNodes = getVisibleElements('span[data-e2e="61148565-2ea3-4c1b"]').filter(
      (node) => normalizeText(node.textContent).toLowerCase() === expected
    )
    const fallbackLabelNodes =
      preferredLabelNodes.length > 0
        ? preferredLabelNodes
        : getVisibleElements('span, div').filter((node) => normalizeText(node.textContent).toLowerCase() === expected)

    for (const labelNode of fallbackLabelNodes) {
      const card =
        labelNode.closest('div[data-e2e="f6855061-9011-24ab"]') ||
        labelNode.parentElement?.parentElement ||
        labelNode.parentElement ||
        null
      if (card instanceof HTMLElement) {
        return card
      }
    }

    return null
  }

  const getMetricCardValueFromCard = (card, label) => {
    if (!(card instanceof HTMLElement)) return ''

    const preferredValue =
      getVisibleElements('span[data-e2e="0bc7b49d-b8b3-02d5"], span[data-e2e="0095ec1d-a3b3-401a"]', card)
        .map((node) => getText(node))
        .find(Boolean) || ''
    if (preferredValue) return preferredValue

    const fallbackValue = Array.from(card.querySelectorAll('span, div'))
      .filter((node) => isVisible(node))
      .map((node) => getText(node))
      .find((text) => text && text.toLowerCase() !== normalizeText(label).toLowerCase())

    return fallbackValue || ''
  }

  const getMetricCardValue = (label) => {
    const card = findMetricCard(label)
    if (!(card instanceof HTMLElement)) return ''
    return getMetricCardValueFromCard(card, label)
  }

  const metricValueCache = {}

  const cacheVisibleMetricValues = () => {
    const cards = getVisibleElements('div[data-e2e="f6855061-9011-24ab"]')
    cards.forEach((card) => {
      if (!(card instanceof HTMLElement)) return
      const labelNode =
        getVisibleElements('span[data-e2e="61148565-2ea3-4c1b"]', card)[0] ||
        getVisibleElements('span, div', card).find((node) => Boolean(getText(node))) ||
        null
      const label = getText(labelNode)
      if (!label) return
      const value = getMetricCardValueFromCard(card, label)
      if (value) {
        metricValueCache[label] = value
      }
    })
  }

  const readMetricValue = (label) => {
    const cachedValue = normalizeText(metricValueCache[label])
    if (cachedValue) return cachedValue
    const liveValue = getMetricCardValue(label)
    if (liveValue) {
      metricValueCache[label] = liveValue
      return liveValue
    }
    return ''
  }

  const readLegendBlock = (index) => {
    const blocks = getVisibleElements('.pcm-pc-legend.pcm-pc-legend-right')
    const block = blocks[index]
    if (!(block instanceof HTMLElement)) return {}

    const labels = getVisibleElements('.pcm-pc-legend-label .ecom-data-overflow-text-content, .pcm-pc-legend-label', block)
      .map((node) => getText(node))
      .filter(Boolean)
    const values = getVisibleElements('.pcm-pc-legend-value .ecom-data-overflow-text-content, .pcm-pc-legend-value', block)
      .map((node) => getText(node))
      .filter(Boolean)

    const result = {}
    for (let idx = 0; idx < Math.min(labels.length, values.length); idx += 1) {
      result[labels[idx]] = values[idx]
    }
    return result
  }

  const readTopBrands = async () => {
    const trigger = Array.from(document.querySelectorAll('button')).find(
      (node) => isVisible(node) && normalizeText(node.textContent) === 'View top brands'
    )
    if (!(trigger instanceof HTMLElement)) return ''

    clickNode(trigger)
    await waitUntil(() => getVisibleElements('div[data-e2e="710cdc7a-878f-599e"]').length > 0, 6000, 200)

    const brands = getVisibleElements('div[data-e2e="710cdc7a-878f-599e"]')
      .map((node) => getText(node))
      .filter((value) => value && value !== 'View top brands')
    const uniqueBrands = Array.from(new Set(brands))

    document.dispatchEvent(
      new KeyboardEvent('keydown', {
        key: 'Escape',
        code: 'Escape',
        keyCode: 27,
        which: 27,
        bubbles: true
      })
    )
    await sleep(200)
    return uniqueBrands.join(',')
  }

  const queryXPathElements = (xpath) => {
    const snapshot = document.evaluate(xpath, document, null, XPathResult.ORDERED_NODE_SNAPSHOT_TYPE, null)
    const results = []
    for (let index = 0; index < snapshot.snapshotLength; index += 1) {
      const node = snapshot.snapshotItem(index)
      if (node instanceof HTMLElement && isVisible(node)) {
        results.push(node)
      }
    }
    return results
  }

  const getMetricCarouselArrows = () => {
    const candidates = [
      ...getVisibleElements('div[data-e2e="7a7839d9-8fa5-dd75"]'),
      ...getVisibleElements(
        'div.h-56.w-16.bg-neutral-bg1.ml-8.flex.flex-shrink-0.items-center.justify-center.text-neutral-text1.cursor-pointer'
      ),
      ...queryXPathElements(
        '//*[starts-with(@id,"garfish_app_for_connection_")]//div[contains(@class,"h-56") and contains(@class,"w-16") and contains(@class,"bg-neutral-bg1") and contains(@class,"cursor-pointer") and .//*[contains(@class,"ArrowRight")]]'
      )
    ]
    const uniqueCandidates = Array.from(new Set(candidates)).filter((node) =>
      Boolean(node.querySelector('svg[class*="ArrowRight"], .alliance-icon-ArrowRight'))
    )
    return uniqueCandidates.sort((left, right) => {
      const leftRect = left.getBoundingClientRect()
      const rightRect = right.getBoundingClientRect()
      if (Math.abs(leftRect.top - rightRect.top) > 6) {
        return leftRect.top - rightRect.top
      }
      return leftRect.left - rightRect.left
    })
  }

  const waitForMetricLabels = async (labels, timeoutMs = 8000) => {
    const expectedLabels = Array.isArray(labels) ? labels : labels ? [labels] : []
    if (expectedLabels.length > 0) {
      return waitUntil(() => expectedLabels.some((label) => Boolean(getMetricCardValue(label))), timeoutMs, 200)
    }
    return true
  }

  const clickArrowByIndex = async (index, readyLabels) => {
    const expectedLabels = Array.isArray(readyLabels) ? readyLabels : readyLabels ? [readyLabels] : []
    if (expectedLabels.length > 0 && expectedLabels.some((label) => Boolean(getMetricCardValue(label)))) {
      cacheVisibleMetricValues()
      return true
    }

    const arrows = getMetricCarouselArrows()
    const preferredArrow = arrows[index]
    const orderedCandidates = preferredArrow
      ? [preferredArrow, ...arrows.filter((node) => node !== preferredArrow)]
      : arrows

    for (const candidate of orderedCandidates) {
      await strongClickNode(candidate)
      const ready = await waitForMetricLabels(expectedLabels, 5000)
      cacheVisibleMetricValues()
      if (ready || expectedLabels.length === 0) {
        return true
      }
    }

    for (let attempt = 0; attempt < 2; attempt += 1) {
      const refreshedCandidates = getMetricCarouselArrows()
      const retryTarget = refreshedCandidates[index]
      if (!(retryTarget instanceof HTMLElement)) break
      await strongClickNode(retryTarget)
      const ready = await waitForMetricLabels(expectedLabels, 5000)
      cacheVisibleMetricValues()
      if (ready || expectedLabels.length === 0) {
        return true
      }
    }

    cacheVisibleMetricValues()
    return expectedLabels.length === 0 ? orderedCandidates.length > 0 : expectedLabels.some((label) => Boolean(getMetricCardValue(label)))
  }

  const findSectionByHeading = (headingText) => {
    const expected = normalizeText(headingText).toLowerCase()
    const candidates = Array.from(document.querySelectorAll('div, span'))
      .filter((node) => isVisible(node) && normalizeText(node.textContent).toLowerCase() === expected)
      .sort((left, right) => {
        const leftHeadingScore = String(left.getAttribute('class') || '').includes('text-head-l') ? 1 : 0
        const rightHeadingScore = String(right.getAttribute('class') || '').includes('text-head-l') ? 1 : 0
        return rightHeadingScore - leftHeadingScore
      })

    for (const candidate of candidates) {
      let current = candidate instanceof HTMLElement ? candidate : candidate.parentElement
      while (current && current !== document.body) {
        const headingInCurrent = Array.from(current.children).find(
          (child) => child instanceof HTMLElement && normalizeText(child.textContent).toLowerCase() === expected
        )
        const thumbnails = current.querySelectorAll('img[alt="video thumbnail"]')
        if (headingInCurrent && thumbnails.length > 0) {
          return current
        }
        current = current.parentElement
      }
    }

    return null
  }

  const collectVideoCards = (sectionRoot) => {
    if (!(sectionRoot instanceof HTMLElement)) return []

    const rawCandidates = Array.from(sectionRoot.querySelectorAll('div')).filter((node) => {
      if (!(node instanceof HTMLElement)) return false
      if (!isVisible(node)) return false
      if (!node.querySelector('img[alt="video thumbnail"]')) return false
      return Array.from(node.querySelectorAll('button')).some(
        (button) => normalizeText(button.textContent) === 'View video on TikTok'
      )
    })

    return rawCandidates.filter(
      (node, index, collection) =>
        !collection.some((otherNode, otherIndex) => otherIndex !== index && otherNode.contains(node))
    )
  }

  const toUtcIso = (text) => {
    const matched = normalizeText(text).match(/(\d{1,2})\.(\d{1,2})\.(\d{4})/)
    if (!matched) return ''
    const month = Number(matched[1])
    const day = Number(matched[2])
    const year = Number(matched[3])
    return new Date(Date.UTC(year, month - 1, day, 0, 0, 0)).toISOString()
  }

  const parseVideoCard = (card) => {
    if (!(card instanceof HTMLElement)) {
      return {
        video_name: '',
        video_released_time_utc: '',
        video_view: '',
        video_like: ''
      }
    }

    const title =
      getVisibleElements('div.mb-4.text-body-m-medium, div[class*="text-body-m-medium"]', card)
        .map((node) => getText(node))
        .find(
          (value) =>
            value &&
            value !== 'View video on TikTok' &&
            value !== 'View products' &&
            !value.startsWith('Release Time:')
        ) || ''

    const releaseText =
      Array.from(card.querySelectorAll('div'))
        .filter((node) => isVisible(node))
        .map((node) => getText(node))
        .find((value) => value.startsWith('Release Time:')) || ''

    const metricValues = getVisibleElements('div.font-semibold', card)
      .map((node) => getText(node))
      .filter(Boolean)

    return {
      video_name: title,
      video_released_time_utc: toUtcIso(releaseText.replace(/^Release Time:\s*/i, '')),
      video_view: metricValues[0] || '',
      video_like: metricValues[1] || ''
    }
  }

  const readVideoSection = (headingText) => {
    const section = findSectionByHeading(headingText)
    const cards = collectVideoCards(section)
    return cards.map((card) => parseVideoCard(card)).filter((item) => item.video_name)
  }

  const readRelativeCreators = () =>
    Array.from(
      new Set(
        getVisibleElements('span[data-e2e="72a4feaf-82c8-ddda"]')
          .map((node) => getDirectText(node))
          .filter(Boolean)
      )
    ).slice(0, 12)

  await waitUntil(
    () => Boolean(getText(document.body).includes('Creator details')),
    30000,
    300
  )
  await scrollForLazyContent()
  await waitUntil(() => Boolean(getVisibleElements('span[data-e2e="b7f56c3b-f013-3448"]').length), 20000, 200)

  const creatorNameNode = getVisibleElements('span[data-e2e="b7f56c3b-f013-3448"], span.text-head-l.mr-8')[0] || null
  const ratingContainer = getVisibleElements('span[data-e2e="74da6c4c-9b51-a49b"]')[0] || null
  const ratingText = getText(ratingContainer)
  const ratingMatch = ratingText.match(/(\d+(?:\.\d+)?)/)
  const reviewCountMatch = ratingText.match(/(\d+)\s+reviews?/i)

  const followerValueNode =
    getVisibleElements('span[data-e2e="7aed0dd7-48ba-6932"], span[data-e2e="9e8f2473-a87f-db74"] span')[0] || null
  const mcnValueNode = getVisibleElements('span[data-e2e="85040a36-fb50-9f7c"]')[0] || null
  const introNode = getVisibleElements('span[data-e2e="2e9732e6-4d06-458d"]')[0] || null

  const brandsList = await readTopBrands()
  cacheVisibleMetricValues()
  await clickArrowByIndex(0, ['Product price'])
  await clickArrowByIndex(1, ['Est. post rate', 'Avg. video likes', 'Avg. video comments', 'Avg. video shares'])
  await clickArrowByIndex(2, ['LIVE GPM', 'LIVE streams', 'Avg. LIVE views'])

  const url = new URL(location.href)

  return {
    creator_id: url.searchParams.get('cid') || '',
    region: url.searchParams.get('shop_region') || '',
    target_url: location.href,
    collected_at_utc: new Date().toISOString(),
    creator_name: getDirectText(creatorNameNode),
    creator_rating: ratingMatch ? ratingMatch[1] : '',
    creator_review_count: reviewCountMatch ? reviewCountMatch[1] : '',
    creator_followers_count: getText(followerValueNode),
    creator_mcn: getText(mcnValueNode),
    creator_intro: getText(introNode, true),
    gmv: readMetricValue('GMV'),
    items_sold: readMetricValue('Items sold'),
    gpm: readMetricValue('GPM'),
    gmv_per_customer: readMetricValue('GMV per customer'),
    est_post_rate: readMetricValue('Est. post rate'),
    avg_commission_rate: readMetricValue('Avg. commission rate'),
    products: readMetricValue('Products'),
    brand_collaborations: readMetricValue('Brand collaborations'),
    brands_list: brandsList,
    product_price: readMetricValue('Product price'),
    video_gpm: readMetricValue('Video GPM'),
    videos_count: readMetricValue('Videos'),
    avg_video_views: readMetricValue('Avg. video views'),
    avg_video_engagement: readMetricValue('Avg. video engagement rate'),
    avg_video_likes: readMetricValue('Avg. video likes'),
    avg_video_comments: readMetricValue('Avg. video comments'),
    avg_video_shares: readMetricValue('Avg. video shares'),
    live_gpm: readMetricValue('LIVE GPM'),
    live_streams: readMetricValue('LIVE streams'),
    avg_live_views: readMetricValue('Avg. LIVE views'),
    avg_live_engagement: readMetricValue('Avg. LIVE engagement rate'),
    avg_live_likes: readMetricValue('Avg. LIVE likes'),
    avg_live_comments: readMetricValue('Avg. LIVE comments'),
    avg_live_shares: readMetricValue('Avg. LIVE shares'),
    gmv_per_sales_channel: readLegendBlock(0),
    gmv_by_product_category: readLegendBlock(1),
    follower_gender: readLegendBlock(2),
    follower_age: readLegendBlock(3),
    videos_list: readVideoSection('Videos'),
    videos_with_product: readVideoSection('Videos with product'),
    relative_creators: readRelativeCreators()
  }
})()
`

export const persistSellerCreatorDetailArtifacts = (detail: SellerCreatorDetailData): { jsonPath: string; csvPath: string } => {
  const outputDir = join(process.cwd(), 'data/creator-detail')
  mkdirSync(outputDir, { recursive: true })

  const timestamp = buildLocalTimestamp()
  const creatorToken = sanitizeFileToken(detail.creator_id || detail.creator_name || 'unknown')
  const jsonPath = join(outputDir, `seller_creator_detail_${creatorToken}_${timestamp}.json`)
  const csvPath = join(outputDir, `seller_creator_detail_${creatorToken}_${timestamp}.csv`)

  writeFileSync(jsonPath, JSON.stringify(detail, null, 2))
  writeFileSync(csvPath, toSingleRowCsv(buildCreatorDetailCsvRow(detail)))
  return { jsonPath, csvPath }
}
