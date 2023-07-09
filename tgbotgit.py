import logging
from urllib.parse import urlparse, quote
from telegram import Update, ParseMode, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, ConversationHandler
import sys
import os
import mysql.connector
import requests
import base64
from random import choice
import random
import openai
import deezepy
import stripe
from flask import Flask, request
import time
from functools import wraps
import schedule
from functools import partial

PORT = int(os.environ.get('PORT', 5000))

app = Flask(__name__)
picture_urls = [
    'https://upload.wikimedia.org/wikipedia/commons/d/dc/Young_cats.jpg',
    'https://upload.wikimedia.org/wikipedia/commons/3/38/Adorable-animal-cat-20787.jpg',
    'https://cdn.pixabay.com/photo/2014/11/30/14/11/cat-551554_640.jpg'
]
usernames = [
    #telegram usernames here
]
# Enable logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)

logger = logging.getLogger(__name__)
TOKEN = 'YOUR TOKEN HERE'
OPENAI_API_KEY = 'YOUR API KEY HERE'
openai.api_key = OPENAI_API_KEY
stripe.api_key = 'YOUR STRIPE API KEY HERE'
stripe.api_version = 'YOUR STRIPE API VERSION'

try:

    NAME = "YOUR DB NAME HERE"
    USER = "YOUR DB USER NAME HERE"
    PASSWORD = "YOUR DB PASSWORD HERE"
    HOST = "YOUR DB HOST HERE"

    mydb = mysql.connector.connect(
        host=HOST,
        user=USER,
        password=PASSWORD,
        database="YOUR DB NAME"
    )

except Exception:
    print('Unexpected error:', sys.exc_info())

# User states
WAITING_AGE, WAITING_QUESTION1, WAITING_QUESTION2, WAITING_QUESTION3, IMAGES = range(5)

mycursor = mydb.cursor()

def start(update, context):
    """Start the conversation and ask for the user's age."""
    update.message.reply_text("Type your age:")

    return WAITING_AGE

def save_answer(update, context):
    user_id = update.message.from_user.id
    answer = update.message.text

def check_age(update, context):
    """Check the user's age and proceed to ask the next questions."""
    age = int(update.message.text)

    if age >= 18:
        context.user_data['age'] = age
        update.message.reply_text("Answer couple of questions")
        update.message.reply_text("Do you like chocolate? Reply with 'yes' or 'no'")

        return WAITING_QUESTION1
    else:
        update.message.reply_text("You must be at least 18 to use our platform")
        return ConversationHandler.END

def ask_question1(update, context):
    """Ask the first question and wait for the answer."""
    answer = update.message.text.lower()

    if answer == 'yes':
        context.user_data['chocolate'] = True
    else:
        context.user_data['chocolate'] = False

    update.message.reply_text("Do you like country music? Reply with 'yes' or 'no'")

    return WAITING_QUESTION2

def ask_question2(update, context):
    """Ask the second question and wait for the answer."""
    answer = update.message.text.lower()

    if answer == 'yes':
        context.user_data['country'] = True
    else:
        context.user_data['country'] = False

    update.message.reply_text("Do you like James Bond movies? Reply with 'yes' or 'no'")

    return WAITING_QUESTION3

def ask_question3(update, context):
    """Ask the third question, display the collected information, and end the conversation."""
    answer = update.message.text.lower()
    update.message.reply_text("Type /image to see some pictures")
    update.message.reply_text("Type /pay to get a premium subscription and be able to see contacts")
    update.message.reply_text("Type /cancel to stop this bot or ask any question so our assistant can answer it")

    if answer == 'yes':
        context.user_data['Bond'] = True
    else:
        context.user_data['Bond'] = False

    age = context.user_data['age']
    interest_sports = context.user_data['chocolate']
    interest_music = context.user_data['country']
    prefer_books = context.user_data['Bond']

    user_id = update.message.from_user.id
    user = update.message.from_user
    username = user.username

    mycursor = mydb.cursor()
    sql = "INSERT INTO feedback (user_id, username, answer) VALUES (%s, %s, %s)"
    val = (user_id, username, str(context.user_data))
    mycursor.execute(sql, val)
    mydb.commit()

    return ConversationHandler.END

def send_image(update, context):
    user_id = update.message.from_user.id
    photo_url = choice(picture_urls)
    context.bot.send_photo(chat_id=user_id, photo=photo_url)

def cancel(update, context):
    """Cancel the conversation."""
    update.message.reply_text('Conversation canceled.')

    return ConversationHandler.END

def handle_message(update, context):
    """Handle user messages and generate AI response."""
    message = update.message.text
    ai_response = generate_ai_response(message)
    update.message.reply_text(ai_response)

def generate_ai_response(message):
    """Generate an AI response using OpenAI ChatGPT API."""
    response = openai.Completion.create(
        engine='text-davinci-003',
        prompt=message,
        max_tokens=100,
        n=1,
        stop=None,
        temperature=0.7
    )
    ai_response = response.choices[0].text.strip()
    return ai_response

