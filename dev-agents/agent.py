import asyncio
import json
import aiohttp
from aiohttp import web
import os
import logging
from datetime import datetime
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("dev-agents")

DISCORD_BOT_TOKEN = os.environ["DISCORD_BOT_TOKEN"]
WORKSPACE = os.environ.get("WORKSPACE", "/workspace")
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6")
MAX_TURNS = int(os.environ.get("MAX_TURNS", "50"))
DISCORD_API = "https://discord.com/api/v10"

_task_lock = asyncio.Lock()
_ws_clients = set()
_current_task = None

# Thread ID -> Claude session ID mapping for conversation continuity
_thread_sessions = {}


# --- Task State ---

class TaskState:
    def __init__(self, channel_id, message_id, author, content):
        self.channel_id = channel_id
        self.message_id = message_id
        self.author = author
        self.content = content
        self.thread_id = None
        self.events = []
        self.agents = {}
        self.started_at = datetime.now().isoformat()
        self.status = "running"
        self.result = ""
        self.cost_usd = 0
        self.num_turns = 0
        self.session_id = None

    def to_dict(self):
        return {
            "author": self.author,
            "content": self.content[:300],
            "status": self.status,
            "agents": self.agents,
            "events": self.events[-50:],
            "started_at": self.started_at,
            "result": self.result[:500],
            "cost_usd": self.cost_usd,
            "num_turns": self.num_turns,
        }


# --- Discord Helpers ---

async def discord_request(method, path, json_body=None):
    headers = {
        "Authorization": f"Bot {DISCORD_BOT_TOKEN}",
        "Content-Type": "application/json",
    }
    async with aiohttp.ClientSession() as session:
        fn = getattr(session, method)
        async with fn(f"{DISCORD_API}{path}", json=json_body, headers=headers) as resp:
            if resp.status not in (200, 201, 204):
                log.error(f"Discord {method} {path} -> {resp.status}")
                return None
            if resp.status == 204:
                return {}
            return await resp.json()


async def send_discord(channel_id, content, reply_to=None):
    chunks = split_message(content)
    for i, chunk in enumerate(chunks):
        body = {"content": chunk}
        if i == 0 and reply_to:
            body["message_reference"] = {"message_id": reply_to}
        await discord_request("post", f"/channels/{channel_id}/messages", body)


async def create_thread(channel_id, message_id, name):
    data = await discord_request(
        "post",
        f"/channels/{channel_id}/messages/{message_id}/threads",
        {"name": name[:100], "auto_archive_duration": 1440},
    )
    return data["id"] if data else None


async def keep_typing(channel_id):
    try:
        while True:
            await discord_request("post", f"/channels/{channel_id}/typing")
            await asyncio.sleep(8)
    except asyncio.CancelledError:
        pass


def split_message(text, limit=1950):
    if len(text) <= limit:
        return [text]
    chunks = []
    while text:
        if len(text) <= limit:
            chunks.append(text)
            break
        split = text[:limit].rfind("\n")
        if split < limit // 2:
            split = limit
        chunks.append(text[:split])
        text = text[split:].lstrip("\n")
    return chunks


# --- WebSocket ---

async def broadcast(event):
    global _current_task
    msg = json.dumps(event)
    dead = set()
    for ws in _ws_clients:
        try:
            await ws.send_str(msg)
        except Exception:
            dead.add(ws)
    _ws_clients -= dead


# --- Stream Parser ---

TOOL_ICONS = {
    "Read": "\U0001f4d6", "Write": "\u270f\ufe0f", "Edit": "\U0001f4dd", "Bash": "\U0001f4bb",
    "Glob": "\U0001f50d", "Grep": "\U0001f50d", "Agent": "\U0001f500",
}


async def parse_stream_line(line, task):
    try:
        data = json.loads(line)
    except json.JSONDecodeError:
        return

    event_type = data.get("type", "")
    now = datetime.now().strftime("%H:%M:%S")

    if event_type == "assistant":
        message = data.get("message", {})
        for block in message.get("content", []):
            if block.get("type") == "tool_use":
                await handle_tool_use(block, task, now)
            elif block.get("type") == "text":
                text = block.get("text", "").strip()
                if text and len(text) > 10:
                    ev = {"type": "text", "text": text[:200], "time": now}
                    task.events.append(ev)
                    await broadcast({"type": "event", "event": ev, "task": task.to_dict()})

    elif event_type == "result":
        task.result = data.get("result", "")
        task.status = "done"
        task.cost_usd = data.get("cost_usd", 0)
        task.num_turns = data.get("num_turns", 0)
        task.session_id = data.get("session_id", None)
        ev = {"type": "result", "text": "Tache terminee", "time": now}
        task.events.append(ev)
        await broadcast({"type": "task_complete", "task": task.to_dict()})


