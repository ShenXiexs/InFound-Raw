from pydantic import BaseModel, ConfigDict


def _to_camel(value: str) -> str:
    parts = value.split("_")
    return parts[0] + "".join(part.capitalize() for part in parts[1:])


class CurrentUserInfo(BaseModel):
    model_config = ConfigDict(
        alias_generator=_to_camel,
        populate_by_name=True,
    )

    jti: str
    if_id: str
    platform_creator_id: str
    platform_creator_username: str
    platform_creator_display_name: str
    email: str
    whatsapp: str
