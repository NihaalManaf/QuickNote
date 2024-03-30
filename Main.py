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



load_dotenv()
openai.api_key = os.getenv('openAI_token')
pdf_path = os.getenv('pdf_path')
project_id = os.getenv('project_id')
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = 'service_account.json'
storage_client = storage.Client()
location = 'asia-southeast1'
bucket_name = os.getenv('bucket_name')

vertexai.init(project=project_id, location=location)

quantity, type, content = "", "", ""

def generate_qns_googleapi() -> str:
    vision_model = GenerativeModel("gemini-1.0-pro-vision")
    response = vision_model.generate_content(
        [
            Part.from_uri(
                "gs://quicknotevideos/set.mp4", mime_type="video/mp4"
            ),
            "Generate 10 questions based on the video content and provide the answers below. If there is math content, you should ask sample math questions instead of the concepts themselves.",
        ]
    )
    return response

def upload_blob(bucket_name, source_file_name, destination_blob_name):
    """Uploads a file to the bucket."""
    bucket = storage_client.get_bucket(bucket_name)
    blob = bucket.blob(destination_blob_name)

    blob.upload_from_filename(source_file_name)

    print(
        "File {} uploaded to {}.".format(
            source_file_name, destination_blob_name
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

def LinktoQns(video_url):
    download_video(video_url) #downloads video
    upload_blob(bucket_name, 'set.mp4', 'set.mp4')
    print(generate_qns_googleapi().text) #Google API Call
    delete_blob(bucket_name, 'set.mp4')
    os.remove('set.mp4')
    
# answer = openai.ChatCompletion.create(
#     model='gpt-3.5-turbo',
#     messages=[
#         {"role": "system",
#         "content": "create" + quantity + "questions from the following text. Return data as " + type + 
#         """ for the user. If user needs notes, provide as much info as possible in a condesned manner. 
#         If the user needs flashcards or question paper, provide the number of questions mentioned previously and put all the quetsions together first and then povide an answer for each question below in the same order"""},
#         {"role": "user", "content": content},
#     ]
# )

# answer = answer.choices[0].message.content
# print(answer)

# extract_frames('set.mp4', 5)  # Extract frames from downloaded videso | DEEMED REDUNDANT
# get_transcript(video_url) #downloads transcipt from video | DEEMED REDUNDANT
# content = extract_text_from_pdf(pdf_path) #GPT-3.5 API Call | DEEMED REDUNDANT


video_url =input("Enter the video URL: ")
LinktoQns(video_url)