async def handle_tool_use(block, task, now):
    name = block.get("name", "unknown")
    inp = block.get("input", {})
    icon = TOOL_ICONS.get(name, "\U0001f527")

    if name == "Agent":
        desc = inp.get("description", "agent")
        agent_name = desc.split()[0] if desc else "agent"
        task.agents[agent_name] = "running"
        discord_msg = f"{icon} **Delegation** -> {desc}"
        ev = {"type": "agent_spawn", "name": agent_name, "description": desc, "time": now}
        # Always post agent spawns to thread
        if task.thread_id:
            await send_discord(task.thread_id, discord_msg)

    elif name in ("Write", "Edit"):
        path = inp.get("file_path", "")
        short = os.path.basename(path) if path else "?"
        discord_msg = f"{icon} `{short}`"
        ev = {"type": "tool", "tool": name, "file": short, "time": now}
        if task.thread_id:
            await send_discord(task.thread_id, discord_msg)

    elif name == "Bash":
        cmd = inp.get("command", "")[:80]
        ev = {"type": "tool", "tool": "Bash", "command": cmd, "time": now}
        # Only post significant bash commands to thread
        if task.thread_id and any(kw in cmd for kw in ["git ", "npm ", "docker ", "test", "build"]):
            await send_discord(task.thread_id, f"{icon} `{cmd}`")

    elif name == "Read":
        path = inp.get("file_path", "")
        short = os.path.basename(path) if path else "?"
        ev = {"type": "tool", "tool": "Read", "file": short, "time": now}
    else:
        ev = {"type": "tool", "tool": name, "time": now}

    task.events.append(ev)
    await broadcast({"type": "event", "event": ev, "task": task.to_dict()})


# --- Claude Runner ---

async def run_claude_stream(prompt, task, resume_session_id=None):
    cmd = [
        "claude", "-p", prompt,
        "--output-format", "stream-json",
        "--dangerously-skip-permissions",
        "--model", CLAUDE_MODEL,
        "--max-turns", str(MAX_TURNS),
    ]

    # Resume existing session for conversation continuity
    if resume_session_id:
        cmd.extend(["--resume", resume_session_id])
        log.info(f"Resuming session {resume_session_id}: {prompt[:80]}...")
    else:
        log.info(f"Running claude (new session): {prompt[:80]}...")

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=WORKSPACE,
    )

    final_result = ""

    try:
        async with asyncio.timeout(900):
            async for line in proc.stdout:
                decoded = line.decode().strip()
                if not decoded:
                    continue
                await parse_stream_line(decoded, task)
                # Capture result from stream
                try:
                    data = json.loads(decoded)
                    if data.get("type") == "result":
                        final_result = data.get("result", "")
                except json.JSONDecodeError:
                    pass

            await proc.wait()
    except TimeoutError:
        proc.kill()
        raise asyncio.TimeoutError("Claude CLI timeout (>15 min)")

    if proc.returncode != 0:
        stderr = await proc.stderr.read()
        error_msg = stderr.decode()[:500]
        # If resume failed, retry without resume
        if resume_session_id and "session" in error_msg.lower():
            log.warning(f"Resume failed, starting fresh session: {error_msg[:100]}")
            return await run_claude_stream(prompt, task, resume_session_id=None)
        raise RuntimeError(f"Claude exited {proc.returncode}: {error_msg}")

    return final_result or "Done."


# --- Task Processor ---

