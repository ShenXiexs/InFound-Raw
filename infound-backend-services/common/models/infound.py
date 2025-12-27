from typing import Any, Optional
import datetime
import decimal

from sqlalchemy import CHAR, Column, DECIMAL, Date, DateTime, Index, Integer, JSON, String, Table, Text, text
from sqlalchemy.dialects.mysql import BIGINT, BIT, CHAR, DATETIME, DECIMAL, INTEGER, TINYINT, TINYTEXT, VARCHAR
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

class Base(DeclarativeBase):
    pass


class Campaigns(Base):
    __tablename__ = 'campaigns'
    __table_args__ = (
        Index('IX_CampaignID', 'platform_campaign_id'),
        Index('IX_ShopID', 'platform_shop_id'),
        {'comment': 'campaigns table'}
    )

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True, comment='campaign id')
    platform: Mapped[str] = mapped_column(String(16), nullable=False, comment='creator platform: 1, TikTok')
    platform_campaign_id: Mapped[str] = mapped_column(String(32), nullable=False, comment='campaign id')
    region: Mapped[str] = mapped_column(String(32), nullable=False, comment='region')
    creator_id: Mapped[str] = mapped_column(CHAR(36), nullable=False, comment='created by')
    creation_time: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=3), nullable=False, comment='created time (UTC)')
    last_modifier_id: Mapped[str] = mapped_column(CHAR(36), nullable=False, comment='updated by')
    last_modification_time: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=3), nullable=False, comment='updated time (UTC)')
    platform_campaign_name: Mapped[Optional[str]] = mapped_column(String(128), comment='campaign name')
    status: Mapped[Optional[str]] = mapped_column(String(64), comment='campaign status')
    registration_period: Mapped[Optional[dict]] = mapped_column(JSON, comment='campaign registration period (JSON object)')
    campaign_period: Mapped[Optional[dict]] = mapped_column(JSON, comment='campaign period (JSON object)')
    pending_product_count: Mapped[Optional[int]] = mapped_column(INTEGER, comment='campaign pending product count')
    approved_product_count: Mapped[Optional[int]] = mapped_column(INTEGER, comment='campaign approved product count')
    date_registered: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, comment='registration date')
    commission_rate: Mapped[Optional[str]] = mapped_column(String(64), comment='commission rate')
    platform_shop_name: Mapped[Optional[str]] = mapped_column(String(64), comment='shop name')
    platform_shop_phone: Mapped[Optional[str]] = mapped_column(String(32), comment='shop phone')
    platform_shop_id: Mapped[Optional[str]] = mapped_column(String(32), comment='shop id')


class ChatMessages(Base):
    __tablename__ = 'chat_messages'
    __table_args__ = (
        Index('IX_Platform_AccountID', 'platform', 'platform_creator_id'),
        {'comment': 'creator chat messages table'}
    )

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True, comment='message id')
    platform: Mapped[str] = mapped_column(String(16), nullable=False, comment='creator platform: 1, TikTok')
    platform_creator_id: Mapped[str] = mapped_column(String(32), nullable=False, comment='creator platform account id')
    platform_creator_display_name: Mapped[str] = mapped_column(String(64), nullable=False, comment='creator display name')
    platform_message_id: Mapped[str] = mapped_column(CHAR(36), nullable=False, comment='platform message id')
    creator_id: Mapped[str] = mapped_column(CHAR(36), nullable=False, comment='created by')
    creation_time: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=3), nullable=False, comment='created time (UTC)')
    last_modifier_id: Mapped[str] = mapped_column(CHAR(36), nullable=False, comment='updated by')
    last_modification_time: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=3), nullable=False, comment='updated time (UTC)')
    region: Mapped[Optional[str]] = mapped_column(String(32), comment='creator region')
    chat_url: Mapped[Optional[str]] = mapped_column(String(1024), comment='creator chat link')
    sender_name: Mapped[Optional[str]] = mapped_column(String(32), comment='sender type: Merchant; Creator')
    content: Mapped[Optional[str]] = mapped_column(Text, comment='message content')
    timestamp: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, comment='message sent time')
    message_type: Mapped[Optional[str]] = mapped_column(String(32), comment='message type')
    is_from_merchant: Mapped[Optional[Any]] = mapped_column(BIT(1), comment='sent by merchant')
    is_reply: Mapped[Optional[Any]] = mapped_column(BIT(1), comment='creator replied')
    is_read: Mapped[Optional[Any]] = mapped_column(BIT(1), comment='creator read')


