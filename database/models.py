# database/models.py
from sqlalchemy import Column, String, Integer, Text, DateTime, Boolean, ForeignKey
from database.db import Base, now_beijing  # 之后 db.py 里会定义 Base
"""
这里定义所有数据库表的ORM模型。
会用 SQLAlchemy 的 Base (from database.db).

表一：商品上传
- class UploadBatch
- class Product

表二：建联任务
- class OutreachTask
- class OutreachTaskLog

表三：达人库
- class Creator
- class CreatorLog
"""

# from sqlalchemy import Column, Integer, String, ...
# from database.db import Base
class OutreachTask(Base):
    __tablename__ = "outreach_task"

    # 任务 ID：你的 crawler 里是字符串，这里我们直接把它当主键
    task_id = Column(String(64), primary_key=True, index=True)

    task_name = Column(String(255))
    campaign_id = Column(String(64))
    campaign_name = Column(String(255))

    product_id = Column(String(64))
    product_name = Column(String(255))

    region = Column(String(64))
    brand = Column(String(255))
    only_first = Column(String(32))  # 暂时用字符串/标志；后面可改成 Boolean
    task_type = Column(String(32), default="Connect")
    status = Column(String(32), default="pending")
    message = Column(Text)
    created_by = Column(String(255))
    account_email = Column(String(255))

    search_keywords = Column(Text)
    product_category = Column(String(255))

    fans_age_range = Column(Text)         # 存成 "18-24,25-34" 这种
    fans_gender = Column(String(32))
    min_fans = Column(String(64))

    content_type = Column(Text)           #  "video,live,..."
    gmv = Column(Text)
    sales = Column(Text)
    min_GMV = Column(String(64))
    max_GMV = Column(String(64))
    min_sales = Column(Text)              # list（兼容旧字段）
    avg_views = Column(String(64))
    min_engagement_rate = Column(String(64))

    email_first_subject = Column(Text)
    email_first_body = Column(Text)
    email_later_subject = Column(Text)
    email_later_body = Column(Text)

    target_new_creators = Column(Integer)
    max_creators = Column(Integer)

    run_at_time = Column(String(64))
    run_end_time = Column(String(64))
    run_time = Column(String(64))

    task_directory = Column(Text)
    log_path = Column(Text)
    output_files = Column(Text)

    # 运行时统计
    connect_creator = Column(String(255))  # 暂时按字符串留，后面如果是数字可以调成 Integer
    new_creators = Column(Integer)
    total_creators = Column(Integer)
    payload_json = Column(Text)
    started_at = Column(DateTime)
    finished_at = Column(DateTime)

    created_at = Column(DateTime, default=now_beijing)

# 下面这些我们先保留空壳，后面按后续表慢慢填
class OutreachTaskLog(Base):
    __tablename__ = "outreach_task_log"
    log_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    # TODO: 后面加 task_id 外键 + event_type + detail + ts

class UploadBatch(Base):
    __tablename__ = "upload_batch"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    uploaded_by = Column(String(100), nullable=False)           # 谁上传
    source_file = Column(String(255), nullable=True)            # 原文件名/路径
    note = Column(String(255), nullable=True)                   # 备注（可空）
    uploaded_at = Column(DateTime, default=now_beijing)     # 北京时间
    total_rows = Column(Integer, default=0)
    dify_total = Column(Integer, default=0)
    dify_processed = Column(Integer, default=0)
    dify_failed = Column(Integer, default=0)
    region_override = Column(String(32), nullable=True)


