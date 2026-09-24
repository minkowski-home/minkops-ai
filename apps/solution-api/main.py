from excel_writer import save_watermarks_to_excel
from fastapi.middleware.cors import CORSMiddleware
from json_writer import save_extracted_json
import base64
import json
from openai import OpenAI
import os
from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File

load_dotenv()
client = OpenAI()

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def home():
    return {"message:" "Image to Excel API is running"}

@app.get("/check-config")
def check_config():
    api_key = os.getenv("OPENAI_API_KEY")

    return{
        "openai_key_loaded": api_key is not None
    }

@app.post("/upload-image")
async def upload_image(file: UploadFile = File(...)):
    image_bytes = await file.read()

    return {
        "filename": file.filename,
        "content_type": file.content_type,
        "size_bytes": len(image_bytes)
    }

@app.post("/extract_image")
async def extract_image(file: UploadFile = File(...)):
    image_bytes = await file.read()

    encoded_image = base64.b64encode(image_bytes).decode("utf-8")

    image_url = (
        f"data:{file.content_type};base64,{encoded_image}"
    )

    response = client.responses.create(
        model = "gpt-5.6-luna",
        input = [
            {
                "role":"user",
                "content":[
                    {
                        "type":"input_text",
                        "text": """
                        Read the watermark information visible in this image.

Extract ONLY these fields:

- date
- time
- latitude
- longitude 
- address
- altitude

Return JSON in exactly this structure:

{
  "watermarks": [
    {
      "date": "",
      "time": "",
      "latitude": "",
      "longitude": "",
      "address": "",
      "altitude": ""
    }
  ]
}

If multiple separate watermarks are visible, create one object for each watermark.

Do not extract project names, vehicle information, materials, weights, company names, signs, or any other information.

Do not guess values. If a requested field is not visible, use null.
"""
                    },
                    {
                        "type": "input_image",
                        "image_url": image_url,
                        "detail": "high",
                    },
                ],
            }
        ],
        text = {
            "format": {
                "type": "json_object"
            }
        },
    )
    extracted_data = json.loads(response.output_text)
    json_path = save_extracted_json(source_filename = file.filename, extracted_data = extracted_data)
    watermarks = extracted_data.get("watermarks", [])
    excel_path = save_watermarks_to_excel(watermarks)

    return{
        "filename" : file.filename,
        "json_backup": str(json_path),
        "excel_file": str(excel_path),
        "extracted_fields": extracted_data,
    }