class CreatorCrawlLogs(Base):
    __tablename__ = 'creator_crawl_logs'
    __table_args__ = (
        Index('IX_Platform_AccountID', 'platform', 'platform_creator_id'),
        Index('IX_Platform_Username', 'platform', 'platform_creator_username'),
        {'comment': 'creator crawl logs table'}
    )

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True, comment='creator id')
    crawl_date: Mapped[datetime.date] = mapped_column(Date, nullable=False, comment='crawl date (date only)')
    platform: Mapped[str] = mapped_column(String(16), nullable=False, comment='creator platform: 1, TikTok')
    platform_creator_id: Mapped[str] = mapped_column(String(32), nullable=False, comment='creator platform account id')
    platform_creator_display_name: Mapped[str] = mapped_column(String(64), nullable=False, comment='creator display name')
    platform_creator_username: Mapped[str] = mapped_column(String(64), nullable=False, comment='creator username')
    creator_id: Mapped[str] = mapped_column(CHAR(36), nullable=False, comment='created by')
    creation_time: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=3), nullable=False, comment='created time (UTC)')
    last_modifier_id: Mapped[str] = mapped_column(CHAR(36), nullable=False, comment='updated by')
    last_modification_time: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=3), nullable=False, comment='updated time (UTC)')
    email: Mapped[Optional[str]] = mapped_column(String(255), comment='creator email')
    whatsapp: Mapped[Optional[str]] = mapped_column(String(32), comment='creator WhatsApp')
    introduction: Mapped[Optional[str]] = mapped_column(Text, comment='creator introduction')
    region: Mapped[Optional[str]] = mapped_column(String(32), comment='creator region')
    currency: Mapped[Optional[str]] = mapped_column(String(32), comment='creator currency')
    categories: Mapped[Optional[str]] = mapped_column(String(128), comment='creator category')
    chat_url: Mapped[Optional[str]] = mapped_column(String(512), comment='creator chat URL')
    search_keywords: Mapped[Optional[str]] = mapped_column(String(128), comment='creator search keywords')
    brand_name: Mapped[Optional[str]] = mapped_column(String(255), comment='last outreach brand name')
    followers: Mapped[Optional[int]] = mapped_column(INTEGER, comment='creator followers (parsed to number)')
    top_brands: Mapped[Optional[str]] = mapped_column(String(255), comment='creator partnered brands')
    sales_revenue: Mapped[Optional[decimal.Decimal]] = mapped_column(DECIMAL(10, 2), comment='GMV')
    sales_units_sold: Mapped[Optional[int]] = mapped_column(INTEGER, comment='units sold')
    sales_gpm: Mapped[Optional[decimal.Decimal]] = mapped_column(DECIMAL(10, 2), comment='GMV per 1,000 impressions')
    sales_revenue_per_buyer: Mapped[Optional[decimal.Decimal]] = mapped_column(DECIMAL(10, 2), comment='average order value')
    gmv_per_sales_channel: Mapped[Optional[str]] = mapped_column(String(32), comment='top GMV channel (with share)')
    gmv_by_product_category: Mapped[Optional[str]] = mapped_column(String(64), comment='top GMV category (with share)')
    avg_commission_rate: Mapped[Optional[decimal.Decimal]] = mapped_column(DECIMAL(10, 4), comment='average commission rate')
    collab_products: Mapped[Optional[int]] = mapped_column(INTEGER, comment='collab product count')
    partnered_brands: Mapped[Optional[int]] = mapped_column(INTEGER, comment='partnered brand count')
    product_price: Mapped[Optional[str]] = mapped_column(String(64), comment='collab product price (range)')
    video_gpm: Mapped[Optional[decimal.Decimal]] = mapped_column(DECIMAL(10, 2), comment='video GPM')
    videos: Mapped[Optional[int]] = mapped_column(INTEGER, comment='video count')
    avg_video_views: Mapped[Optional[int]] = mapped_column(INTEGER, comment='average video views')
    avg_video_engagement_rate: Mapped[Optional[decimal.Decimal]] = mapped_column(DECIMAL(10, 4), comment='avg video engagement rate')
    avg_video_likes: Mapped[Optional[int]] = mapped_column(INTEGER, comment='avg video likes')
    avg_video_comments: Mapped[Optional[int]] = mapped_column(INTEGER, comment='avg video comments')
    avg_video_shares: Mapped[Optional[int]] = mapped_column(INTEGER, comment='avg video shares')
    live_gpm: Mapped[Optional[decimal.Decimal]] = mapped_column(DECIMAL(10, 2), comment='live GMV per 1,000 views')
    live_streams: Mapped[Optional[int]] = mapped_column(INTEGER, comment='video count')
    avg_live_views: Mapped[Optional[int]] = mapped_column(INTEGER, comment='avg live views')
    avg_live_engagement_rate: Mapped[Optional[decimal.Decimal]] = mapped_column(DECIMAL(10, 4), comment='avg live engagement rate')
    avg_live_likes: Mapped[Optional[int]] = mapped_column(INTEGER, comment='avg live likes')
    avg_live_comments: Mapped[Optional[int]] = mapped_column(INTEGER, comment='avg live comments')
    avg_live_shares: Mapped[Optional[int]] = mapped_column(INTEGER, comment='avg live shares')
    followers_male: Mapped[Optional[decimal.Decimal]] = mapped_column(DECIMAL(10, 4), comment='male follower share')
    followers_female: Mapped[Optional[decimal.Decimal]] = mapped_column(DECIMAL(10, 4), comment='female follower share')
    followers_18_24: Mapped[Optional[decimal.Decimal]] = mapped_column(DECIMAL(10, 4), comment='18-24 age share')
    followers_25_34: Mapped[Optional[decimal.Decimal]] = mapped_column(DECIMAL(10, 4), comment='25-34 age share')
    followers_35_44: Mapped[Optional[decimal.Decimal]] = mapped_column(DECIMAL(10, 4), comment='35-44 age share')
    followers_45_54: Mapped[Optional[decimal.Decimal]] = mapped_column(DECIMAL(10, 4), comment='45-54 age share')
    followers_55_more: Mapped[Optional[decimal.Decimal]] = mapped_column(DECIMAL(10, 4), comment='55+ age share')
    connect: Mapped[Optional[Any]] = mapped_column(BIT(1), comment='outreach completed')
    reply: Mapped[Optional[Any]] = mapped_column(BIT(1), comment='replied')
    send: Mapped[Optional[Any]] = mapped_column(BIT(1), comment='outreach task sent successfully')


