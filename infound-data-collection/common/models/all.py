from typing import Any, Optional
import datetime
import decimal

from sqlalchemy import CHAR, DECIMAL, Date, DateTime, Index, Integer, JSON, String, Text, text
from sqlalchemy.dialects.mysql import BIGINT, BIT, CHAR, DATETIME, DECIMAL, INTEGER, TINYINT, TINYTEXT, VARCHAR
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

class Base(DeclarativeBase):
    pass


class Campaigns(Base):
    __tablename__ = 'campaigns'
    __table_args__ = (
        Index('IX_CampaignID', 'platform_campaign_id'),
        Index('IX_ShopID', 'platform_shop_id'),
        {'comment': '活动表'}
    )

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True, comment='活动 id')
    platform: Mapped[str] = mapped_column(String(16), nullable=False, comment='达人所在平台：1，TikTok；')
    platform_campaign_id: Mapped[str] = mapped_column(String(32), nullable=False, comment='活动id')
    region: Mapped[str] = mapped_column(String(32), nullable=False, comment='地区')
    creator_id: Mapped[str] = mapped_column(CHAR(36), nullable=False, comment='创建人')
    creation_time: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=3), nullable=False, comment='创建时间（UTC时间）')
    last_modifier_id: Mapped[str] = mapped_column(CHAR(36), nullable=False, comment='更新人')
    last_modification_time: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=3), nullable=False, comment='更新时间（UTC时间）')
    platform_campaign_name: Mapped[Optional[str]] = mapped_column(String(128), comment='活动名称')
    status: Mapped[Optional[str]] = mapped_column(String(64), comment='活动状态')
    registration_period: Mapped[Optional[dict]] = mapped_column(JSON, comment='活动注册时间段（JSON 对象）')
    campaign_period: Mapped[Optional[dict]] = mapped_column(JSON, comment='活动时间段（JSON 对象）')
    pending_product_count: Mapped[Optional[int]] = mapped_column(INTEGER, comment='活动等待审核商品数')
    approved_product_count: Mapped[Optional[int]] = mapped_column(INTEGER, comment='活动通过商品数')
    date_registered: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, comment='注册日期')
    commission_rate: Mapped[Optional[str]] = mapped_column(String(64), comment='佣金比例')
    platform_shop_name: Mapped[Optional[str]] = mapped_column(String(64), comment='店铺名称')
    platform_shop_phone: Mapped[Optional[str]] = mapped_column(String(32), comment='店铺电话')
    platform_shop_id: Mapped[Optional[str]] = mapped_column(String(32), comment='店铺号')


class ChatMessages(Base):
    __tablename__ = 'chat_messages'
    __table_args__ = (
        Index('IX_Platform_AccountID', 'platform', 'platform_creator_id'),
        {'comment': '达人聊天记录表'}
    )

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True, comment='信息id')
    platform: Mapped[str] = mapped_column(String(16), nullable=False, comment='达人所在平台：1，TikTok；')
    platform_creator_id: Mapped[str] = mapped_column(String(32), nullable=False, comment='达人所在平台的账号 Id')
    platform_creator_display_name: Mapped[str] = mapped_column(String(64), nullable=False, comment='达人所在平台的用户昵称')
    platform_message_id: Mapped[str] = mapped_column(CHAR(36), nullable=False, comment='平台信息id')
    creator_id: Mapped[str] = mapped_column(CHAR(36), nullable=False, comment='创建人')
    creation_time: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=3), nullable=False, comment='创建时间（UTC 时间）')
    last_modifier_id: Mapped[str] = mapped_column(CHAR(36), nullable=False, comment='更新人')
    last_modification_time: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=3), nullable=False, comment='更新时间（UTC 时间）')
    region: Mapped[Optional[str]] = mapped_column(String(32), comment='达人所在地区')
    chat_url: Mapped[Optional[str]] = mapped_column(String(1024), comment='达人聊天页链接')
    sender_name: Mapped[Optional[str]] = mapped_column(String(32), comment='发送人类型：Merchant; Creator')
    content: Mapped[Optional[str]] = mapped_column(Text, comment='信息内容')
    timestamp: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, comment='发消息时间')
    message_type: Mapped[Optional[str]] = mapped_column(String(32), comment='消息类型')
    is_from_merchant: Mapped[Optional[Any]] = mapped_column(BIT(1), comment='是否发自商家')
    is_reply: Mapped[Optional[Any]] = mapped_column(BIT(1), comment='达人是否回复')
    is_read: Mapped[Optional[Any]] = mapped_column(BIT(1), comment='达人是否已读')


