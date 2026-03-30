import re

from pydantic import AliasChoices, Field, field_validator

from shared_application_services import BaseDTO


def _to_camel(value: str) -> str:
    parts = value.split("_")
    return parts[0] + "".join(part.capitalize() for part in parts[1:])


def _is_valid_china_phone_username(value: str) -> bool:
    """校验是否为合法中国手机号格式（username：如 8613800138000、13800138000、+8613800138000）"""
    if not value or not value.strip():
        return False
    s = re.sub(r"[\s-]+", "", value.strip())
    return bool(re.fullmatch(r"(?:\+?86)?(1[3-9]\d{9})", s))


def _is_valid_username(value: str) -> bool:
    """校验用户名：4-30个字符，仅限字母、数字、下划线"""
    if not value or not value.strip():
        return False
    if len(value) < 4 or len(value) > 30:
        return False
    return bool(re.fullmatch(r"[A-Za-z0-9_]+", value))


class SendVerificationCodeRequest(BaseDTO):
    phoneNumber: str = Field(
        validation_alias=AliasChoices("phoneNumber"),
        serialization_alias="phoneNumber",
    )
    purpose: str = Field(
        validation_alias=AliasChoices("purpose"),
        serialization_alias="purpose",
    )


PASSWORD_MIN_LEN = 8
PASSWORD_MAX_LEN = 16


class SignUpRequest(BaseDTO):
    username: str = Field(
        validation_alias=AliasChoices("username"),
        serialization_alias="username",
        description="用户名：4-30个字符，仅限字母、数字、下划线",
    )
    phoneNumber: str = Field(
        validation_alias=AliasChoices("phoneNumber"),
        serialization_alias="phoneNumber",
        description="手机号，用于接收验证码",
    )
    password: str = Field(
        validation_alias=AliasChoices("password"),
        serialization_alias="password",
        description="密码：8-16位，字母、数字、特殊符号三选二，不允许中间有空格",
    )
    verificationCode: str = Field(
        validation_alias=AliasChoices("verificationCode"),
        serialization_alias="verificationCode",
        description="验证码：6位数字",
    )

    @field_validator("username")
    @classmethod
    def username_must_be_valid(cls, v: str) -> str:
        v = v.strip()
        if not _is_valid_username(v):
            if len(v) < 4:
                raise ValueError("用户名不能少于4个字符")
            if len(v) > 30:
                raise ValueError("用户名不可以超过30字符")
            if not re.fullmatch(r"[A-Za-z0-9_]+", v):
                raise ValueError("用户名只可以包含字母、数字和下划线")
        return v

    @field_validator("phoneNumber")
    @classmethod
    def phone_number_must_be_china_phone(cls, v: str) -> str:
        if not _is_valid_china_phone_username(v):
            raise ValueError("请使用正确的手机号")
        return v.strip()

    @field_validator("password")
    @classmethod
    def password_must_meet_requirements(cls, v: str) -> str:
        if len(v) < PASSWORD_MIN_LEN:
            raise ValueError("密码不能少于8个字符")
        if len(v) > PASSWORD_MAX_LEN:
            raise ValueError("密码不可以超过16字符")

        if " " in v:
            raise ValueError("密码不可以包含空格")

        has_letter = bool(re.search(r"[A-Za-z]", v))
        has_digit = bool(re.search(r"\d", v))
        has_special = bool(re.search(r"[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>\/?]", v))

        type_count = sum([has_letter, has_digit, has_special])
        if type_count < 2:
            raise ValueError("密码不可以使用纯数字或纯字母，必须包含字母、数字、特殊符号中的至少两种")

        return v

    @field_validator("verificationCode")
    @classmethod
    def verification_code_must_be_6_digits(cls, v: str) -> str:
        v = v.strip()
        if len(v) != 6:
            raise ValueError("验证码必须是6位数字")
        if not v.isdigit():
            raise ValueError("验证码必须是6位数字")
        return v


class LoginRequest(BaseDTO):
    username: str = Field(
        validation_alias=AliasChoices("username"),
        serialization_alias="username",
        min_length=1,
        max_length=64,
        description="用户名或手机号（支持使用用户名或手机号登录）",
    )
    password: str = Field(
        validation_alias=AliasChoices("password"),
        serialization_alias="password",
        min_length=1,
        max_length=PASSWORD_MAX_LEN,
        description="密码不能为空",
    )

    @field_validator("username")
    @classmethod
    def username_must_not_be_empty(cls, v: str) -> str:
        """只验证非空，不限制格式（允许手机号或用户名）"""
        if not v or not v.strip():
            raise ValueError("用户名或手机号不能为空")
        return v.strip()