class Creators(Base):
    __tablename__ = 'creators'
    __table_args__ = (
        Index('IX_Platform_AccountID', 'platform', 'platform_creator_id'),
        Index('IX_Platform_Username', 'platform', 'platform_creator_username'),
        {'comment': 'creators table'}
    )

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True, comment='creator id')
    platform: Mapped[str] = mapped_column(String(16), nullable=False, comment='creator platform: 1, TikTok')
    platform_creator_id: Mapped[str] = mapped_column(String(32), nullable=False, comment='creator platform account id')
    platform_creator_display_name: Mapped[str] = mapped_column(String(64), nullable=False, comment='creator display name')
    platform_creator_username: Mapped[str] = mapped_column(String(64), nullable=False, comment='creator username')
    creator_id: Mapped[str] = mapped_column(CHAR(36), nullable=False, comment='created by')
    creation_time: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=3), nullable=False, comment='created time (UTC)')
    last_modifier_id: Mapped[str] = mapped_column(CHAR(36), nullable=False, comment='updated by')
    last_modification_time: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=3), nullable=False, comment='updated time (UTC)')
    email: Mapped[Optional[str]] = mapped_column(String(255), comment='creator email')
    whatsapp: Mapped[Optional[str]] = mapped_column(String(32), comment='creator WhatsApp')
    introduction: Mapped[Optional[str]] = mapped_column(Text, comment='creator introduction')
    region: Mapped[Optional[str]] = mapped_column(String(32), comment='creator region')
    currency: Mapped[Optional[str]] = mapped_column(String(32), comment='creator currency')
    categories: Mapped[Optional[str]] = mapped_column(String(128), comment='creator category')
    chat_url: Mapped[Optional[str]] = mapped_column(String(512), comment='creator chat URL')
    search_keywords: Mapped[Optional[str]] = mapped_column(String(128), comment='creator search keywords')
    brand_name: Mapped[Optional[str]] = mapped_column(String(255), comment='last outreach brand name')
    followers: Mapped[Optional[int]] = mapped_column(INTEGER, comment='creator followers (parsed to number)')
    top_brands: Mapped[Optional[str]] = mapped_column(String(255), comment='creator partnered brands')
    sales_revenue: Mapped[Optional[decimal.Decimal]] = mapped_column(DECIMAL(10, 2), comment='GMV')
    sales_units_sold: Mapped[Optional[int]] = mapped_column(INTEGER, comment='units sold')
    sales_gpm: Mapped[Optional[decimal.Decimal]] = mapped_column(DECIMAL(10, 2), comment='GMV per 1,000 impressions')
    sales_revenue_per_buyer: Mapped[Optional[decimal.Decimal]] = mapped_column(DECIMAL(10, 2), comment='average order value')
    gmv_per_sales_channel: Mapped[Optional[str]] = mapped_column(String(32), comment='top GMV channel (with share)')
    gmv_by_product_category: Mapped[Optional[str]] = mapped_column(String(64), comment='top GMV category (with share)')
    avg_commission_rate: Mapped[Optional[decimal.Decimal]] = mapped_column(DECIMAL(10, 4), comment='average commission rate')
    collab_products: Mapped[Optional[int]] = mapped_column(INTEGER, comment='collab product count')
    partnered_brands: Mapped[Optional[int]] = mapped_column(INTEGER, comment='partnered brand count')
    product_price: Mapped[Optional[str]] = mapped_column(String(64), comment='collab product price (range)')
    video_gpm: Mapped[Optional[decimal.Decimal]] = mapped_column(DECIMAL(10, 2), comment='video GPM')
    videos: Mapped[Optional[int]] = mapped_column(INTEGER, comment='video count')
    avg_video_views: Mapped[Optional[int]] = mapped_column(INTEGER, comment='average video views')
    avg_video_engagement_rate: Mapped[Optional[decimal.Decimal]] = mapped_column(DECIMAL(10, 4), comment='avg video engagement rate')
    avg_video_likes: Mapped[Optional[int]] = mapped_column(INTEGER, comment='avg video likes')
    avg_video_comments: Mapped[Optional[int]] = mapped_column(INTEGER, comment='avg video comments')
    avg_video_shares: Mapped[Optional[int]] = mapped_column(INTEGER, comment='avg video shares')
    live_gpm: Mapped[Optional[decimal.Decimal]] = mapped_column(DECIMAL(10, 2), comment='live GMV per 1,000 views')
    live_streams: Mapped[Optional[int]] = mapped_column(INTEGER, comment='video count')
    avg_live_views: Mapped[Optional[int]] = mapped_column(INTEGER, comment='avg live views')
    avg_live_engagement_rate: Mapped[Optional[decimal.Decimal]] = mapped_column(DECIMAL(10, 4), comment='avg live engagement rate')
    avg_live_likes: Mapped[Optional[int]] = mapped_column(INTEGER, comment='avg live likes')
    avg_live_comments: Mapped[Optional[int]] = mapped_column(INTEGER, comment='avg live comments')
    avg_live_shares: Mapped[Optional[int]] = mapped_column(INTEGER, comment='avg live shares')
    followers_male: Mapped[Optional[decimal.Decimal]] = mapped_column(DECIMAL(10, 4), comment='male follower share')
    followers_female: Mapped[Optional[decimal.Decimal]] = mapped_column(DECIMAL(10, 4), comment='female follower share')
    followers_18_24: Mapped[Optional[decimal.Decimal]] = mapped_column(DECIMAL(10, 4), comment='18-24 age share')
    followers_25_34: Mapped[Optional[decimal.Decimal]] = mapped_column(DECIMAL(10, 4), comment='25-34 age share')
    followers_35_44: Mapped[Optional[decimal.Decimal]] = mapped_column(DECIMAL(10, 4), comment='35-44 age share')
    followers_45_54: Mapped[Optional[decimal.Decimal]] = mapped_column(DECIMAL(10, 4), comment='45-54 age share')
    followers_55_more: Mapped[Optional[decimal.Decimal]] = mapped_column(DECIMAL(10, 4), comment='55+ age share')