class CreatorCrawlLogs(Base):
    __tablename__ = 'creator_crawl_logs'
    __table_args__ = (
        Index('IX_Platform_AccountID', 'platform', 'platform_creator_id'),
        Index('IX_Platform_Username', 'platform', 'platform_creator_username'),
        {'comment': '达人抓取日志表'}
    )

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True, comment='达人 Id')
    crawl_date: Mapped[datetime.date] = mapped_column(Date, nullable=False, comment='抓取日期（无时分秒）')
    platform: Mapped[str] = mapped_column(String(16), nullable=False, comment='达人所在平台：1，TikTok；')
    platform_creator_id: Mapped[str] = mapped_column(String(32), nullable=False, comment='达人所在平台的账号 Id')
    platform_creator_display_name: Mapped[str] = mapped_column(String(64), nullable=False, comment='达人所在平台的用户昵称')
    platform_creator_username: Mapped[str] = mapped_column(String(64), nullable=False, comment='达人所在平台的用户名')
    task_id: Mapped[Optional[str]] = mapped_column(CHAR(36), comment='任务 Id')
    creator_id: Mapped[str] = mapped_column(CHAR(36), nullable=False, comment='创建人')
    creation_time: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=3), nullable=False, comment='创建时间（UTC 时间）')
    last_modifier_id: Mapped[str] = mapped_column(CHAR(36), nullable=False, comment='更新人')
    last_modification_time: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=3), nullable=False, comment='更新时间（UTC 时间）')
    email: Mapped[Optional[str]] = mapped_column(String(255), comment='达人 Email')
    whatsapp: Mapped[Optional[str]] = mapped_column(String(32), comment='达人 WhatsApp 账号')
    introduction: Mapped[Optional[str]] = mapped_column(Text, comment='达人自我介绍')
    region: Mapped[Optional[str]] = mapped_column(String(32), comment='达人所在地区')
    currency: Mapped[Optional[str]] = mapped_column(String(32), comment='达人所在地区货币类型')
    categories: Mapped[Optional[str]] = mapped_column(String(128), comment='达人在平台的分类')
    chat_url: Mapped[Optional[str]] = mapped_column(String(512), comment='达人在平台的聊天窗口 URL')
    search_keywords: Mapped[Optional[str]] = mapped_column(String(128), comment='达人被搜索到的关键词')
    brand_name: Mapped[Optional[str]] = mapped_column(String(255), comment='最后建联品牌的名称')
    followers: Mapped[Optional[int]] = mapped_column(INTEGER, comment='达人关注数（文本转化为数字）')
    top_brands: Mapped[Optional[str]] = mapped_column(String(255), comment='达人合作优质品牌')
    sales_revenue: Mapped[Optional[decimal.Decimal]] = mapped_column(DECIMAL(10, 2), comment='GMV')
    sales_units_sold: Mapped[Optional[int]] = mapped_column(INTEGER, comment='成交件数')
    sales_gpm: Mapped[Optional[decimal.Decimal]] = mapped_column(DECIMAL(10, 2), comment='千次曝光成交金额')
    sales_revenue_per_buyer: Mapped[Optional[decimal.Decimal]] = mapped_column(DECIMAL(10, 2), comment='客单价')
    gmv_per_sales_channel: Mapped[Optional[str]] = mapped_column(String(32), comment='最多 GMV 的渠道（包含比例）')
    gmv_by_product_category: Mapped[Optional[str]] = mapped_column(String(64), comment='最多 GMV 的商品类目（包含比例）')
    avg_commission_rate: Mapped[Optional[decimal.Decimal]] = mapped_column(DECIMAL(10, 4), comment='平均佣金率')
    collab_products: Mapped[Optional[int]] = mapped_column(INTEGER, comment='合作商品数')
    partnered_brands: Mapped[Optional[int]] = mapped_column(INTEGER, comment='合作品牌数')
    product_price: Mapped[Optional[str]] = mapped_column(String(64), comment='合作商品价格（范围）')
    video_gpm: Mapped[Optional[decimal.Decimal]] = mapped_column(DECIMAL(10, 2), comment='视频GPM')
    videos: Mapped[Optional[int]] = mapped_column(INTEGER, comment='视频数')
    avg_video_views: Mapped[Optional[int]] = mapped_column(INTEGER, comment='平均视频播放量')
    avg_video_engagement_rate: Mapped[Optional[decimal.Decimal]] = mapped_column(DECIMAL(10, 4), comment='视频平均互动率')
    avg_video_likes: Mapped[Optional[int]] = mapped_column(INTEGER, comment='视频平均点赞数')
    avg_video_comments: Mapped[Optional[int]] = mapped_column(INTEGER, comment='视频平均评论数')
    avg_video_shares: Mapped[Optional[int]] = mapped_column(INTEGER, comment='视频平均分享数')
    live_gpm: Mapped[Optional[decimal.Decimal]] = mapped_column(DECIMAL(10, 2), comment='直播千次观看成交金额')
    live_streams: Mapped[Optional[int]] = mapped_column(INTEGER, comment='视频数')
    avg_live_views: Mapped[Optional[int]] = mapped_column(INTEGER, comment='直播平均观看数')
    avg_live_engagement_rate: Mapped[Optional[decimal.Decimal]] = mapped_column(DECIMAL(10, 4), comment='直播平均互动率')
    avg_live_likes: Mapped[Optional[int]] = mapped_column(INTEGER, comment='直播平均点赞数')
    avg_live_comments: Mapped[Optional[int]] = mapped_column(INTEGER, comment='直播平均评论数')
    avg_live_shares: Mapped[Optional[int]] = mapped_column(INTEGER, comment='直播平均分享数')
    followers_male: Mapped[Optional[decimal.Decimal]] = mapped_column(DECIMAL(10, 4), comment='粉丝男性占比')
    followers_female: Mapped[Optional[decimal.Decimal]] = mapped_column(DECIMAL(10, 4), comment='粉丝女性占比')
    followers_18_24: Mapped[Optional[decimal.Decimal]] = mapped_column(DECIMAL(10, 4), comment='18-24岁占比')
    followers_25_34: Mapped[Optional[decimal.Decimal]] = mapped_column(DECIMAL(10, 4), comment='25-34岁占比')
    followers_35_44: Mapped[Optional[decimal.Decimal]] = mapped_column(DECIMAL(10, 4), comment='35-44岁占比')
    followers_45_54: Mapped[Optional[decimal.Decimal]] = mapped_column(DECIMAL(10, 4), comment='45-54岁占比')
    followers_55_more: Mapped[Optional[decimal.Decimal]] = mapped_column(DECIMAL(10, 4), comment='大于 55 岁占比')


