"""
EnergyBae Agent — FastAPI Server
Handles bill uploads, extraction, Excel generation, and conversation flow.
Connect this to Twilio/WATI WhatsApp webhook.
"""

import os
import uuid
import json
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse, JSONResponse
import uvicorn

from bill_agent import run as process_bill

app = FastAPI(title="EnergyBae Solar Agent", version="1.0")

UPLOAD_DIR = Path("uploads")
OUTPUT_DIR = Path("outputs")
UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

TEMPLATE_PATH = "template.xlsx"

# ── Brochure mapping ──────────────────────────────────────────────────────────
BROCHURES = {
    "solar": "brochures/solar.pdf",
    "wind":  "brochures/wind.pdf",
    "hybrid": "brochures/hybrid.pdf",
}

CALCULATOR_URL = "https://v0-solar-proposal-boq-calculator.vercel.app/"

# ── Conversation state (in-memory; use Redis/DB in production) ─────────────────
sessions: dict = {}


# ─────────────────────────────────────────────────────────────────────────────
# Route 1: Send brochure based on interest
# ─────────────────────────────────────────────────────────────────────────────
@app.get("/brochure/{type}")
def get_brochure(type: str):
    """
    Founder triggers this to send the right brochure to a client.
    GET /brochure/solar  →  returns solar brochure PDF
    """
    type = type.lower()
    if type not in BROCHURES:
        raise HTTPException(400, f"Unknown type '{type}'. Use: solar, wind, hybrid")
    path = BROCHURES[type]
    if not Path(path).exists():
        return JSONResponse({"message": f"Brochure path configured: {path}. Add the PDF file here."})
    return FileResponse(path, media_type="application/pdf", filename=f"EnergyBae_{type}_brochure.pdf")


# ─────────────────────────────────────────────────────────────────────────────
# Route 2: Upload bill → extract → fill Excel
# ─────────────────────────────────────────────────────────────────────────────
@app.post("/process-bill")
async def process_bill_endpoint(
    file: UploadFile = File(...),
    session_id: str = Form(default=None)
):
    """
    Client uploads their electricity bill (PDF or image).
    Returns filled Excel file + extracted data summary.
    """
    # Save uploaded file
    session_id = session_id or str(uuid.uuid4())
    suffix = Path(file.filename).suffix
    bill_path = UPLOAD_DIR / f"{session_id}{suffix}"

    with open(bill_path, "wb") as f:
        f.write(await file.read())

    # Process
    try:
        output_path = OUTPUT_DIR / f"solar_analysis_{session_id}.xlsx"
        result_path, extracted_data = process_bill(
            str(bill_path),
            TEMPLATE_PATH,
            str(output_path)
        )
    except Exception as e:
        raise HTTPException(500, f"Bill processing failed: {str(e)}")

    # Store session state
    sessions[session_id] = {
        "extracted": extracted_data,
        "excel_path": str(output_path),
        "stage": "awaiting_site_visit_decision"
    }

    # Build response summary
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
                f"✅ Hi {extracted_data.get('consumer_name', 'there')}! "
                f"We've analysed your electricity bill. "
                f"Your average consumption is ~{round(avg_units)} units/month.\n\n"
                f"Would you like:\n"
                f"A) A *paid site visit* by our expert for a detailed assessment\n"
                f"B) Calculate your solar proposal *yourself* using our free tool: {CALCULATOR_URL}"
            )
        }
    })


# ─────────────────────────────────────────────────────────────────────────────
# Route 3: Download the filled Excel
# ─────────────────────────────────────────────────────────────────────────────
@app.get("/download/{session_id}")
def download_excel(session_id: str):
    """Download the filled Excel for a session."""
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


# ─────────────────────────────────────────────────────────────────────────────
# Route 4: WhatsApp webhook (Twilio/WATI format)
# ─────────────────────────────────────────────────────────────────────────────
@app.post("/whatsapp-webhook")
async def whatsapp_webhook(body: dict):
    """
    Receives WhatsApp messages from Twilio/WATI.
    Handles the conversation flow:
      → User sends 'solar'/'wind'/'hybrid' → send brochure
      → User sends bill → extract + fill Excel
      → User replies A/B → site visit or calculator link
    """
    # Twilio format: body.From, body.Body, body.MediaUrl0
    sender = body.get("From", "")
    message_text = body.get("Body", "").strip().lower()
    media_url = body.get("MediaUrl0")  # attached file

    session = sessions.get(sender, {"stage": "new"})
    reply = ""

    # ── New user or keyword trigger ──
    if any(kw in message_text for kw in ["solar", "wind", "hybrid"]):
        interest = next(kw for kw in ["solar", "wind", "hybrid"] if kw in message_text)
        sessions[sender] = {"stage": "sent_brochure", "interest": interest}
        reply = (
            f"Thanks for your interest in {interest.title()} energy! 🌞\n"
            f"I'm sending you our {interest} brochure.\n\n"
            f"Please share your latest electricity bill (PDF or photo) "
            f"so we can calculate your ideal solar system size!"
        )
        # In production: attach brochure file here via Twilio Media API

    # ── User sends bill ──
    elif media_url or session.get("stage") == "sent_brochure":
        reply = (
            "📄 Got your bill! Analysing it now... This takes about 10 seconds. ⏳"
        )
        # In production: download media_url, call /process-bill, send back results
        # Here we return the instruction to trigger that flow
        sessions[sender] = {**session, "stage": "bill_received", "media_url": media_url}

    # ── User picks site visit or self-serve ──
    elif session.get("stage") == "awaiting_site_visit_decision":
        if "a" in message_text or "site visit" in message_text or "visit" in message_text:
            reply = (
                "Great! Our expert will visit your site. 🏠\n"
                "A nominal site visit fee applies.\n"
                "Please share your preferred date & time and we'll confirm shortly.\n"
                "📞 You can also call us: +91 9112233120"
            )
            sessions[sender] = {**session, "stage": "site_visit_booked"}
        elif "b" in message_text or "calculator" in message_text or "myself" in message_text:
            reply = (
                f"Perfect! Use our free Solar Proposal Calculator: 🔗\n"
                f"{CALCULATOR_URL}\n\n"
                f"Enter your details and get an instant proposal with savings & ROI!"
            )
            sessions[sender] = {**session, "stage": "self_serve"}
        else:
            reply = (
                "Please reply with:\n"
                "*A* — for a site visit by our expert\n"
                "*B* — to use the free calculator yourself"
            )

    # ── Default greeting ──
    else:
        reply = (
            "👋 Welcome to EnergyBae!\n"
            "We help you save on electricity with Solar, Wind & Hybrid solutions.\n\n"
            "What are you interested in?\n"
            "Reply: *Solar*, *Wind*, or *Hybrid*"
        )
        sessions[sender] = {"stage": "greeted"}

    return JSONResponse({"reply": reply, "to": sender})


# ─────────────────────────────────────────────────────────────────────────────
# Route 5: Health check
# ─────────────────────────────────────────────────────────────────────────────
@app.get("/")
def health():
    return {"status": "EnergyBae Agent is running 🌞", "version": "1.0"}


if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
