import requests
from telegram import InlineKeyboardMarkup, InlineKeyboardButton, Update
from telegram.ext import Updater, MessageHandler, CallbackQueryHandler, Filters, CallbackContext
import logging
from config import TG_VERIFY_KEY, TG_VERIFY_BOT_TOKEN


logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
    )

def handle_message(update: Update, context: CallbackContext) -> None:
    user_id = update.message.from_user.id
    first_name = update.message.from_user.first_name

    logging.info("Message from %s (ID: %s) received", first_name, user_id)

    if update.message.photo:
        keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("Подтвердить", callback_data='approve'),
                     InlineKeyboardButton("Отклонить", callback_data='deny')]
                ])
        update.message.reply_text('Выберите действие:', reply_markup=keyboard)

def handle_button(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()

    user_response = query.data

    user_id = update.callback_query.from_user.id

    status = 'approved' if user_response == 'approve' else 'denied'
    api_url = f"http://main_app:1024/set_verify/{user_id}"
    headers = {"Authorization": f"Bearer {TG_VERIFY_KEY}"}

    requests.post(api_url, json={"status": status}, headers=headers)
    query.edit_message_text(f"Статус обновлен: {status}")


def main():
    updater = Updater(TG_VERIFY_BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(MessageHandler(Filters.photo & ~Filters.command, handle_message))
    dp.add_handler(CallbackQueryHandler(handle_button))

    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()