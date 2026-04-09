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
    user_id: str
    user_name: str
    nick_name: str
    user_type: str | None
    email: str | None
    phone_number: str | None
    sex: int | None
    avatar: str | None
    status: int | None
    dept_id: int | None

