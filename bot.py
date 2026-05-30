import os
import uuid
import logging
import aiohttp
from datetime import datetime, timedelta
from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from database import init_db, get_user, add_user, update_balance, update_referral, update_upi, update_task_time, add_withdrawal

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
BOT_USERNAME = os.getenv("BOT_USERNAME")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
AROLINKS_API_KEY = os.getenv("AROLINKS_API_KEY")

CHANNELS = [
    {"id": os.getenv("PUBLIC_CHANNEL_ID"), "link": os.getenv("PUBLIC_CHANNEL_LINK")},
    {"id": os.getenv("PRIVATE_CHANNEL_ID"), "link": os.getenv("PRIVATE_CHANNEL_LINK")}
]

# Temporary memory
active_tasks = {}
user_states = {}

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# ==================== HELPER FUNCTIONS ====================

async def check_force_join(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user_id = update.effective_user.id
    not_joined = []

    for ch in CHANNELS:
        try:
            member = await context.bot.get_chat_member(chat_id=ch["id"], user_id=user_id)
            if member.status in ['left', 'kicked']:
                not_joined.append(ch["link"])
        except Exception as e:
            logging.error(f"Force join check error on {ch['id']}: {e}")
            not_joined.append(ch["link"])

    if not_joined:
        keyboard = [[InlineKeyboardButton(f"📢 Join Channel {i+1}", url=link)] for i, link in enumerate(not_joined)]
        keyboard.append([InlineKeyboardButton("✅ Joined (Check Again)", callback_data="check_join")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        msg = "⚠️ **Bot use karne ke liye hamare channels join karna zaroori hai!**\nJoin karke 'Joined' pe click karein."
        
        if update.callback_query:
            await update.callback_query.message.reply_text(msg, reply_markup=reply_markup, parse_mode='Markdown')
        else:
            await update.message.reply_text(msg, reply_markup=reply_markup, parse_mode='Markdown')
        return False
    return True

async def generate_arolink(long_url: str) -> str:
    api_url = f"https://arolinks.com/api?api={AROLINKS_API_KEY}&url={long_url}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(api_url) as response:
                data = await response.json()
                if data.get("status") == "success":
                    return data.get("shortenedUrl")
    except Exception as e:
        logging.error(f"Arolinks API Error: {e}")
    return None

def get_main_keyboard():
    return ReplyKeyboardMarkup([
        ["👤 Profile", "👥 Refer & Earn"],
        ["💰 Earn Tasks", "💸 Withdraw"],
        ["🏦 Set UPI", "📞 Support"]
    ], resize_keyboard=True)

# ==================== MAIN HANDLERS ====================

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_force_join(update, context):
        return

    user = update.effective_user
    args = context.args
    db_user = await get_user(user.id)

    if not db_user:
        await add_user(user.id, user.first_name)
        
        # New User Referral Check
        if args and args[0].startswith("ref_"):
            referrer_id = int(args[0].split("_")[1])
            if referrer_id != user.id:  # Anti-self refer
                await update_balance(referrer_id, 10.0)
                await update_referral(referrer_id)
                try:
                    await context.bot.send_message(chat_id=referrer_id, text=f"🎉 **New Referral!**\n{user.first_name} ne aapke link se join kiya. ₹10 added!", parse_mode='Markdown')
                except:
                    pass

    # Task Verification Check
    if args and args[0].startswith("task_"):
        token = args[0]
        if token in active_tasks and active_tasks[token] == user.id:
            del active_tasks[token]
            await update_balance(user.id, 20.0)
            
            await update.message.reply_text("✅ **Task Verified!**\nAapke wallet me ₹20 add ho gaye hain.", parse_mode='Markdown')
            return
        else:
            await update.message.reply_text("❌ Yeh task link invalid hai ya expire ho chuka hai.")
            return

    await update.message.reply_text(f"Welcome {user.first_name}! 👋\nChoose an option:", reply_markup=get_main_keyboard())

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "check_join":
        if await check_force_join(update, context):
            await query.message.delete()
            await query.message.reply_text("✅ Verification successful! /start type karein.")

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text

    if not await check_force_join(update, context):
        return

    # Handle Set UPI State
    if user_states.get(user_id) == "WAITING_FOR_UPI":
        if "@" in text:
            await update_upi(user_id, text)
            del user_states[user_id]
            await update.message.reply_text(f"✅ UPI ID Saved Successfully: `{text}`", parse_mode='Markdown', reply_markup=get_main_keyboard())
        else:
            await update.message.reply_text("❌ Invalid UPI ID. Please send a valid UPI (e.g. yourname@ybl) or /cancel.")
        return

    db_user = await get_user(user_id)

    if text == "👤 Profile":
        profile_text = (
            f"👤 **Profile Info**\n\n"
            f"🆔 ID: `{user_id}`\n"
            f"💰 Balance: ₹{db_user[2]}\n"
            f"📈 Total Earned: ₹{db_user[3]}\n"
            f"💸 Total Withdrawn: ₹{db_user[4]}\n"
            f"👥 Referrals: {db_user[5]}\n"
            f"🏦 UPI ID: `{db_user[6]}`"
        )
        await update.message.reply_text(profile_text, parse_mode='Markdown')

    elif text == "👥 Refer & Earn":
        ref_link = f"https://t.me/{BOT_USERNAME}?start=ref_{user_id}"
        await update.message.reply_text(
            f"🎁 **Refer & Earn Program**\n\n"
            f"Har naye user ko invite karne par ₹10 milenge.\n\n"
            f"🔗 **Aapka Referral Link:**\n`{ref_link}`",
            parse_mode='Markdown'
        )

    elif text == "💰 Earn Tasks":
        # Check 24-hour cooldown
        if db_user[7]:
            last_time = datetime.strptime(db_user[7], "%Y-%m-%d %H:%M:%S.%f")
            if datetime.now() < last_time + timedelta(hours=24):
                time_left = (last_time + timedelta(hours=24)) - datetime.now()
                hours, remainder = divmod(time_left.seconds, 3600)
                minutes, _ = divmod(remainder, 60)
                await update.message.reply_text(f"⏳ **Cooldown Active!**\nNaya task {hours}h {minutes}m ke baad milega.")
                return

        processing_msg = await update.message.reply_text("🔄 Task generate ho raha hai, please wait...")
        
        task_token = f"task_{uuid.uuid4().hex[:8]}"
        active_tasks[user_id] = task_token 
        deep_link = f"https://t.me/{BOT_USERNAME}?start={task_token}"
        
        short_link = await generate_arolink(deep_link)
        
        if short_link:
            await processing_msg.edit_text(
                text=(
                    f"🎯 **New Task Available! (₹20)**\n\n"
                    f"1. Niche diye link par click karein.\n"
                    f"2. Ads skip karke final page tak pahunche.\n"
                    f"3. Wapas bot me redirect hone par reward milega!\n\n"
                    f"🔗 Link: {short_link}"
                ),
                parse_mode='Markdown'
            )
            await update_task_time(user_id, datetime.now())
        else:
            await processing_msg.edit_text("❌ API error! Baad me try karein.")

    elif text == "🏦 Set UPI":
        user_states[user_id] = "WAITING_FOR_UPI"
        await update.message.reply_text("🏦 Apni valid UPI ID type karke bhejein:")

    elif text == "💸 Withdraw":
        if db_user[6] == 'Not Set':
            await update.message.reply_text("❌ Pehle '🏦 Set UPI' me jake apni UPI ID save karein.")
            return
        if db_user[2] < 100:
            await update.message.reply_text(f"❌ Minimum withdrawal ₹100 hai.\nAapka balance: ₹{db_user[2]}")
            return
        
        amount = db_user[2]
        await update_balance(user_id, -amount) # Deduct balance
        await add_withdrawal(user_id, amount, db_user[6])
        
        # Notify Admin
        admin_text = f"🚨 **New Withdrawal Request**\n\nUser ID: `{user_id}`\nAmount: ₹{amount}\nUPI: `{db_user[6]}`"
        await context.bot.send_message(chat_id=ADMIN_ID, text=admin_text, parse_mode='Markdown')
        
        await update.message.reply_text(f"✅ Withdrawal of ₹{amount} requested successfully! Admin 24-48 hours me approve karenge.")

    elif text == "📞 Support":
        await update.message.reply_text("📞 Contact admin for support: @YourSupportUsername")

async def cancel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in user_states:
        del user_states[user_id]
    await update.message.reply_text("❌ Action cancelled.", reply_markup=get_main_keyboard())

# ==================== APP RUNNER ====================

# ==================== APP RUNNER ====================

# Yeh function bot start hone se pehle DB banayega
async def setup_db(application: Application):
    await init_db()
    print("Database Initialized successfully!")

def main():
    # Application build karte waqt 'post_init' me setup_db pass karenge
    app = Application.builder().token(BOT_TOKEN).post_init(setup_db).build()

    # Handlers add karein
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("cancel", cancel_cmd))
    app.add_handler(CallbackQueryHandler(callback_handler, pattern="^check_join$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    print("Bot is starting...")
    
    # Sync polling start karein
    app.run_polling()

if __name__ == '__main__':
    main()