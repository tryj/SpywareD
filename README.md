# 🎮 Discord Remote Control Bot

ระบบควบคุมคอมพิวเตอร์ระยะไกลผ่าน Discord  
รองรับการจับภาพหน้าจอ ดูข้อมูล WiFi และดึงรหัส WiFi ที่เคยเชื่อมต่อ  
ทำงานข้ามเครือข่ายผ่าน **ngrok tunnel**

---

## ✨ ฟีเจอร์

| คำสั่ง | หน้าที่ | ต้อง Admin |
|--------|---------|:----------:|
| `!cap` | 📸 จับภาพหน้าจอของ client | ❌ |
| `!wifi` | 📶 ดูข้อมูล WiFi ปัจจุบัน (SSID, Signal, Band) | ❌ |
| `!wifi-pass` | 🔐 ดูรหัส WiFi ที่เคยเชื่อมต่อทั้งหมด | ✅ |
| `!ping` | 🏓 เช็คสถานะ bot | ❌ |

---

## 🏗️ สถาปัตยกรรม

```
┌─────────────────┐                    ┌─────────────────┐
│   Discord       │                    │   PC2 (Client)  │
│   (User)        │                    │   client.py     │
└────────┬────────┘                    └────────┬────────┘
         │ !cap / !wifi                          │
         │ / !wifi-pass                          │ poll /pending ทุก 2s
         ▼                                       │
┌─────────────────┐    ngrok tunnel    ┌────────▼────────┐
│   PC1 (Server)  │◄──────────────────►│   POST /upload  │
│   server.py     │                    │   (multipart)   │
│   port 8765     │                    └─────────────────┘
└─────────────────┘
```

**Flow การทำงาน:**
1. User พิมพ์ `!cap` ใน Discord
2. Server (PC1) สร้าง Future รอ + ตอบ "กำลังขอ..."
3. Client (PC2) poll `/pending` เจองาน → ทำงาน → POST กลับที่ `/upload`
4. Server Future ได้ผล → ส่งกลับ Discord

---

## 📁 โครงสร้างโปรเจกต์

```         
    ├── server.py   ← รันบน PC1
    ├── requirements.txt
    └── .env                   # BOT_TOKEN, API_SECRET
                 
  ├── client.py     ← รันบน PC2         # Poll + Capture + Send
  └── requirements.txt
  ├── .gitignore
  └── README.md
```

---

## 🚀 การติดตั้ง

### ความต้องการของระบบ