class Creators(Base):
    __tablename__ = 'creators'
    __table_args__ = (
        Index('IX_Platform_AccountID', 'platform', 'platform_creator_id'),
        Index('IX_Platform_Username', 'platform', 'platform_creator_username'),
        {'comment': '达人表'}
    )

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True, comment='达人 Id')
    platform: Mapped[str] = mapped_column(String(16), nullable=False, comment='达人所在平台：1，TikTok；')
    platform_creator_id: Mapped[str] = mapped_column(String(32), nullable=False, comment='达人所在平台的账号 Id')
    platform_creator_display_name: Mapped[str] = mapped_column(String(64), nullable=False, comment='达人所在平台的用户昵称')
    platform_creator_username: Mapped[str] = mapped_column(String(64), nullable=False, comment='达人所在平台的用户名')
    creator_id: Mapped[str] = mapped_column(CHAR(36), nullable=False, comment='创建人')
    creation_time: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=3), nullable=False, comment='创建时间（UTC 时间）')
    last_modifier_id: Mapped[str] = mapped_column(CHAR(36), nullable=False, comment='更新人')
    last_modification_time: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=3), nullable=False, comment='更新时间（UTC 时间）')
    email: Mapped[Optional[str]] = mapped_column(String(255), comment='达人 Email')
    whatsapp: Mapped[Optional[str]] = mapped_column(String(32), comment='达人 WhatsApp 账号')
    introduction: Mapped[Optional[str]] = mapped_column(Text, comment='达人自我介绍')
    region: Mapped[Optional[str]] = mapped_column(String(32), comment='达人所在地区')
    currency: Mapped[Optional[str]] = mapped_column(String(32), comment='达人所在地区货币类型')
    categories: Mapped[Optional[str]] = mapped_column(String(128), comment='达人在平台的分类')
    chat_url: Mapped[Optional[str]] = mapped_column(String(512), comment='达人在平台的聊天窗口 URL')
    search_keywords: Mapped[Optional[str]] = mapped_column(String(128), comment='达人被搜索到的关键词')
    brand_name: Mapped[Optional[str]] = mapped_column(String(255), comment='最后建联品牌的名称')
    followers: Mapped[Optional[int]] = mapped_column(INTEGER, comment='达人关注数（文本转化为数字）')
    top_brands: Mapped[Optional[str]] = mapped_column(String(255), comment='达人合作优质品牌')
    sales_revenue: Mapped[Optional[decimal.Decimal]] = mapped_column(DECIMAL(10, 2), comment='GMV')
    sales_units_sold: Mapped[Optional[int]] = mapped_column(INTEGER, comment='成交件数')
    sales_gpm: Mapped[Optional[decimal.Decimal]] = mapped_column(DECIMAL(10, 2), comment='千次曝光成交金额')
    sales_revenue_per_buyer: Mapped[Optional[decimal.Decimal]] = mapped_column(DECIMAL(10, 2), comment='客单价')
    gmv_per_sales_channel: Mapped[Optional[str]] = mapped_column(String(32), comment='最多 GMV 的渠道（包含比例）')
    gmv_by_product_category: Mapped[Optional[str]] = mapped_column(String(64), comment='最多 GMV 的商品类目（包含比例）')
    avg_commission_rate: Mapped[Optional[decimal.Decimal]] = mapped_column(DECIMAL(10, 4), comment='平均佣金率')
    collab_products: Mapped[Optional[int]] = mapped_column(INTEGER, comment='合作商品数')
    partnered_brands: Mapped[Optional[int]] = mapped_column(INTEGER, comment='合作品牌数')
    product_price: Mapped[Optional[str]] = mapped_column(String(64), comment='合作商品价格（范围）')
    video_gpm: Mapped[Optional[decimal.Decimal]] = mapped_column(DECIMAL(10, 2), comment='视频GPM')
    videos: Mapped[Optional[int]] = mapped_column(INTEGER, comment='视频数')
    avg_video_views: Mapped[Optional[int]] = mapped_column(INTEGER, comment='平均视频播放量')
    avg_video_engagement_rate: Mapped[Optional[decimal.Decimal]] = mapped_column(DECIMAL(10, 4), comment='视频平均互动率')
    avg_video_likes: Mapped[Optional[int]] = mapped_column(INTEGER, comment='视频平均点赞数')
    avg_video_comments: Mapped[Optional[int]] = mapped_column(INTEGER, comment='视频平均评论数')
    avg_video_shares: Mapped[Optional[int]] = mapped_column(INTEGER, comment='视频平均分享数')
    live_gpm: Mapped[Optional[decimal.Decimal]] = mapped_column(DECIMAL(10, 2), comment='直播千次观看成交金额')
    live_streams: Mapped[Optional[int]] = mapped_column(INTEGER, comment='视频数')
    avg_live_views: Mapped[Optional[int]] = mapped_column(INTEGER, comment='直播平均观看数')
    avg_live_engagement_rate: Mapped[Optional[decimal.Decimal]] = mapped_column(DECIMAL(10, 4), comment='直播平均互动率')
    avg_live_likes: Mapped[Optional[int]] = mapped_column(INTEGER, comment='直播平均点赞数')
    avg_live_comments: Mapped[Optional[int]] = mapped_column(INTEGER, comment='直播平均评论数')
    avg_live_shares: Mapped[Optional[int]] = mapped_column(INTEGER, comment='直播平均分享数')
    followers_male: Mapped[Optional[decimal.Decimal]] = mapped_column(DECIMAL(10, 4), comment='粉丝男性占比')
    followers_female: Mapped[Optional[decimal.Decimal]] = mapped_column(DECIMAL(10, 4), comment='粉丝女性占比')
    followers_18_24: Mapped[Optional[decimal.Decimal]] = mapped_column(DECIMAL(10, 4), comment='18-24岁占比')
    followers_25_34: Mapped[Optional[decimal.Decimal]] = mapped_column(DECIMAL(10, 4), comment='25-34岁占比')
    followers_35_44: Mapped[Optional[decimal.Decimal]] = mapped_column(DECIMAL(10, 4), comment='35-44岁占比')
    followers_45_54: Mapped[Optional[decimal.Decimal]] = mapped_column(DECIMAL(10, 4), comment='45-54岁占比')
    followers_55_more: Mapped[Optional[decimal.Decimal]] = mapped_column(DECIMAL(10, 4), comment='大于 55 岁占比')


