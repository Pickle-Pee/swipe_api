import os

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackQueryHandler
import logging
# Импортируйте любые дополнительные библиотеки или модули, необходимые для взаимодействия с вашей базой данных или API

# Настройка логгирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
    )

# Токен вашего бота
TOKEN = 'YOUR_TOKEN_HERE'


def start(update, context):
    update.message.reply_text('Пожалуйста, отправьте фото для профиля и селфи для верификации.')


def photo(update, context):
    user_id = update.message.from_user.id
    first_name = update.message.from_user.first_name

    # Сохраните фотографии, и передайте их вместе с user_id и first_name на ваше API

    # PSEUDOCODE: Передайте фото и информацию о пользователе на ваше API
    # response = requests.post(YOUR_API_ENDPOINT, data={"user_id": user_id, "first_name": first_name, "photos": photos})

    keyboard = [
        [
            InlineKeyboardButton("Подтвердить", callback_data='true'),
            InlineKeyboardButton("Отклонить", callback_data='false')
        ]
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    update.message.reply_text('Выберите действие:', reply_markup=reply_markup)


def button(update, context):
    query = update.callback_query

    # Обновите флаг верификации в вашей базе данных в соответствии с выбором администратора
    # PSEUDOCODE: Обновите статус верификации в базе данных
    # response = requests.patch(YOUR_API_ENDPOINT, data={"user_id": user_id, "verification_status": query.data})

    query.edit_message_text(text=f"Выбрано: {query.data}")


def main():
    updater = Updater(token=TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler('start', start))
    dp.add_handler(MessageHandler(Filters.photo, photo))
    dp.add_handler(CallbackQueryHandler(button))

    updater.start_polling()
    updater.idle()


if __name__ == "__main__":
    import uvicorn

    app_host = os.getenv("MAIN_APP_HOST")
    uvicorn.run(host=app_host, port=1027)