"""
EnergyBae Agent — FastAPI Server
"""

import os
import uuid
import json
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from bill_agent import run as process_bill

app = FastAPI(title="EnergyBae Solar Agent", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = Path("uploads")
OUTPUT_DIR = Path("outputs")
UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

TEMPLATE_PATH = "template.xlsx"
if not Path(TEMPLATE_PATH).exists():
    TEMPLATE_PATH = Path(__file__).parent / "template.xlsx"

BROCHURES = {
    "solar": "brochures/solar.pdf",
    "wind":  "brochures/wind.pdf",
    "hybrid": "brochures/hybrid.pdf",
}

CALCULATOR_URL = "https://v0-solar-proposal-boq-calculator.vercel.app/"

sessions: dict = {}


@app.get("/brochure/{type}")
def get_brochure(type: str):
    type = type.lower()
    if type not in BROCHURES:
        raise HTTPException(400, f"Unknown type '{type}'. Use: solar, wind, hybrid")
    path = BROCHURES[type]
    if not Path(path).exists():
        return JSONResponse({"message": f"Brochure path configured: {path}. Add the PDF file here."})
    return FileResponse(path, media_type="application/pdf", filename=f"EnergyBae_{type}_brochure.pdf")


@app.post("/process-bill")
async def process_bill_endpoint(
    file: UploadFile = File(...),
    session_id: str = Form(default=None)
):
    session_id = session_id or str(uuid.uuid4())
    suffix = Path(file.filename).suffix
    bill_path = UPLOAD_DIR / f"{session_id}{suffix}"

    with open(bill_path, "wb") as f:
        f.write(await file.read())

    try:
        output_path = OUTPUT_DIR / f"solar_analysis_{session_id}.xlsx"
        result_path, extracted_data = process_bill(
            str(bill_path),
            str(TEMPLATE_PATH),
            str(output_path)
        )
    except Exception as e:
        raise HTTPException(500, f"Bill processing failed: {str(e)}")

    sessions[session_id] = {
        "extracted": extracted_data,
        "excel_path": str(output_path),
        "stage": "awaiting_site_visit_decision"
    }

    monthly = extracted_data.get("monthly_data", [])
    avg_units = sum(m["units"] for m in monthly if m.get("units")) / max(len(monthly), 1)

    return JSONResponse({
        "session_id": session_id,
        "status": "success",
        "summary": {
            "consumer_name": extracted_data.get("consumer_name"),
            "consumer_no": extracted_data.get("consumer_no"),
            "sanctioned_load_kw": extracted_data.get("sanctioned_load"),
            "months_extracted": len(monthly),
            "avg_monthly_units": round(avg_units, 1),
        },
        "excel_download_url": f"/download/{session_id}",
        "next_step": {
            "message": (
                f"Hi {extracted_data.get('consumer_name', 'there')}!\n"
                f"We've analysed your electricity bill.\n"
                f"Your average consumption is ~{round(avg_units)} units/month.\n\n"
                f"Would you like:\n"
                f"A) A paid site visit by our expert\n"
                f"B) Calculate your solar proposal yourself: {CALCULATOR_URL}"
            )
        }
    })


@app.get("/download/{session_id}")
def download_excel(session_id: str):
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    path = Path(session["excel_path"])
    if not path.exists():
        raise HTTPException(404, "Excel file not found")
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=f"EnergyBae_SolarAnalysis_{session_id[:8]}.xlsx"
    )


@app.post("/whatsapp-webhook")
async def whatsapp_webhook(body: dict):
    sender = body.get("From", "")
    message_text = body.get("Body", "").strip().lower()
    media_url = body.get("MediaUrl0")

    session = sessions.get(sender, {"stage": "new"})
    reply = ""

    if any(kw in message_text for kw in ["solar", "wind", "hybrid"]):
        interest = next(kw for kw in ["solar", "wind", "hybrid"] if kw in message_text)
        sessions[sender] = {"stage": "sent_brochure", "interest": interest}
        reply = (
            f"Thanks for your interest in {interest.title()} energy!\n"
            f"I'm sending you our {interest} brochure.\n\n"
            f"Please share your latest electricity bill (PDF or photo)!"
        )
    elif media_url or session.get("stage") == "sent_brochure":
        reply = "Got your bill! Analysing it now... This takes about 10 seconds."
        sessions[sender] = {**session, "stage": "bill_received", "media_url": media_url}
    elif session.get("stage") == "awaiting_site_visit_decision":
        if "a" in message_text or "visit" in message_text:
            reply = (
                "Great! Our expert will visit your site.\n"
                "Please share your preferred date & time.\n"
                "Call us: +91 9112233120"
            )
            sessions[sender] = {**session, "stage": "site_visit_booked"}
        elif "b" in message_text or "calculator" in message_text:
            reply = f"Use our free Solar Proposal Calculator:\n{CALCULATOR_URL}"
            sessions[sender] = {**session, "stage": "self_serve"}
        else:
            reply = "Please reply:\nA — for a site visit\nB — to use the free calculator"
    else:
        reply = (
            "Welcome to EnergyBae!\n"
            "We help you save on electricity with Solar, Wind & Hybrid solutions.\n\n"
            "Reply: Solar, Wind, or Hybrid"
        )
        sessions[sender] = {"stage": "greeted"}

    return JSONResponse({"reply": reply, "to": sender})


@app.get("/")
def health():
    return {"status": "EnergyBae Agent is running 🌞", "version": "1.0"}


if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=int(os.environ.get("PORT", 8000)), reload=False)
