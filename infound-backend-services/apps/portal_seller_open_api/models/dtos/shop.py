from datetime import datetime

from pydantic import AliasChoices, Field

from shared_application_services import BaseDTO


class AddShopRequest(BaseDTO):
    name: str = Field(
        validation_alias=AliasChoices("name"),
        serialization_alias="name",
        description="店铺名称",
        min_length=1,
        max_length=255,
    )
    entryId: int = Field(
        validation_alias=AliasChoices("entryId"),
        serialization_alias="entryId",
        description="平台配置表 seller_tk_shop_platform_settings 的主键 Id",
        ge=1,
    )
    remark: str = Field(
        validation_alias=AliasChoices("remark"),
        serialization_alias="remark",
        description="店铺备注",
        min_length=0,
        max_length=512,
    )


class ShopEntry(BaseDTO):
    entryId: int = Field(
        validation_alias=AliasChoices("entryId"),
        serialization_alias="entryId",
        description="平台配置表 seller_tk_shop_platform_settings 主键 id",
        ge=1,
    )
    regionCode: str = Field(
        validation_alias=AliasChoices("regionCode"),
        serialization_alias="regionCode",
        description="地区编号（符合 ISO 标准）",
        min_length=1,
        max_length=8,
    )
    regionName: str = Field(
        validation_alias=AliasChoices("regionName"),
        serialization_alias="regionName",
        description="地区名称",
        min_length=1,
        max_length=64,
    )
    shopType: str = Field(
        validation_alias=AliasChoices("shopType"),
        serialization_alias="shopType",
        description="店铺类型：LOCAL-本土店，CROSS_BORDER-跨境店",
        min_length=1,
        max_length=16,
    )
    loginUrl: str = Field(
        validation_alias=AliasChoices("loginUrl"),
        serialization_alias="loginUrl",
        description="登录入口 URL",
        min_length=1,
        max_length=255,
    )


class ShopListItem(BaseDTO):
    id: str = Field(
        validation_alias=AliasChoices("id"),
        serialization_alias="id",
        description="店铺Id",
        min_length=1,
        max_length=36,
    )
    name: str = Field(
        validation_alias=AliasChoices("name"),
        serialization_alias="name",
        description="店铺名称",
        min_length=1,
        max_length=255,
    )
    regionCode: str = Field(
        validation_alias=AliasChoices("regionCode"),
        serialization_alias="regionCode",
        description="地区编码",
        min_length=1,
        max_length=32,
    )
    regionName: str = Field(
        validation_alias=AliasChoices("regionName"),
        serialization_alias="regionName",
        description="地区名称",
        min_length=1,
        max_length=64,
    )
    shopType: str = Field(
        validation_alias=AliasChoices("shopType"),
        serialization_alias="shopType",
        description="店铺类型",
        min_length=1,
        max_length=32,
    )
    loginUrl: str = Field(
        validation_alias=AliasChoices("loginUrl"),
        serialization_alias="loginUrl",
        description="登录入口",
        min_length=1,
        max_length=255,
    )
    remark: str = Field(
        validation_alias=AliasChoices("remark"),
        serialization_alias="remark",
        description="店铺备注",
        max_length=512,
        default="",
    )
    shopLastOpen: datetime | None = Field(
        validation_alias=AliasChoices("shopLastOpen"),
        serialization_alias="shopLastOpen",
        description="最近一次打开时间（UTC）",
        default=None,
    )


class OpenShopRequest(BaseDTO):
    id: str = Field(
        validation_alias=AliasChoices("id", "shopId"),
        serialization_alias="id",
        description="店铺Id",
        min_length=1,
        max_length=36,
    )


class DeleteShopRequest(BaseDTO):
    id: str = Field(
        validation_alias=AliasChoices("id", "shopId"),
        serialization_alias="id",
        description="店铺Id",
        min_length=1,
        max_length=36,
    )


class UpdateShopRequest(BaseDTO):
    id: str = Field(
        validation_alias=AliasChoices("id", "shopId"),
        serialization_alias="id",
        description="店铺Id",
        min_length=1,
        max_length=36,
    )
    name: str | None = Field(
        validation_alias=AliasChoices("name"),
        serialization_alias="name",
        description="店铺名称",
        min_length=1,
        max_length=255,
        default=None,
    )
    entryId: int | None = Field(
        validation_alias=AliasChoices("entryId"),
        serialization_alias="entryId",
        description="平台配置表 seller_tk_shop_platform_settings 的主键 Id",
        ge=1,
        default=None,
    )
    remark: str = Field(
        validation_alias=AliasChoices("remark"),
        serialization_alias="remark",
        description="店铺备注",
        max_length=512,
    )