class OpsUsers(Base):
    __tablename__ = 'ops_users'
    __table_args__ = {'comment': '用户信息表'}

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True, comment='用户ID')
    user_name: Mapped[str] = mapped_column(VARCHAR(64), nullable=False, comment='用户账号')
    password: Mapped[str] = mapped_column(VARCHAR(64), nullable=False, server_default=text("''"), comment='密码')
    nick_name: Mapped[str] = mapped_column(VARCHAR(36), nullable=False, comment='用户昵称')
    creator_id: Mapped[str] = mapped_column(CHAR(36), nullable=False, comment='创建人')
    creation_time: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, comment='创建时间')
    last_modifier_id: Mapped[str] = mapped_column(CHAR(36), nullable=False, comment='更新人')
    last_modification_time: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, comment='更新时间')
    user_type: Mapped[Optional[str]] = mapped_column(VARCHAR(2), server_default=text("'00'"), comment='用户类型（00系统用户）')
    email: Mapped[Optional[str]] = mapped_column(VARCHAR(64), server_default=text("''"), comment='用户邮箱')
    phone_number: Mapped[Optional[str]] = mapped_column(VARCHAR(64), server_default=text("''"), comment='手机号码')
    sex: Mapped[Optional[int]] = mapped_column(TINYINT, server_default=text("'0'"), comment='用户性别：0-男, 1-女, 2-未知')
    avatar: Mapped[Optional[str]] = mapped_column(VARCHAR(256), server_default=text("''"), comment='头像地址')
    status: Mapped[Optional[int]] = mapped_column(TINYINT, server_default=text("'0'"), comment='帐号状态：0-正常, 1-停用')
    dept_id: Mapped[Optional[int]] = mapped_column(BIGINT, comment='部门ID')
    login_ip: Mapped[Optional[str]] = mapped_column(VARCHAR(128), server_default=text("''"), comment='最后登录IP')
    login_date: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, comment='最后登录时间')
    remark: Mapped[Optional[str]] = mapped_column(VARCHAR(512), comment='备注')
    deleted: Mapped[Optional[Any]] = mapped_column(BIT(1))


