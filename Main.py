import openai
import os
import pdfplumber
from dotenv import load_dotenv, dotenv_values
 
load_dotenv()
openai.api_key = os.getenv('openAI_token')
pdf_path = os.getenv('pdf_path')

def extract_text_from_pdf(pdf_path):
    text = ''
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text += page.extract_text()
    return text

quantity = input("How many questions would you like?: ")
content = extract_text_from_pdf(pdf_path)

answer = openai.ChatCompletion.create(
    model='gpt-3.5-turbo',
    messages=[
        {"role": "system", "content": "You are given some text. You are to read and learn from the text and generate" + quantity + " questions from the text. You are to provide answers to all questions as well."},
        {"role": "user", "content": content},
    ]
)

answer = answer.choices[0].message.content
print(answer)

