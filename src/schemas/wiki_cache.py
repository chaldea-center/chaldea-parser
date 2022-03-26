from pydantic import BaseModel, NoneStr


class _WikiPageBase(BaseModel):
    name: str
    updated: int


class WikiPageInfo(_WikiPageBase):
    redirect: NoneStr = None
    text: str


class WikiImageInfo(_WikiPageBase):
    imageinfo: dict


class WikiCache(BaseModel):
    host: str
    created: int = 0
    updated: int = 0
    pages: dict[str, WikiPageInfo] = {}  # page.text()
    images: dict[str, WikiImageInfo] = {}  # page.imageinfo
