import openai
import os
import re
import pdfplumber
from dotenv import load_dotenv, dotenv_values
import cv2
import youtube_dl
from youtube_transcript_api import YouTubeTranscriptApi

load_dotenv()
openai.api_key = os.getenv('openAI_token')
pdf_path = os.getenv('pdf_path')

quantity, type, content = "", "", ""

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

# quantity = input("How many questions would you like?: ")
# type = input("How would you like the output?: ")
# content = extract_text_from_pdf(pdf_path)
    
answer = openai.ChatCompletion.create(
    model='gpt-3.5-turbo',
    messages=[
        {"role": "system",
        "content": "create" + quantity + "questions from the following text. Return data as " + type + 
        """ for the user. If user needs notes, provide as much info as possible in a condesned manner. 
        If the user needs flashcards or question paper, provide the number of questions mentioned previously and put all the quetsions together first and then povide an answer for each question below in the same order"""},
        {"role": "user", "content": content},
    ]
)
answer = answer.choices[0].message.content
print(answer)


video_url =input("Enter the video URL: ")
get_transcript(video_url)
#download_video(video_url)
#extract_frames('set.mp4', 5)  # Extract a frame every 5 seconds