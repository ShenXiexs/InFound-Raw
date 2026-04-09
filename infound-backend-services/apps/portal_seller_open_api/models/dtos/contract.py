from pydantic import AliasChoices, Field, field_validator

from shared_application_services import BaseDTO


class ContractRuleListItem(BaseDTO):
    ruleCode: str = Field(
        validation_alias=AliasChoices("ruleCode"),
        serialization_alias="ruleCode",
    )
    name: str = Field(validation_alias=AliasChoices("name"), serialization_alias="name")
    description: str | None = Field(
        default=None,
        validation_alias=AliasChoices("description"),
        serialization_alias="description",
    )
    remark: str | None = Field(
        default=None,
        validation_alias=AliasChoices("remark"),
        serialization_alias="remark",
    )
    message: str | None = Field(
        default=None,
        validation_alias=AliasChoices("message"),
        serialization_alias="message",
    )
    isConfigured: bool = Field(
        validation_alias=AliasChoices("isConfigured"),
        serialization_alias="isConfigured",
    )
    isActive: bool = Field(
        validation_alias=AliasChoices("isActive"),
        serialization_alias="isActive",
    )
    canEnable: bool = Field(
        validation_alias=AliasChoices("canEnable"),
        serialization_alias="canEnable",
    )


class ContractRuleDetailData(BaseDTO):
    ruleCode: str = Field(
        validation_alias=AliasChoices("ruleCode"),
        serialization_alias="ruleCode",
    )
    name: str = Field(validation_alias=AliasChoices("name"), serialization_alias="name")
    description: str | None = Field(
        default=None,
        validation_alias=AliasChoices("description"),
        serialization_alias="description",
    )
    remark: str | None = Field(
        default=None,
        validation_alias=AliasChoices("remark"),
        serialization_alias="remark",
    )
    executionEvent: str = Field(
        validation_alias=AliasChoices("executionEvent"),
        serialization_alias="executionEvent",
    )
    message: str = Field(validation_alias=AliasChoices("message"), serialization_alias="message")
    isActive: bool = Field(
        validation_alias=AliasChoices("isActive"),
        serialization_alias="isActive",
    )


class SaveContractRuleRequest(BaseDTO):
    shopId: str = Field(
        min_length=1,
        max_length=36,
        validation_alias=AliasChoices("shopId"),
        serialization_alias="shopId",
        description="店铺 ID",
    )

    @field_validator("shopId")
    @classmethod
    def _strip_shop_id(cls, value: str) -> str:
        s = value.strip()
        if not s:
            raise ValueError("shopId 不能为空")
        return s
    message: str | None = Field(
        default=None,
        max_length=2000,
        validation_alias=AliasChoices("message"),
        serialization_alias="message",
        description="消息模板（TikTok 侧建议 2000 字内）",
    )
    isActive: bool = Field(
        default=False,
        validation_alias=AliasChoices("isActive"),
        serialization_alias="isActive",
        description="是否启用",
    )

    @field_validator("message")
    @classmethod
    def _strip_message(cls, value: str | None) -> str | None:
        if value is None:
            return None
        s = value.strip()
        return s or None


class ContractReminderRecordListRequest(BaseDTO):
    shopId: str = Field(
        min_length=1,
        max_length=36,
        validation_alias=AliasChoices("shopId"),
        serialization_alias="shopId",
        description="店铺 ID",
    )
    ruleCode: str | None = Field(
        default=None,
        validation_alias=AliasChoices("ruleCode"),
        serialization_alias="ruleCode",
        description="规则编码过滤",
    )
