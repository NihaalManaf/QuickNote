from telegram import Bot, Update
from telegram.ext import *
import re
from datetime import datetime
import traceback
from pymongo import MongoClient
import os
import vertexai
from vertexai.generative_models import GenerativeModel, Part
from google.cloud import storage
import openai
import pdfplumber
from dotenv import load_dotenv, dotenv_values
import cv2
import yt_dlp as youtube_dl
from youtube_transcript_api import YouTubeTranscriptApi
import prompts
from moviepy.editor import VideoFileClip
import math
import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import pdfkit
from PyPDF2 import PdfReader, PdfWriter, PdfFileReader
import time, logging
from concurrent.futures import ThreadPoolExecutor, as_completed

load_dotenv()
TOKEN = os.getenv('telegram_token')
bot = Bot(TOKEN)
BOT_USERNAME = "@QuickNoteSGbot"

load_dotenv()
project_id = os.getenv('project_id')
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = 'service_account.json'
storage_client = storage.Client()
location = 'asia-southeast1'
bucket_name = os.getenv('bucket_name')

vertexai.init(project=project_id, location=location)

#Back end functions -------------------------
def generate_qns_googleapi(prompt, data_type, file) -> str:
    vision_model = GenerativeModel("gemini-1.0-pro-vision")
    response = vision_model.generate_content(
        [
            Part.from_uri(
                "gs://"+ bucket_name +"/"+ file, mime_type=data_type
            ),
            prompt,
        ]
    )
    return response

def upload_blob(bucket_name, source_file_name):
    """Uploads a file to the bucket."""
    bucket = storage_client.get_bucket(bucket_name)
    blob = bucket.blob(source_file_name)

    blob.upload_from_filename(source_file_name)

    print(
        "File {} uploaded to {}.".format(
            source_file_name, source_file_name
        )
    )

def delete_blob(bucket_name, blob_name):
    """Deletes a blob from the bucket."""
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(blob_name)

    blob.delete()

    print(f"Blob {blob_name} deleted.")

def get_youtube_video_id(url):
    # Extract video ID from URL
    regex = r'(?:youtube\.com\/(?:[^\/\n\s]+\/\s*[^\/\n\s]+\/|(?:v|e(?:mbed)?)\/|.*[?&]v=)|youtu\.be\/)([^"&?\/\s]{11})'
    match = re.search(regex, url)
    return match.group(1) if match else None

def get_transcript(video_url):
    video_id = get_youtube_video_id(video_url)
    if video_id:
        try:
            transcript = YouTubeTranscriptApi.get_transcript(video_id)
            for entry in transcript:
                print(f"Time: {entry['start']} - Text: {entry['text']}")
        except Exception as e:
            print("An error occurred:", e)
    else:
        print("Invalid YouTube URL")

def download_video(video_url):
    ydl_opts = {
        'format': 'worst', 
        'outtmpl': 'set.%(ext)s',  
    }

    with youtube_dl.YoutubeDL(ydl_opts) as ydl:
        ydl.download([video_url])
    
    clip_length = 120  # 2 minutes
    video = VideoFileClip('set.mp4')
    video_length = int(video.duration)
    num_clips = math.ceil(video_length / clip_length)

    for i in range(num_clips):
        start_time = i * clip_length
        end_time = min((i + 1) * clip_length, video_length)
        clip = video.subclip(start_time, end_time)
        clip.write_videofile(f"{'set.mp4'}_clip_{i+1}.mp4", codec="libx264", audio_codec="aac")
        clips.append(f"{'set.mp4'}_clip_{i+1}.mp4")

def extract_frames(video_path, interval):
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS) 
    frame_interval = int(fps * interval)

    frame_count = 0
    saved_frame_count = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if frame_count % frame_interval == 0:
            filename = f'frame_{saved_frame_count}.jpg'
            cv2.imwrite(filename, frame)
            saved_frame_count += 1

        frame_count += 1

    cap.release()

def extract_text_from_pdf(pdf_path):
    text = ''
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text += page.extract_text()
    return text