class OutreachTasks(Base):
    __tablename__ = 'outreach_tasks'
    __table_args__ = {'comment': '建联任务表'}

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True, comment='任务 Id')
    platform: Mapped[str] = mapped_column(String(16), nullable=False, comment='任务所在平台：1，TikTok；')
    task_name: Mapped[str] = mapped_column(String(64), nullable=False, comment='任务名称')
    creator_id: Mapped[str] = mapped_column(CHAR(36), nullable=False, comment='创建人')
    creation_time: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=3), nullable=False, comment='创建时间（UTC 时间）')
    last_modifier_id: Mapped[str] = mapped_column(CHAR(36), nullable=False, comment='更新人')
    last_modification_time: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=3), nullable=False, comment='更新时间（UTC 时间）')
    platform_campaign_id: Mapped[Optional[str]] = mapped_column(String(64), comment='活动 Id')
    platform_campaign_name: Mapped[Optional[str]] = mapped_column(String(128), comment='活动名称')
    platform_product_id: Mapped[Optional[str]] = mapped_column(String(64), comment='商品id')
    platform_product_name: Mapped[Optional[str]] = mapped_column(String(128), comment='商品名称')
    product_list: Mapped[Optional[dict]] = mapped_column(JSON, comment='商品列表（JSON 数组）')
    region: Mapped[Optional[str]] = mapped_column(String(32), comment='地区')
    brand: Mapped[Optional[str]] = mapped_column(String(255), comment='品牌')
    message_send_strategy: Mapped[Optional[int]] = mapped_column(TINYINT, comment='消息发送策略：0 表示新老达人都按常规策略发送消息；1 表示仅对从未建联的新达人发送首次消息；2 表示只跟进历史未回复的达人发送后续消息')
    task_type: Mapped[Optional[str]] = mapped_column(String(32), comment='任务类型')
    status: Mapped[Optional[str]] = mapped_column(String(32), comment='任务状态')
    message: Mapped[Optional[str]] = mapped_column(String(512), comment='任务信息')
    accound_email: Mapped[Optional[str]] = mapped_column(String(255), comment='任务执行的 TikTok 账号')
    search_keywords: Mapped[Optional[str]] = mapped_column(String(255), comment='搜索关键词')
    product_categories: Mapped[Optional[dict]] = mapped_column(JSON, comment='商品类目（JSON 数组）')
    fans_age_range: Mapped[Optional[dict]] = mapped_column(JSON, comment='粉丝年龄范围（JSON 数组）')
    fans_gender: Mapped[Optional[dict]] = mapped_column(JSON, comment='粉丝性别（JSON 对象）')
    content_types: Mapped[Optional[dict]] = mapped_column(JSON, comment='达人内容类型（JSON 数组）')
    gmv_range: Mapped[Optional[dict]] = mapped_column(JSON, comment='达人 gmv 范围（JSON 数组）')
    sales_range: Mapped[Optional[dict]] = mapped_column(JSON, comment='达人 sales 范围（JSON 数组）')
    min_fans: Mapped[Optional[int]] = mapped_column(INTEGER, comment='最小粉丝数')
    min_avg_views: Mapped[Optional[int]] = mapped_column(INTEGER, comment='最小平均播放量')
    min_engagement_rate: Mapped[Optional[int]] = mapped_column(INTEGER, comment='最小参与率')
    first_message: Mapped[Optional[str]] = mapped_column(Text, comment='初次消息内容')
    second_message: Mapped[Optional[str]] = mapped_column(Text, comment='二次消息内容')
    new_creators_expect_count: Mapped[Optional[int]] = mapped_column(INTEGER, comment='期望建联新达人数量目标')
    max_creators: Mapped[Optional[int]] = mapped_column(INTEGER, comment='最多出来处理达人数量')
    plan_execute_time: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, comment='计划启动时间')
    plan_stop_time: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, comment='计划终止时间')
    spend_time: Mapped[Optional[int]] = mapped_column(INTEGER, comment='任务运行时长（单位：秒）')
    new_creators_real_count: Mapped[Optional[int]] = mapped_column(INTEGER, comment='实际新增达人数量')
    real_start_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, comment='启动时间')
    real_end_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, comment='结束时间')


