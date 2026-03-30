import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, Header
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from apps.portal_seller_open_api.app_constants import HEADER_DEVICE_ID, HEADER_TOKEN, HEADER_DEVICE_TYPE
from apps.portal_seller_open_api.core.config import Settings
from apps.portal_seller_open_api.core.deps import get_sms_service, get_db_session, get_token_manager, get_settings
from apps.portal_seller_open_api.exceptions import raise_sms_error, ErrorCodes, raise_error, raise_account_error, \
    raise_user_error
from apps.portal_seller_open_api.models.dtos.account import (
    SendVerificationCodeRequest,
    SignUpRequest,
    LoginRequest,
)
from apps.portal_seller_open_api.services.identity_user_service import get_password_hash, verify_password, \
    setup_user_stomp_queue
from apps.portal_seller_open_api.services.sms_service import SmsService
from core_base import get_logger, APIResponse, success_response
from core_web import get_request_domain
from shared_domain.models.infound import IfIdentityUsers
from shared_seller_application_services.current_user_info import CurrentUserInfo
from shared_seller_application_services.token_manager import TokenManager

router = APIRouter(tags=["账号"])
logger = get_logger()


def _username_for_db(normalized_phone: str) -> str:
    """存库用：地区码 86 + 11 位手机号，如 8615228749650（由 +8615228749650 得到）"""
    if not normalized_phone or not normalized_phone.startswith("+"):
        return normalized_phone or ""
    return normalized_phone[1:]  # "+8615228749650" -> "8615228749650"


@router.post(
    "/account/send-verification-code/sms",
    response_model=APIResponse[dict],
    response_model_by_alias=True,
)
async def send_verification_code_sms(
        request: SendVerificationCodeRequest,
        service: SmsService = Depends(get_sms_service),
) -> APIResponse[dict]:
    """发送短信验证码"""
    try:
        success, error_msg = service.send_sms_verification_code(request.phoneNumber, request.purpose)

        if not success:
            if error_msg == "1206":
                raise raise_sms_error("5 分钟内发送次数超过限制", ErrorCodes.SMS_SEND_LIMIT_EXCEEDED)
            raise raise_sms_error(error_msg or "发送失败", ErrorCodes.BAD_REQUEST)

        return success_response(data={"message": "验证码已发送"})

    except Exception as e:
        logger.error(f"发送短信验证码失败: {str(e)}", exc_info=True)
        raise raise_error("发送失败", ErrorCodes.INTERNAL_ERROR, status_code=500)


@router.post(
    "/account/sign-up",
    response_model=APIResponse[dict],
    response_model_by_alias=True,
)
async def sign_up(
        sign_up_request: SignUpRequest,
        request: Request,
        response: Response,
        xunda_device_id: Annotated[str, Header(alias=HEADER_DEVICE_ID)],
        xunda_device_type: Annotated[str, Header(alias=HEADER_DEVICE_TYPE)],
        db: Annotated[AsyncSession, Depends(get_db_session)],
        sms_service: SmsService = Depends(get_sms_service),
        token_manager: TokenManager = Depends(get_token_manager),
        settings: Settings = Depends(get_settings),
) -> APIResponse[dict]:
    """注册账号"""
    try:
        # 规范化手机号（用于验证码验证）
        normalized_phone = SmsService.normalize_china_phone_number(sign_up_request.phoneNumber)
        if not normalized_phone:
            raise raise_account_error("请使用正确的手机号", ErrorCodes.INVALID_PHONE_NUMBER)
        phone_number = normalized_phone

        # 使用手机号验证验证码
        is_valid, error_code = sms_service.verify_code(phone_number, sign_up_request.verificationCode)
        if not is_valid:
            if error_code == "1207":
                raise raise_sms_error("验证码失效", ErrorCodes.VERIFICATION_CODE_EXPIRED)
            elif error_code == "1202":
                raise raise_sms_error("验证码错误", ErrorCodes.VERIFICATION_CODE_INVALID)
            raise raise_sms_error(error_code or "验证失败", ErrorCodes.BAD_REQUEST)

        # 使用用户名作为存储的用户名
        stored_username = sign_up_request.username

        # 检查用户名是否已存在
        sql = select(IfIdentityUsers).where(
            and_(
                IfIdentityUsers.user_name == stored_username,
                (IfIdentityUsers.deleted.is_(None)) | (IfIdentityUsers.deleted == 0)
            )
        )
        existing_user = (await db.execute(sql)).scalar_one_or_none()
        if existing_user:
            raise raise_account_error("该用户名已被使用", ErrorCodes.USER_ALREADY_EXISTS)

        stored_phone_number = _username_for_db(phone_number)  # "+8615228749650" -> "8615228749650"

        # 检查手机号是否已被注册
        phone_check_sql = select(IfIdentityUsers).where(
            and_(
                IfIdentityUsers.phone_number == stored_phone_number,
                (IfIdentityUsers.deleted.is_(None)) | (IfIdentityUsers.deleted == 0)
            )
        )
        existing_phone_user = (await db.execute(phone_check_sql)).scalar_one_or_none()
        if existing_phone_user:
            raise raise_account_error("该手机号已被注册", ErrorCodes.PHONE_ALREADY_REGISTERED)

        hashed_password = get_password_hash(sign_up_request.password)

        now = datetime.now(timezone.utc)
        user_id = str(uuid.uuid4())

        if not await setup_user_stomp_queue(user_id, settings.rabbitmq_web_stomp):
            raise raise_error("注册失败", ErrorCodes.INTERNAL_ERROR, status_code=500)

        new_user = IfIdentityUsers(
            id=user_id,
            user_name=stored_username,
            password_hash=hashed_password,
            from_platform="TikTok",
            from_device_id=xunda_device_id,
            from_site=get_request_domain(request),  # 注册来源站点：商户端
            phone_number=stored_phone_number,
            phone_number_confirmed=1,
            email_confirmed=0,
            two_factor_enabled=0,
            lockout_enabled=0,
            access_failed_count=0,
            creator_id=user_id,  # 创建人就是自己
            creation_time=now,
            last_modifier_id=user_id,
            last_modification_time=now,
            deleted=0
        )

        db.add(new_user)
        try:
            await db.commit()
            await db.refresh(new_user)
        except Exception:
            # DB 提交失败：尽力清理已创建的 MQ 通道，避免孤儿队列堆积
            await db.rollback()
            # await UserChannelService.delete_user_channel(user_id)
            raise

        jti = str(uuid.uuid4())

        current_user_info = CurrentUserInfo(
            jti=jti,
            iat=datetime.now(timezone.utc),
            user_id=new_user.id,
            username=new_user.user_name,
            phone_number=new_user.phone_number,
            device_id=xunda_device_id,
            device_type=xunda_device_type,
        )

        access_token = token_manager.create_access_token(current_user_info)

        # 登录态 Cookie
        response.set_cookie(
            key="xunda_token_name",
            value=HEADER_TOKEN,
            max_age=30 * 24 * 60 * 60,
            httponly=False,
            samesite="lax",
        )

        response.set_cookie(
            key="xunda_token_value",
            value=access_token,
            max_age=30 * 24 * 60 * 60,  # 30天
            httponly=False,  # 不要HttpOnly
            samesite="lax",
        )

        return success_response(data={"success": True})

    except HTTPException as http_ex:
        raise http_ex
    except Exception as e:
        logger.error(f"注册失败: {str(e)}", exc_info=True)
        await db.rollback()
        raise raise_error("注册失败", ErrorCodes.INTERNAL_ERROR, status_code=500)


