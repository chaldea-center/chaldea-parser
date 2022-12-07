from discord_webhook import DiscordEmbed, DiscordWebhook

from ..config import settings
from .helper import LocalProxy
from .log import logger


def _execute(webhook: DiscordWebhook, **kwargs):
    with LocalProxy():
        return webhook.execute(**kwargs)


def get_webhook():
    return DiscordWebhook(
        settings.discord_webhook,
        username="Chaldea Parser",
        avatar_url="https://docs.chaldea.center/logo.png",
    )


def text(msg: str):
    logger.info(msg)
    webhook = get_webhook()
    if not webhook.url:
        return
    webhook.set_content(msg)
    with LocalProxy():
        return _execute(webhook)


def wiki_links(mc_links: list[str], fandom_links: list[str]):
    if not mc_links and not fandom_links:
        return
    webhook = get_webhook()
    if not webhook.url:
        return
    if mc_links:
        mc = DiscordEmbed(title="Invalid Mooncell links")
        mc.set_author("Mooncell", icon_url="https://fgo.wiki/ioslogo.png")
        mc.set_description(
            ", ".join([f"[{link}](https://fgo.wiki/w/{link})" for link in mc_links])
        )
        webhook.add_embed(mc)
    if fandom_links:
        fandom = DiscordEmbed(title="Invalid Fandom links")
        fandom.set_author(
            "Fandom", icon_url="https://www.fandom.com/f2/assets/favicons/favicon.ico"
        )
        fandom.set_description(
            ", ".join(
                [
                    f"[{link}](https://fategrandorder.fandom.com/wiki/{link})"
                    for link in fandom_links
                ]
            )
        )
        webhook.add_embed(fandom)
    return _execute(webhook)