class OpsUsers(Base):
    __tablename__ = 'ops_users'
    __table_args__ = {'comment': 'user info table'}

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True, comment='user id')
    user_name: Mapped[str] = mapped_column(VARCHAR(64), nullable=False, comment='user account')
    password: Mapped[str] = mapped_column(VARCHAR(64), nullable=False, server_default=text("''"), comment='password')
    nick_name: Mapped[str] = mapped_column(VARCHAR(36), nullable=False, comment='user nickname')
    creator_id: Mapped[str] = mapped_column(CHAR(36), nullable=False, comment='created by')
    creation_time: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, comment='created time')
    last_modifier_id: Mapped[str] = mapped_column(CHAR(36), nullable=False, comment='updated by')
    last_modification_time: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, comment='updated time')
    user_type: Mapped[Optional[str]] = mapped_column(VARCHAR(2), server_default=text("'00'"), comment='user type (00=system user)')
    email: Mapped[Optional[str]] = mapped_column(VARCHAR(64), server_default=text("''"), comment='user email')
    phone_number: Mapped[Optional[str]] = mapped_column(VARCHAR(64), server_default=text("''"), comment='mobile number')
    sex: Mapped[Optional[int]] = mapped_column(TINYINT, server_default=text("'0'"), comment='gender: 0=male, 1=female, 2=unknown')
    avatar: Mapped[Optional[str]] = mapped_column(VARCHAR(256), server_default=text("''"), comment='avatar URL')
    status: Mapped[Optional[int]] = mapped_column(TINYINT, server_default=text("'0'"), comment='account status: 0=active, 1=disabled')
    dept_id: Mapped[Optional[int]] = mapped_column(BIGINT, comment='department id')
    login_ip: Mapped[Optional[str]] = mapped_column(VARCHAR(128), server_default=text("''"), comment='last login IP')
    login_date: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, comment='last login time')
    remark: Mapped[Optional[str]] = mapped_column(VARCHAR(512), comment='notes')
    deleted: Mapped[Optional[Any]] = mapped_column(BIT(1))


