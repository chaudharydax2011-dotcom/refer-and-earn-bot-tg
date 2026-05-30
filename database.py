import aiosqlite
from datetime import datetime

DB_NAME = "/data/bot_database.db"

async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('''CREATE TABLE IF NOT EXISTS users (
            telegram_id INTEGER PRIMARY KEY,
            first_name TEXT,
            balance REAL DEFAULT 0.0,
            total_earned REAL DEFAULT 0.0,
            total_withdrawn REAL DEFAULT 0.0,
            referrals INTEGER DEFAULT 0,
            upi_id TEXT DEFAULT 'Not Set',
            last_task_time TIMESTAMP,
            join_date TIMESTAMP
        )''')
        await db.execute('''CREATE TABLE IF NOT EXISTS withdrawals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER,
            amount REAL,
            upi_id TEXT,
            status TEXT DEFAULT 'Pending'
        )''')
        await db.commit()

async def get_user(telegram_id):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
        return await cursor.fetchone()

async def add_user(telegram_id, first_name):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT OR IGNORE INTO users (telegram_id, first_name, join_date) VALUES (?, ?, ?)",
            (telegram_id, first_name, datetime.now())
        )
        await db.commit()

async def update_balance(telegram_id, amount):
    async with aiosqlite.connect(DB_NAME) as db:
        if amount > 0:
            await db.execute("UPDATE users SET balance = balance + ?, total_earned = total_earned + ? WHERE telegram_id = ?", (amount, amount, telegram_id))
        else:
            await db.execute("UPDATE users SET balance = balance + ? WHERE telegram_id = ?", (amount, telegram_id))
        await db.commit()

async def update_referral(referrer_id):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE users SET referrals = referrals + 1 WHERE telegram_id = ?", (referrer_id,))
        await db.commit()

async def update_upi(telegram_id, upi_id):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE users SET upi_id = ? WHERE telegram_id = ?", (upi_id, telegram_id))
        await db.commit()

async def update_task_time(telegram_id, time):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE users SET last_task_time = ? WHERE telegram_id = ?", (time, telegram_id))
        await db.commit()

async def add_withdrawal(telegram_id, amount, upi_id):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT INTO withdrawals (telegram_id, amount, upi_id) VALUES (?, ?, ?)", (telegram_id, amount, upi_id))
        await db.commit()
