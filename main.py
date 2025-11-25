import os
import asyncio
from dotenv import load_dotenv

from telebot.types import (
    KeyboardButton, 
    ReplyKeyboardMarkup, 
    InlineKeyboardMarkup, 
    InlineKeyboardButton
)
from telebot.async_telebot import AsyncTeleBot

from database import (
    get_user, add_user, update_user, init_db, 
    create_request, accept_request, claim_request, claim_refund,
    get_pool
)

load_dotenv()
API_TOKEN = os.getenv("API_TOKEN")
print("Token type:", type(API_TOKEN))
print("Token length:", len(str(API_TOKEN)) if API_TOKEN else 0)
print("Token first 5:", API_TOKEN[:5] if API_TOKEN else "None")
print("Token contains colon:", ":" in str(API_TOKEN) if API_TOKEN else False)
if not API_TOKEN:
    raise RuntimeError("API_TOKEN is missing. Set it in your environment or .env file.")

bot = AsyncTeleBot(API_TOKEN)

# State management
user_states = {}

# ==================== MENU HELPERS ====================

def get_main_menu():
    """Returns the main menu keyboard"""
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    keyboard.add(
        KeyboardButton("🔍 View Requests"),
        KeyboardButton("➕ Create Request")
    )
    keyboard.add(
        KeyboardButton("📋 My Activity"),
        KeyboardButton("💰 Check Credits")
    )
    keyboard.add(KeyboardButton("❓ Click here to understand how to use me"))
    return keyboard

def get_activity_menu():
    """Returns the My Activity submenu"""
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    keyboard.add(
        KeyboardButton("📤 Requests I Made"),
        KeyboardButton("📥 Requests I Accepted")
    )
    keyboard.add(KeyboardButton("⬅️ Back to Menu"))
    return keyboard

def get_cancel_menu():
    """Returns a menu with just Cancel button"""
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    keyboard.add(KeyboardButton("❌ Cancel"))
    return keyboard

def get_contact_keyboard():
    """Returns keyboard asking for contact"""
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    button = KeyboardButton(text="📱 Send my info", request_contact=True)
    keyboard.add(button)
    return keyboard

# ==================== START & REGISTRATION ====================

@bot.message_handler(commands=['start'])
async def send_welcome(message):
    telegram_id = message.from_user.id
    
    # Check if user already exists
    user = await get_user(telegram_id)
    
    if user:
        # User exists, go straight to main menu
        await bot.send_message(
            message.chat.id,
            f"Welcome back, {user['name']}! 👋\n\nWhat would you like to do?",
            reply_markup=get_main_menu()
        )
    else:
        # New user, ask for contact
        first = message.from_user.first_name or ""
        last = message.from_user.last_name or ""
        
        await add_user(telegram_id, f"{first} {last}".strip(), 3.0, None)
        
        await bot.send_message(
            message.chat.id,
            "🏦 Welcome to TimeBank Bot!\n\n"
            "TimeBank is a community exchange platform where you can:\n"
            "• Request help and spend time credits\n"
            "• Help others and earn time credits\n"
            "• Everyone starts with 3.0 credits!\n\n"
            "Please share your contact info to get started.",
            reply_markup=get_contact_keyboard()
        )

@bot.message_handler(content_types=['contact'])
async def handle_contact(message):
    contact = message.contact
    telegram_id = message.from_user.id
    
    first = contact.first_name or ""
    last = contact.last_name or ""
    phone_number = contact.phone_number
    
    await update_user(telegram_id, name=f"{first} {last}".strip(), phone_number=phone_number)
    
    await bot.send_message(
        message.chat.id,
        "✅ Thanks! Your contact info has been saved.\n\n"
        "You've been credited with 3.0 hours to start! 🎉",
        reply_markup=get_main_menu()
    )

# ==================== MAIN MENU HANDLERS ====================

