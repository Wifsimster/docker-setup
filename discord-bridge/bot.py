import discord
import aiohttp
import asyncio
import os
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("discord-bridge")

CHANNEL_DEV = int(os.environ.get("CHANNEL_DEV", "0"))
CHANNEL_GENERAL = int(os.environ.get("CHANNEL_GENERAL", "0"))

N8N_GENERAL_WEBHOOK_URL = os.environ.get("N8N_GENERAL_WEBHOOK_URL", "")
DEV_AGENTS_URL = os.environ.get("DEV_AGENTS_URL", "")
BOT_TOKEN = os.environ["DISCORD_BOT_TOKEN"]

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)


@client.event
async def on_ready():
    log.info(f"Bot connecte : {client.user} (id={client.user.id})")
    log.info(f"Channels : dev={CHANNEL_DEV}, general={CHANNEL_GENERAL}")


def get_parent_channel_id(channel):
    """Return the channel ID, resolving threads to their parent channel ID."""
    if isinstance(channel, discord.Thread):
        return channel.parent_id
    return channel.id


@client.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    channel_id = get_parent_channel_id(message.channel)

    # Route #dev -> dev-agents (fire-and-forget, long-running)
    if channel_id == CHANNEL_DEV and DEV_AGENTS_URL:
        await forward_to_dev_agents(message)
        return

    # Route #general -> n8n media agent (read-only multimedia, @mention required)
    if channel_id == CHANNEL_GENERAL and N8N_GENERAL_WEBHOOK_URL:
        is_thread = isinstance(message.channel, discord.Thread)
        mentioned = client.user.mentioned_in(message) and not message.mention_everyone
        # In threads: always respond (conversation continuity). In channel: require @mention.
        if not is_thread and not mentioned:
            return
        # Strip the bot mention from the message content
        content_clean = message.content.replace(f"<@{client.user.id}>", "").strip()
        if not content_clean:
            return
        message.content = content_clean
        await handle_n8n_channel(message, N8N_GENERAL_WEBHOOK_URL)
        return


async def create_conversation_thread(message: discord.Message):
    """Create a Discord thread from a top-level message for conversation isolation."""
    thread_name = message.content[:80] if len(message.content) <= 80 else message.content[:77] + "..."
    try:
        thread = await message.create_thread(
            name=thread_name,
            auto_archive_duration=1440,  # 24h auto-archive
        )
        log.info(f"Thread cree: {thread.name} (id={thread.id})")
        return thread
    except discord.HTTPException as e:
        log.error(f"Erreur creation thread: {e}")
        return None


async def handle_n8n_channel(message: discord.Message, webhook_url: str):
    """Generic handler for n8n-backed channels with auto-threading and memory."""
    is_thread = isinstance(message.channel, discord.Thread)

    log.info(f"Message recu de {message.author.name} dans #{message.channel.name}: {message.content[:80]}")

    if not is_thread:
        thread = await create_conversation_thread(message)
        if thread:
            await _forward_and_reply(message, thread, webhook_url)
        else:
            await _forward_and_reply(message, None, webhook_url)
    else:
        await _forward_and_reply(message, message.channel, webhook_url)


async def _forward_and_reply(message: discord.Message, reply_target, webhook_url: str):
    """Forward to n8n webhook and post reply to the target channel/thread."""
    is_thread = isinstance(message.channel, discord.Thread)

    if reply_target and not is_thread:
        session_id = str(reply_target.id)
    elif is_thread:
        session_id = str(message.channel.id)
    else:
        session_id = str(message.channel.id)

    payload = {
        "sessionId": session_id,
        "channelId": str(message.channel.id),
        "parentChannelId": str(message.channel.parent_id) if is_thread else str(message.channel.id),
        "channelName": message.channel.name,
        "isThread": is_thread or (reply_target is not None),
        "content": message.content,
        "author": {
            "id": str(message.author.id),
            "username": message.author.name,
            "bot": message.author.bot,
        },
        "messageId": str(message.id),
        "guildId": str(message.guild.id) if message.guild else None,
    }

    dest = reply_target if reply_target and not is_thread else message.channel

    try:
        async with dest.typing():
            async with aiohttp.ClientSession() as session:
                async with session.post(webhook_url, json=payload, timeout=aiohttp.ClientTimeout(total=120)) as resp:
                    if resp.status not in (200, 201, 204):
                        log.warning(f"n8n webhook repondu {resp.status}")
                        return

                    body = await resp.text()
                    if not body or body.strip() == "ok":
                        return

                    try:
                        data = await resp.json()
                        reply = data.get("reply", "").strip()
                    except Exception:
                        reply = body.strip()

                    if not reply:
                        return

                    if len(reply) > 1950:
                        reply = reply[:1947] + "..."

                    await dest.send(reply)
                    log.info(f"Reponse envoyee dans #{dest.name} ({len(reply)} chars)")
    except asyncio.TimeoutError:
        log.warning("n8n webhook timeout (>120s)")
        await dest.send("Timeout - la requete a pris trop de temps.")
    except Exception as e:
        log.error(f"Erreur webhook n8n: {e}")


async def forward_to_dev_agents(message: discord.Message):
    is_thread = isinstance(message.channel, discord.Thread)
    payload = {
        "channelId": str(message.channel.id),
        "content": message.content,
        "author": message.author.name,
        "messageId": str(message.id),
        "isThread": is_thread,
        "threadId": str(message.channel.id) if is_thread else None,
        "parentChannelId": str(message.channel.parent_id) if is_thread else str(message.channel.id),
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(DEV_AGENTS_URL, json=payload, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status in (200, 201, 202):
                    await message.add_reaction("\U0001f680")  # rocket
                    log.info(f"Dev task forwarded from {message.author.name}: {message.content[:80]}")
                else:
                    await message.reply("dev-agents indisponible", mention_author=False)
    except Exception as e:
        log.error(f"Forward to dev-agents failed: {e}")
        await message.reply("dev-agents indisponible", mention_author=False)


client.run(BOT_TOKEN)
