import asyncio
import sqlite3
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.filters import Command
import os

# ====================== AYARLAR ======================
TOKEN = os.getenv("TOKEN") or "8950737869:AAF83_1E3hV2Zkc7uw_HUa0E-D-UTsMlIvg"
ADMIN_ID = 8773299135
MAX_MSG_LEN = 300

bot = Bot(token=TOKEN)
dp = Dispatcher()

# ====================== DATABASE ======================
conn = sqlite3.connect("bot.db", check_same_thread=False)
cur = conn.cursor()

cur.execute("""CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    is_group INTEGER DEFAULT 0
)""")

cur.execute("""CREATE TABLE IF NOT EXISTS tickets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    msg TEXT,
    answered INTEGER DEFAULT 0,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
)""")

conn.commit()

# ====================== STATES ======================
user_states = {}
admin_states = {}

# ====================== START ======================
@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    if message.chat.type in ["group", "supergroup"]:
        cur.execute("INSERT OR REPLACE INTO users (user_id, username, is_group) VALUES (?, ?, ?)",
                    (message.chat.id, message.chat.title or "Grup", 1))
        conn.commit()
        await message.answer("🌟 Grup kaydedildi!")
    else:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📩 Destek Talebi Oluştur", callback_data="support")]
        ])
        await message.answer("🌟 Hoş geldin!\nDestek için butona bas.", reply_markup=kb)
        
        cur.execute("INSERT OR REPLACE INTO users (user_id, username, is_group) VALUES (?, ?, ?)",
                    (message.from_user.id, message.from_user.username or "Yok", 0))
        conn.commit()


# ====================== ADMIN PANEL ======================
@dp.message(Command("admin"))
async def admin_panel(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Bu komut sadece admin'e özeldir!")
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📂 Yanıtlanmamış Destekler", callback_data="open_tickets")],
        [InlineKeyboardButton(text="🗂 Yanıtlanmış Destekler", callback_data="answered")],
        [InlineKeyboardButton(text="👥 Kullanıcılara Mesaj Gönder", callback_data="send_to_user")],
        [InlineKeyboardButton(text="📢 Toplu Duyuru", callback_data="broadcast")]
    ])
    await message.answer("🔐 **Admin Paneli**", reply_markup=kb)


# ====================== CALLBACKS ======================
@dp.callback_query()
async def callbacks(call: types.CallbackQuery):
    uid = call.from_user.id
    data = call.data

    if data == "support":
        await call.message.answer("📝 Destek mesajınızı veya görselinizi gönderin:")
        user_states[uid] = "awaiting_support"
        await call.answer()
        return

    if uid != ADMIN_ID:
        await call.answer("Yetkiniz yok!", show_alert=True)
        return

    if data == "open_tickets":
        cur.execute("SELECT DISTINCT user_id FROM tickets WHERE answered = 0")
        users_list = cur.fetchall()

        if not users_list:
            await call.message.answer("✅ Yanıtlanmamış destek yok.")
            return

        buttons = [[InlineKeyboardButton(text=f"👤 {u[0]}", callback_data=f"show_{u[0]}")] for u in users_list]
        kb = InlineKeyboardMarkup(inline_keyboard=buttons)
        await call.message.answer("📂 **Yanıtlanmamış Destekler**", reply_markup=kb)

    elif data.startswith("show_"):
        user_id = int(data.split("_")[1])
        cur.execute("SELECT id, msg FROM tickets WHERE user_id = ? AND answered = 0", (user_id,))
        tickets = cur.fetchall()

        for ticket_id, msg in tickets:
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ Yanıtla", callback_data=f"reply_{ticket_id}")],
                [InlineKeyboardButton(text="🗑 Sil", callback_data=f"delete_{ticket_id}")]
            ])
            await call.message.answer(f"**Ticket ID:** `{ticket_id}`\n\n{msg}", reply_markup=kb)

    elif data.startswith("reply_"):
        ticket_id = int(data.split("_")[1])
        cur.execute("SELECT user_id FROM tickets WHERE id = ?", (ticket_id,))
        result = cur.fetchone()
        if result:
            admin_states[uid] = ("reply", result[0], ticket_id)
            await call.message.answer(f"📨 `{result[0]}` ID'li kullanıcıya yanıt yazın:")
        await call.answer()

    elif data.startswith("delete_"):
        ticket_id = int(data.split("_")[1])
        cur.execute("DELETE FROM tickets WHERE id = ?", (ticket_id,))
        conn.commit()
        await call.message.answer(f"🗑 Ticket `{ticket_id}` silindi.")
        await call.answer()

    elif data == "send_to_user":
        cur.execute("SELECT user_id, username FROM users WHERE is_group = 0 LIMIT 100")
        users = cur.fetchall()

        if not users:
            await call.message.answer("Henüz kayıtlı kullanıcı yok.")
            return

        buttons = []
        for user_id, username in users:
            buttons.append([InlineKeyboardButton(
                text=f"👤 {user_id} @{username or 'no_username'}", 
                callback_data=f"msg_to_{user_id}"
            )])
        
        kb = InlineKeyboardMarkup(inline_keyboard=buttons)
        await call.message.answer("📤 **Mesaj göndermek istediğin kullanıcıyı seç:**", reply_markup=kb)

    elif data.startswith("msg_to_"):
        target_id = int(data.split("_")[2])
        admin_states[uid] = ("direct_msg", target_id)
        await call.message.answer(f"✅ `{target_id}` numaralı kullanıcıya mesaj/görsel gönderebilirsiniz.\n\nİçeriği şimdi gönderin.")
        await call.answer()

    elif data == "answered":
        cur.execute("SELECT id, user_id, msg FROM tickets WHERE answered = 1 ORDER BY timestamp DESC LIMIT 20")
        tickets = cur.fetchall()
        if not tickets:
            await call.message.answer("Yanıtlanmış ticket yok.")
            return
        text = "🗂 **Yanıtlanmış Destekler:**\n\n"
        for t in tickets:
            text += f"ID: `{t[0]}` | User: `{t[1]}`\n{t[2][:150]}...\n\n"
        await call.message.answer(text)

    elif data == "broadcast":
        admin_states[uid] = "broadcast"
        await call.message.answer("📢 Toplu duyuru için mesaj veya görsel gönderin:")

    await call.answer()