@bot.message_handler(func=lambda m: m.text == "🔍 View Requests")
async def view_requests(message):
    chat_id = message.chat.id
    telegram_id = message.from_user.id
    
    pool = await get_pool()
    async with pool.acquire() as conn:
        requests = await conn.fetch(
            "SELECT r.request_id, r.title, r.description, r.hours, u.name "
            "FROM requests r "
            "JOIN users u ON r.requester_id = u.telegram_id "
            "WHERE r.open = TRUE AND r.requester_id != $1",
            telegram_id
        )
    
    if not requests:
        await bot.send_message(
            chat_id,
            "No open requests available right now. 🤷\n\n"
            "Try creating one!",
            reply_markup=get_main_menu()
        )
        return
    
    # Create message with inline buttons for each request
    for req in requests:
        req_id = req['request_id']
        title = req['title']
        desc = req['description']
        hours = req['hours']
        requester = req['name']
        
        text = (
            f"📋 *{title}*\n"
            f"Requested by: {requester}\n"
            f"Hours: {hours}\n\n"
            f"{desc}"
        )
        
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton(
            f"✅ Accept Request #{req_id}",
            callback_data=f"accept:{req_id}"
        ))
        
        await bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=markup)
    
    await bot.send_message(
        chat_id,
        "👆 Tap a button above to accept a request!",
        reply_markup=get_main_menu()
    )

@bot.message_handler(func=lambda m: m.text == "➕ Create Request")
async def start_create_request(message):
    chat_id = message.chat.id
    user_states[chat_id] = {'flow': 'awaiting_title', 'data': {}}
    
    await bot.send_message(
        chat_id,
        "Let's create a request! 📝\n\n"
        "What is the *title* of your request?\n"
        "For example: 'Need company at doctor's appointment' or 'Looking for a math tutor'",
        parse_mode="Markdown",
        reply_markup=get_cancel_menu()
    )

@bot.message_handler(func=lambda m: m.text == "📋 My Activity")
async def my_activity(message):
    await bot.send_message(
        message.chat.id,
        "What would you like to view?",
        reply_markup=get_activity_menu()
    )

@bot.message_handler(func=lambda m: m.text == "💰 Check Credits")
async def check_credits(message):
    telegram_id = message.from_user.id
    user = await get_user(telegram_id)
    
    if user:
        credits = user['credits']
        await bot.send_message(
            message.chat.id,
            f"💰 Your current balance:\n*{credits:.1f} time credits*",
            parse_mode="Markdown",
            reply_markup=get_main_menu()
        )
    else:
        await bot.send_message(
            message.chat.id,
            "❌ User not found. Please /start again.",
            reply_markup=get_main_menu()
        )

@bot.message_handler(func=lambda m: m.text == "❓ Click here to understand how to use me")
async def show_help(message):
    help_text = (
        "🏦 *TimeBank Bot Help*\n\n"
        "*How it works:*\n"
        "1️⃣ Everyone starts with 3.0 time credits\n"
        "2️⃣ Create a request → credits deducted immediately\n"
        "3️⃣ Accept someone's request → help them out\n"
        "4️⃣ Claim completion → earn credits!\n\n"
        "*Menu Options:*\n"
        "🔍 *View Requests* - See available help requests\n"
        "➕ *Create Request* - Ask for help\n"
        "📋 *My Activity* - Manage your requests by cancelling or viewing them\n"
        "💰 *Check Credits* - View your balance\n\n"
        "*Tips:*\n"
        "• You can't accept your own requests\n"
        "• Credits are deducted when you post\n"
        "• Credits are earned when you complete work\n"
        "• Cancel unused requests to get refunds"
    )
    
    await bot.send_message(
        message.chat.id,
        help_text,
        parse_mode="Markdown",
        reply_markup=get_main_menu()
    )

# ==================== ACTIVITY SUBMENU ====================

@bot.message_handler(func=lambda m: m.text == "📤 Requests I Made")
async def my_requests(message):
    chat_id = message.chat.id
    telegram_id = message.from_user.id
    
    pool = await get_pool()
    async with pool.acquire() as conn:
        requests = await conn.fetch(
            "SELECT request_id, title, hours, open, accepter_id, has_been_claimed, cancelled "
            "FROM requests WHERE requester_id = $1 "
            "ORDER BY created_at DESC",
            telegram_id
        )
    
    if not requests:
        await bot.send_message(
            chat_id,
            "You haven't made any requests yet.",
            reply_markup=get_activity_menu()
        )
        return

    for req in requests:
        req_id = req['request_id']
        title = req['title']
        hours = req['hours']
        open_status = req['open']
        accepter_id = req['accepter_id']
        claimed = req['has_been_claimed']
        cancelled = req['cancelled']
        
        if claimed:
            status = "✅ Completed"
            buttons = []
        elif cancelled:
            status = "❌ Cancelled"
            buttons = []
        elif open_status:
            status = "🟢 Open (waiting for help)"
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton(
                f"❌ Cancel & Refund",
                callback_data=f"refund:{req_id}"
            ))
            buttons = markup
        else:
            status = "🟡 Accepted (waiting for completion)"
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton(
                f"✅ Mark as Complete",
                callback_data=f"complete:{req_id}"
            ))
            buttons = markup
        
        text = f"📋 *{title}*\nHours: {hours}\nStatus: {status}"
        
        if buttons:
            await bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=buttons)
        else:
            await bot.send_message(chat_id, text, parse_mode="Markdown")
    
    await bot.send_message(
        chat_id,
        "👆 Manage your requests above",
        reply_markup=get_activity_menu()
    )