- **Python** 3.10+ (แนะนำ 3.11+)
- **Windows** (client — เพราะใช้ `netsh wlan`)
- **ngrok account** (ฟรี) — [สมัครที่นี่](https://dashboard.ngrok.com/signup)
- **Discord Bot Token** — [สร้างที่นี่](https://discord.com/developers/applications)

---

### 🔧 ขั้นตอนที่ 1: สร้าง Discord Bot

1. ไปที่ https://discord.com/developers/applications
2. กด **New Application** → ตั้งชื่อ
3. ไปที่แท็บ **Bot** → กด **Reset Token** → copy เก็บไว้
4. เปิด **Privileged Gateway Intents** ทั้งหมด:
   - ✅ Presence Intent
   - ✅ Server Members Intent
   - ✅ **Message Content Intent** ← สำคัญ!
5. ไปที่ **OAuth2 → URL Generator**:
   - Scopes: `bot`
   - Bot Permissions: `Send Messages`, `Attach Files`, `Read Message History`
6. Copy URL → เปิดใน browser → เชิญ bot เข้า server

---

### 🖥️ ขั้นตอนที่ 2: ตั้งค่า Server (PC1)

```powershell
cd server
pip install -r requirements.txt
```

สร้างไฟล์ `.env`:
```env
BOT_TOKEN=your_discord_bot_token_here
HTTP_PORT=8765
API_SECRET=change_me_to_random_32_bytes_hex
```

**🔑 สร้าง API_SECRET แบบสุ่ม:**
```powershell
python -c "import secrets; print(secrets.token_hex(32))"
```

Copy ผลลัพธ์ไปใส่ `API_SECRET=` ใน `.env`

**รัน server:**
```powershell
python server.py
```

ควรเห็น:
```
============================================================
[HTTP] Listening on 0.0.0.0:8765
[HTTP] Local  : http://127.0.0.1:8765
[HTTP] LAN    : http://192.168.1.152:8765
[HTTP] Health : http://192.168.1.152:8765/health
[HTTP] เปิด ngrok อีกหน้าต่าง: ngrok http 8765
============================================================
[BOT] Logged in as YourBot#1234 (ID: ...)
[BOT] Commands: !cap, !wifi, !wifi-pass, !ping
```

---

### 🌐 ขั้นตอนที่ 3: ตั้งค่า ngrok (PC1)

**ติดตั้ง ngrok:**
1. ดาวน์โหลด: https://ngrok.com/download
2. แตกไฟล์ → ได้ `ngrok.exe`
3. Authtoken ครั้งเดียว:
   ```powershell
   ngrok config add-authtoken YOUR_AUTHTOKEN
   ```
   (copy จาก https://dashboard.ngrok.com/get-started/your-authtoken)

**เปิด tunnel (หน้าต่างใหม่):**
```powershell
ngrok http 8765
```

จะได้ URL แบบนี้ — **copy เก็บไว้**:
```
Forwarding    https://c3b7-xxxx.ngrok-free.app -> http://localhost:8765
```

**💡 แนะนำ: ใช้ Static Domain (ฟรี) เพื่อให้ URL ไม่เปลี่ยน**
```powershell
ngrok http 8765 --domain=your-name.ngrok-free.app
```

---

### 🖥️ ขั้นตอนที่ 4: ตั้งค่า Client (PC2)

```powershell
cd client
pip install -r requirements.txt
```

แก้ 2 บรรทัดใน `client.py`:
```python
NGROK_URL = "https://c3b7-xxxx.ngrok-free.app"   # ← URL จาก ngrok
API_KEY   = "change_me_to_random_32_bytes_hex"   # ← ต้องตรงกับ server .env
```

**รัน client:**
```powershell
python client.py
```

ควรเห็น:
```
[CLIENT] polling https://xxx.ngrok-free.app/pending every 2.0s
[CLIENT] กด Ctrl+C เพื่อหยุด
[CLIENT] health: {'status': 'healthy', 'bot': 'YourBot#1234', ...}
```

**⚠️ ถ้าต้องการใช้ `!wifi-pass` → รันแบบ Administrator:**
```powershell
# คลิกขวา PowerShell → Run as Administrator
cd C:\path\to\client
python client.py
```

---

## 🎮 การใช้งาน

ใน Discord channel ที่ bot อยู่ พิมพ์:

### 📸 จับภาพหน้าจอ
```
!cap
```
→ bot จะตอบ "📸 กำลังขอภาพหน้าจอจาก client..." แล้วได้รูปภาพ

### 📶 ดูข้อมูล WiFi
```
!wifi
```
→ ได้ embed สีฟ้า แสดงข้อมูล WiFi ปัจจุบัน

### 🔐 ดูรหัส WiFi
```
!wifi-pass
```
→ ได้ embed สีแดง แสดงรหัส WiFi ทุก profile ที่เคยเชื่อมต่อ

### 🏓 เช็คสถานะ
```
!ping
```
→ `🏓 pong! latency 42ms`

---

## ⚙️ การตั้งค่า (Configuration)

### Server (`server/.env`)

| ตัวแปร | ค่าเริ่มต้น | คำอธิบาย |
|--------|-------------|----------|
| `BOT_TOKEN` | - | Discord bot token (จำเป็น) |
| `HTTP_PORT` | `8765` | Port ของ HTTP server |
| `API_SECRET` | - | Secret key สำหรับ client (จำเป็น) |

### Client (`client/client.py`)

| ตัวแปร | ค่าเริ่มต้น | คำอธิบาย |
|--------|-------------|----------|
| `NGROK_URL` | - | URL จาก ngrok (จำเป็น) |
| `API_KEY` | - | ต้องตรงกับ `API_SECRET` |
| `POLL_INTERVAL` | `2.0` | วินาทีระหว่าง poll |
| `MAX_WIFI_CHARS` | `100000` | จำกัดขนาดข้อมูล WiFi |

---

## 🌐 HTTP API (สำหรับ developers)

### `GET /health` — เช็คสถานะ
ไม่ต้อง API key

```bash
curl http://127.0.0.1:8765/health
```
```json
{
  "status": "healthy",
  "bot": "YourBot#1234",
  "pending": 0,
  "uptime": 123.4
}
```

### `GET /pending` — Client poll งาน
ต้อง API key (limit 180/min)

```bash
curl -H "X-API-Key: YOUR_SECRET" http://127.0.0.1:8765/pending
```
```json
{"has_task": false}
```

### `POST /upload` — Client ส่งผลลัพธ์
ต้อง API key (limit 30/min) — `multipart/form-data`

| Field | Type | คำอธิบาย |
|-------|------|----------|
| `channel_id` | int | Discord channel ID |
| `type` | str | `cap` / `wifi` / `wifi-pass` |
| `image` | file | PNG (เฉพาะ cap) |
| `text` | str | ข้อมูล (เฉพาะ wifi / wifi-pass) |

---

## 🔐 ความปลอดภัย

- ✅ **HTTPS** — ngrok ให้ฟรีทุก tunnel
- ✅ **API Key** — สุ่ม 32 bytes hex ส่งผ่าน header `X-API-Key`
- ✅ **Rate Limit** — แยกตาม `(ip, path)`
  - `/pending` → 180 req/min
  - `/upload` → 30 req/min
- ✅ **Content-Type check** — ป้องกัน payload ผิดรูปแบบ

### ⚠️ ข้อควรระวัง

- `!wifi-pass` เป็นข้อมูลอ่อนไหว → ควรใช้ใน **private channel**
- รัน client แบบ **Administrator** เพื่อให้เห็นรหัส WiFi ทุก profile
- **อย่า commit `.env`** ขึ้น git
- ถ้าไม่ใช้แล้ว **ปิด ngrok** ทันที

---

## 🧯 Troubleshooting

| อาการ | สาเหตุ | วิธีแก้ |
|-------|--------|--------|
| Client ไม่ตอบกลับ | client ไม่รัน / URL ผิด | เช็ค client + `NGROK_URL` |
| `401 unauthorized` | API_KEY ไม่ตรง | เช็ค `.env` กับ client.py |
| `429 rate limited` | Poll ถี่เกิน | เพิ่ม `POLL_INTERVAL` |
| `400 expected multipart` | Client เวอร์ชันเก่า | ใช้ `FormData` + `content_type="text/plain"` |
| `!wifi-pass` ว่าง | ไม่ได้รันแบบ Admin | Run as Administrator |
| ngrok warning page | ไม่ได้ใส่ header | Client ใส่ header แล้ว, กด Visit Site 1 ครั้ง |

---

## 📊 Tech Stack

| ส่วน | ไลบรารี | เวอร์ชัน |
|------|---------|----------|
| Discord | `discord.py` | ≥2.3.2 |
| HTTP Server | `aiohttp` | ≥3.9.0 |
| HTTP Client | `aiohttp` | ≥3.9.0 |
| จับภาพ | `mss` | ≥9.0.1 |
| ประมวลผลรูป | `Pillow` | ≥10.0.0 |
| Config | `python-dotenv` | ≥1.0.0 |
| Tunnel | `ngrok` | ≥3.x |

---

## 📋 Roadmap

- [ ] WebSocket แทน polling (realtime)
- [ ] Auto-delete ข้อความ `!wifi-pass` หลัง 60 วิ
- [ ] รองรับ Linux / macOS (client)
- [ ] ระบุ client หลายตัว (multi-client)
- [ ] ระบบ authentication แบบหลาย key
- [ ] บันทึก log การใช้งาน

---

## 📜 License

MIT License — ใช้ฟรี แก้ไขได้ แจกจ่ายได้

---

## 🙏 Credits

- [discord.py](https://github.com/Rapptz/discord.py)
- [aiohttp](https://github.com/aio-libs/aiohttp)
- [mss](https://github.com/BoboTiG/python-mss)
- [ngrok](https://ngrok.com/)

---

**⭐ ถ้าโปรเจกต์นี้มีประโยชน์ อย่าลืมกด Star!**
