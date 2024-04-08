from telegram import Bot, Update
from telegram.ext import *
import logging
import time
import re
from datetime import datetime
import traceback
from pymongo import MongoClient
import os
import Backend
from dotenv import load_dotenv, dotenv_values

load_dotenv()
TOKEN = os.getenv('telegram_token')
bot = Bot(TOKEN)
BOT_USERNAME = "@QuickNoteSGbot"

#Start and basic Commands -------------------
         
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Hello! Welcome to QuickNote. We are still in development.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("This is the help command.")
    
#Conversation Handlers ---------------------

LINK, TYPE, QNTY, RETURNQNS = range(4)

async def start_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Please enter the link to the video you want to generate questions for.")
    return LINK

async def get_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    link = update.message.text
    context.user_data['link'] = link
    await update.message.reply_text("Please enter the type of content you want to generate questions for (flashcard or Question_Paper).")
    return TYPE

async def get_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    content_type = update.message.text
    context.user_data['type'] = content_type
    await update.message.reply_text("Please enter the quantity of questions you want to generate.")
    return QNTY

async def get_quantity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    quantity = update.message.text
    context.user_data['quantity'] = quantity
    await update.message.reply_text("Generating questions...")
    return RETURNQNS

async def return_questions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    link = context.user_data['link']
    content_type = context.user_data['type']
    quantity = context.user_data['quantity']
    response = Backend.generate_questions(link,quantity, content_type)
    await update.message.reply_text(response)
    return ConversationHandler.END



#Message Handlers --------------------------  
async def handle_message(update:Update, context:ContextTypes.DEFAULT_TYPE): 
    message_type: str = update.message.chat.type #type of chat - Group or private
    text: str = update.message.text #any new message in group

    print(f'User({update.message.chat.id}) in  {message_type}: "{text}"')

    if message_type == 'supergroup':
        if BOT_USERNAME in text:
            new_text: str = text.replace(BOT_USERNAME, '').strip()
            response:str = "You're text is" + text
        else:
            return
    else:
        response:str = "You're text is" + text

    print('Bot:', response)
    await update.message.reply_text(response)

async def error_handler(update:Update, context:ContextTypes.DEFAULT_TYPE):
    trace = traceback.format_exc()
    print(f'Update {update} caused error {context.error}\nTraceback:\n{trace}')



if __name__ == "__main__":
    print("Starting bot...")
    app = ApplicationBuilder().token(TOKEN).build()

    #Commands ----------------------------------------------------------------------------------------------------
    app.add_handler(CommandHandler('start',start_command))
    app.add_handler(CommandHandler('help',help_command))

    #Conversation Handlers ----------------------------------------------------------------------------------------------------
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('generate', start_conversation)],
        states={
            LINK: [MessageHandler(filters.TEXT, get_link)],
            TYPE: [MessageHandler(filters.TEXT, get_type)],
            QNTY: [MessageHandler(filters.TEXT, get_quantity)],
            RETURNQNS: [MessageHandler(filters.TEXT, return_questions)]
        },
        fallbacks=[CommandHandler('cancel', start_command)]
    )

    #Messages ----------------------------------------------------------------------------------------------------
    app.add_handler(MessageHandler(filters.TEXT, handle_message))

    #Errors ----------------------------------------------------------------------------------------------------
    app.add_error_handler(error_handler)

    print("Polling...")
    app.run_polling(poll_interval=3) 