async def process_task(channel_id, content, message_id, author, is_thread=False, thread_id=None):
    global _current_task

    task = TaskState(channel_id, message_id, author, content)
    _current_task = task

    # Determine if this is a follow-up in an existing thread
    resume_session_id = None
    if is_thread and thread_id and thread_id in _thread_sessions:
        resume_session_id = _thread_sessions[thread_id]
        task.thread_id = thread_id
        log.info(f"Follow-up in thread {thread_id}, resuming session {resume_session_id}")

    async with _task_lock:
        # Only create a new thread if this is NOT a follow-up in an existing thread
        if not task.thread_id:
            thread_name = content[:80] if len(content) <= 80 else content[:77] + "..."
            task.thread_id = await create_thread(channel_id, message_id, thread_name)

        if task.thread_id and not resume_session_id:
            await send_discord(task.thread_id, f"\U0001f7e2 **Jarvis CEO** demarre l'analyse...\n**Repo workspace :** `{WORKSPACE}`\n**Modele :** `{CLAUDE_MODEL}`")
        elif task.thread_id and resume_session_id:
            await send_discord(task.thread_id, f"\U0001f504 **Jarvis CEO** reprend la conversation...")

        await broadcast({"type": "task_start", "task": task.to_dict()})

        typing_task = asyncio.create_task(keep_typing(task.thread_id or channel_id))
        try:
            result = await run_claude_stream(content, task, resume_session_id=resume_session_id)
            typing_task.cancel()

            # Store session ID for conversation continuity
            if task.session_id and task.thread_id:
                _thread_sessions[task.thread_id] = task.session_id
                log.info(f"Stored session {task.session_id} for thread {task.thread_id}")

            # Mark all running agents as done
            for name in task.agents:
                if task.agents[name] == "running":
                    task.agents[name] = "done"

            # Post final result
            target = task.thread_id or channel_id
            summary = result
            if task.cost_usd:
                summary += f"\n\n\U0001f4ca *{task.num_turns} tours, ${task.cost_usd:.4f}*"
            await send_discord(target, summary, message_id if not task.thread_id else None)

            # Also reply in main channel with short summary (only for new tasks, not follow-ups)
            if task.thread_id and not resume_session_id:
                short = result[:300] + ("..." if len(result) > 300 else "")
                await send_discord(channel_id, f"\u2705 **Terminee** -- voir le thread pour les details.\n{short}", message_id)

            log.info(f"Task done for {author} ({len(result)} chars, ${task.cost_usd:.4f})")

        except asyncio.TimeoutError:
            typing_task.cancel()
            task.status = "timeout"
            msg = "\u26a0\ufe0f Timeout (>15 min)"
            await send_discord(task.thread_id or channel_id, msg)
            await broadcast({"type": "task_error", "error": "timeout", "task": task.to_dict()})

        except Exception as e:
            typing_task.cancel()
            task.status = "error"
            log.error(f"Task failed: {e}")
            await send_discord(task.thread_id or channel_id, f"\u274c Erreur: {e}")
            await broadcast({"type": "task_error", "error": str(e), "task": task.to_dict()})

        finally:
            _current_task = None


# --- HTTP Handlers ---

async def handle_task(request):
    data = await request.json()
    channel_id = data["channelId"]
    content = data["content"]
    message_id = data.get("messageId")
    author = data.get("author", "unknown")
    is_thread = data.get("isThread", False)
    thread_id = data.get("threadId")

    log.info(f"Task from {author} (thread={is_thread}, threadId={thread_id}): {content[:80]}")

    if _task_lock.locked():
        await send_discord(channel_id, "\u23f3 Une tache est deja en cours, patiente.", message_id)
        return web.Response(status=202, text="busy")

    asyncio.create_task(process_task(channel_id, content, message_id, author, is_thread, thread_id))
    return web.Response(status=202, text="accepted")


async def handle_health(request):
    status = "busy" if _task_lock.locked() else "idle"
    return web.json_response({
        "status": status,
        "task": _current_task.to_dict() if _current_task else None,
        "active_sessions": len(_thread_sessions),
    })


async def handle_ws(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    _ws_clients.add(ws)
    log.info(f"WS client connected ({len(_ws_clients)} total)")

    # Send current state
    if _current_task:
        await ws.send_str(json.dumps({"type": "task_state", "task": _current_task.to_dict()}))
    else:
        await ws.send_str(json.dumps({"type": "idle"}))

    try:
        async for msg in ws:
            pass  # read-only ws
    finally:
        _ws_clients.discard(ws)
        log.info(f"WS client disconnected ({len(_ws_clients)} total)")

    return ws


async def handle_dashboard(request):
    html = (Path(__file__).parent / "dashboard.html").read_text()
    return web.Response(text=html, content_type="text/html")


# --- App ---

app = web.Application()
app.router.add_post("/task", handle_task)
app.router.add_get("/health", handle_health)
app.router.add_get("/ws", handle_ws)
app.router.add_get("/", handle_dashboard)

if __name__ == "__main__":
    log.info(f"Starting dev-agents (workspace={WORKSPACE}, model={CLAUDE_MODEL})")
    web.run_app(app, host="0.0.0.0", port=8585)
