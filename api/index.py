import sys
import os
import traceback
from fastapi import FastAPI

app = FastAPI()

# إضافة المجلد الرئيسي للمسار
root_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root_path not in sys.path:
    sys.path.insert(0, root_path)

@app.get("/{full_path:path}")
def catch_all(full_path: str):
    try:
        import main
        return {"status": "success", "message": "main.py imported successfully!"}
    except Exception as e:
        return {
            "status": "error",
            "error_type": type(e).__name__,
            "error_message": str(e),
            "traceback": traceback.format_exc().splitlines()
        }