import json
from datetime import datetime
from pathlib import Path
from uuid import uuid4

BASE_DIR = Path(__file__).resolve().parent
JSON_DIR = BASE_DIR / "data" / "json"

def save_extracted_json(source_filename, extracted_data):
    JSON_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    record_id = uuid4().hex[:8]

    filename = f"{timestamp}_{record_id}.json"

    file_path = JSON_DIR/filename

    record= {
        "record_id":record_id,
        "source_filename":source_filename,
        "created_at": datetime.now().isoformat(),
        "extracted_data": extracted_data,
    }

    with open(file_path, "w", encoding = "utf-8") as json_file:
        json.dump(
            record,
            json_file,
            indent=2,
            ensure_ascii = False,
        )
    return file_path