class OutreachTasks(Base):
    __tablename__ = 'outreach_tasks'
    __table_args__ = {'comment': 'outreach tasks table'}

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True, comment='task id')
    platform: Mapped[str] = mapped_column(String(16), nullable=False, comment='task platform: 1, TikTok')
    task_name: Mapped[str] = mapped_column(String(64), nullable=False, comment='task name')
    creator_id: Mapped[str] = mapped_column(CHAR(36), nullable=False, comment='created by')
    creation_time: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=3), nullable=False, comment='created time (UTC)')
    last_modifier_id: Mapped[str] = mapped_column(CHAR(36), nullable=False, comment='updated by')
    last_modification_time: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=3), nullable=False, comment='updated time (UTC)')
    platform_campaign_id: Mapped[Optional[str]] = mapped_column(String(64), comment='campaign id')
    platform_campaign_name: Mapped[Optional[str]] = mapped_column(String(128), comment='campaign name')
    platform_product_id: Mapped[Optional[str]] = mapped_column(String(64), comment='product id')
    platform_product_name: Mapped[Optional[str]] = mapped_column(String(128), comment='product name')
    region: Mapped[Optional[str]] = mapped_column(String(32), comment='region')
    brand: Mapped[Optional[str]] = mapped_column(String(255), comment='brand')
    message_send_strategy: Mapped[Optional[int]] = mapped_column(TINYINT, comment='message strategy: 0=all creators; 1=new creators only; 2=follow up on unreplied creators')
    task_type: Mapped[Optional[str]] = mapped_column(String(32), comment='task type')
    status: Mapped[Optional[str]] = mapped_column(String(32), comment='task status')
    message: Mapped[Optional[str]] = mapped_column(String(512), comment='task info')
    accound_email: Mapped[Optional[str]] = mapped_column(String(255), comment='TikTok account used for task')
    search_keywords: Mapped[Optional[str]] = mapped_column(String(255), comment='search keywords')
    product_categories: Mapped[Optional[dict]] = mapped_column(JSON, comment='product categories (JSON array)')
    fans_age_range: Mapped[Optional[dict]] = mapped_column(JSON, comment='follower age ranges (JSON array)')
    fans_gender: Mapped[Optional[dict]] = mapped_column(JSON, comment='follower gender (JSON object)')
    content_types: Mapped[Optional[dict]] = mapped_column(JSON, comment='creator content types (JSON array)')
    gmv_range: Mapped[Optional[dict]] = mapped_column(JSON, comment='creator GMV range (JSON array)')
    sales_range: Mapped[Optional[dict]] = mapped_column(JSON, comment='creator sales range (JSON array)')
    min_fans: Mapped[Optional[int]] = mapped_column(INTEGER, comment='min follower count')
    min_avg_views: Mapped[Optional[int]] = mapped_column(INTEGER, comment='min average views')
    min_engagement_rate: Mapped[Optional[int]] = mapped_column(INTEGER, comment='min participation rate')
    first_message: Mapped[Optional[str]] = mapped_column(Text, comment='initial message content')
    second_message: Mapped[Optional[str]] = mapped_column(Text, comment='follow-up message content')
    new_creators_expect_count: Mapped[Optional[int]] = mapped_column(INTEGER, comment='target new creators to outreach')
    max_creators: Mapped[Optional[int]] = mapped_column(INTEGER, comment='max creators to process')
    plan_execute_time: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, comment='scheduled start time')
    plan_stop_time: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, comment='scheduled end time')
    spend_time: Mapped[Optional[int]] = mapped_column(INTEGER, comment='task duration (seconds)')
    new_creators_real_count: Mapped[Optional[int]] = mapped_column(INTEGER, comment='actual new creator count')
    real_start_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, comment='start time')
    real_end_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, comment='end time')


class Products(Base):
    __tablename__ = 'products'
    __table_args__ = (
        Index('IX_CampaignID', 'platform', 'platform_campaign_id'),
        Index('IX_ProductId', 'platform', 'platform_product_id'),
        {'comment': 'campaign products table'}
    )

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True, comment='product id')
    region: Mapped[str] = mapped_column(String(32), nullable=False, comment='region')
    platform: Mapped[str] = mapped_column(String(16), nullable=False, comment='creator platform: 1, TikTok')
    platform_campaign_id: Mapped[str] = mapped_column(String(36), nullable=False, comment='campaign id')
    platform_product_id: Mapped[str] = mapped_column(String(32), nullable=False, comment='product id')
    creator_id: Mapped[str] = mapped_column(CHAR(36), nullable=False, comment='created by')
    creation_time: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=3), nullable=False, comment='created time (UTC)')
    last_modifier_id: Mapped[str] = mapped_column(CHAR(36), nullable=False, comment='updated by')
    last_modification_time: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=3), nullable=False, comment='updated time (UTC)')
    platform_shop_name: Mapped[Optional[str]] = mapped_column(String(128), comment='shop name')
    platform_shop_phone: Mapped[Optional[str]] = mapped_column(String(32), comment='shop phone')
    platform_shop_id: Mapped[Optional[str]] = mapped_column(String(32), comment='shop id')
    thumbnail: Mapped[Optional[str]] = mapped_column(String(512), comment='image URL')
    product_name: Mapped[Optional[str]] = mapped_column(String(1024), comment='product name')
    product_name_cn: Mapped[Optional[str]] = mapped_column(String(1024), comment='product name (CN)')
    product_category_name: Mapped[Optional[str]] = mapped_column(String(128), comment='product category')
    partner_rate: Mapped[Optional[decimal.Decimal]] = mapped_column(DECIMAL(10, 2), comment='partner commission rate')
    creator_rate: Mapped[Optional[decimal.Decimal]] = mapped_column(DECIMAL(10, 2), comment='creator commission rate')
    cost_product: Mapped[Optional[str]] = mapped_column(String(255), comment='estimated product cost (range)')
    affiliate_link: Mapped[Optional[str]] = mapped_column(String(512), comment='extra links (some from tap are unused)')
    product_link: Mapped[Optional[str]] = mapped_column(String(512), comment='product link')
    product_rating: Mapped[Optional[int]] = mapped_column(TINYINT, comment='rating')
    reviews_count: Mapped[Optional[int]] = mapped_column(INTEGER, comment='product review count')
    product_sku: Mapped[Optional[str]] = mapped_column(String(64), comment='product SKU')
    stock: Mapped[Optional[int]] = mapped_column(INTEGER, comment='stock')
    available_sample_count: Mapped[Optional[int]] = mapped_column(INTEGER, comment='available sample count')
    item_sold: Mapped[Optional[int]] = mapped_column(INTEGER, comment='product sales')
    sale_price_min: Mapped[Optional[decimal.Decimal]] = mapped_column(DECIMAL(10, 2), comment='lowest sale price')
    sale_price_max: Mapped[Optional[decimal.Decimal]] = mapped_column(DECIMAL(10, 2), comment='highest sale price')
    selling_point: Mapped[Optional[str]] = mapped_column(Text, comment='selling points')
    selling_point_cn: Mapped[Optional[str]] = mapped_column(Text, comment='selling points (CN)')
    shooting_guide: Mapped[Optional[str]] = mapped_column(Text, comment='shooting guidelines')
    shooting_guide_cn: Mapped[Optional[str]] = mapped_column(Text, comment='shooting guidelines (CN)')
    examples: Mapped[Optional[dict]] = mapped_column(JSON, comment='sample images (JSON list)')


