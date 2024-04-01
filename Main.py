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
clips = []

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
    


def pdftoQns(quantity, type):
    
    if type == 'flashcard':
        prompt = prompts.flashcard
    else:
        prompt = prompts.question_paper

    upload_blob(bucket_name, 'pdf.pdf')
    print(generate_qns_googleapi(prompt + quantity, 'application/pdf', 'pdf.pdf').text) #Google API Call
    delete_blob(bucket_name, 'pdf.pdf')


link = str(input("Enter the video link: "))
type = input("What type of questions do you want? (flashcard or question_paper): ")
quantity = input("How many questions do you want? ")
context = compilationcontent(link, clips)
print(contexttoQns(context, quantity, type).text)


# LinktoQns(link, quantity, type)



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

# video maxumum length is 2 minutes
# maximum number of pages in a pdf is 16

# extract_frames('set.mp4', 5)  # Extract frames from downloaded videso | DEEMED REDUNDANT
# get_transcript(video_url) #downloads transcipt from video | DEEMED REDUNDANT
# content = extract_text_from_pdf(pdf_path) #GPT-3.5 API Call | DEEMED REDUNDANT
