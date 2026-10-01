"""Legacy API storage binding; artifact persistence lives in platform."""

from pathlib import Path

from minkops_platform.artifacts import save_extracted_json as save_artifact

APP_DIR = Path(__file__).resolve().parents[2]
JSON_DIR = APP_DIR / "data/json"


def save_extracted_json(source_filename, extracted_data):
    return save_artifact(JSON_DIR, source_filename, extracted_data)
