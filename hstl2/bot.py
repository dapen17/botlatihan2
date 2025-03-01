import os
import json
import asyncio
from telethon import TelegramClient, events, errors
from features import configure_event_handlers  # Import fitur tambahan

# Load konfigurasi dari file
CONFIG_FILE = 'config.json'
if not os.path.exists(CONFIG_FILE):
    raise FileNotFoundError(f"File konfigurasi '{CONFIG_FILE}' tidak ditemukan.")

with open(CONFIG_FILE, 'r') as f:
    config = json.load(f)

api_id = config.get('api_id')
api_hash = config.get('api_hash')
bot_token = config.get('bot_token')

if not api_id or not api_hash or not bot_token:
    raise ValueError("API ID, API Hash, dan Bot Token harus diisi di config.json.")

# Direktori untuk menyimpan sesi
SESSION_DIR = 'sessions'
if not os.path.exists(SESSION_DIR):
    os.makedirs(SESSION_DIR)

# Inisialisasi bot utama
bot_client = TelegramClient('bot_session', api_id, api_hash)

# Dictionary untuk menyimpan sesi pengguna sementara
user_sessions = {}  # Struktur: {user_id: {'client': TelegramClient, 'phone': str}}

@bot_client.on(events.NewMessage(pattern='/start'))
async def start(event):
    await event.reply(
        "Selamat datang di bot multi-login! 😊\n"
        "Masukkan nomor telepon Anda dengan mengetik:\n"
        "`/login <Nomor Telepon>` (contoh: /login +628123456789)"
    )

@bot_client.on(events.NewMessage(pattern='/login (.+)'))
async def login(event):
    sender = await event.get_sender()
    user_id = sender.id
    phone = event.pattern_match.group(1)

    session_file = os.path.join(SESSION_DIR, f'{user_id}_{phone.replace("+", "")}.session')

    # **Cek apakah sesi sudah ada**
    if os.path.exists(session_file):
        try:
            user_client = TelegramClient(session_file, api_id, api_hash)
            await user_client.connect()

            # **Pastikan sesi tidak terkunci**
            if await user_client.is_user_authorized():
                user_sessions[user_id] = {"client": user_client, "phone": phone}
                await event.reply(f"✅ Anda sudah login sebelumnya! Langsung terhubung sebagai {phone}.")
                await configure_event_handlers(user_client, user_id)
                return
            else:
                await user_client.disconnect()  # Tutup sesi jika tidak valid
                os.remove(session_file)  # Hapus sesi yang corrupt
                await event.reply("⚠️ Sesi lama tidak valid, melakukan login ulang...")
        except errors.SessionPasswordNeededError:
            await event.reply("⚠️ Sesi ini membutuhkan password. Silakan login ulang dengan OTP.")
        except Exception as e:
            await event.reply(f"⚠️ Gagal menggunakan sesi lama: {e}. Login ulang diperlukan.")
            try:
                await user_client.disconnect()
            except:
                pass

    # **Jika sesi tidak ada atau terkunci, lakukan login ulang dengan OTP**
    try:
        user_client = TelegramClient(session_file, api_id, api_hash)
        await user_client.connect()
        await user_client.send_code_request(phone)

        user_sessions[user_id] = {"client": user_client, "phone": phone}
        await event.reply(f"✅ Kode OTP telah dikirim ke nomor {phone}! Masukkan kode dengan mengetik:\n`/verify <Kode>`")
    except errors.FloodWaitError as e:
        await event.reply(f"⚠️ Tunggu {e.seconds} detik sebelum mencoba lagi.")
    except Exception as e:
        await event.reply(f"⚠️ Gagal mengirim kode OTP: {e}")

@bot_client.on(events.NewMessage(pattern='/verify (.+)'))
async def verify(event):
    sender = await event.get_sender()
    user_id = sender.id
    code = event.pattern_match.group(1)

    if user_id not in user_sessions:
        await event.reply("⚠️ Anda belum login. Gunakan perintah `/login` terlebih dahulu.")
        return

    user_client = user_sessions[user_id]["client"]
    phone = user_sessions[user_id]["phone"]

    try:
        await user_client.sign_in(phone, code)
        await event.reply(f"✅ Verifikasi berhasil untuk nomor {phone}! Anda sekarang dapat menggunakan fitur.")
        await configure_event_handlers(user_client, user_id)
    except Exception as e:
        await event.reply(f"⚠️ Gagal memverifikasi kode untuk nomor {phone}: {e}")

@bot_client.on(events.NewMessage(pattern='/logout (.+)'))
async def logout(event):
    sender = await event.get_sender()
    user_id = sender.id
    phone = event.pattern_match.group(1)

    session_file = os.path.join(SESSION_DIR, f'{user_id}_{phone.replace("+", "")}.session')

    if user_id in user_sessions and user_sessions[user_id]['phone'] == phone:
        user_client = user_sessions[user_id]['client']
        await user_client.disconnect()
        del user_sessions[user_id]

        if os.path.exists(session_file):
            os.remove(session_file)
            await event.reply(f"✅ Berhasil logout untuk nomor {phone}.")
        else:
            await event.reply(f"⚠️ Tidak ada sesi aktif untuk nomor {phone}.")
    else:
        await event.reply(f"⚠️ Tidak ada sesi aktif untuk nomor {phone}.")

@bot_client.on(events.NewMessage(pattern='/list_sessions'))
async def list_sessions(event):
    sender = await event.get_sender()
    user_id = sender.id

    if user_id not in user_sessions or not user_sessions[user_id]:
        await event.reply("⚠️ Tidak ada sesi yang aktif.")
        return

    active_sessions = []
    for user_id, session_info in user_sessions.items():
        phone = session_info["phone"]
        active_sessions.append(f"Nomor Telepon: {phone}")

    # If no active sessions found
    if not active_sessions:
        await event.reply("⚠️ Anda belum login dengan nomor telepon manapun.")
        return

    await event.reply(
        f"📋 **Sesi Aktif Anda:**\n\n" + "\n".join(active_sessions)
    )

@bot_client.on(events.NewMessage(pattern='/help'))
async def help_command(event):
    await event.reply(
        "📋 **Daftar Perintah untuk Bot Multi-Login:**\n\n"
        "`/start` - Mulai interaksi dengan bot.\n"
        "`/login <Nomor>` - Masukkan nomor telepon Anda untuk login.\n"
        "`/verify <Kode>` - Verifikasi kode OTP.\n"
        "`/logout <Nomor>` - Logout dari sesi yang aktif.\n"
        "`/list_sessions` - Tampilkan daftar sesi aktif beserta nomor telepon.\n"
        "`/help` - Tampilkan daftar perintah."
    )

async def run_bot():
    while True:
        try:
            print("Bot berjalan!")
            await bot_client.start(bot_token=bot_token)
            await bot_client.run_until_disconnected()
        except (errors.FloodWaitError, errors.RPCError) as e:
            print(f"Telegram error: {e}. Tunggu sebelum mencoba lagi.")
            await asyncio.sleep(5)
        except Exception as e:
            print(f"Error tidak terduga: {e}. Restart dalam 10 detik...")
            await asyncio.sleep(10)

if __name__ == '__main__':
    asyncio.run(run_bot())