def requires_permission(func):
    @wraps(func)
    def wrapper(update, context):
        user = update.message.from_user
        username = user.username
        mycursor.execute("SELECT is_subscription FROM subscription WHERE username = %s", (username,))
        result = mycursor.fetchone()
        print(result)

        if result and result[0] == 1:
            # User has permission, execute the function
            return func(update, context)
        else:
            # User does not have permission, deny access
            update.message.reply_text("You don't have access to contacts yet. Pay first.")

    return wrapper

@requires_permission    
def send_random_user_id(update, context):
    randUser = random.choice(usernames)

    if randUser is not None:
        # Create the contact link
        contact_link = f"https://t.me/{randUser}"
        update.message.reply_text(f"You can contact the user using this link: {contact_link}")
    else:
        update.message.reply_text("Sorry, no usernames are available.")     

def start_payment(update, context):
    # Create the Checkout Session
    user = update.message.from_user
    username = user.username
    try:
        # Check if the user already has an active subscription
        mycursor.execute("SELECT is_subscription FROM subscription WHERE username = %s", (username,))
        result = mycursor.fetchone()

        if result is not None and result[0] == 1:
            update.message.reply_text("You already have an active subscription.")
            return

    except Exception as e:
        logger.error('Failed to fetch subscription information from the database: %s', str(e))

    session = stripe.checkout.Session.create(
        payment_method_types=['card'],
        line_items=[
            {
                'price': 'YOUR PRODUCT PRICE ID',
                'quantity': 1,
            },
        ],
        mode='payment',
        success_url='https://yourwebsite.com/success',
        cancel_url='https://yourwebsite.com/cancel',
    )
    # Get the URL for the Checkout Session
    payment_url = session.url
    # Send the payment URL back to the user
    update.message.reply_text(f"You can proceed with the payment by clicking on this link: {payment_url}")    
    user_id = update.message.from_user.id
    user = update.message.from_user
    username = user.username
    customer_details = session.get('customer_details')
    if customer_details is not None:
        email = customer_details.get('email')
    session_id = session['id']

    while True:
        session = stripe.checkout.Session.retrieve(session_id)
        if session.payment_status == 'paid':
            logger.info('Payment is successful')
            try:
                sql = "INSERT INTO subscription (user_id, session_id, metadata, username, is_subscription) VALUES (%s, %s, %s, %s, %s)"
                val = (user_id, session.id, str(session.metadata), username, True)
                mycursor.execute(sql, val)
                mydb.commit()
                logger.info('Payment information stored in the database')
            except Exception as e:
                logger.error('Failed to store payment information in the database: %s', str(e))
            break
        elif session.payment_status == 'unpaid':
            # Wait for 10 second before checking again
            time.sleep(10)
        else:
            logger.error('Payment is not yet completed. Payment status: %s', session.payment_status)
            if session.payment_status == 'requires_payment_method':
                logger.error('Payment requires a valid payment method.')
            elif session.payment_status == 'requires_action':
                logger.error('Payment requires user action.')
            else:
                logger.error('Unexpected payment status.')
            return

def send_notification(bot_token, chat_id, message):
    chat_id = 'YOUR CHAT ID'
    url = f'https://api.telegram.org/bot{bot_token}/sendMessage'
    payload = {
        'chat_id': chat_id,
        'text': message
    }
    response = requests.post(url, json=payload)
    if response.status_code == 200:
        print('Notification sent successfully.')
    else:
        print('Failed to send notification.')

def send_periodic_notification():
    bot_token = TOKEN
    chat_id = 'YOUR CHAT ID'
    message = 'Do not forget about our /contact function;)'
    send_notification(bot_token, chat_id, message)         

def main():
    """Start the bot."""
    # Create the Updater and pass it your bot's token
    updater = Updater(TOKEN, use_context=True)
    # Get the dispatcher to register handlers
    dp = updater.dispatcher
    # Create a ConversationHandler with states and handlers
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            WAITING_AGE: [MessageHandler(Filters.regex(r'^\d+$'), check_age)],
            WAITING_QUESTION1: [MessageHandler(Filters.regex(r'^yes|no$'), ask_question1)],
            WAITING_QUESTION2: [MessageHandler(Filters.regex(r'^yes|no$'), ask_question2)],
            WAITING_QUESTION3: [MessageHandler(Filters.regex(r'^yes|no$'), ask_question3)],
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    # Add the ConversationHandler to the dispatcher
    dp.add_handler(conv_handler)
    dp.add_handler(CommandHandler("image", send_image))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))
    dp.add_handler(CommandHandler("contact", send_random_user_id))
    dp.add_handler(CommandHandler("pay", start_payment))

    # Start the Bot
    updater.start_webhook(listen="0.0.0.0", port=int(PORT), url_path=TOKEN)
    updater.bot.setWebhook('YOUR HEROKU APP URL' + TOKEN)

    schedule.every(14400).seconds.do(send_periodic_notification)
    while True:
        schedule.run_pending()
        time.sleep(1)

    updater.idle()

if __name__ == '__main__':
    main()  