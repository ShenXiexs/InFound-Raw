export type OutreachCreatorType = 'ALL' | 'NEW_ONLY' | 'NEW_AND_NOT_REPLIED'

const OUTREACH_PRODUCT_CATEGORY_OPTIONS: Array<{ label: string; value: string }> = [
  { label: 'Home Supplies', value: '600001' },
  { label: 'Kitchenware', value: '600024' },
  { label: 'Textiles & Soft Furnishings', value: '600154' },
  { label: 'Household Appliances', value: '600942' },
  { label: 'Womenswear & Underwear', value: '601152' },
  { label: 'Shoes', value: '601352' },
  { label: 'Beauty & Personal Care', value: '601450' },
  { label: 'Phones & Electronics', value: '601739' },
  { label: 'Computers & Office Equipment', value: '601755' },
  { label: 'Pet Supplies', value: '602118' },
  { label: 'Sports & Outdoor', value: '603014' },
  { label: 'Toys & Hobbies', value: '604206' },
  { label: 'Furniture', value: '604453' },
  { label: 'Tools & Hardware', value: '604579' },
  { label: 'Home Improvement', value: '604968' },
  { label: 'Automotive & Motorcycle', value: '605196' },
  { label: 'Fashion Accessories', value: '605248' },
  { label: 'Health', value: '700645' },
  { label: 'Books, Magazines & Audio', value: '801928' },
  { label: "Kids' Fashion", value: '802184' },
  { label: 'Menswear & Underwear', value: '824328' },
  { label: 'Luggage & Bags', value: '824584' },
  { label: 'Collectibles', value: '951432' },
  { label: 'Jewelry Accessories & Derivatives', value: '953224' }
]

export const OUTREACH_PRODUCT_CATEGORY_LABEL_MAP: Record<string, string> = {
  ...Object.fromEntries(OUTREACH_PRODUCT_CATEGORY_OPTIONS.map((item) => [item.value, item.label])),
  '601303': 'Modest Fashion'
}

export const OUTREACH_AVG_COMMISSION_RATE_OPTIONS = ['All', 'Less than 20%', 'Less than 15%', 'Less than 10%', 'Less than 5%']
export const OUTREACH_CONTENT_TYPE_OPTIONS = ['All', 'Video', 'LIVE']
export const OUTREACH_CREATOR_AGENCY_OPTIONS = ['All', 'Managed by Agency', 'Independent creators']
export const OUTREACH_FOLLOWER_GENDER_OPTIONS = ['All', 'Female', 'Male']

export const OUTREACH_SORT_LABEL_MAP: Record<string, string> = {
  OFFICIAL_DEFAULT: '官方默认值',
  GMV_DESC: '达人GMV降序',
  FOLLOWERS_DESC: '达人粉丝数降序',
  COMMISSION_DESC: '达人佣金率降序',
  '0': '相关性',
  '1': '达人GMV',
  '2': '商品销量',
  '3': '达人粉丝数',
  '4': '平均视频播放量',
  '5': '互动率'
}

export const OUTREACH_CREATOR_TYPE_LABEL_MAP: Record<OutreachCreatorType, string> = {
  ALL: '建联所有达人',
  NEW_ONLY: '只建联新达人',
  NEW_AND_NOT_REPLIED: '建联新达人和未回复达人'
}

export const OUTREACH_AVG_COMMISSION_RATE_LABEL_MAP: Record<string, string> = {
  All: '全部',
  'Less than 20%': '低于 20%',
  'Less than 15%': '低于 15%',
  'Less than 10%': '低于 10%',
  'Less than 5%': '低于 5%'
}

export const OUTREACH_CONTENT_TYPE_LABEL_MAP: Record<string, string> = {
  All: '全部',
  Video: '视频',
  LIVE: '直播'
}

export const OUTREACH_CREATOR_AGENCY_LABEL_MAP: Record<string, string> = {
  All: '全部',
  'Managed by Agency': '机构签约达人',
  'Managed by agency': '机构签约达人',
  'Independent creators': '独立达人'
}

export const OUTREACH_FOLLOWER_GENDER_LABEL_MAP: Record<string, string> = {
  All: '全部',
  Female: '女',
  Male: '男'
}
