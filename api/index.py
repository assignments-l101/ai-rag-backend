import sys
import os
import traceback
from fastapi import FastAPI

app = FastAPI()

# ضبط مسار المشروع الرئيسي
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

@app.get("/{full_path:path}")
def catch_all(full_path: str):
    try:
        from main import app as real_app
        return {"status": "success", "message": "App loaded successfully!"}
    except Exception as e:
        return {
            "error_type": type(e).__name__,
            "error_message": str(e),
            "traceback": traceback.format_exc().splitlines()
        }