@router.post(
    "/account/login",
    response_model=APIResponse[dict],
    response_model_by_alias=True,
)
async def login(
        login_request: LoginRequest,
        response: Response,
        xunda_device_id: Annotated[str, Header(alias=HEADER_DEVICE_ID)],
        xunda_device_type: Annotated[str, Header(alias=HEADER_DEVICE_TYPE)],
        db: Annotated[AsyncSession, Depends(get_db_session)],
        token_manager: TokenManager = Depends(get_token_manager),
) -> APIResponse[dict]:
    """登录（商户端）支持手机号或用户名登录"""
    try:
        # 判断输入是手机号还是用户名
        normalized_phone = SmsService.normalize_china_phone_number(login_request.username)
        is_phone = normalized_phone is not None

        # 构建查询条件：支持通过用户名或手机号登录
        conditions = [
            (IfIdentityUsers.deleted.is_(None)) | (IfIdentityUsers.deleted == 0)
        ]

        if is_phone:
            # 如果是手机号，规范化后转换为数据库格式（86开头）查询 phone_number 字段
            phone_for_query = _username_for_db(normalized_phone)  # "+8615228749650" -> "8615228749650"
            conditions.append(IfIdentityUsers.phone_number == phone_for_query)
        else:
            # 如果是用户名，直接查询 user_name 字段
            conditions.append(IfIdentityUsers.user_name == login_request.username)

        sql = select(IfIdentityUsers).where(and_(*conditions))
        user: IfIdentityUsers = (await db.execute(sql)).scalar_one_or_none()
        if not user:
            raise raise_user_error("查无此用户", ErrorCodes.USER_NOT_FOUND)

        if not verify_password(login_request.password, user.password_hash):
            raise raise_account_error("密码错误", ErrorCodes.INVALID_PASSWORD)

        jti = str(uuid.uuid4())

        current_user_info = CurrentUserInfo(
            jti=jti,
            iat=datetime.now(timezone.utc),
            user_id=user.id,
            username=user.user_name,
            phone_number=user.phone_number,
            device_id=xunda_device_id,
            device_type=xunda_device_type,
        )

        access_token = token_manager.create_access_token(current_user_info)

        response.set_cookie(
            key="xunda_token_name",
            value=HEADER_TOKEN,
            max_age=30 * 24 * 60 * 60,
            httponly=False,
            samesite="lax",
        )

        response.set_cookie(
            key="xunda_token_value",
            value=access_token,
            max_age=30 * 24 * 60 * 60,  # 30天
            httponly=False,  # 不要HttpOnly
            samesite="lax",
        )

        return success_response(data={"success": True})

    except HTTPException as http_ex:
        raise http_ex
    except Exception as e:
        logger.error(f"登录失败: {str(e)}", exc_info=True)
        raise
