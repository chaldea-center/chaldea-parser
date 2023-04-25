from urllib.parse import quote

from discord_webhook import DiscordEmbed, DiscordWebhook

from ..config import settings
from .helper import LocalProxy
from .log import logger


def _execute(webhook: DiscordWebhook, **kwargs):
    if not webhook.url:
        logger.warning(f"Discord webhook not set, data={webhook.json}")
        return
    with LocalProxy():
        resp = webhook.execute(**kwargs)
        if resp:
            logger.debug(resp.text)
        else:
            logger.warning("No response from discord webhook")
        return resp


def get_webhook():
    return DiscordWebhook(
        settings.discord_webhook,
        username="Chaldea Parser",
        avatar_url="https://docs.chaldea.center/logo.png",
    )


def text(msg: str):
    logger.info(msg)
    webhook = get_webhook()
    webhook.set_content(msg)
    return _execute(webhook)


def _encode_url(url: str):
    return quote(url, safe=";/?:@&=+$,")


def md_link(title: str, link: str):
    return f"[{title}]({_encode_url(link)})"


def mc_link(title: str):
    return md_link(title, f"https://fgo.wiki/w/{title}")


def fandom_link(title: str):
    return md_link(title, f"https://fategrandorder.fandom.com/wiki/{title}")


def mc_links(titles: list[str]):
    return ", ".join([mc_link(x) for x in titles])


def fandom_links(titles: list[str]):
    return ", ".join([fandom_link(x) for x in titles])


def mc(title: str, content: str):
    webhook = get_webhook()
    em = DiscordEmbed(title=title)
    em.set_author("Mooncell", icon_url="https://fgo.wiki/ioslogo.png")
    em.set_description(content)
    webhook.add_embed(em)
    _execute(webhook)


def fandom(title: str, content: str):
    webhook = get_webhook()
    em = DiscordEmbed(title=title)
    em.set_author(
        "Fandom", icon_url="https://www.fandom.com/f2/assets/favicons/favicon.ico"
    )
    em.set_description(content)
    webhook.add_embed(em)
    _execute(webhook)


def wiki_links(mc_links: list[str], fandom_links: list[str]):
    if not mc_links and not fandom_links:
        return

    webhook = get_webhook()
    if mc_links:
        mc = DiscordEmbed(title="Invalid Mooncell links")
        mc.set_author("Mooncell", icon_url="https://fgo.wiki/ioslogo.png")
        mc.set_description(
            ", ".join(
                [md_link(link, f"https://fgo.wiki/w/{link}") for link in mc_links]
            )
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
                    md_link(link, f"https://fategrandorder.fandom.com/wiki/{link}")
                    for link in fandom_links
                ]
            )
        )
        webhook.add_embed(fandom)
    return _execute(webhook)
