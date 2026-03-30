from datetime import datetime

from pydantic import AliasChoices, Field, field_validator, model_validator

from shared_application_services import BaseDTO


class CreatorFilterDTO(BaseDTO):
    keyword: str | None = Field(default=None, validation_alias=AliasChoices("keyword"), serialization_alias="keyword")
    productCategories: list[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices("productCategories"),
        serialization_alias="productCategories",
    )
    avgCommissionRate: int | None = Field(
        default=None,
        ge=0,
        le=100,
        validation_alias=AliasChoices("avgCommissionRate"),
        serialization_alias="avgCommissionRate",
    )
    contentTypes: int | None = Field(default=None, validation_alias=AliasChoices("contentTypes"), serialization_alias="contentTypes")
    creatorAgency: int | None = Field(default=None, validation_alias=AliasChoices("creatorAgency"), serialization_alias="creatorAgency")
    fastGrowing: bool = Field(default=False, validation_alias=AliasChoices("fastGrowing"), serialization_alias="fastGrowing")
    notInvitedInPast90Days: bool = Field(
        default=False,
        validation_alias=AliasChoices("notInvitedInPast90Days"),
        serialization_alias="notInvitedInPast90Days",
    )
    fansAgeRange: list[str] = Field(default_factory=list, validation_alias=AliasChoices("fansAgeRange"), serialization_alias="fansAgeRange")
    fansGender: int | None = Field(default=None, validation_alias=AliasChoices("fansGender"), serialization_alias="fansGender")
    fansCountRange: dict | None = Field(default=None, validation_alias=AliasChoices("fansCountRange"), serialization_alias="fansCountRange")
    gmvRange: list[str] = Field(default_factory=list, validation_alias=AliasChoices("gmvRange"), serialization_alias="gmvRange")
    salesCountRange: list[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices("salesCountRange"),
        serialization_alias="salesCountRange",
    )
    minAvgVideoViews: int | None = Field(
        default=None,
        ge=0,
        validation_alias=AliasChoices("minAvgVideoViews"),
        serialization_alias="minAvgVideoViews",
    )
    minAvgLiveViews: int | None = Field(
        default=None,
        ge=0,
        validation_alias=AliasChoices("minAvgLiveViews"),
        serialization_alias="minAvgLiveViews",
    )
    minEngagementRate: int | None = Field(
        default=None,
        ge=0,
        le=100,
        validation_alias=AliasChoices("minEngagementRate"),
        serialization_alias="minEngagementRate",
    )
    creatorEstimatedPublishRate: int | None = Field(
        default=None,
        validation_alias=AliasChoices("creatorEstimatedPublishRate"),
        serialization_alias="creatorEstimatedPublishRate",
    )
    coBranding: list[str] = Field(default_factory=list, validation_alias=AliasChoices("coBranding"), serialization_alias="coBranding")
    sortBy: int = Field(validation_alias=AliasChoices("sortBy"), serialization_alias="sortBy")

    @field_validator("sortBy")
    @classmethod
    def _validate_sort_by(cls, value: int) -> int:
        # 0-相关性, 1-GMV, 2-成交件数, 3-粉丝数, 4-平均视频播放量, 5-互动率
        if value not in {0, 1, 2, 3, 4, 5}:
            raise ValueError("sortBy 仅支持 0~5")
        return value


