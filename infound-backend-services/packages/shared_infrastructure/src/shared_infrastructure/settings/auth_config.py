from core_base.settings import SettingsBase


class IFAuthSettings(SettingsBase):
    required_header: str = "INFoundCreatorAuth"
    secret_key: str = "94dfc07baaef3854516a0f0f0d0d22f5bb887b1b28380fcb6734d055f353d43b"
    expire_days: int = 14
    max_tokens: int = 5
