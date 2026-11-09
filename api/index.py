import sys
import os
import traceback
from fastapi import FastAPI

app = FastAPI()

# إضافة المجلد الرئيسي للمسار
path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if path not in sys.path:
    sys.path.append(path)

@app.get("/{full_path:path}")
def catch_all(full_path: str):
    try:
        from main import app as real_app
        return {"status": "imported successfully"}
    except Exception as e:
        return {
            "error": str(e),
            "type": type(e).__name__,
            "traceback": traceback.format_exc().splitlines()
        }