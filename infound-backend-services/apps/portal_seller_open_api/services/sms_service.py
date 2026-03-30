import json
import random
import re
from typing import Optional

from alibabacloud_credentials.client import Client as CredentialClient
from alibabacloud_dysmsapi20170525 import models as dysmsapi_20170525_models
from alibabacloud_dysmsapi20170525.client import Client as Dysmsapi20170525Client
from alibabacloud_tea_openapi import models as open_api_models
from alibabacloud_tea_util import models as util_models

from apps.portal_seller_open_api.core.config import IFAliSmsSettings
from core_base import get_logger
from core_redis import RedisClientManager
from core_redis.redis_setting import RedisSettings


class SmsService:

    def __init__(self, settings: IFAliSmsSettings, redis_settings: RedisSettings):
        self.settings = settings
        self.redis_settings = redis_settings
        self.logger = get_logger("SmsService")

    @staticmethod
    def normalize_china_phone_number(phone_number: str) -> Optional[str]:
        """
        规范化中国手机号为 E.164 格式：+86XXXXXXXXXXX（严格校验，避免误判）

        允许输入：
        - +8613800138000
        - 8613800138000
        - 13800138000

        不允许：
        - 868613800138000（中间夹杂“86”被错误剔除后变成合法号的情况）
        - +868613800138000（号码长度超标）
        """
        if not phone_number:
            return None

        s = phone_number.strip()
        if not s:
            return None

        # 容错处理常见分隔符：空格/制表符等空白、连字符
        # 例：138-0013-8000 / 138 0013 8000
        s = re.sub(r"[\s-]+", "", s)

        # 仅允许在“开头”出现一次国家码前缀（+86 或 86），不能做全局 replace
        # 捕获完整号码，确保没有多余字符或多余位数
        m = re.fullmatch(r'(?:\+?86)?(1[3-9]\d{9})', s)
        if not m:
            return None

        national = m.group(1)  # 11位中国手机号（不含国家码）
        return f"+86{national}"

    @staticmethod
    def _generate_verification_code() -> str:
        """生成6位数字验证码"""
        return str(random.randint(100000, 999999))

    def _create_sms_client(self) -> Dysmsapi20170525Client:
        """创建阿里云短信客户端"""
        from alibabacloud_credentials import models as credential_models

        # 优先从环境变量读取凭证
        access_key_id = self.settings.access_key_id
        access_key_secret = self.settings.access_key_secret

        # 如果找到了凭证，使用显式凭证配置
        if access_key_id and access_key_secret:
            self.logger.info(f"成功加载阿里云凭证，AccessKey ID: {access_key_id[:8]}...")
            credential_config = credential_models.Config(
                type='access_key',
                access_key_id=access_key_id,
                access_key_secret=access_key_secret
            )
            credential = CredentialClient(credential_config)
            self.logger.info("使用显式凭证创建阿里云短信客户端")
        else:
            # 如果仍然没有凭证，使用默认的CredentialClient（会尝试多种方式加载）
            self.logger.warning(
                f"未找到阿里云凭证 - AccessKey ID: {'已设置' if access_key_id else '未设置'}, AccessKey Secret: {'已设置' if access_key_secret else '未设置'}")
            self.logger.warning("将使用默认凭证加载方式（会尝试环境变量、配置文件、ECS RAM角色等）")
            credential = CredentialClient()

        config = open_api_models.Config(
            credential=credential
        )
        config.endpoint = 'dysmsapi.aliyuncs.com'
        return Dysmsapi20170525Client(config)

    def _get_verification_code_redis_key(self, phone_number: str) -> str:
        """获取验证码在Redis中的key"""
        return f"{self.redis_settings.prefix}:xunda:verificationCode:{phone_number}"

    def _get_send_count_redis_key(self, phone_number: str) -> str:
        """获取发送次数统计在Redis中的key"""
        return f"{self.redis_settings.prefix}:xunda:smsSendCount:{phone_number}"

    def send_sms_verification_code(self, phone_number: str, purpose: str) -> tuple[bool, Optional[str]]:
        """
        发送短信验证码

        Args:
            phone_number: 手机号（带+86前缀，如+8613800138000）
            purpose: 用途（如signup）

        Returns:
            (是否成功, 错误信息)
        """
        try:
            # 1. 验证手机号格式（目前只支持中国手机号）
            normalized_phone_number = self.normalize_china_phone_number(phone_number)
            if not normalized_phone_number:
                self.logger.warning(f"手机号格式不正确或不是中国手机号: {phone_number}")
                return False, "目前只支持中国手机号"

            # 2. 检查5分钟内发送次数
            redis_client = RedisClientManager.get_client()
            send_count_key = self._get_send_count_redis_key(normalized_phone_number)
            send_count = redis_client.get(send_count_key)

            # 检查发送次数限制
            if send_count:
                count = int(send_count)
                if count >= self.settings.max_send_count_per_phone:
                    self.logger.warning(f"手机号 {phone_number} 在5分钟内已发送{count}次，超过限制")
                    return False, "1206"  # 错误编码1206：5分钟内发送次数超过限制

            # 3. 生成验证码
            verification_code = self._generate_verification_code()
            final_verification_code = verification_code  # 默认使用我们生成的验证码

            # 4. 调用阿里云短信服务发送验证码
            client = self._create_sms_client()

            phone = normalized_phone_number[3:]  # 去掉 +86 前缀

            # 构建模板参数（JSON字符串）
            template_param = json.dumps({
                "code": verification_code
            }, ensure_ascii=False)

            # 获取短信配置
            sign_name = self.settings.sign_name
            template_code = self.settings.template_code

            request = dysmsapi_20170525_models.SendSmsRequest(
                phone_numbers=phone,
                sign_name=sign_name,
                template_code=template_code,
                template_param=template_param
            )

            try:
                resp = client.send_sms_with_options(request, util_models.RuntimeOptions())
                self.logger.info(f"阿里云短信发送响应: {resp}")

                # 检查响应是否成功（dysmsapi 的响应格式）
                if hasattr(resp, 'body'):
                    body = resp.body
                    # dysmsapi 使用 Code 字段判断成功与否，Code == "OK" 表示成功
                    code = None
                    message = None

                    # 如果 body 是字典类型
                    if isinstance(body, dict):
                        code = body.get('Code', body.get('code', ''))
                        message = body.get('Message', body.get('message', ''))
                    # 如果 body 是对象类型
                    elif hasattr(body, 'Code'):
                        code = body.Code
                        message = getattr(body, 'Message', getattr(body, 'message', ''))
                    elif hasattr(body, 'code'):
                        code = body.code
                        message = getattr(body, 'message', getattr(body, 'Message', ''))

                    # 如果 Code 不是 "OK"，表示发送失败
                    if code and code != "OK":
                        self.logger.error(f"阿里云短信API返回错误: Code={code}, Message={message}")
                        return False, f"短信发送失败: {message or code}"

                # 检查 HTTP 状态码
                if hasattr(resp, 'status_code') and resp.status_code != 200:
                    error_message = f"HTTP状态码: {resp.status_code}"
                    self.logger.error(f"阿里云短信API HTTP错误: {error_message}")
                    return False, f"短信发送失败: {error_message}"

                # 如果API调用成功，使用我们生成的验证码
                self.logger.info(f"阿里云短信发送成功，使用生成的验证码: {final_verification_code}")

            except Exception as e:
                self.logger.error(f"调用阿里云短信服务失败: {str(e)}", exc_info=True)
                # 处理异常信息
                error_msg = str(e)
                if hasattr(e, 'message'):
                    error_msg = e.message
                if hasattr(e, 'data') and isinstance(e.data, dict):
                    recommend = e.data.get("Recommend")
                    if recommend:
                        self.logger.error(f"诊断地址: {recommend}")
                return False, f"短信发送失败: {error_msg}"

            # 5. 将验证码存储到Redis（覆盖之前的验证码）
            # 注意：一个手机号对应一个验证码，第二次请求发送会覆盖掉前面缓存的
            code_key = self._get_verification_code_redis_key(normalized_phone_number)
            redis_client.setex(code_key, self.settings.verification_code_expire_seconds, final_verification_code)
            self.logger.info(
                f"验证码已存储到Redis: {code_key}, 验证码: {final_verification_code}, 有效期{self.settings.verification_code_expire_seconds}秒")

            # 6. 更新发送次数统计（5分钟窗口）
            if send_count:
                # 如果已存在，增加计数（Redis的incr操作会自动处理）
                redis_client.incr(send_count_key)
                # 确保过期时间重置为5分钟（防止计数过期）
                redis_client.expire(send_count_key, self.settings.send_count_window_seconds)
            else:
                # 如果不存在，创建新的计数，初始值为1，过期时间5分钟
                redis_client.setex(send_count_key, self.settings.send_count_window_seconds, 1)

            self.logger.info(f"验证码已发送到 {normalized_phone_number}（输入: {phone_number}），用途: {purpose}")
            return True, None

        except Exception as e:
            self.logger.error(f"发送短信验证码时发生错误: {str(e)}", exc_info=True)
            return False, f"发送失败: {str(e)}"

    def verify_code(self, phone_number: str, code: str) -> tuple[bool, Optional[str]]:
        """
        验证验证码

        Args:
            phone_number: 手机号
            code: 验证码

        Returns:
            (是否有效, 错误信息)
        """
        try:
            redis_client = RedisClientManager.get_client()
            # 允许调用方传入 +86/86/11位；统一按规范化手机号取 key
            normalized_phone_number = self.normalize_china_phone_number(phone_number)
            if not normalized_phone_number:
                return False, "1202"  # 按“验证码错误”处理不合法手机号输入

            code_key = self._get_verification_code_redis_key(normalized_phone_number)
            stored_code = redis_client.get(code_key)

            if not stored_code:
                return False, "1207"  # 错误编码1207：验证码失效

            if stored_code != code:
                return False, "1202"  # 错误编码1202：验证码错误

            # 验证成功后删除验证码（一次性使用）
            redis_client.delete(code_key)
            return True, None

        except Exception as e:
            self.logger.error(f"验证验证码时发生错误: {str(e)}", exc_info=True)
            return False, f"验证失败: {str(e)}"
