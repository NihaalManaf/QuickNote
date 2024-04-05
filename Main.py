import openai
import os
import re
import pdfplumber
from dotenv import load_dotenv, dotenv_values
import cv2
import youtube_dl
from youtube_transcript_api import YouTubeTranscriptApi
import vertexai
from vertexai.generative_models import GenerativeModel, Part
from google.cloud import storage
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
openai.api_key = os.getenv('openAI_token')
project_id = os.getenv('project_id')
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = 'service_account.json'
storage_client = storage.Client()
location = 'asia-southeast1'
bucket_name = os.getenv('bucket_name')

vertexai.init(project=project_id, location=location)

quantity, type, content = "", "", ""
clips = []
pdfs = []

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

#main functions to generate output

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
    response = vision_model.generate_content(context)
    return response

def upload_file(file):
    try:
        upload_blob(bucket_name, file)
        return file
    except Exception as e:
        logging.error(f"Error uploading {file}: {e}")
        return None

# Function to make an API request
def make_api_request(file, prompt):
    try:
        print("scanning")
        text = generate_qns_googleapi("Extract as much information as possible", 'application/pdf', file).text
        return text
    except Exception as e:
        logging.error(f"Error in API request for {file}: {e}")
        return ""

# Function to delete a file
def delete_file(file):
    delete_blob(bucket_name, file)
    os.remove(file)

def pdftoQns(quantity, type, name):
    if type == 'flashcard':
        prompt = prompts.flashcard
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
                time.sleep(0.5)  # Wait for 0.5 seconds before starting the next thread

        contexts = [future.result() for future in as_completed(futures)]
        full_context = ''.join(contexts)
    
    print(contexts)
    print("deleting files now")

    # Delete files
    for file in uploaded_files:
        if file is not None:
            delete_file(file)

    print(contexttoQns(full_context, quantity, type).text)


def websitetopdf():
    link = input("Enter the website URL: ")
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
    pdfkit.from_string(html, 'output.pdf', options=options)
    pdftoQns(quantity, type, 'output')
    os.remove('output.pdf')

    # Close the browser
    browser.quit()

# link = str(input("Enter the video link: "))
# type = input("What type of questions do you want? (flashcard or question_paper): ")
# quantity = input("How many questions do you want? ")
# context = compilationcontent(link, clips)
# print(contexttoQns(context, quantity, type).text)

logging.basicConfig(level=logging.INFO)
# websitetopdf() #not all websites work, some websites have restrictions on scraping
pdftoQns("10", 'flashcard', 'test')


# Things to consider.
# Video name is not unique. So when multiple people use this, it may end up crashing the system. So once we are 
# closer to completing the back end and begin front end production, we should consider how this will function 
# with multiple users. possibly requiring mongodb

# Things to consider for optimization of youtube video to Questions
# Video Splitting: If your hardware supports it, process multiple video clips in parallel. This can be done by creating separate threads or processes for each video clip.
# Uploading: Upload multiple clips simultaneously using asynchronous requests or multi-threading.
# Batch Processing: Instead of processing each video clip individually, see if it's possible to batch-process multiple clips together in a single request, if the API supports it. This can significantly reduce the number of API calls and waiting time.
# Reducing Video Quality
# Direct Cloud Processing: If possible, perform the video splitting and processing directly in the cloud. 
# Compress data where appropriate to reduce upload and download times
# Output qns as soon as it loads in instead of loading all at once after all pdfs/clips has been processed

# video maxumum length is 2 minutes
# maximum number of pages in a pdf is 16

# extract_frames('set.mp4', 5)  # Extract frames from downloaded videso | DEEMED REDUNDANT
# get_transcript(video_url) #downloads transcipt from video | DEEMED REDUNDANT
# content = extract_text_from_pdf(pdf_path) #GPT-3.5 API Call | DEEMED REDUNDANT