class Products(Base):
    __tablename__ = 'products'
    __table_args__ = (
        Index('IX_CampaignID', 'platform', 'platform_campaign_id'),
        Index('IX_ProductId', 'platform', 'platform_product_id'),
        {'comment': '活动商品表'}
    )

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True, comment='商品 Id')
    region: Mapped[str] = mapped_column(String(32), nullable=False, comment='地区')
    platform: Mapped[str] = mapped_column(String(16), nullable=False, comment='达人所在平台：1，TikTok；')
    platform_campaign_id: Mapped[str] = mapped_column(String(36), nullable=False, comment='活动 Id')
    platform_product_id: Mapped[str] = mapped_column(String(32), nullable=False, comment='商品 Id')
    creator_id: Mapped[str] = mapped_column(CHAR(36), nullable=False, comment='创建人')
    creation_time: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=3), nullable=False, comment='创建时间（UTC时间）')
    last_modifier_id: Mapped[str] = mapped_column(CHAR(36), nullable=False, comment='更新人')
    last_modification_time: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=3), nullable=False, comment='更新时间（UTC时间）')
    platform_shop_name: Mapped[Optional[str]] = mapped_column(String(128), comment='店铺名称')
    platform_shop_phone: Mapped[Optional[str]] = mapped_column(String(32), comment='店铺电话')
    platform_shop_id: Mapped[Optional[str]] = mapped_column(String(32), comment='店铺号')
    thumbnail: Mapped[Optional[str]] = mapped_column(String(512), comment='图片链接')
    product_name: Mapped[Optional[str]] = mapped_column(String(1024), comment='商品名称')
    product_name_cn: Mapped[Optional[str]] = mapped_column(String(1024), comment='商品中文名')
    product_category_name: Mapped[Optional[str]] = mapped_column(String(128), comment='商品类目')
    partner_rate: Mapped[Optional[decimal.Decimal]] = mapped_column(DECIMAL(10, 2), comment='partner佣金比例')
    creator_rate: Mapped[Optional[decimal.Decimal]] = mapped_column(DECIMAL(10, 2), comment='达人佣金比例')
    cost_product: Mapped[Optional[str]] = mapped_column(String(255), comment='预估商品成本（是一个范围）')
    affiliate_link: Mapped[Optional[str]] = mapped_column(String(512), comment='附属链接（实测tap给的部分没用）')
    product_link: Mapped[Optional[str]] = mapped_column(String(512), comment='商品链接')
    product_rating: Mapped[Optional[int]] = mapped_column(TINYINT, comment='评分')
    reviews_count: Mapped[Optional[int]] = mapped_column(INTEGER, comment='商品评论量')
    product_sku: Mapped[Optional[str]] = mapped_column(String(64), comment='商品SKU')
    stock: Mapped[Optional[int]] = mapped_column(INTEGER, comment='库存')
    available_sample_count: Mapped[Optional[int]] = mapped_column(INTEGER, comment='可用样品数量')
    item_sold: Mapped[Optional[int]] = mapped_column(INTEGER, comment='商品销量')
    sale_price_min: Mapped[Optional[decimal.Decimal]] = mapped_column(DECIMAL(10, 2), comment='最低销售价格')
    sale_price_max: Mapped[Optional[decimal.Decimal]] = mapped_column(DECIMAL(10, 2), comment='最高销售价格')
    selling_point: Mapped[Optional[str]] = mapped_column(TINYTEXT, comment='卖点')
    selling_point_cn: Mapped[Optional[str]] = mapped_column(TINYTEXT, comment='卖点中文')
    shooting_guide: Mapped[Optional[str]] = mapped_column(TINYTEXT, comment='拍摄指南')
    shooting_guide_cn: Mapped[Optional[str]] = mapped_column(TINYTEXT, comment='拍摄指南中文')


class SampleContentCrawlLogs(Base):
    __tablename__ = 'sample_content_crawl_logs'
    __table_args__ = (
        Index('IX_ProductID', 'platform_product_id'),
        {'comment': '样品内容抓取日志表'}
    )

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True, comment='日志 Id（自增）')
    crawl_date: Mapped[datetime.date] = mapped_column(Date, nullable=False, comment='抓取日期（无时分秒）')
    platform_product_id: Mapped[str] = mapped_column(String(64), nullable=False, comment='商品 Id')
    creator_id: Mapped[str] = mapped_column(CHAR(36), nullable=False, comment='创建人')
    creation_time: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=3), nullable=False, comment='创建时间（UTC时间）')
    last_modifier_id: Mapped[str] = mapped_column(CHAR(36), nullable=False, comment='更新人')
    last_modification_time: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=3), nullable=False, comment='更新时间（UTC时间）')
    region: Mapped[Optional[str]] = mapped_column(String(32), comment='达人所在地区')
    type: Mapped[Optional[str]] = mapped_column(String(32), comment='推广视频/直播类型：1，视频；2，直播')
    platform_creator_id: Mapped[Optional[str]] = mapped_column(String(32), comment='达人所在平台的账号 Id')
    platform_creator_display_name: Mapped[Optional[str]] = mapped_column(String(64), comment='达人所在平台的用户昵称')
    platform_creator_username: Mapped[Optional[str]] = mapped_column(String(64), comment='达人所在平台的用户名')
    platform_detail_url: Mapped[Optional[str]] = mapped_column(String(512), comment='达人所在平台url')
    promotion_name: Mapped[Optional[str]] = mapped_column(String(255), comment='推广视频/直播名称')
    promotion_time: Mapped[Optional[str]] = mapped_column(String(255), comment='推广视频/直播时间')
    promotion_view_count: Mapped[Optional[int]] = mapped_column(INTEGER, comment='推广视频/直播观看数')
    promotion_like_count: Mapped[Optional[int]] = mapped_column(INTEGER, comment='推广视频/直播点赞数')
    promotion_comment_count: Mapped[Optional[int]] = mapped_column(INTEGER, comment='推广视频/直播评论数')
    promotion_order_count: Mapped[Optional[int]] = mapped_column(INTEGER, comment='推广视频/直播订单数')
    promotion_order_total_amount: Mapped[Optional[decimal.Decimal]] = mapped_column(DECIMAL(10, 2), comment='推广视频/直播收入')


