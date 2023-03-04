from app.schemas.common import BaseModelORJson


class _WikiPageBase(BaseModelORJson):
    name: str
    updated: int


class WikiPageInfo(_WikiPageBase):
    redirect: str | None = None
    text: str


class WikiImageInfo(_WikiPageBase):
    info: dict = {}

    @property
    def title(self) -> str:
        return self.info["title"]

    @property
    def file_name(self) -> str:
        """Without namespace"""
        return self.title.split(":", maxsplit=1)[-1].replace(" ", "_")

    @property
    def imageinfo(self) -> dict:
        return self.info["imageinfo"][0]

    @property
    def url(self) -> str:
        return self.imageinfo["url"]


class WikiCache(BaseModelORJson):
    host: str
    created: int = 0
    updated: int = 0
    pages: dict[str, WikiPageInfo] = {}  # page.text()
    images: dict[str, WikiImageInfo] = {}  # page.imageinfo
