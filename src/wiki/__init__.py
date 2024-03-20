from ..config import settings
from .wiki_tool import WikiTool


MOONCELL = WikiTool(
    "fgo.wiki",
    img_url_prefix="https://media.fgo.wiki",
    path="/",
    user=settings.mc_user,
    pwd=settings.mc_pwd,
    webpath="w",
)
FANDOM = WikiTool(
    "fategrandorder.fandom.com",
    img_url_prefix="https://static.wikia.nocookie.net/fategrandorder/images",
    path="/",
    user=settings.fandom_user,
    pwd=settings.fandom_pwd,
    webpath="wiki",
)
