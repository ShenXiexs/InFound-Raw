from pydantic import AliasChoices, BaseModel, ConfigDict, Field

def _to_camel(value: str) -> str:
    parts = value.split("_")
    return parts[0] + "".join(part.capitalize() for part in parts[1:])


class LoginRequest(BaseModel):
    model_config = ConfigDict(
        alias_generator=_to_camel,
        populate_by_name=True,
    )

    sample_id: str = Field(
        validation_alias=AliasChoices("sampleId", "sampleID"),
        serialization_alias="sampleID",
    )
    user_name: str = Field(
        validation_alias=AliasChoices("userName", "username"),
        serialization_alias="userName",
    )
