from pathlib import Path

from pydantic import BaseSettings, NoneStr


__all__ = ["Settings", "settings"]


class Settings(BaseSettings):
    class Config:
        env_file = ".env"

    output_dir: str = "data/"
    cache_dir: str = "cache/"
    log_dir: str = "logs/"
    static_dir: str = "static/"

    # keys
    user_mc: str = ""
    pwd_mc: str = ""
    user_fandom: str = ""
    pwd_fandom: str = ""

    environment: str = ""
    quest_phase_expire: int = 30
    skip_quests: bool = False

    # proxy, for development
    x_http_proxy: NoneStr = None
    x_https_proxy: NoneStr = None
    x_all_proxy: NoneStr = None

    @property
    def is_debug(self):
        return self.environment == "debug"

    @property
    def atlas_export_dir(self) -> Path:
        return Path(self.cache_dir) / "atlas_export"

    @property
    def output_wiki(self) -> Path:
        return Path(self.output_dir) / "wiki"

    @property
    def output_dist(self) -> Path:
        return Path(self.output_dir) / "dist"

    @property
    def output_mapping(self) -> Path:
        return Path(self.output_dir) / "mappings"


settings = Settings()

Path(settings.cache_dir).mkdir(parents=True, exist_ok=True)
Path(settings.log_dir).mkdir(parents=True, exist_ok=True)
