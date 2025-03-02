import asyncio
import re
from telethon import events, errors
from datetime import datetime
from collections import defaultdict
from telethon.tl.types import InputPeerUser


# Menyimpan status per akun dan grup
active_groups = defaultdict(lambda: defaultdict(bool))  # {group_id: {user_id: status}}
active_bc_interval = defaultdict(lambda: defaultdict(bool))  # {user_id: {type: status}}
blacklist = set()
usernames_history = defaultdict(list)
message_count = defaultdict(int)  # {tanggal: jumlah_pesan}
auto_replies = defaultdict(str)  # {user_id: pesan_auto_reply}

def parse_interval(interval_str):
    """Konversi format [10s, 1m, 2h, 1d] menjadi detik."""
    match = re.match(r'^(\d+)([smhd])$', interval_str)
    if not match:
        return None
    value, unit = match.groups()
    value = int(value)
    return value * {'s': 1, 'm': 60, 'h': 3600, 'd': 86400}[unit]

def get_today_date():
    """Mengembalikan tanggal hari ini dalam format YYYY-MM-DD."""
    return datetime.now().strftime("%Y-%m-%d")

async def configure_event_handlers(client, user_id):
    """Konfigurasi semua fitur bot untuk user_id tertentu."""

    @client.on(events.NewMessage(pattern=r'^gal ping$'))
    async def ping_handler(event):
        """Tes koneksi bot."""
        await event.reply("\U0001F3D3 Pong! Bot aktif.")
        message_count[get_today_date()] += 1

    @client.on(events.NewMessage(pattern=r'^gal bcstar (.+)$'))
    async def broadcast_handler(event):
        """Broadcast pesan ke semua chat kecuali blacklist."""
        custom_message = event.pattern_match.group(1)
        await event.reply(f"\u2705 Memulai broadcast ke semua chat: {custom_message}")
        async for dialog in client.iter_dialogs():
            if dialog.id in blacklist:
                continue
            try:
                await client.send_message(dialog.id, custom_message)
                message_count[get_today_date()] += 1
            except Exception as e:
                print(f"Gagal mengirim pesan ke {dialog.name}: {e}")

    @client.on(events.NewMessage(pattern=r'^gal bcstargr(\d+) (\d+[smhd]) (.+)$'))
    async def broadcast_group_handler(event):
        """Broadcast pesan hanya ke grup dengan interval tertentu dan update pesan secara dinamis."""
        group_number = event.pattern_match.group(1)
        interval_str, custom_message = event.pattern_match.groups()[1:]
        interval = parse_interval(interval_str)

        if not interval:
            await event.reply("\u26A0 Format waktu salah! Gunakan format 10s, 1m, 2h, dll.")
            return

        if active_bc_interval[user_id][f"group{group_number}"]:
            await event.reply(f"\u26A0 Broadcast ke grup {group_number} sudah berjalan.")
            return

        active_bc_interval[user_id][f"group{group_number}"] = True
        message = await event.reply(f"\u2705 Memulai broadcast ke grup {group_number} dengan interval {interval_str}: {custom_message}\nMengirim ke grup: 0/0...")

        total_groups = 0  # Track total grup yang ada
        total_groups_sent = 0  # Track total grup yang sudah terkirim pesan

        # Hitung total grup yang ada
        async for dialog in client.iter_dialogs():
            if dialog.is_group and dialog.id not in blacklist:
                total_groups += 1

        if total_groups == 0:
            await message.edit("🚫 Tidak ada grup untuk dikirim!")
            return

        # Proses broadcast ke grup dengan interval dan update pesan secara dinamis
        while active_bc_interval[user_id][f"group{group_number}"]:
            sent_in_group = 0  # Track jumlah grup yang telah diproses dalam loop ini

            # Kirim pesan ke setiap grup
            for dialog in await client.get_dialogs():
                if dialog.is_group and dialog.id not in blacklist:
                    try:
                        await client.send_message(dialog.id, custom_message)
                        total_groups_sent += 1
                        sent_in_group += 1
                        message_count[get_today_date()] += 1
                    except Exception as e:
                        print(f"Gagal mengirim pesan ke {dialog.name}: {e}")

            # Update pesan dengan jumlah grup yang telah dikirim dan interval yang tersisa
            await message.edit(f"\u2705 Memulai broadcast ke grup {group_number} dengan interval {interval_str}: {custom_message}\nMengirim ke grup: {total_groups_sent}/{total_groups}... Interval: {interval_str}")

            # Jika semua grup sudah diproses, reset counter dan mulai lagi dari 0
            if total_groups_sent >= total_groups:
                total_groups_sent = 0
                # Mengulang pesan setelah semua terkirim
                await message.edit(f"\u2705 Memulai ulang broadcast ke grup {group_number}... Mengirim ke grup: 0/{total_groups}... Interval: {interval_str}")

            # Tunggu sesuai interval waktu sebelum melanjutkan
            await asyncio.sleep(interval)

        # Update pesan ketika broadcast selesai
        await message.edit(f"✅ Broadcast ke grup {group_number} selesai!")

    @client.on(events.NewMessage(pattern=r'^gal stopbcstargr(\d+)$'))
    async def stop_broadcast_group_handler(event):
        """Hentikan broadcast grup."""
        group_number = event.pattern_match.group(1)
        if active_bc_interval[user_id][f"group{group_number}"]:
            active_bc_interval[user_id][f"group{group_number}"] = False
            await event.reply(f"\u2705 Broadcast ke grup {group_number} dihentikan.")
        else:
            await event.reply(f"\u26A0 Tidak ada broadcast grup {group_number} yang berjalan.")

    @client.on(events.NewMessage(pattern=r'^gal setreply (.+)$'))
    async def set_auto_reply(event):
        """Mengatur pesan balasan otomatis."""
        reply_message = event.pattern_match.group(1)
        auto_replies[user_id] = reply_message
        await event.reply(f"\u2705 Auto-reply diatur: {reply_message}")

    @client.on(events.NewMessage(incoming=True))
    async def auto_reply_handler(event):
        """Menangani auto-reply untuk setiap pesan masuk."""
        if event.is_private and user_id in auto_replies and auto_replies[user_id]:
            try:
                sender = await event.get_sender()
                peer = InputPeerUser(sender.id, sender.access_hash)  # Pakai InputPeerUser
                
                await client.send_message(peer, auto_replies[user_id])
                await client.send_read_acknowledge(peer)  # Tandai sebagai telah dibaca

                message_count[get_today_date()] += 1
            except errors.rpcerrorlist.UsernameNotOccupiedError:
                print("Gagal mengirim auto-reply: Username tidak ditemukan.")
            except errors.rpcerrorlist.FloodWaitError as e:
                print(f"Bot terkena flood wait. Coba lagi dalam {e.seconds} detik.")
            except Exception as e:
                print(f"Gagal mengirim auto-reply: {e}")

    @client.on(events.NewMessage(pattern=r'^gal stopall$'))
    async def stop_all_handler(event):
        """Reset semua pengaturan (setreply, broadcast, dll)."""
        # Reset status broadcast untuk setiap grup
        for group_key in active_bc_interval[user_id].keys():
            active_bc_interval[user_id][group_key] = False

        # Reset auto-reply
        auto_replies[user_id] = ""

        # Reset blacklist (optional, jika ingin menghapus semua blacklist untuk user)
        blacklist.clear()

        # Reset group activity status (optional, jika perlu reset status per grup)
        for group_id in active_groups.keys():
            active_groups[group_id][user_id] = False

        # Pastikan untuk menghentikan semua broadcast yang sedang berjalan
        for group_key in active_bc_interval[user_id].keys():
            if active_bc_interval[user_id][group_key]:
                active_bc_interval[user_id][group_key] = False

        await event.reply("\u2705 Semua pengaturan telah direset dan semua broadcast dihentikan.")

    @client.on(events.NewMessage(pattern=r'^gal help$'))
    async def help_handler(event):
        """Tampilkan daftar perintah."""
        help_text = (
            "\U0001F4AC Daftar Perintah:\n"
            "gal ping - Cek status bot\n"
            "gal bcstar <pesan> - Kirim broadcast ke semua chat\n"
            "gal bcstargr<nomor> <interval> <pesan> - Kirim broadcast ke grup tertentu\n"
            "gal stopbcstargr<nomor> - Hentikan broadcast ke grup tertentu\n"
            "gal setreply <pesan> - Set auto-reply untuk chat masuk untuk seluruh akun yang terkoneksi bot\n"
            "gal stopall - Reset semua pengaturan semua akun yang ada di bot\n"
            "gal help - Menampilkan daftar perintah"
        )
        await event.reply(help_text)
