import discord
import aiohttp
import asyncio
import os
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("discord-bridge")

CHANNEL_CHAT = int(os.environ["CHANNEL_CHAT"])
CHANNEL_DEV = int(os.environ.get("CHANNEL_DEV", "0"))

N8N_WEBHOOK_URL = os.environ["N8N_WEBHOOK_URL"]
N8N_RESET_WEBHOOK_URL = os.environ.get("N8N_RESET_WEBHOOK_URL", "")
DEV_AGENTS_URL = os.environ.get("DEV_AGENTS_URL", "")
BOT_TOKEN = os.environ["DISCORD_BOT_TOKEN"]

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)


@client.event
async def on_ready():
    log.info(f"Bot connecte : {client.user} (id={client.user.id})")
    log.info(f"Channels : chat={CHANNEL_CHAT}, dev={CHANNEL_DEV}")


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

    # Route #chat (and its threads) -> n8n webhook (request-reply)
    if channel_id != CHANNEL_CHAT:
        return

    # Handle !reset command — clear conversation memory for this thread
    if message.content.strip().lower() == "!reset":
        await handle_reset(message)
        return

    log.info(f"Message recu de {message.author.name} dans #{message.channel.name}: {message.content[:80]}")

    is_thread = isinstance(message.channel, discord.Thread)

    # For top-level messages in #chat, auto-create a thread for conversation context
    if not is_thread:
        thread = await create_conversation_thread(message)
        if thread:
            await forward_to_n8n(message, thread)
        else:
            # Fallback: reply inline if thread creation fails
            await forward_to_n8n(message, None)
    else:
        # Already in a thread — forward with thread context
        await forward_to_n8n(message, message.channel)


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


async def forward_to_n8n(message: discord.Message, thread):
    """Forward message to n8n webhook with session context for conversation memory."""
    is_thread = isinstance(message.channel, discord.Thread)

    # Session ID: thread ID for thread-scoped memory
    # If we just created a thread, use its ID. If already in a thread, use channel ID.
    if thread and not is_thread:
        session_id = str(thread.id)
    elif is_thread:
        session_id = str(message.channel.id)
    else:
        session_id = str(message.channel.id)

    payload = {
        "sessionId": session_id,
        "channelId": str(message.channel.id),
        "parentChannelId": str(message.channel.parent_id) if is_thread else str(message.channel.id),
        "channelName": message.channel.name,
        "isThread": is_thread or (thread is not None),
        "content": message.content,
        "author": {
            "id": str(message.author.id),
            "username": message.author.name,
            "bot": message.author.bot,
        },
        "messageId": str(message.id),
        "guildId": str(message.guild.id) if message.guild else None,
    }

    # Determine where to send the reply
    reply_channel = thread if thread and not is_thread else message.channel

    try:
        async with reply_channel.typing():
            async with aiohttp.ClientSession() as session:
                async with session.post(N8N_WEBHOOK_URL, json=payload, timeout=aiohttp.ClientTimeout(total=120)) as resp:
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

                    # Discord limit: 2000 chars
                    if len(reply) > 1950:
                        reply = reply[:1947] + "..."

                    await reply_channel.send(reply)
                    log.info(f"Reponse envoyee dans #{reply_channel.name} ({len(reply)} chars)")
    except asyncio.TimeoutError:
        log.warning("n8n webhook timeout (>120s)")
        await reply_channel.send("Timeout - la requete a pris trop de temps.")
    except Exception as e:
        log.error(f"Erreur webhook n8n: {e}")


async def handle_reset(message: discord.Message):
    """Handle !reset command to clear conversation memory for the current thread."""
    is_thread = isinstance(message.channel, discord.Thread)
    session_id = str(message.channel.id) if is_thread else str(message.channel.id)

    if N8N_RESET_WEBHOOK_URL:
        try:
            async with aiohttp.ClientSession() as session:
                payload = {"sessionId": session_id}
                async with session.post(N8N_RESET_WEBHOOK_URL, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status in (200, 201, 204):
                        await message.reply("Contexte reinitialise.", mention_author=False)
                        log.info(f"Memory reset for session {session_id}")
                    else:
                        await message.reply("Erreur lors de la reinitialisation.", mention_author=False)
        except Exception as e:
            log.error(f"Reset failed: {e}")
            await message.reply("Erreur lors de la reinitialisation.", mention_author=False)
    else:
        await message.reply("Reset non configure (N8N_RESET_WEBHOOK_URL manquant).", mention_author=False)


async def forward_to_dev_agents(message: discord.Message):
    payload = {
        "channelId": str(message.channel.id),
        "content": message.content,
        "author": message.author.name,
        "messageId": str(message.id),
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
