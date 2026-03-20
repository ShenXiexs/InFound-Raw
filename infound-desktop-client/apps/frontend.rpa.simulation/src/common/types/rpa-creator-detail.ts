import type { SellerRpaTaskContextInput } from './seller-rpa-report'

export interface SellerCreatorDetailContextInput {
  platform?: string
  platformCreatorId?: string
  platformCreatorUsername?: string
  platformCreatorDisplayName?: string
  chatUrl?: string
  searchKeyword?: string
  searchKeywords?: string
  brandName?: string
  categories?: unknown
  currency?: string
  email?: string
  whatsapp?: string
  connect?: boolean | number | string
  reply?: boolean | number | string
  send?: boolean | number | string
}

export interface SellerCreatorDetailPayload extends SellerRpaTaskContextInput {
  creatorId: string
  context?: SellerCreatorDetailContextInput
}

export interface SellerCreatorDetailPayloadInput extends Partial<SellerCreatorDetailPayload> {}

export interface SellerCreatorDetailData {
  creator_id: string
  region: string
  target_url: string
  collected_at_utc: string
  creator_name: string
  creator_rating: string
  creator_review_count: string
  creator_followers_count: string
  creator_mcn: string
  creator_intro: string
  gmv: string
  items_sold: string
  gpm: string
  gmv_per_customer: string
  est_post_rate: string
  avg_commission_rate: string
  products: string
  brand_collaborations: string
  brands_list: string[] | string
  product_price: string
  video_gpm: string
  videos_count: string
  avg_video_views: string
  avg_video_engagement: string
  avg_video_likes: string
  avg_video_comments: string
  avg_video_shares: string
  live_gpm: string
  live_streams: string
  avg_live_views: string
  avg_live_engagement: string
  avg_live_likes: string
  avg_live_comments: string
  avg_live_shares: string
  gmv_per_sales_channel: Record<string, unknown>
  gmv_by_product_category: Record<string, unknown>
  follower_gender: Record<string, unknown>
  follower_age: Record<string, unknown>
  videos_list: unknown[]
  videos_with_product: unknown[]
  relative_creators: unknown[]
}
