from pydantic import BaseModel, Field, NoneStr


class WikiPageInfo(BaseModel):
    name: str
    redirect: NoneStr = None
    text: str
    updated: int


class WikiCache(BaseModel):
    host: str
    created: int = 0
    updated: int = 0
    pages: dict[str, WikiPageInfo] = Field(default_factory=dict)  # page.text()
    images: dict[str, dict] = Field(default_factory=dict)  # page.imageinfo