class SampleContents(Base):
    __tablename__ = 'sample_contents'
    __table_args__ = (
        Index('IX_ProductID', 'platform_product_id'),
        {'comment': '样品内容表'}
    )

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True, comment='样品内容 Id（自增）')
    platform_product_id: Mapped[str] = mapped_column(String(64), nullable=False, comment='商品 Id')
    creator_id: Mapped[str] = mapped_column(CHAR(36), nullable=False, comment='创建人')
    creation_time: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=3), nullable=False, comment='创建时间（UTC时间）')
    last_modifier_id: Mapped[str] = mapped_column(CHAR(36), nullable=False, comment='更新人')
    last_modification_time: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=3), nullable=False, comment='更新时间（UTC时间）')
    region: Mapped[Optional[str]] = mapped_column(String(32), comment='达人所在地区')
    type: Mapped[Optional[str]] = mapped_column(String(32), comment='推广视频/直播类型：1，视频；2，直播')
    platform_creator_id: Mapped[Optional[str]] = mapped_column(String(32), comment='达人所在平台的账号 Id')
    platform_creator_display_name: Mapped[Optional[str]] = mapped_column(String(64), comment='达人所在平台的用户昵称')
    platform_creator_username: Mapped[Optional[str]] = mapped_column(String(64), comment='达人所在平台的用户名')
    platform_detail_url: Mapped[Optional[str]] = mapped_column(String(512), comment='达人所在平台url')
    promotion_name: Mapped[Optional[str]] = mapped_column(String(255), comment='推广视频/直播名称')
    promotion_time: Mapped[Optional[str]] = mapped_column(String(255), comment='推广视频/直播时间')
    promotion_view_count: Mapped[Optional[int]] = mapped_column(INTEGER, comment='推广视频/直播观看数')
    promotion_like_count: Mapped[Optional[int]] = mapped_column(INTEGER, comment='推广视频/直播点赞数')
    promotion_comment_count: Mapped[Optional[int]] = mapped_column(INTEGER, comment='推广视频/直播评论数')
    promotion_order_count: Mapped[Optional[int]] = mapped_column(INTEGER, comment='推广视频/直播订单数')
    promotion_order_total_amount: Mapped[Optional[decimal.Decimal]] = mapped_column(DECIMAL(10, 2), comment='推广视频/直播收入')


class SampleCrawlLogs(Base):
    __tablename__ = 'sample_crawl_logs'
    __table_args__ = (
        Index('IX_CampaignID', 'platform_campaign_id'),
        Index('IX_ProductID', 'platform_product_id'),
        {'comment': '样品抓取日志表'}
    )

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True, comment='日志 Id（自增）')
    crawl_date: Mapped[datetime.date] = mapped_column(Date, nullable=False, comment='抓取日期（无时分秒）')
    platform_product_id: Mapped[str] = mapped_column(String(64), nullable=False, comment='商品 Id')
    creator_id: Mapped[str] = mapped_column(CHAR(36), nullable=False, comment='创建人')
    creation_time: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=3), nullable=False, comment='创建时间（UTC时间）')
    last_modifier_id: Mapped[str] = mapped_column(CHAR(36), nullable=False, comment='更新人')
    last_modification_time: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=3), nullable=False, comment='更新时间（UTC时间）')
    region: Mapped[Optional[str]] = mapped_column(String(32), comment='地区')
    stock: Mapped[Optional[int]] = mapped_column(INTEGER, comment='库存')
    product_sku: Mapped[Optional[str]] = mapped_column(String(64), comment='商品SKU')
    available_sample_count: Mapped[Optional[int]] = mapped_column(INTEGER, comment='可用样品数量')
    is_uncooperative: Mapped[Optional[Any]] = mapped_column(BIT(1), comment='是否不可合作')
    is_unapprovable: Mapped[Optional[Any]] = mapped_column(BIT(1), comment='是否不可同意')
    status: Mapped[Optional[str]] = mapped_column(String(32), comment='样品管理状态：1，待审核；2，准备发货；3，已发货；4，未发布任何内容；5，已完成；6，已取消')
    request_time_remaining: Mapped[Optional[str]] = mapped_column(String(255), comment='剩余申请时间')
    platform_campaign_id: Mapped[Optional[str]] = mapped_column(String(64), comment='活动id')
    platform_campaign_name: Mapped[Optional[str]] = mapped_column(Text, comment='活动名称')
    platform_creator_display_name: Mapped[Optional[str]] = mapped_column(String(64), comment='达人所在平台的用户昵称')
    platform_creator_username: Mapped[Optional[str]] = mapped_column(String(255), comment='达人所在平台的用户名')
    platform_creator_id: Mapped[Optional[str]] = mapped_column(String(32), comment='达人所在平台的账号 Id')
    post_rate: Mapped[Optional[decimal.Decimal]] = mapped_column(DECIMAL(10, 4), comment='达人发布率')
    is_showcase: Mapped[Optional[Any]] = mapped_column(BIT(1), comment='是否橱窗展示')
    content_summary: Mapped[Optional[dict]] = mapped_column(JSON, comment='达人推广视频/直播类型相关数据摘要（JSON 对象）')
    ad_code: Mapped[Optional[dict]] = mapped_column(JSON, comment='AD Code（JSON 数组）')


