from core_base.settings import SettingsBase


class RedisSettings(SettingsBase):
    host: str = "47.238.5.253"
    port: int = 8802
    password: str = "gcc+tvKgtjd&n_^@"
    db: int = 0
    prefix: str = "if.dev"
