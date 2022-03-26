from ..config import settings
from .wiki_tool import WikiTool


MOONCELL = WikiTool("fgo.wiki", "/", settings.mc_user, settings.mc_pwd)
FANDOM = WikiTool(
    "fategrandorder.fandom.com", "/", settings.fandom_user, settings.fandom_pwd
)