class Product(Base):
    __tablename__ = "product"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    batch_id = Column(Integer, ForeignKey("upload_batch.id"), index=True, nullable=False)
    source_row_index = Column(Integer, nullable=True, index=False)

    # —— 与前端字段对应 一一
    backend_system_id = Column(String(128), index=True)         # 后端系统标识
    region = Column(String(32), index=True)                     # 国家
    campaign_id = Column(String(64), index=True)
    campaign_name = Column(String(255), index=True)             # 活动名称
    product_name = Column(String(255))
    thumbnail = Column(Text)                                    # 产品缩略图
    product_id = Column(String(128), index=True)
    SKU_product = Column(String(128), index=True)               # 产品SKU名称
    sale_price = Column(String(64))
    shop_name = Column(String(255), index=True)                 # 店铺名称
    campaign_start_time = Column(String(64))
    campaign_end_time = Column(String(64))
    creator_rate = Column(String(32))
    partner_rate = Column(String(32))                           # 机构佣金比例（先存字符串，比如“10%/15%”）
    cost_product = Column(String(64))
    available_samples = Column(String(32))                      # 样品数量（先字符串，后续可转INT）
    stock = Column(String(32))
    item_sold = Column(String(32))
    affiliate_link = Column(Text)                               # 联盟链接
    product_link = Column(Text)                                 # 商品链接
    product_name_cn = Column(Text)
    selling_point = Column(Text)
    selling_point_cn = Column(Text)
    shooting_guide = Column(Text)
    shooting_guide_cn = Column(Text)
    product_category_name = Column(String(255))

    # 常规元信息
    created_at = Column(DateTime, default=now_beijing)
    updated_at = Column(DateTime, default=now_beijing)
    
class Creator(Base):
    __tablename__ = "creator"

    # 用平台上的 id 做主键。如果 creator_id 不是全局唯一，就暂时当成字符串主键用
    creator_id = Column(String(128), primary_key=True, index=True)

    creator_name = Column(String(255))
    categories = Column(Text)
    followers = Column(Integer)
    intro = Column(Text)

    region = Column(String(64))

    whatsapp = Column(String(255))
    email = Column(String(255))
    creator_chaturl = Column(Text)

    search_keywords = Column(Text)
    top_brands = Column(Text)

    # 我们把这些合作/表现类的信息也放一点点在主表里，方便快速列表展示
    avg_video_views = Column(Integer)
    avg_video_engagement_rate = Column(String(64))
    avg_live_views = Column(Integer)
    avg_live_engagement_rate = Column(String(64))

    updated_at = Column(DateTime, default=now_beijing)

class CreatorLog(Base):
    __tablename__ = "creator_log"

    log_id = Column(Integer, primary_key=True, index=True, autoincrement=True)

    # 归属哪个达人
    creator_id = Column(String(128), index=True)

    # 采集元信息
    task_id = Column(String(64), index=True)       # 哪个任务跑出来的
    shop_name = Column(String(255), index=True)    # 哪个店/品牌在看的
    brand_name = Column(String(255))
    region = Column(String(64))

    # 对这个达人本次抓取到的业务指标
    sales_revenue = Column(String(64))
    sales_units_sold = Column(String(64))
    sales_gpm = Column(String(64))
    sales_revenue_per_buyer = Column(String(64))

    gmv_per_sales_channel = Column(Text)
    gmv_by_product_category = Column(Text)

    avg_commission_rate = Column(String(64))
    collab_products = Column(Text)
    partnered_brands = Column(Text)
    product_price = Column(String(64))

    video_gpm = Column(String(64))
    videos = Column(String(64))
    avg_video_views = Column(String(64))
    avg_video_engagement_rate = Column(String(64))
    avg_video_likes = Column(String(64))
    avg_video_comments = Column(String(64))
    avg_video_shares = Column(String(64))

    live_gpm = Column(String(64))
    live_streams = Column(String(64))
    avg_live_views = Column(String(64))
    avg_live_engagement_rate = Column(String(64))
    avg_live_likes = Column(String(64))
    avg_live_comments = Column(String(64))
    avg_live_shares = Column(String(64))

    followers_male = Column(String(64))
    followers_female = Column(String(64))
    followers_18_24 = Column(String(64))
    followers_25_34 = Column(String(64))
    followers_35_44 = Column(String(64))
    followers_45_54 = Column(String(64))
    followers_55_more = Column(String(64))

    # 外联相关状态
    partner_id = Column(String(128))
    connect = Column(Boolean)
    reply = Column(Boolean)
    send = Column(Boolean)
    send_time = Column(String(64))

    # 联系信息这次的快照
    whatsapp = Column(String(255))
    email = Column(String(255))

    created_at = Column(DateTime, default=now_beijing)
