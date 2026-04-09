from datetime import datetime

from shared_application_services import BaseDTO


class CurrentUserInfo(BaseDTO):
    jti: str
    iat: datetime  # 添加签发时间，用于排序
    user_id: str
    username: str
    phone_number: str
    device_id: str
    device_type: str
