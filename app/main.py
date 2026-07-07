import os
import json
import sys
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv

# Load env
load_dotenv()

# Add project root to path to import generator/eval modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from generator.generate import generate_reply
from eval.evaluate import evaluate_response

app = FastAPI(title="Hiver AI Support Copilot & Eval System")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request Models
class GenerateRequest(BaseModel):
    incoming_email: str

class EvaluateRequest(BaseModel):
    incoming_email: str
    generated_reply: str
    gold_reply: str
    retrieved_examples: list

# API Routes
@app.post("/api/generate")
async def api_generate(req: GenerateRequest):
    try:
        res = generate_reply(req.incoming_email, top_k=3)
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/evaluate")
async def api_evaluate(req: EvaluateRequest):
    try:
        eval_res = evaluate_response(
            incoming=req.incoming_email,
            generated=req.generated_reply,
            gold=req.gold_reply,
            retrieved=req.retrieved_examples
        )
        return eval_res
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/report")
async def api_report():
    results_path = "eval/results.json"
    report_path = "eval/report.md"
    
    if not os.path.exists(results_path) or not os.path.exists(report_path):
        # If evaluation hasn't been run yet, return empty/placeholder
        return {
            "has_eval": False,
            "message": "Evaluation pipeline has not been executed yet. Run it from the terminal or wait."
        }
        
    try:
        with open(results_path, "r", encoding="utf-8") as f:
            results = json.load(f)
        with open(report_path, "r", encoding="utf-8") as f:
            report_md = f.read()
            
        return {
            "has_eval": True,
            "results": results,
            "report_markdown": report_md
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading evaluation reports: {e}")

# Serve UI
os.makedirs("app/static", exist_ok=True)

@app.get("/")
async def get_index():
    index_path = "app/static/index.html"
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "UI file static/index.html not found. Backend running."}

# Mount static files (for css/js if separated)
app.mount("/static", StaticFiles(directory="app/static"), name="static")
