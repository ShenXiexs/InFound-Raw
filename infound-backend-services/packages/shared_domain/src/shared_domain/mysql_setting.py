from core_base.settings import SettingsBase


class MySQLSettings(SettingsBase):
    host: str = "47.238.5.253"
    port: int = 8801
    user: str = "infound-stg"
    password: str = "&3$BSW)mGxE(Zk"
    db: str = "infound.stg"
    charset: str = "utf8mb4"

    @property
    def sqlalchemy_database_url(self) -> str:
        return f"mysql+aiomysql://{self.user}:{self.password}@{self.host}:{self.port}/{self.db}?charset={self.charset}"
