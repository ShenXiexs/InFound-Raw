# database/ingest_creator_data.py
from database.db import get_session, now_beijing
from database.models import Creator, CreatorLog

def log_creator_snapshot_to_db(creator_data: dict, task_id: str, shop_name: str):
    cid = str(creator_data.get("creator_id"))
    if not cid:
        return  # 没有稳定ID就不写库，避免脏数据

    with get_session() as db:
        # 1) upsert Creator
        row = db.query(Creator).filter(Creator.creator_id == cid).first()
        if not row:
            row = Creator(creator_id=cid)
            db.add(row)

        row.creator_name = creator_data.get('creator_name')
        row.categories = creator_data.get('categories')
        row.followers = creator_data.get('followers')
        row.intro = creator_data.get('intro')
        row.region = creator_data.get('region')
        row.whatsapp = creator_data.get('whatsapp')
        row.email = creator_data.get('email')
        row.creator_chaturl = creator_data.get('creator_chaturl')
        row.search_keywords = creator_data.get('search_keywords')
        row.top_brands = creator_data.get('top_brands')
        row.avg_video_views = creator_data.get('avg_video_views')
        row.avg_video_engagement_rate = creator_data.get('avg_video_engagement_rate')
        row.avg_live_views = creator_data.get('avg_live_views')
        row.avg_live_engagement_rate = creator_data.get('avg_live_engagement_rate')
        row.updated_at = now_beijing()

        # 2) append CreatorLog
        log = CreatorLog(
            creator_id=cid,
            task_id=str(task_id),
            shop_name=str(shop_name),
            brand_name=creator_data.get('brand_name'),
            region=creator_data.get('region'),
            sales_revenue=creator_data.get('sales_revenue'),
            sales_units_sold=creator_data.get('sales_units_sold'),
            sales_gpm=creator_data.get('sales_gpm'),
            sales_revenue_per_buyer=creator_data.get('sales_revenue_per_buyer'),
            gmv_per_sales_channel=creator_data.get('gmv_per_sales_channel'),
            gmv_by_product_category=creator_data.get('gmv_by_product_category'),
            avg_commission_rate=creator_data.get('avg_commission_rate'),
            collab_products=creator_data.get('collab_products'),
            partnered_brands=creator_data.get('partnered_brands'),
            product_price=creator_data.get('product_price'),
            video_gpm=creator_data.get('video_gpm'),
            videos=creator_data.get('videos'),
            avg_video_views=creator_data.get('avg_video_views'),
            avg_video_engagement_rate=creator_data.get('avg_video_engagement_rate'),
            avg_video_likes=creator_data.get('avg_video_likes'),
            avg_video_comments=creator_data.get('avg_video_comments'),
            avg_video_shares=creator_data.get('avg_video_shares'),
            live_gpm=creator_data.get('live_gpm'),
            live_streams=creator_data.get('live_streams'),
            avg_live_views=creator_data.get('avg_live_views'),
            avg_live_engagement_rate=creator_data.get('avg_live_engagement_rate'),
            avg_live_likes=creator_data.get('avg_live_likes'),
            avg_live_comments=creator_data.get('avg_live_comments'),
            avg_live_shares=creator_data.get('avg_live_shares'),
            followers_male=creator_data.get('followers_male'),
            followers_female=creator_data.get('followers_female'),
            followers_18_24=creator_data.get('followers_18_24'),
            followers_25_34=creator_data.get('followers_25_34'),
            followers_35_44=creator_data.get('followers_35_44'),
            followers_45_54=creator_data.get('followers_45_54'),
            followers_55_more=creator_data.get('followers_55_more'),
            partner_id=creator_data.get('partner_id'),
            connect=creator_data.get('connect'),
            reply=creator_data.get('reply'),
            send=creator_data.get('send'),
            send_time=creator_data.get('send_time'),
            whatsapp=creator_data.get('whatsapp'),
            email=creator_data.get('email'),
            created_at=now_beijing(),
        )
        db.add(log)