@bot.message_handler(func=lambda m: m.text == "📥 Requests I Accepted")
async def requests_accepted(message):
    chat_id = message.chat.id
    telegram_id = message.from_user.id
    
    pool = await get_pool()
    async with pool.acquire() as conn:
        requests = await conn.fetch(
            "SELECT request_id, title, hours, has_been_claimed "
            "FROM requests WHERE accepter_id = $1 "
            "ORDER BY accepted_at DESC",
            telegram_id
        )
    
    if not requests:
        await bot.send_message(
            chat_id,
            "You haven't accepted any requests yet.",
            reply_markup=get_activity_menu()
        )
        return
    
    for req in requests:
        req_id = req['request_id']
        title = req['title']
        hours = req['hours']
        claimed = req['has_been_claimed']
        
        if claimed:
            status = "✅ Claimed (credits received)"
            buttons = None
        else:
            status = "⏳ Pending (claim when done)"
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton(
                f"💰 Claim {hours} Credits",
                callback_data=f"claim:{req_id}"
            ))
            buttons = markup
        
        text = f"📋 *{title}*\nHours: {hours}\nStatus: {status}"
        
        if buttons:
            await bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=buttons)
        else:
            await bot.send_message(chat_id, text, parse_mode="Markdown")
    
    await bot.send_message(
        chat_id,
        "👆 Claim your credits above",
        reply_markup=get_activity_menu()
    )

@bot.message_handler(func=lambda m: m.text == "⬅️ Back to Menu")
async def back_to_menu(message):
    await bot.send_message(
        message.chat.id,
        "Main Menu:",
        reply_markup=get_main_menu()
    )

# ==================== CREATE REQUEST FLOW ====================

@bot.message_handler(func=lambda m: m.text == "❌ Cancel")
async def cancel_operation(message):
    chat_id = message.chat.id
    if chat_id in user_states:
        user_states.pop(chat_id)
    
    await bot.send_message(
        chat_id,
        "Operation cancelled.",
        reply_markup=get_main_menu()
    )

@bot.message_handler(func=lambda m: 
    m.chat.id in user_states and 
    user_states[m.chat.id].get('flow') == 'awaiting_title'
)
async def handle_title(message):
    chat_id = message.chat.id
    user_states[chat_id]['data']['title'] = message.text.strip()
    user_states[chat_id]['flow'] = 'awaiting_description'
    
    await bot.send_message(
        chat_id,
        "Great! Now provide a *description*.\n\n"
        "When and where do you need help?",
        parse_mode="Markdown",
        reply_markup=get_cancel_menu()
    )

@bot.message_handler(func=lambda m: 
    m.chat.id in user_states and 
    user_states[m.chat.id].get('flow') == 'awaiting_description'
)
async def handle_description(message):
    chat_id = message.chat.id
    user_states[chat_id]['data']['description'] = message.text.strip()
    user_states[chat_id]['flow'] = 'awaiting_hours'
    
    await bot.send_message(
        chat_id,
        "How many *hours* do you need help for?\n\n"
        "Send a number (e.g., 2 or 1.5)",
        parse_mode="Markdown",
        reply_markup=get_cancel_menu()
    )

@bot.message_handler(func=lambda m:
    m.chat.id in user_states and
    user_states[m.chat.id].get('flow') == 'awaiting_hours'
)
async def handle_hours(message):
    chat_id = message.chat.id
    
    # Validate number
    try:
        hours = float(message.text)
        if hours <= 0:
            await bot.send_message(chat_id, "❌ Hours must be positive. Try again:")
            return
    except ValueError:
        await bot.send_message(chat_id, "❌ Please send a valid number:")
        return
    
    data = user_states.pop(chat_id)['data']
    data['hours'] = hours
    
    # Create the request
    success = await create_request(
        message.from_user.id,
        data['title'],
        data['description'],
        data['hours']
    )
    
    if success:
        await bot.send_message(
            chat_id,
            f"✅ Request created!\n\n"
            f"{data['hours']} credits have been deducted from your balance.\n"
            f"Let's wait for someone to help you out!",
            reply_markup=get_main_menu()
        )
    else:
        await bot.send_message(
            chat_id,
            f"❌ Failed to create request.\n\n"
            f"You might not have enough credits ({data['hours']} needed).\n"
            f"Check your balance with 💰 Check Credits.",
            reply_markup=get_main_menu()
        )