class Samples(Base):
    __tablename__ = 'samples'
    __table_args__ = (
        Index('IX_CampaignID', 'platform_campaign_id'),
        Index('IX_ProductID', 'platform_product_id'),
        {'comment': '样品表'}
    )

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True, comment='样品 Id')
    platform_product_id: Mapped[str] = mapped_column(String(64), nullable=False, comment='商品 Id')
    creator_id: Mapped[str] = mapped_column(CHAR(36), nullable=False, comment='创建人')
    creation_time: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=3), nullable=False, comment='创建时间（UTC时间）')
    last_modifier_id: Mapped[str] = mapped_column(CHAR(36), nullable=False, comment='更新人')
    last_modification_time: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=3), nullable=False, comment='更新时间（UTC时间）')
    region: Mapped[Optional[str]] = mapped_column(String(32), comment='地区')
    stock: Mapped[Optional[int]] = mapped_column(INTEGER, comment='库存')
    product_sku: Mapped[Optional[str]] = mapped_column(String(64), comment='商品SKU')
    available_sample_count: Mapped[Optional[int]] = mapped_column(INTEGER, comment='可用样品数量')
    is_uncooperative: Mapped[Optional[Any]] = mapped_column(BIT(1), comment='是否不可合作')
    is_unapprovable: Mapped[Optional[Any]] = mapped_column(BIT(1), comment='是否不可同意')
    status: Mapped[Optional[str]] = mapped_column(String(32), comment='样品管理状态：1，待审核；2，准备发货；3，已发货；4，未发布任何内容；5，已完成；6，已取消')
    request_time_remaining: Mapped[Optional[str]] = mapped_column(String(255), comment='剩余申请时间')
    platform_campaign_id: Mapped[Optional[str]] = mapped_column(String(64), comment='活动id')
    platform_campaign_name: Mapped[Optional[str]] = mapped_column(Text, comment='活动名称')
    platform_creator_display_name: Mapped[Optional[str]] = mapped_column(String(64), comment='达人所在平台的用户昵称')
    platform_creator_username: Mapped[Optional[str]] = mapped_column(String(255), comment='达人所在平台的用户名')
    post_rate: Mapped[Optional[decimal.Decimal]] = mapped_column(DECIMAL(10, 4), comment='达人发布率')
    is_showcase: Mapped[Optional[Any]] = mapped_column(BIT(1), comment='是否橱窗展示')
    content_summary: Mapped[Optional[dict]] = mapped_column(JSON, comment='达人推广视频/直播类型相关数据摘要（JSON 对象）')
    ad_code: Mapped[Optional[dict]] = mapped_column(JSON, comment='AD Code（JSON 数组）')


class UploadProductBatch(Base):
    __tablename__ = 'upload_product_batch'
    __table_args__ = (
        Index('IX_UploadID', 'id'),
        {'comment': '上传商品文件表'}
    )

    id: Mapped[str] = mapped_column(CHAR(36), primary_key=True, comment='上传id')
    region: Mapped[str] = mapped_column(String(32), nullable=False, comment='地区')
    creator_id: Mapped[str] = mapped_column(CHAR(36), nullable=False, comment='创建人')
    creation_time: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=3), nullable=False, comment='创建时间（UTC 时间）')
    last_modifier_id: Mapped[str] = mapped_column(CHAR(36), nullable=False, comment='更新人')
    last_modification_time: Mapped[datetime.datetime] = mapped_column(DATETIME(fsp=3), nullable=False, comment='更新时间（UTC 时间）')
    source_file: Mapped[Optional[str]] = mapped_column(String(255), comment='源文件')
    note: Mapped[Optional[str]] = mapped_column(Text, comment='备注')
    total_rows: Mapped[Optional[int]] = mapped_column(Integer, comment='上传文件的总行数')
    dify_total: Mapped[Optional[int]] = mapped_column(Integer, comment='dify需处理总行数')
    dify_processed: Mapped[Optional[int]] = mapped_column(Integer, comment='dify已经处理的行数')
    dify_failed: Mapped[Optional[int]] = mapped_column(Integer, comment='dify处理失败的行数')
