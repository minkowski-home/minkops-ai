from minkops_api.excel_writer import save_watermarks_to_excel
from fastapi.middleware.cors import CORSMiddleware
from minkops_api.json_writer import save_extracted_json
import base64
import json
from openai import OpenAI
import os
from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File
from fastapi import HTTPException, Request
from psycopg.types.json import Jsonb
from minkops_api.auth import Db, User, require_csrf, tenant_access
from minkops_api.auth import router as core_router
from minkops_api.workspace import router as workspace_router
from minkops_api.accounts import router as accounts_router
from minkops_api.desktop import router as desktop_router
from minkops_api.discovery import router as discovery_router

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

app = FastAPI()


@app.middleware("http")
async def private_api_cache(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "private, no-store"
    return response


app.include_router(core_router)
app.include_router(workspace_router)
app.include_router(accounts_router)
app.include_router(desktop_router)
app.include_router(discovery_router)
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
    return {"message": "Minkops API is running"}

async def extract_image(file: UploadFile = File(...)):
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=503,
            detail="Image extraction is unavailable: set OPENAI_API_KEY in apps/solution-api/.env and restart the API.",
        )

    image_bytes = await file.read()

    encoded_image = base64.b64encode(image_bytes).decode("utf-8")

    image_url = (
        f"data:{file.content_type};base64,{encoded_image}"
    )

    response = OpenAI(api_key=api_key).responses.create(
        model = "gpt-6-luna",
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


@app.post("/api/tenants/{slug}/test/image-to-excel")
async def run_image_to_excel_test(slug: str, request: Request, user: User, connection: Db,
                                  file: UploadFile = File(...)):
    require_csrf(request)
    tenant, _ = tenant_access(slug, user, connection)
    if slug != "mock-tenant":
        raise HTTPException(404, "Test workflow not found.")
    workflow = connection.execute(
        """SELECT id FROM workflows WHERE tenant_id = %s
           AND key = 'image-to-excel-test' AND status = 'active'""",
        (tenant["id"],),
    ).fetchone()
    if not workflow:
        raise HTTPException(404, "Test workflow not active.")
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(422, "Choose an image file.")
    result = await extract_image(file)
    task = connection.execute(
        """INSERT INTO tasks (tenant_id, workflow_id, title, status, progress, summary)
           VALUES (%s, %s, %s, 'completed', 100, 'Image extracted and spreadsheet saved.')
           RETURNING id""",
        (tenant["id"], workflow["id"], f"Extract {file.filename or 'image'}"),
    ).fetchone()
    for event_type, summary, progress in [
        ("received", "Image received", 20),
        ("extracted", "Fields extracted", 75),
        ("completed", "Spreadsheet saved", 100),
    ]:
        connection.execute(
            """INSERT INTO task_events (tenant_id, task_id, event_type, summary, progress)
               VALUES (%s, %s, %s, %s, %s)""",
            (tenant["id"], task["id"], event_type, summary, progress),
        )
    connection.execute(
        """INSERT INTO event_outbox (tenant_id, event_type, aggregate_id, payload)
           VALUES (%s, 'task.completed', %s, %s)""",
        (tenant["id"], task["id"],
         Jsonb({"workflow_id": str(workflow["id"]), "filename": file.filename,
                "actor_id": str(user["id"])})),
    )
    return {"task_id": str(task["id"]), **result}