class CreateOutreachTaskRequest(BaseDTO):
    shopId: str = Field(
        min_length=1,
        max_length=36,
        validation_alias=AliasChoices("shopId"),
        serialization_alias="shopId",
    )
    taskName: str = Field(
        min_length=1,
        max_length=64,
        validation_alias=AliasChoices("taskName"),
        serialization_alias="taskName",
    )
    startTime: datetime | None = Field(
        default=None,
        validation_alias=AliasChoices("startTime"),
        serialization_alias="startTime",
        description="计划启动时间：不传=立即建联；传入且与当前分钟相同=立即建联；传入且晚于当前分钟=Redis 任务中心排队；早于当前分钟=无效",
    )
    creatorFilter: CreatorFilterDTO = Field(
        validation_alias=AliasChoices("creatorFilter"),
        serialization_alias="creatorFilter",
    )
    duplicateCheckType: int | None = Field(
        default=None,
        validation_alias=AliasChoices("duplicateCheckType"),
        serialization_alias="duplicateCheckType",
        description="查重类型：1=活动，2=商品，3=品牌；不传表示店铺全局查重",
    )
    duplicateCheckCode: str | None = Field(
        default=None,
        max_length=64,
        validation_alias=AliasChoices("duplicateCheckCode"),
        serialization_alias="duplicateCheckCode",
        description="查重码；为空时表示店铺全局查重",
    )
    plannedCount: int = Field(
        ge=1,
        validation_alias=AliasChoices("plannedCount"),
        serialization_alias="plannedCount",
    )
    outreachMode: str = Field(
        validation_alias=AliasChoices("outreachMode"),
        serialization_alias="outreachMode",
    )
    firstMessage: str = Field(
        min_length=1,
        max_length=2000,
        validation_alias=AliasChoices("firstMessage"),
        serialization_alias="firstMessage",
    )
    replyMessage: str | None = Field(
        default=None,
        max_length=2000,
        validation_alias=AliasChoices("replyMessage"),
        serialization_alias="replyMessage",
    )
    attachProducts: bool = Field(
        default=False,
        validation_alias=AliasChoices("attachProducts"),
        serialization_alias="attachProducts",
    )
    productIds: list[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices("productIds"),
        serialization_alias="productIds",
    )

    @field_validator("taskName", "firstMessage", mode="before")
    @classmethod
    def _trim_text(cls, value: str) -> str:
        if value is None:
            return ""
        return str(value).strip()

    @field_validator("replyMessage", mode="before")
    @classmethod
    def _trim_reply_message(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @field_validator("duplicateCheckCode", mode="before")
    @classmethod
    def _trim_duplicate_check_code(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @field_validator("outreachMode", mode="before")
    @classmethod
    def _normalize_mode(cls, value: str) -> str:
        return str(value or "").strip().upper()

    @field_validator("productIds", mode="before")
    @classmethod
    def _normalize_product_ids(cls, value) -> list[str]:
        if value is None:
            return []
        items = value if isinstance(value, list) else str(value).split(",")
        return [str(item).strip() for item in items if str(item).strip()]

    @model_validator(mode="after")
    def _validate_rules(self) -> "CreateOutreachTaskRequest":
        valid_modes = {"ALL", "NEW_ONLY", "NEW_AND_UNREPLIED"}
        if self.outreachMode not in valid_modes:
            raise ValueError("outreachMode 仅支持 ALL/NEW_ONLY/NEW_AND_UNREPLIED")

        if self.duplicateCheckType not in {None, 1, 2, 3}:
            raise ValueError("duplicateCheckType 仅支持 1/2/3")

        if self.outreachMode == "ALL" and not self.replyMessage:
            raise ValueError("outreachMode=ALL 时 replyMessage 必填")

        if self.attachProducts:
            if not self.productIds:
                raise ValueError("attachProducts=true 时 productIds 必填")
            if len(self.productIds) > 4:
                raise ValueError("productIds 最多支持 4 个")
        elif self.productIds:
            self.productIds = []

        return self


class CreateOutreachTaskData(BaseDTO):
    taskId: str = Field(validation_alias=AliasChoices("taskId"), serialization_alias="taskId")
    status: str = Field(validation_alias=AliasChoices("status"), serialization_alias="status")
    savedStartTime: datetime | None = Field(
        default=None,
        validation_alias=AliasChoices("savedStartTime"),
        serialization_alias="savedStartTime",
    )


class OutreachTaskDetailResponse(BaseDTO):
    taskId: str = Field(validation_alias=AliasChoices("taskId"), serialization_alias="taskId")
    shopId: str = Field(validation_alias=AliasChoices("shopId"), serialization_alias="shopId")
    taskName: str = Field(validation_alias=AliasChoices("taskName"), serialization_alias="taskName")
    startTime: datetime | None = Field(
        default=None,
        validation_alias=AliasChoices("startTime"),
        serialization_alias="startTime",
    )
    creatorFilter: CreatorFilterDTO = Field(
        validation_alias=AliasChoices("creatorFilter"),
        serialization_alias="creatorFilter",
    )
    duplicateCheckType: int | None = Field(
        default=None,
        validation_alias=AliasChoices("duplicateCheckType"),
        serialization_alias="duplicateCheckType",
    )
    duplicateCheckCode: str | None = Field(
        default=None,
        validation_alias=AliasChoices("duplicateCheckCode"),
        serialization_alias="duplicateCheckCode",
    )
    plannedCount: int = Field(validation_alias=AliasChoices("plannedCount"), serialization_alias="plannedCount")
    outreachMode: str = Field(validation_alias=AliasChoices("outreachMode"), serialization_alias="outreachMode")
    firstMessage: str = Field(validation_alias=AliasChoices("firstMessage"), serialization_alias="firstMessage")
    replyMessage: str | None = Field(
        default=None,
        validation_alias=AliasChoices("replyMessage"),
        serialization_alias="replyMessage",
    )
    attachProducts: bool = Field(validation_alias=AliasChoices("attachProducts"), serialization_alias="attachProducts")
    productIds: list[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices("productIds"),
        serialization_alias="productIds",
    )
    status: str = Field(validation_alias=AliasChoices("status"), serialization_alias="status")
    lastModificationTime: datetime = Field(
        validation_alias=AliasChoices("lastModificationTime"),
        serialization_alias="lastModificationTime",
    )


class UpdateOutreachTaskRequest(CreateOutreachTaskRequest):
    lastModificationTime: datetime = Field(
        validation_alias=AliasChoices("lastModificationTime"),
        serialization_alias="lastModificationTime",
    )


class UpdateOutreachTaskData(BaseDTO):
    taskId: str = Field(validation_alias=AliasChoices("taskId"), serialization_alias="taskId")
    lastModificationTime: datetime = Field(
        validation_alias=AliasChoices("lastModificationTime"),
        serialization_alias="lastModificationTime",
    )


class StartOutreachTaskRequest(BaseDTO):
    shopId: str = Field(
        min_length=1,
        max_length=36,
        validation_alias=AliasChoices("shopId"),
        serialization_alias="shopId",
    )
    lastModificationTime: datetime = Field(
        validation_alias=AliasChoices("lastModificationTime"),
        serialization_alias="lastModificationTime",
    )


class StartOutreachTaskData(BaseDTO):
    taskId: str = Field(validation_alias=AliasChoices("taskId"), serialization_alias="taskId")
    status: str = Field(validation_alias=AliasChoices("status"), serialization_alias="status")
    startTime: datetime | None = Field(
        default=None,
        validation_alias=AliasChoices("startTime"),
        serialization_alias="startTime",
    )
    lastModificationTime: datetime = Field(
        validation_alias=AliasChoices("lastModificationTime"),
        serialization_alias="lastModificationTime",
    )


class EndOutreachTaskRequest(BaseDTO):
    shopId: str = Field(
        min_length=1,
        max_length=36,
        validation_alias=AliasChoices("shopId"),
        serialization_alias="shopId",
    )
    lastModificationTime: datetime = Field(
        validation_alias=AliasChoices("lastModificationTime"),
        serialization_alias="lastModificationTime",
    )


class EndOutreachTaskData(BaseDTO):
    taskId: str = Field(validation_alias=AliasChoices("taskId"), serialization_alias="taskId")
    status: str = Field(validation_alias=AliasChoices("status"), serialization_alias="status")
    endTime: datetime = Field(validation_alias=AliasChoices("endTime"), serialization_alias="endTime")
    lastModificationTime: datetime = Field(
        validation_alias=AliasChoices("lastModificationTime"),
        serialization_alias="lastModificationTime",
    )


class OutreachTaskListRequest(BaseDTO):
    shopId: str = Field(
        min_length=1,
        max_length=36,
        validation_alias=AliasChoices("shopId"),
        serialization_alias="shopId",
    )
    keyword: str | None = Field(
        default=None,
        validation_alias=AliasChoices("keyword"),
        serialization_alias="keyword",
    )
    status: str | None = Field(
        default=None,
        validation_alias=AliasChoices("status"),
        serialization_alias="status",
    )


class OutreachTaskListItem(BaseDTO):
    taskId: str = Field(validation_alias=AliasChoices("taskId"), serialization_alias="taskId")
    taskName: str = Field(validation_alias=AliasChoices("taskName"), serialization_alias="taskName")
    startTime: datetime | None = Field(
        default=None,
        validation_alias=AliasChoices("startTime"),
        serialization_alias="startTime",
    )
    plannedCount: int = Field(validation_alias=AliasChoices("plannedCount"), serialization_alias="plannedCount")
    realCount: int = Field(validation_alias=AliasChoices("realCount"), serialization_alias="realCount")
    newCount: int = Field(validation_alias=AliasChoices("newCount"), serialization_alias="newCount")
    spendTime: int = Field(validation_alias=AliasChoices("spendTime"), serialization_alias="spendTime")
    status: str = Field(validation_alias=AliasChoices("status"), serialization_alias="status")
    lastModificationTime: datetime = Field(
        validation_alias=AliasChoices("lastModificationTime"),
        serialization_alias="lastModificationTime",
    )


class OutreachTaskListData(BaseDTO):
    total: int = Field(validation_alias=AliasChoices("total"), serialization_alias="total")
    page: int = Field(validation_alias=AliasChoices("page"), serialization_alias="page")
    pageSize: int = Field(validation_alias=AliasChoices("pageSize"), serialization_alias="pageSize")
    items: list[OutreachTaskListItem] = Field(
        default_factory=list,
        validation_alias=AliasChoices("list"),
        serialization_alias="list",
    )
