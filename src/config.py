import json
from pathlib import Path

from app.schemas.common import Region
from pydantic import BaseSettings, NoneStr


__all__ = ["Settings", "settings"]


class Settings(BaseSettings):
    class Config:
        env_file = ".env"

    output_dir: str = "data/"
    cache_dir: str = "cache/"
    log_dir: str = "logs/"

    # keys
    mc_user: str = ""
    mc_pwd: str = ""
    fandom_user: str = ""
    fandom_pwd: str = ""

    environment: str = ""

    discord_webhook: str = ""

    # proxy, for development
    x_http_proxy: NoneStr = None
    x_https_proxy: NoneStr = None
    x_all_proxy: NoneStr = None

    tmp_vars: dict = {}

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

    @property
    def cache_http_cache(self) -> Path:
        return Path(self.cache_dir) / "http_cache"

    @property
    def cache_wiki(self) -> Path:
        return Path(self.cache_dir) / "wiki"

    @property
    def commit_msg(self) -> Path:
        return Path(self.output_dir) / "commit-msg.txt"


settings = Settings()

Path(settings.cache_dir).mkdir(parents=True, exist_ok=True)
Path(settings.log_dir).mkdir(parents=True, exist_ok=True)


class PayloadSetting(BaseSettings):
    regions: list[Region] = []  # from aa/api
    event: str | None = None
    run_wiki_parser: bool | None = None
    run_atlas_parser: bool | None = None
    force_update_export: bool = False
    enable_wiki_threading: bool = False
    clear_cache_http: bool = False
    clear_cache_wiki: bool = False
    clear_wiki_changed: float | None = None  # -101: clear all image caches
    clear_wiki_moved: float | None = None
    clear_wiki_empty: bool = False
    skip_mapping: bool = False
    skip_quests: bool = False
    use_prev_drops: bool = True
    recent_quest_expire: int = 7
    main_story_quest_expire: int = 90
    expired_wars: list[int] = []  # -1=any interlude
    skip_prev_quest_drops: bool = False
    slow_mode: bool = False
    patch_mappings: bool = True
    mc_extra_svt: dict[int, str] = {}
    mc_extra_ce: dict[int, str] = {}
    extra: dict = {}

    class Config:
        @classmethod
        def customise_sources(
            cls,
            init_settings,
            env_settings,
            file_secret_settings,
        ):
            def json_config_settings_source(settings: BaseSettings) -> dict:
                fp = Path("payload.json")
                if fp.exists():
                    return json.loads(fp.read_text())
                return {}

            return (
                init_settings,
                json_config_settings_source,
                env_settings,
                file_secret_settings,
            )