# ====================== MESAJ İŞLEME ======================
@dp.message()
async def handle_message(message: types.Message):
    uid = message.from_user.id
    uname = message.from_user.username or "Yok"

    if user_states.get(uid) == "awaiting_support":
        content = message.text or (message.caption or "📷 Görsel")
        
        if message.text and len(message.text) > MAX_MSG_LEN:
            await message.answer("⚠️ Mesaj çok uzun!")
            return

        cur.execute("INSERT INTO tickets (user_id, msg) VALUES (?, ?)", (uid, content))
        conn.commit()
        ticket_id = cur.lastrowid

        if message.photo:
            await bot.send_photo(ADMIN_ID, message.photo[-1].file_id,
                caption=f"🆕 Yeni Destek\nTicket: `{ticket_id}`\nUser: `{uid}` (@{uname})\n\n{content}")
        else:
            await bot.send_message(ADMIN_ID,
                f"🆕 Yeni Destek\nTicket: `{ticket_id}`\nUser: `{uid}` (@{uname})\n\n{message.text}")

        await message.answer("✅ Talebiniz admin'e iletildi.")
        user_states[uid] = None
        return

    if uid == ADMIN_ID and uid in admin_states:
        state = admin_states[uid]

        if state == "broadcast":
            cur.execute("SELECT user_id FROM users")
            users = [row[0] for row in cur.fetchall()]
            success = 0
            for user_id in users:
                try:
                    if message.photo:
                        await bot.send_photo(user_id, message.photo[-1].file_id, caption=message.caption or "📢 Duyuru")
                    else:
                        await bot.send_message(user_id, f"📢 **Duyuru**\n\n{message.text}")
                    success += 1
                except:
                    continue
            await message.answer(f"✅ Duyuru {success} kişiye gönderildi.")
            admin_states.pop(uid, None)

        elif isinstance(state, tuple) and state[0] == "direct_msg":
            target_id = state[1]
            try:
                if message.photo:
                    await bot.send_photo(target_id, message.photo[-1].file_id,
                                       caption=f"👤 **Admin Mesajı**\n\n{message.caption or ''}")
                else:
                    await bot.send_message(target_id, f"👤 **Admin Mesajı**\n\n{message.text}")
                
                await message.answer(f"✅ Mesaj başarıyla `{target_id}` ID'li kullanıcıya gönderildi.")
            except Exception as e:
                await message.answer(f"❌ Mesaj gönderilemedi: {e}")
            
            admin_states.pop(uid, None)

        elif isinstance(state, tuple) and state[0] == "reply":
            target_id = state[1]
            ticket_id = state[2]
            try:
                if message.photo:
                    await bot.send_photo(target_id, message.photo[-1].file_id,
                                       caption=f"👤 **Admin Yanıtı**\n\n{message.caption or ''}")
                else:
                    await bot.send_message(target_id, f"👤 **Admin Yanıtı**\n\n{message.text}")

                cur.execute("DELETE FROM tickets WHERE id = ?", (ticket_id,))
                conn.commit()
                await message.answer(f"✅ Yanıt gönderildi ve ticket silindi.")
            except Exception as e:
                await message.answer(f"❌ Hata: {e}")
            admin_states.pop(uid, None)


async def main():
    print("🤖 İletişim Botu başlatıldı... Admin paneli için /admin yazın.")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
