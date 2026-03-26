from pydantic import AliasChoices, Field

from shared_application_services import BaseDTO


def _to_camel(value: str) -> str:
    parts = value.split("_")
    return parts[0] + "".join(part.capitalize() for part in parts[1:])


class LoginRequest(BaseDTO):
    sample_id: str = Field(
        validation_alias=AliasChoices("sampleId", "sampleID"),
        serialization_alias="sampleID",
    )
    username: str = Field(
        validation_alias=AliasChoices("userName", "username"),
        serialization_alias="userName",
    )