t_products_backup_20251205 = Table(
    'products_backup_20251205', Base.metadata,
    Column('id', CHAR(36), nullable=False, comment='product id'),
    Column('region', String(32), nullable=False, comment='region'),
    Column('platform', String(16), nullable=False, comment='creator platform: 1, TikTok'),
    Column('platform_campaign_id', String(36), nullable=False, comment='campaign id'),
    Column('platform_product_id', String(32), nullable=False, comment='product id'),
    Column('platform_shop_name', String(128), comment='shop name'),
    Column('platform_shop_phone', String(32), comment='shop phone'),
    Column('platform_shop_id', String(32), comment='shop id'),
    Column('thumbnail', String(512), comment='image URL'),
    Column('product_name', String(1024), comment='product name'),
    Column('product_name_cn', String(1024), comment='product name (CN)'),
    Column('product_category_name', String(128), comment='product category'),
    Column('partner_rate', DECIMAL(10, 2), comment='partner commission rate'),
    Column('creator_rate', DECIMAL(10, 2), comment='creator commission rate'),
    Column('cost_product', String(255), comment='estimated product cost (range)'),
    Column('affiliate_link', String(512), comment='extra links (some from tap are unused)'),
    Column('product_link', String(512), comment='product link'),
    Column('product_rating', TINYINT, comment='rating'),
    Column('reviews_count', INTEGER, comment='product review count'),
    Column('product_sku', String(64), comment='product SKU'),
    Column('stock', INTEGER, comment='stock'),
    Column('available_sample_count', INTEGER, comment='available sample count'),
    Column('item_sold', INTEGER, comment='product sales'),
    Column('sale_price_min', DECIMAL(10, 2), comment='lowest sale price'),
    Column('sale_price_max', DECIMAL(10, 2), comment='highest sale price'),
    Column('selling_point', TINYTEXT, comment='selling points'),
    Column('selling_point_cn', TINYTEXT, comment='selling points (CN)'),
    Column('shooting_guide', TINYTEXT, comment='shooting guidelines'),
    Column('shooting_guide_cn', TINYTEXT, comment='shooting guidelines (CN)'),
    Column('creator_id', CHAR(36), nullable=False, comment='created by'),
    Column('creation_time', DATETIME(fsp=3), nullable=False, comment='created time (UTC)'),
    Column('last_modifier_id', CHAR(36), nullable=False, comment='updated by'),
    Column('last_modification_time', DATETIME(fsp=3), nullable=False, comment='updated time (UTC)')
)


