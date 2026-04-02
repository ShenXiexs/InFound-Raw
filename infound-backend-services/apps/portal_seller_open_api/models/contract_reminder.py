from __future__ import annotations

from datetime import datetime

from pydantic import AliasChoices, Field

from shared_application_services import BaseDTO


class ContractReminderRuleConfigItem(BaseDTO):
    ruleId: int = Field(validation_alias=AliasChoices("ruleId"), serialization_alias="ruleId")
    ruleCode: str = Field(validation_alias=AliasChoices("ruleCode"), serialization_alias="ruleCode")
    ruleName: str = Field(validation_alias=AliasChoices("ruleName"), serialization_alias="ruleName")
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
    defaultMessage: str | None = Field(
        default=None,
        validation_alias=AliasChoices("defaultMessage"),
        serialization_alias="defaultMessage",
    )
    messageTemplate: str | None = Field(
        default=None,
        validation_alias=AliasChoices("messageTemplate"),
        serialization_alias="messageTemplate",
    )
    isActive: bool = Field(validation_alias=AliasChoices("isActive"), serialization_alias="isActive")
    hasOverride: bool = Field(
        validation_alias=AliasChoices("hasOverride"),
        serialization_alias="hasOverride",
    )
    lastModificationTime: datetime | None = Field(
        default=None,
        validation_alias=AliasChoices("lastModificationTime"),
        serialization_alias="lastModificationTime",
    )


class ContractReminderRuleConfigUpsertItem(BaseDTO):
    ruleCode: str = Field(validation_alias=AliasChoices("ruleCode"), serialization_alias="ruleCode")
    isActive: bool = Field(validation_alias=AliasChoices("isActive"), serialization_alias="isActive")
    messageTemplate: str | None = Field(
        default=None,
        validation_alias=AliasChoices("messageTemplate"),
        serialization_alias="messageTemplate",
    )


class ContractReminderRuleConfigUpdateRequest(BaseDTO):
    shopId: str = Field(validation_alias=AliasChoices("shopId"), serialization_alias="shopId")
    items: list[ContractReminderRuleConfigUpsertItem] = Field(
        default_factory=list,
        validation_alias=AliasChoices("items"),
        serialization_alias="items",
    )


class ContractReminderRuleConfigListData(BaseDTO):
    shopId: str = Field(validation_alias=AliasChoices("shopId"), serialization_alias="shopId")
    items: list[ContractReminderRuleConfigItem] = Field(
        default_factory=list,
        validation_alias=AliasChoices("items"),
        serialization_alias="items",
    )


class ContractReminderMonitorItem(BaseDTO):
    id: str = Field(validation_alias=AliasChoices("id"), serialization_alias="id")
    platformProductId: str = Field(
        validation_alias=AliasChoices("platformProductId"),
        serialization_alias="platformProductId",
    )
    platformCreatorId: str = Field(
        validation_alias=AliasChoices("platformCreatorId"),
        serialization_alias="platformCreatorId",
    )
    sampleRequestId: str | None = Field(
        default=None,
        validation_alias=AliasChoices("sampleRequestId"),
        serialization_alias="sampleRequestId",
    )
    creatorName: str | None = Field(
        default=None,
        validation_alias=AliasChoices("creatorName"),
        serialization_alias="creatorName",
    )
    currentStatus: str = Field(
        validation_alias=AliasChoices("currentStatus"),
        serialization_alias="currentStatus",
    )
    previousStatus: str | None = Field(
        default=None,
        validation_alias=AliasChoices("previousStatus"),
        serialization_alias="previousStatus",
    )
    statusEnteredAt: datetime = Field(
        validation_alias=AliasChoices("statusEnteredAt"),
        serialization_alias="statusEnteredAt",
    )
    lastCrawledAt: datetime = Field(
        validation_alias=AliasChoices("lastCrawledAt"),
        serialization_alias="lastCrawledAt",
    )
    expiredInMs: int | None = Field(
        default=None,
        validation_alias=AliasChoices("expiredInMs"),
        serialization_alias="expiredInMs",
    )
    expiredInText: str | None = Field(
        default=None,
        validation_alias=AliasChoices("expiredInText"),
        serialization_alias="expiredInText",
    )
    cycleToken: str = Field(validation_alias=AliasChoices("cycleToken"), serialization_alias="cycleToken")
    lastModificationTime: datetime = Field(
        validation_alias=AliasChoices("lastModificationTime"),
        serialization_alias="lastModificationTime",
    )


class ContractReminderMonitorListData(BaseDTO):
    total: int = Field(validation_alias=AliasChoices("total"), serialization_alias="total")
    page: int = Field(validation_alias=AliasChoices("page"), serialization_alias="page")
    pageSize: int = Field(validation_alias=AliasChoices("pageSize"), serialization_alias="pageSize")
    items: list[ContractReminderMonitorItem] = Field(
        default_factory=list,
        validation_alias=AliasChoices("items"),
        serialization_alias="items",
    )


class ContractReminderLogItem(BaseDTO):
    id: int = Field(validation_alias=AliasChoices("id"), serialization_alias="id")
    ruleCode: str = Field(validation_alias=AliasChoices("ruleCode"), serialization_alias="ruleCode")
    platformProductId: str | None = Field(
        default=None,
        validation_alias=AliasChoices("platformProductId"),
        serialization_alias="platformProductId",
    )
    platformCreatorId: str = Field(
        validation_alias=AliasChoices("platformCreatorId"),
        serialization_alias="platformCreatorId",
    )
    sampleRequestId: str | None = Field(
        default=None,
        validation_alias=AliasChoices("sampleRequestId"),
        serialization_alias="sampleRequestId",
    )
    currentStatus: str | None = Field(
        default=None,
        validation_alias=AliasChoices("currentStatus"),
        serialization_alias="currentStatus",
    )
    cycleToken: str | None = Field(
        default=None,
        validation_alias=AliasChoices("cycleToken"),
        serialization_alias="cycleToken",
    )
    taskPlanId: str | None = Field(
        default=None,
        validation_alias=AliasChoices("taskPlanId"),
        serialization_alias="taskPlanId",
    )
    message: str = Field(validation_alias=AliasChoices("message"), serialization_alias="message")
    triggeredAt: datetime | None = Field(
        default=None,
        validation_alias=AliasChoices("triggeredAt"),
        serialization_alias="triggeredAt",
    )
    sendStatus: str | None = Field(
        default=None,
        validation_alias=AliasChoices("sendStatus"),
        serialization_alias="sendStatus",
    )
    errorMsg: str | None = Field(
        default=None,
        validation_alias=AliasChoices("errorMsg"),
        serialization_alias="errorMsg",
    )
    creationTime: datetime = Field(
        validation_alias=AliasChoices("creationTime"),
        serialization_alias="creationTime",
    )


class ContractReminderLogListData(BaseDTO):
    total: int = Field(validation_alias=AliasChoices("total"), serialization_alias="total")
    page: int = Field(validation_alias=AliasChoices("page"), serialization_alias="page")
    pageSize: int = Field(validation_alias=AliasChoices("pageSize"), serialization_alias="pageSize")
    items: list[ContractReminderLogItem] = Field(
        default_factory=list,
        validation_alias=AliasChoices("items"),
        serialization_alias="items",
    )
