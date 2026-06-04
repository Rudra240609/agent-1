# EnergyBae Solar Load Calculator Agent

Automates the electricity bill → solar sizing workflow for EnergyBae.

## What it does
1. Accepts an electricity bill (PDF or image)
2. Extracts key fields using Claude Vision AI (OCR)
3. Fills the Solar Load Excel template automatically
4. Sends filled Excel to the EnergyBae team
5. Asks the client: site visit OR self-serve calculator

---

## Setup

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Set your API key
```bash
cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY
```

### 3. Add your Excel template
Place `template.xlsx` (the EnergyBae Solar Load template) in this folder.

---

## Usage

### Option A — Command line (test a single bill)
```bash
python bill_agent.py path/to/electricity_bill.pdf
```
This will:
- Extract bill data
- Print a summary
- Save filled Excel as `solar_analysis_<filename>.xlsx`

### Option B — Run the full API server
```bash
python server.py
```
Server starts at http://localhost:8000

API endpoints:
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Health check |
| `/brochure/{solar\|wind\|hybrid}` | GET | Download brochure |
| `/process-bill` | POST | Upload bill → get filled Excel |
| `/download/{session_id}` | GET | Download filled Excel |
| `/whatsapp-webhook` | POST | WhatsApp message handler |

### Test the API
```bash
# Upload a bill and get filled Excel
curl -X POST http://localhost:8000/process-bill \
  -F "file=@electricity_bill.pdf"
```

---

## WhatsApp Integration

### Option 1 — WATI (Recommended for India)
1. Sign up at https://wati.io
2. Connect your WhatsApp Business number
3. Set webhook URL to: `https://your-server.com/whatsapp-webhook`
4. Done — messages flow automatically

### Option 2 — Twilio
1. Sign up at https://console.twilio.com
2. Get a WhatsApp sandbox number
3. Set webhook to your server URL
4. Add Twilio credentials to `.env`

### Deploy your server (free options)
- **Railway**: https://railway.app (easiest, free tier)
- **Render**: https://render.com (free tier)
- **ngrok** (for local testing): `ngrok http 8000`

---

## Conversation Flow

```
Client: "Hi, interested in solar"
Bot:    → Sends solar brochure PDF
        → "Please share your electricity bill"

Client: [uploads bill PDF/photo]
Bot:    → Extracts data via Claude Vision
        → Fills Excel template
        → Sends Excel to EnergyBae team email
        → "Average usage: 530 units/month
           A) Paid site visit  B) Free calculator"

Client: "B"
Bot:    → Sends calculator link
        → https://v0-solar-proposal-boq-calculator.vercel.app/
```

---

## Files
```
bill_agent.py       ← Core AI extraction + Excel filling logic
server.py           ← FastAPI web server + WhatsApp webhook
template.xlsx       ← EnergyBae Solar Load Excel template
requirements.txt    ← Python dependencies
.env.example        ← Environment variables template
uploads/            ← Temporary bill storage
outputs/            ← Generated Excel files
brochures/          ← Add solar.pdf, wind.pdf, hybrid.pdf here
```

---

## Submission (for EnergyBae task)
- Demo: Run `python bill_agent.py sample_bill.pdf` and record screen
- Output: The generated `solar_analysis_*.xlsx` file
- Explanation: "Built a Python agent using Claude Vision API to OCR electricity bills and auto-fill the Solar Load Excel template. FastAPI server handles the full WhatsApp conversation flow."