class SampleContentCrawlLogs(Base):
    __tablename__ = 'sample_content_crawl_logs'
    __table_args__ = (
        Index('IX_ProductID', 'platform_product_id'),
        {'comment': 'sample content crawl logs table'}
    )

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True, comment='log id (auto increment)')
    crawl_date: Mapped[datetime.date] = mapped_column(Date, nullable=False, comment='crawl date (date only)')
    platform_product_id: Mapped[str] = mapped_column(String(64), nullable=False, comment='product id')
    creator_id: Mapped[str] = mapped_column(CHAR(36), nullable=False, comment='created by')
    creation_time: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=3), nullable=False, comment='created time (UTC)')
    last_modifier_id: Mapped[str] = mapped_column(CHAR(36), nullable=False, comment='updated by')
    last_modification_time: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=3), nullable=False, comment='updated time (UTC)')
    region: Mapped[Optional[str]] = mapped_column(String(32), comment='creator region')
    type: Mapped[Optional[str]] = mapped_column(String(32), comment='promo type: 1=video; 2=live')
    platform_creator_id: Mapped[Optional[str]] = mapped_column(String(32), comment='creator platform account id')
    platform_creator_display_name: Mapped[Optional[str]] = mapped_column(String(64), comment='creator display name')
    platform_creator_username: Mapped[Optional[str]] = mapped_column(String(64), comment='creator username')
    promotion_name: Mapped[Optional[str]] = mapped_column(String(255), comment='promo video/live name')
    promotion_time: Mapped[Optional[str]] = mapped_column(String(255), comment='promo video/live time')
    promotion_view_count: Mapped[Optional[int]] = mapped_column(INTEGER, comment='promo video/live views')
    promotion_like_count: Mapped[Optional[int]] = mapped_column(INTEGER, comment='promo video/live likes')
    promotion_comment_count: Mapped[Optional[int]] = mapped_column(INTEGER, comment='promo video/live comments')
    promotion_order_count: Mapped[Optional[int]] = mapped_column(INTEGER, comment='promo video/live order count')
    promotion_order_total_amount: Mapped[Optional[decimal.Decimal]] = mapped_column(DECIMAL(10, 2), comment='promo video/live revenue')


class SampleContents(Base):
    __tablename__ = 'sample_contents'
    __table_args__ = (
        Index('IX_ProductID', 'platform_product_id'),
        {'comment': 'sample content table'}
    )

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True, comment='sample content id (auto increment)')
    platform_product_id: Mapped[str] = mapped_column(String(64), nullable=False, comment='product id')
    creator_id: Mapped[str] = mapped_column(CHAR(36), nullable=False, comment='created by')
    creation_time: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=3), nullable=False, comment='created time (UTC)')
    last_modifier_id: Mapped[str] = mapped_column(CHAR(36), nullable=False, comment='updated by')
    last_modification_time: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=3), nullable=False, comment='updated time (UTC)')
    region: Mapped[Optional[str]] = mapped_column(String(32), comment='creator region')
    type: Mapped[Optional[str]] = mapped_column(String(32), comment='promo type: 1=video; 2=live')
    platform_creator_id: Mapped[Optional[str]] = mapped_column(String(32), comment='creator platform account id')
    platform_creator_display_name: Mapped[Optional[str]] = mapped_column(String(64), comment='creator display name')
    platform_creator_username: Mapped[Optional[str]] = mapped_column(String(64), comment='creator username')
    promotion_name: Mapped[Optional[str]] = mapped_column(String(255), comment='promo video/live name')
    promotion_time: Mapped[Optional[str]] = mapped_column(String(255), comment='promo video/live time')
    promotion_view_count: Mapped[Optional[int]] = mapped_column(INTEGER, comment='promo video/live views')
    promotion_like_count: Mapped[Optional[int]] = mapped_column(INTEGER, comment='promo video/live likes')
    promotion_comment_count: Mapped[Optional[int]] = mapped_column(INTEGER, comment='promo video/live comments')
    promotion_order_count: Mapped[Optional[int]] = mapped_column(INTEGER, comment='promo video/live order count')
    promotion_order_total_amount: Mapped[Optional[decimal.Decimal]] = mapped_column(DECIMAL(10, 2), comment='promo video/live revenue')


class SampleCrawlLogs(Base):
    __tablename__ = 'sample_crawl_logs'
    __table_args__ = (
        Index('IX_CampaignID', 'platform_campaign_id'),
        Index('IX_ProductID', 'platform_product_id'),
        {'comment': 'sample crawl logs table'}
    )

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True, comment='log id (auto increment)')
    crawl_date: Mapped[datetime.date] = mapped_column(Date, nullable=False, comment='crawl date (date only)')
    platform_product_id: Mapped[str] = mapped_column(String(64), nullable=False, comment='product id')
    creator_id: Mapped[str] = mapped_column(CHAR(36), nullable=False, comment='created by')
    creation_time: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=3), nullable=False, comment='created time (UTC)')
    last_modifier_id: Mapped[str] = mapped_column(CHAR(36), nullable=False, comment='updated by')
    last_modification_time: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=3), nullable=False, comment='updated time (UTC)')
    region: Mapped[Optional[str]] = mapped_column(String(32), comment='region')
    stock: Mapped[Optional[int]] = mapped_column(INTEGER, comment='stock')
    product_sku: Mapped[Optional[str]] = mapped_column(String(64), comment='product SKU')
    available_sample_count: Mapped[Optional[int]] = mapped_column(INTEGER, comment='available sample count')
    is_uncooperative: Mapped[Optional[Any]] = mapped_column(BIT(1), comment='not cooperative')
    is_unapprovable: Mapped[Optional[Any]] = mapped_column(BIT(1), comment='not approvable')
    status: Mapped[Optional[str]] = mapped_column(String(32), comment='sample status: 1=to review; 2=ready to ship; 3=shipped; 4=no content; 5=completed; 6=canceled')
    request_time_remaining: Mapped[Optional[str]] = mapped_column(String(255), comment='remaining request time')
    platform_campaign_id: Mapped[Optional[str]] = mapped_column(String(64), comment='campaign id')
    platform_campaign_name: Mapped[Optional[str]] = mapped_column(Text, comment='campaign name')
    platform_creator_display_name: Mapped[Optional[str]] = mapped_column(String(64), comment='creator display name')
    platform_creator_username: Mapped[Optional[str]] = mapped_column(String(255), comment='creator username')
    platform_creator_id: Mapped[Optional[str]] = mapped_column(String(32), comment='creator platform account id')
    post_rate: Mapped[Optional[decimal.Decimal]] = mapped_column(DECIMAL(10, 4), comment='creator posting rate')
    is_showcase: Mapped[Optional[Any]] = mapped_column(BIT(1), comment='is showcase')
    content_summary: Mapped[Optional[dict]] = mapped_column(JSON, comment='creator promo video/live summary (JSON object)')
    ad_code: Mapped[Optional[dict]] = mapped_column(JSON, comment='AD code (JSON array)')


