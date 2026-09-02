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
N8N_FEEDBACK_WEBHOOK_URL = os.environ.get("N8N_FEEDBACK_WEBHOOK_URL", "")
N8N_RESET_WEBHOOK_URL = os.environ.get("N8N_RESET_WEBHOOK_URL", "")
DEV_AGENTS_URL = os.environ.get("DEV_AGENTS_URL", "")
BOT_TOKEN = os.environ["DISCORD_BOT_TOKEN"]

DISCORD_LIMIT = 1900
JARVIS_COLOR = 0x5865F2
WAIT_TEXT = "⏳ Je regarde ça…"


class JarvisClient(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(intents=intents)
        self.tree = discord.app_commands.CommandTree(self)

    async def setup_hook(self):
        # Vue persistante : les boutons survivent a un redemarrage du bot
        self.add_view(JarvisView())


client = JarvisClient()


# ─────────────────────────────────────────────────────────────────────────────
# Mise en forme
# ─────────────────────────────────────────────────────────────────────────────

def split_message(text: str, limit: int = DISCORD_LIMIT):
    """Split a long reply into Discord-sized chunks on natural boundaries."""
    if len(text) <= limit:
        return [text]

    chunks, current = [], ""
    for block in text.split("\n\n"):
        candidate = block if not current else current + "\n\n" + block
        if len(candidate) <= limit:
            current = candidate
            continue
        if current:
            chunks.append(current)
            current = ""
        # Le bloc seul depasse encore la limite : on redecoupe ligne par ligne
        for line in block.split("\n"):
            candidate = line if not current else current + "\n" + line
            if len(candidate) <= limit:
                current = candidate
                continue
            if current:
                chunks.append(current)
                current = ""
            while len(line) > limit:
                chunks.append(line[:limit])
                line = line[limit:]
            current = line
    if current:
        chunks.append(current)
    return chunks


def build_embeds(cards):
    """Turn the workflow's `cards` payload into Discord embeds."""
    embeds = []
    for card in (cards or [])[:4]:
        title = card.get("title") or "Sans titre"
        year = card.get("year")
        embed = discord.Embed(
            title=f"{title} ({year})" if year else title,
            description=card.get("overview") or None,
            color=JARVIS_COLOR,
        )
        if card.get("poster"):
            embed.set_thumbnail(url=card["poster"])

        meta = []
        rating = card.get("rating")
        if rating:
            meta.append(f"⭐ {round(float(rating), 1)}")
        if card.get("runtime"):
            meta.append(f"⏱ {card['runtime']} min")
        if card.get("seasons"):
            meta.append(f"📺 {card['seasons']} saisons")
        genres = card.get("genres") or []
        if genres:
            meta.append(" · ".join(genres))
        if not card.get("available", True):
            meta.append("⚠️ pas encore sur le serveur")
        if meta:
            embed.set_footer(text="  —  ".join(meta))
        embeds.append(embed)
    return embeds


# ─────────────────────────────────────────────────────────────────────────────
# Appels n8n
# ─────────────────────────────────────────────────────────────────────────────

async def call_agent(payload: dict, timeout: int = 180):
    """Call the media agent. Returns (data, error_message)."""
    if not N8N_GENERAL_WEBHOOK_URL:
        return None, "Le pont vers l'agent n'est pas configuré."
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                N8N_GENERAL_WEBHOOK_URL, json=payload,
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as resp:
                body = await resp.text()
                if resp.status not in (200, 201, 204):
                    log.warning(f"n8n a repondu {resp.status}: {body[:200]}")
                    return None, f"L'agent a répondu une erreur ({resp.status}). Réessaie dans un instant."
                if not body or body.strip() == "ok":
                    return None, "L'agent n'a rien renvoyé. Réessaie dans un instant."
                try:
                    data = await resp.json()
                except Exception:
                    return {"reply": body.strip()}, None
                if not (data.get("reply") or "").strip():
                    return None, "L'agent n'a rien renvoyé. Réessaie dans un instant."
                return data, None
    except asyncio.TimeoutError:
        log.warning(f"n8n timeout (>{timeout}s)")
        return None, "Ça a pris trop de temps — l'agent n'a pas répondu à temps."
    except Exception as e:
        log.error(f"Erreur appel n8n: {e}")
        return None, f"Je n'ai pas pu joindre l'agent ({type(e).__name__})."


async def post_json(url: str, payload: dict, timeout: int = 60):
    if not url:
        return None
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
                if resp.status not in (200, 201, 204):
                    log.warning(f"POST {url} -> {resp.status}")
                    return None
                try:
                    return await resp.json()
                except Exception:
                    return {}
    except Exception as e:
        log.error(f"POST {url} echoue: {e}")
        return None


def build_payload(*, session_id, channel, author, content, is_thread, is_new_thread, message_id=None, guild_id=None):
    return {
        "sessionId": str(session_id),
        "channelId": str(channel.id),
        "parentChannelId": str(channel.parent_id) if isinstance(channel, discord.Thread) else str(channel.id),
        "channelName": getattr(channel, "name", "?"),
        "isThread": is_thread,
        "isNewThread": is_new_thread,
        "content": content,
        "author": {"id": str(author.id), "username": author.name, "bot": author.bot},
        "messageId": str(message_id) if message_id else None,
        "guildId": str(guild_id) if guild_id else None,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Rendu de la reponse
# ─────────────────────────────────────────────────────────────────────────────

async def render_answer(placeholder: discord.Message, dest, data: dict):
    """Edit the placeholder with the answer, then post the rest + embeds + buttons."""
    reply = (data.get("reply") or "").strip()
    embeds = build_embeds(data.get("cards"))
    # Les boutons ne servent que sous une recommandation : pas de « autre suggestion »
    # ni de pouce sous une réponse de conversation courante.
    view = JarvisView() if embeds else None
    chunks = split_message(reply)

    if len(chunks) == 1:
        await placeholder.edit(content=chunks[0], embeds=embeds, view=view)
    else:
        await placeholder.edit(content=chunks[0], embeds=[], view=None)
        for chunk in chunks[1:-1]:
            if chunk.strip():
                await dest.send(chunk)
        await dest.send(chunks[-1], embeds=embeds, view=view or discord.utils.MISSING)

    log.info(f"Reponse envoyee dans #{getattr(dest, 'name', '?')} ({len(reply)} chars, {len(embeds)} fiches)")


async def run_exchange(dest, author, content, *, is_new_thread=False, message_id=None,
                       guild_id=None, thread_to_rename=None):
    """Full round-trip: placeholder -> agent -> rendered answer (or a clear error)."""
    placeholder = await dest.send(WAIT_TEXT)
    payload = build_payload(
        session_id=dest.id, channel=dest, author=author, content=content,
        is_thread=isinstance(dest, discord.Thread), is_new_thread=is_new_thread,
        message_id=message_id, guild_id=guild_id,
    )

    async with dest.typing():
        data, error = await call_agent(payload)

    if error:
        await placeholder.edit(content=f"❌ {error}")
        return

    if thread_to_rename is not None and (data.get("title") or "").strip():
        try:
            await thread_to_rename.edit(name=data["title"].strip()[:100])
        except discord.HTTPException as e:
            log.warning(f"Renommage du fil impossible: {e}")

    await render_answer(placeholder, dest, data)


# ─────────────────────────────────────────────────────────────────────────────
# Boutons
# ─────────────────────────────────────────────────────────────────────────────

async def last_question_in(channel, before_message) -> str:
    """Find the most recent human message in the thread, used as feedback context."""
    try:
        async for m in channel.history(limit=30, before=before_message):
            if not m.author.bot and m.content.strip():
                return m.content.strip()[:800]
    except Exception as e:
        log.warning(f"Lecture de l'historique impossible: {e}")
    return ""


class JarvisView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Autre suggestion", emoji="🎲",
                       style=discord.ButtonStyle.secondary, custom_id="jarvis:reroll")
    async def reroll(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        dest = interaction.channel
        await run_exchange(
            dest, interaction.user,
            "Propose-moi autre chose, différent de ce que tu viens de suggérer.",
            guild_id=interaction.guild_id,
        )

    @discord.ui.button(emoji="👍", style=discord.ButtonStyle.secondary, custom_id="jarvis:up")
    async def thumbs_up(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._feedback(interaction, "up")

    @discord.ui.button(emoji="👎", style=discord.ButtonStyle.secondary, custom_id="jarvis:down")
    async def thumbs_down(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._feedback(interaction, "down")

    async def _feedback(self, interaction: discord.Interaction, sentiment: str):
        await interaction.response.defer(ephemeral=True)
        question = await last_question_in(interaction.channel, interaction.message)
        result = await post_json(N8N_FEEDBACK_WEBHOOK_URL, {
            "discordUser": interaction.user.name,
            "sentiment": sentiment,
            "question": question,
            "reply": (interaction.message.content or "")[:2500],
        })

        if result is None:
            await interaction.followup.send("Je n'ai pas réussi à noter ça, désolé.", ephemeral=True)
            return

        facts = result.get("facts") or []
        if facts:
            retenu = "\n".join(f"• {f}" for f in facts)
            await interaction.followup.send(f"C'est noté, je m'en souviendrai :\n{retenu}", ephemeral=True)
        else:
            await interaction.followup.send("C'est noté.", ephemeral=True)


# ─────────────────────────────────────────────────────────────────────────────
# Slash commands
# ─────────────────────────────────────────────────────────────────────────────

async def start_thread_exchange(interaction: discord.Interaction, header: str, question: str):
    """Open a thread from a slash command and run the exchange inside it."""
    channel = interaction.channel
    if isinstance(channel, discord.Thread):
        await interaction.followup.send(header)
        await run_exchange(channel, interaction.user, question, guild_id=interaction.guild_id)
        return

    anchor = await interaction.followup.send(header, wait=True)
    try:
        thread = await anchor.create_thread(name=question[:90], auto_archive_duration=1440)
    except discord.HTTPException as e:
        log.error(f"Creation du fil impossible: {e}")
        await run_exchange(channel, interaction.user, question, guild_id=interaction.guild_id)
        return

    await run_exchange(thread, interaction.user, question, is_new_thread=True,
                       guild_id=interaction.guild_id, thread_to_rename=thread)


@client.tree.command(name="film", description="Une idée de film à regarder")
@discord.app_commands.describe(envie="Ton envie du moment : genre, durée, ambiance… (facultatif)")
async def cmd_film(interaction: discord.Interaction, envie: str = ""):
    await interaction.response.defer()
    question = f"Propose-moi un film à regarder. {envie}".strip() if envie else \
        "Propose-moi un film à regarder ce soir."
    await start_thread_exchange(interaction, f"🎬 **{interaction.user.display_name}** cherche un film", question)


@client.tree.command(name="serie", description="Une idée de série à commencer")
@discord.app_commands.describe(envie="Ton envie du moment : genre, ambiance, format… (facultatif)")
async def cmd_serie(interaction: discord.Interaction, envie: str = ""):
    await interaction.response.defer()
    question = f"Propose-moi une série à regarder. {envie}".strip() if envie else \
        "Propose-moi une série à commencer."
    await start_thread_exchange(interaction, f"📺 **{interaction.user.display_name}** cherche une série", question)


@client.tree.command(name="quoi-de-neuf", description="Les derniers ajouts et ce qui arrive bientôt")
async def cmd_news(interaction: discord.Interaction):
    await interaction.response.defer()
    question = ("Qu'est-ce qui est arrivé récemment sur le serveur, et qu'est-ce qui sort "
                "dans les prochains jours ? Sois synthétique.")
    await start_thread_exchange(interaction, f"🆕 **{interaction.user.display_name}** demande les nouveautés", question)


@client.tree.command(name="reset", description="Oublier la conversation de ce fil")
async def cmd_reset(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    if not isinstance(interaction.channel, discord.Thread):
        await interaction.followup.send(
            "À utiliser dans un fil de discussion : c'est là que je garde le contexte.", ephemeral=True)
        return
    result = await post_json(N8N_RESET_WEBHOOK_URL, {
        "sessionId": str(interaction.channel.id), "scope": "session"})
    if result is None:
        await interaction.followup.send("Je n'ai pas réussi à effacer ce fil.", ephemeral=True)
    else:
        await interaction.followup.send("Mémoire de ce fil effacée. On repart de zéro.", ephemeral=True)


@client.tree.command(name="oublie-mes-gouts", description="Effacer les préférences que Jarvis a retenues sur toi")
async def cmd_forget(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    result = await post_json(N8N_RESET_WEBHOOK_URL, {
        "discordUser": interaction.user.name, "scope": "profile"})
    if result is None:
        await interaction.followup.send("Je n'ai pas réussi à effacer ton profil.", ephemeral=True)
    else:
        await interaction.followup.send("J'ai oublié tes préférences. Table rase.", ephemeral=True)


@client.tree.command(name="aide", description="Ce que Jarvis sait faire")
async def cmd_help(interaction: discord.Interaction):
    embed = discord.Embed(
        title="Jarvis — majordome du serveur média",
        description="Mentionne-moi dans le salon, ou utilise une commande. "
                    "Je réponds dans un fil pour garder le contexte.",
        color=JARVIS_COLOR,
    )
    embed.add_field(
        name="Commandes",
        value=("`/film` — une idée de film, selon ton envie\n"
               "`/serie` — une idée de série\n"
               "`/quoi-de-neuf` — les derniers ajouts et les sorties à venir\n"
               "`/reset` — j'oublie la conversation du fil\n"
               "`/oublie-mes-gouts` — j'oublie tes préférences"),
        inline=False,
    )
    embed.add_field(
        name="Sous mes réponses",
        value="🎲 une autre suggestion  ·  👍 / 👎 pour m'apprendre tes goûts",
        inline=False,
    )
    embed.add_field(
        name="Ce que je consulte",
        value="Films, séries et musique suivis, activité Plex en direct, historique de visionnage. "
              "En lecture seule : je ne télécharge ni ne pilote quoi que ce soit.",
        inline=False,
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)


# ─────────────────────────────────────────────────────────────────────────────
# Evenements
# ─────────────────────────────────────────────────────────────────────────────

@client.event
async def on_ready():
    log.info(f"Bot connecte : {client.user} (id={client.user.id})")
    log.info(f"Channels : dev={CHANNEL_DEV}, general={CHANNEL_GENERAL}")
    channel = client.get_channel(CHANNEL_GENERAL)
    if channel is None or channel.guild is None:
        log.warning("Salon general introuvable : slash commands non synchronisees")
        return
    guild = discord.Object(id=channel.guild.id)
    try:
        client.tree.copy_global_to(guild=guild)
        synced = await client.tree.sync(guild=guild)
        log.info(f"Slash commands synchronisees sur {channel.guild.name}: {[c.name for c in synced]}")
    except discord.Forbidden:
        log.error("Sync des slash commands refusee : le bot n'a pas le scope applications.commands")
    except Exception as e:
        log.error(f"Sync des slash commands echouee: {e}")


def get_parent_channel_id(channel):
    """Return the channel ID, resolving threads to their parent channel ID."""
    if isinstance(channel, discord.Thread):
        return channel.parent_id
    return channel.id


async def should_answer_in_thread(message: discord.Message) -> bool:
    """In a thread, answer freely while it's a one-to-one; once a third party joins, wait to be called."""
    if client.user.mentioned_in(message) and not message.mention_everyone:
        return True
    humans = set()
    try:
        async for m in message.channel.history(limit=30):
            if m.author.bot:
                continue
            humans.add(m.author.id)
            if len(humans) > 1:
                return False
    except Exception as e:
        log.warning(f"Lecture de l'historique du fil impossible: {e}")
        return True
    return True


@client.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    channel_id = get_parent_channel_id(message.channel)

    # Route #dev -> dev-agents (fire-and-forget, long-running)
    if channel_id == CHANNEL_DEV and DEV_AGENTS_URL:
        await forward_to_dev_agents(message)
        return

    # Route #general -> n8n media agent (read-only multimedia)
    if channel_id == CHANNEL_GENERAL and N8N_GENERAL_WEBHOOK_URL:
        is_thread = isinstance(message.channel, discord.Thread)
        mentioned = client.user.mentioned_in(message) and not message.mention_everyone

        if is_thread:
            if not await should_answer_in_thread(message):
                return
        elif not mentioned:
            return

        content = message.content.replace(f"<@{client.user.id}>", "").strip()
        if not content:
            return

        log.info(f"Message de {message.author.name} dans #{message.channel.name}: {content[:80]}")

        if is_thread:
            await run_exchange(message.channel, message.author, content,
                               message_id=message.id, guild_id=message.guild.id if message.guild else None)
            return

        # Message racine dans le salon : on ouvre un fil dedie
        try:
            thread = await message.create_thread(name=content[:90], auto_archive_duration=1440)
        except discord.HTTPException as e:
            log.error(f"Creation du fil impossible: {e}")
            await run_exchange(message.channel, message.author, content,
                               message_id=message.id, guild_id=message.guild.id if message.guild else None)
            return

        await run_exchange(thread, message.author, content, is_new_thread=True,
                           message_id=message.id, guild_id=message.guild.id if message.guild else None,
                           thread_to_rename=thread)


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