# ==================== INLINE BUTTON CALLBACKS ====================

@bot.callback_query_handler(func=lambda call: call.data.startswith('accept:'))
async def callback_accept(call):
    request_id = int(call.data.split(':')[1])
    telegram_id = call.from_user.id
    
    # Accept the request
    await accept_request(request_id, telegram_id)
    
    await bot.answer_callback_query(
        call.id,
        "✅ Request accepted! Complete it to earn credits."
    )
    
    await bot.edit_message_reply_markup(
        call.message.chat.id,
        call.message.message_id,
        reply_markup=None
    )
    
    await bot.send_message(
        call.message.chat.id,
        "🎉 You've accepted this request!\n\n"
        "Complete the task, then go to:\n"
        "📋 My Activity → 📥 Requests I Accepted → Claim Credits",
        reply_markup=get_main_menu()
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('claim:'))
async def callback_claim(call):
    request_id = int(call.data.split(':')[1])
    telegram_id = call.from_user.id
    
    # Verify this user is the accepter
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT accepter_id, hours FROM requests WHERE request_id = $1",
            request_id
        )
    
    if not row or row['accepter_id'] != telegram_id:
        await bot.answer_callback_query(call.id, "❌ You didn't accept this request")
        return
    
    hours = row['hours']
    success = await claim_request(request_id, telegram_id)
    
    if success:
        await bot.answer_callback_query(
            call.id,
            f"✅ {hours} credits claimed!"
        )
        
        await bot.edit_message_reply_markup(
            call.message.chat.id,
            call.message.message_id,
            reply_markup=None
        )
        
        await bot.send_message(
            call.message.chat.id,
            f"🎉 You earned {hours} time credits!\n\n"
            f"Check your new balance with 💰 Check Credits",
            reply_markup=get_main_menu()
        )
    else:
        await bot.answer_callback_query(call.id, "❌ Failed to claim")

@bot.callback_query_handler(func=lambda call: call.data.startswith('refund:'))
async def callback_refund(call):
    request_id = int(call.data.split(':')[1])
    telegram_id = call.from_user.id
    
    # Verify this user is the requester
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT requester_id, hours FROM requests WHERE request_id = $1",
            request_id
        )
    
    if not row or row['requester_id'] != telegram_id:
        await bot.answer_callback_query(call.id, "❌ This isn't your request")
        return
    
    hours = row['hours']
    success = await claim_refund(request_id)
    
    if success:
        await bot.answer_callback_query(
            call.id,
            f"✅ {hours} credits refunded"
        )
        
        await bot.edit_message_reply_markup(
            call.message.chat.id,
            call.message.message_id,
            reply_markup=None
        )
        
        await bot.send_message(
            call.message.chat.id,
            f"Request cancelled.\n{hours} credits have been returned to your account.",
            reply_markup=get_main_menu()
        )
    else:
        await bot.answer_callback_query(call.id, "❌ Failed to refund")

@bot.callback_query_handler(func=lambda call: call.data.startswith('complete:'))
async def callback_complete(call):
    request_id = int(call.data.split(':')[1])
    telegram_id = call.from_user.id
    
    # Get the accepter_id to pass to claim_request
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT accepter_id FROM requests WHERE request_id = $1",
            request_id
        )
    
    if not row or not row['accepter_id']:
        await bot.answer_callback_query(call.id, "❌ No one has accepted this request yet")
        return
    
    # Call claim_request with the accepter_id
    success = await claim_request(request_id, row['accepter_id'])
    
    if success:
        await bot.answer_callback_query(call.id, "✅ Marked as complete!")
        
        await bot.edit_message_reply_markup(
            call.message.chat.id,
            call.message.message_id,
            reply_markup=None
        )
        
        await bot.send_message(
            call.message.chat.id,
            "✅ Request marked as complete!\n\n"
            "The helper has been awarded their credits.",
            reply_markup=get_main_menu()
        )
    else:
        await bot.answer_callback_query(call.id, "❌ Failed to complete")

# ==================== MAIN ====================

async def main():
    await init_db()
    print("🏦 TimeBank Bot is running...")
    await bot.polling(non_stop=True, request_timeout=60)

if __name__ == "__main__":
    asyncio.run(main())