class Samples(Base):
    __tablename__ = 'samples'
    __table_args__ = (
        Index('IX_CampaignID', 'platform_campaign_id'),
        Index('IX_ProductID', 'platform_product_id'),
        {'comment': 'samples table'}
    )

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True, comment='sample id')
    platform_product_id: Mapped[str] = mapped_column(String(64), nullable=False, comment='product id')
    creator_id: Mapped[str] = mapped_column(CHAR(36), nullable=False, comment='created by')
    creation_time: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=3), nullable=False, comment='created time (UTC)')
    last_modifier_id: Mapped[str] = mapped_column(CHAR(36), nullable=False, comment='updated by')
    last_modification_time: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=3), nullable=False, comment='updated time (UTC)')
    region: Mapped[Optional[str]] = mapped_column(String(32), comment='region')
    stock: Mapped[Optional[int]] = mapped_column(INTEGER, comment='stock')
    product_sku: Mapped[Optional[str]] = mapped_column(String(64), comment='product SKU')
    available_sample_count: Mapped[Optional[int]] = mapped_column(INTEGER, comment='available sample count')
    is_uncooperative: Mapped[Optional[Any]] = mapped_column(BIT(1), comment='not cooperative')
    is_unapprovable: Mapped[Optional[Any]] = mapped_column(BIT(1), comment='not approvable')
    status: Mapped[Optional[str]] = mapped_column(String(32), comment='sample status: 1=to review; 2=ready to ship; 3=shipped; 4=no content; 5=completed; 6=canceled')
    request_time_remaining: Mapped[Optional[str]] = mapped_column(String(255), comment='remaining request time')
    platform_campaign_id: Mapped[Optional[str]] = mapped_column(String(64), comment='campaign id')
    platform_campaign_name: Mapped[Optional[str]] = mapped_column(Text, comment='campaign name')
    platform_creator_display_name: Mapped[Optional[str]] = mapped_column(String(64), comment='creator display name')
    platform_creator_username: Mapped[Optional[str]] = mapped_column(String(255), comment='creator username')
    platform_creator_id: Mapped[Optional[str]] = mapped_column(String(32), comment='creator platform account id')
    post_rate: Mapped[Optional[decimal.Decimal]] = mapped_column(DECIMAL(10, 4), comment='creator posting rate')
    is_showcase: Mapped[Optional[Any]] = mapped_column(BIT(1), comment='is showcase')
    content_summary: Mapped[Optional[dict]] = mapped_column(JSON, comment='creator promo video/live summary (JSON object)')
    ad_code: Mapped[Optional[dict]] = mapped_column(JSON, comment='AD code (JSON array)')


class UploadProductBatch(Base):
    __tablename__ = 'upload_product_batch'
    __table_args__ = (
        Index('IX_UploadID', 'id'),
        {'comment': 'product upload files table'}
    )

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True, comment='upload id')
    region: Mapped[str] = mapped_column(String(32), nullable=False, comment='region')
    creator_id: Mapped[str] = mapped_column(CHAR(36), nullable=False, comment='created by')
    creation_time: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=3), nullable=False, comment='created time (UTC)')
    last_modifier_id: Mapped[str] = mapped_column(CHAR(36), nullable=False, comment='updated by')
    last_modification_time: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=3), nullable=False, comment='updated time (UTC)')
    source_file: Mapped[Optional[str]] = mapped_column(String(255), comment='source file')
    note: Mapped[Optional[str]] = mapped_column(Text, comment='notes')
    total_rows: Mapped[Optional[int]] = mapped_column(Integer, comment='total rows in uploaded file')
    dify_total: Mapped[Optional[int]] = mapped_column(Integer, comment='dify total rows to process')
    dify_processed: Mapped[Optional[int]] = mapped_column(Integer, comment='dify processed row count')
    dify_failed: Mapped[Optional[int]] = mapped_column(Integer, comment='dify failed row count')