def split_pdf(input_pdf):
    pdf_reader = PdfReader(input_pdf)

    for i in range(len(pdf_reader.pages)):
        pdf_writer = PdfWriter()
        pdf_writer.add_page(pdf_reader.pages[i])

        with open(f"page_{i + 1}.pdf", "wb") as output_pdf:
            pdf_writer.write(output_pdf)
            pdfs.append(f"page_{i + 1}.pdf")

def compilationcontent(video_url, clips):
    prompt = "Provide as much information as possible from the video that is revelant."
    context = ""
    download_video(video_url)
    for clip in clips: 
        upload_blob(bucket_name, clip)
        context = generate_qns_googleapi(prompt, 'video/mp4', clip).text + context
        delete_blob(bucket_name, clip)
        os.remove(clip)
    os.remove('set.mp4')
    return context

def contexttoQns(context, quantity, type):
    
    if type == 'flashcard':
        prompt = prompts.flashcard
    else:
        prompt = prompts.question_paper

    vision_model = GenerativeModel("gemini-1.0-pro-vision")
    context = context + prompt + quantity
    response = vision_model.generate_content(context).text
    return response

def upload_file(file):
    try:
        upload_blob(bucket_name, file)
        return file
    except Exception as e:
        logging.error(f"Error uploading {file}: {e}")
        return None

def make_api_request(file, prompt):
    try:
        text = generate_qns_googleapi("Extract as much information as possible", 'application/pdf', file).text
        print(text)
        return text
    except Exception as e:
        logging.error(f"Error in API request for {file}: {e}")
        return ""

def delete_file(file):
    delete_blob(bucket_name, file)
    os.remove(file)

def pdftoQns(quantity, type, name):
    if type == 'flashcard':
        prompt = "tell me all the historical and logical errors from this text"
    else:
        prompt = prompts.question_paper
    
    split_pdf(name + '.pdf')
    
    # Upload files in parallel
    with ThreadPoolExecutor() as executor:
        futures = [executor.submit(upload_file, pdf) for pdf in pdfs]
        uploaded_files = [future.result() for future in as_completed(futures)]

    print("upload done")

    # Make API requests in parallel
    with ThreadPoolExecutor(max_workers= 8) as executor:
        futures = []
        for file in uploaded_files:
            if file is not None:
                future = executor.submit(make_api_request, file, prompt)
                futures.append(future)
                time.sleep(1)  # Wait for 0.5 seconds before starting the next thread

        contexts = [future.result() for future in as_completed(futures)]
        full_context = ''.join(contexts)
    
    print("deleting files now")

    print(contexttoQns(full_context, quantity, type).text)

    # Delete files
    with ThreadPoolExecutor() as executor:
        futures = [executor.submit(delete_file, pdf) for pdf in pdfs]

def websitetopdf():
    link = input("Enter the website URL: ")
    type = input("What type of questions do you want? (flashcard or question_paper): ")
    quantity = input("How many questions do you want? ")
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")

    # Initialize Selenium WebDriver with headless Chrome
    browser = webdriver.Chrome(options=chrome_options)
    browser.get(link)

    # Saving page HTML to a variable
    html = browser.page_source

    #Ignoring load errors due to bad request / no access to certain resources
    options = {
    'load-error-handling': 'ignore',
    'enable-local-file-access': '' 
    }
    # Saving HTML to PDF
    pdfkit.from_string(html, 'test.pdf', options=options)
    pdftoQns(quantity, type, 'test')
    os.remove('test.pdf')

    # Close the browser
    browser.quit()

async def linktoqns(link, quantity, type):
    clips = []
    print("Downloading video")
    content = compilationcontent(link, clips)
    return contexttoQns(content, quantity, type)

#Start and basic Commands -------------------
         
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Hello! Welcome to QuickNote. We are still in development.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("This is the help command.")
    
#Conversation Handlers ---------------------

LINK, TYPE, QNTY, RETURNQNS = range(4)
user_data = {}

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
    await update.message.reply_text(linktoqns(link,quantity, content_type))
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
    app.add_handler(conv_handler)

    #Messages ----------------------------------------------------------------------------------------------------
    app.add_handler(MessageHandler(filters.TEXT, handle_message))

    #Errors ----------------------------------------------------------------------------------------------------
    app.add_error_handler(error_handler)

    print("Polling...")
    app.run_polling(poll_interval=3) 