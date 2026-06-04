"""
EnergyBae Agent — FastAPI Server with built-in UI
"""

import os
import uuid
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from bill_agent import run as process_bill

app = FastAPI(title="EnergyBae Solar Agent", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
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

CALCULATOR_URL = "https://v0-solar-proposal-boq-calculator.vercel.app/"
sessions: dict = {}


@app.get("/", response_class=HTMLResponse)
def home():
    return HTMLResponse(content="""
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>EnergyBae — Bill Analyzer</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: Arial, sans-serif; background: #f4f6f9; min-height: 100vh; display: flex; align-items: center; justify-content: center; padding: 1rem; }
    .card { background: white; border-radius: 12px; padding: 2rem; width: 100%; max-width: 520px; box-shadow: 0 2px 16px rgba(0,0,0,0.08); }
    .logo { display: flex; align-items: center; gap: 10px; margin-bottom: 1.5rem; }
    .logo-dot { width: 36px; height: 36px; background: #2e7d32; border-radius: 8px; display: flex; align-items: center; justify-content: center; color: white; font-weight: bold; font-size: 14px; }
    h1 { font-size: 20px; color: #1a1a1a; }
    p.sub { font-size: 13px; color: #666; margin-top: 4px; }
    .dropzone { border: 2px dashed #c8e6c9; border-radius: 10px; padding: 2rem; text-align: center; margin: 1.5rem 0; cursor: pointer; background: #f9fbe7; }
    .dropzone:hover { background: #f1f8e9; }
    .dropzone input { display: none; }
    .dropzone-icon { font-size: 36px; margin-bottom: 8px; }
    .dropzone p { font-size: 14px; color: #555; }
    .fname { font-size: 13px; color: #2e7d32; margin-top: 6px; font-weight: 600; }
    button { width: 100%; padding: 12px; background: #2e7d32; color: white; border: none; border-radius: 8px; font-size: 15px; font-weight: 600; cursor: pointer; }
    button:disabled { background: #aaa; cursor: not-allowed; }
    .status { margin-top: 1rem; padding: 12px 16px; border-radius: 8px; font-size: 14px; display: none; }
    .loading { background: #e3f2fd; color: #1565c0; display: block !important; }
    .success { background: #e8f5e9; color: #2e7d32; display: block !important; }
    .error { background: #ffebee; color: #c62828; display: block !important; }
    .result-box { margin-top: 1.2rem; background: #f9f9f9; border-radius: 8px; padding: 1rem; font-size: 13px; display: none; }
    .result-box table { width: 100%; border-collapse: collapse; }
    .result-box td { padding: 5px 8px; border-bottom: 1px solid #eee; }
    .result-box td:first-child { color: #888; width: 50%; }
    .result-box td:last-child { font-weight: 500; }
    .dl-btn { margin-top: 1rem; display: none; padding: 10px; background: #1565c0; color: white; border-radius: 8px; text-align: center; text-decoration: none; font-size: 14px; font-weight: 600; }
    .msg-box { margin-top: 1rem; background: #fff8e1; border-radius: 8px; padding: 12px; font-size: 13px; color: #555; white-space: pre-line; border-left: 3px solid #f9a825; display: none; }
  </style>
</head>
<body>
  <div class="card">
    <div class="logo">
      <div class="logo-dot">EB</div>
      <div>
        <h1>EnergyBae Bill Analyzer</h1>
        <p class="sub">Upload MSEDCL bill → get solar sizing instantly</p>
      </div>
    </div>
    <div class="dropzone" onclick="document.getElementById('billFile').click()">
      <input type="file" id="billFile" accept=".pdf,.jpg,.jpeg,.png" onchange="onFile(this)"/>
      <div class="dropzone-icon">📄</div>
      <p>Click to upload electricity bill</p>
      <p style="font-size:12px;color:#aaa;margin-top:4px;">PDF, JPG or PNG</p>
      <p class="fname" id="fname"></p>
    </div>
    <button id="btn" onclick="submit()" disabled>Analyze Bill</button>
    <div class="status" id="status"></div>
    <div class="result-box" id="resultBox"><table id="tbl"></table></div>
    <a class="dl-btn" id="dlBtn" target="_blank">⬇ Download Filled Excel</a>
    <div class="msg-box" id="msgBox"></div>
  </div>
  <script>
    let file = null;
    function onFile(inp) {
      file = inp.files[0];
      document.getElementById('fname').textContent = file ? '✓ ' + file.name : '';
      document.getElementById('btn').disabled = !file;
    }
    async function submit() {
      if (!file) return;
      const btn = document.getElementById('btn');
      const status = document.getElementById('status');
      btn.disabled = true;
      status.className = 'status loading';
      status.textContent = '⏳ Analyzing bill using AI... ~15 seconds';
      document.getElementById('resultBox').style.display = 'none';
      document.getElementById('dlBtn').style.display = 'none';
      document.getElementById('msgBox').style.display = 'none';
      const fd = new FormData();
      fd.append('file', file);
      try {
        const res = await fetch('/process-bill', { method: 'POST', body: fd });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Server error');
        const s = data.summary;
        status.className = 'status success';
        status.textContent = '✅ Bill analyzed successfully!';
        const rows = [
          ['Consumer name', s.consumer_name || '—'],
          ['Consumer no.', s.consumer_no || '—'],
          ['Sanctioned load', s.sanctioned_load_kw ? s.sanctioned_load_kw + ' kW' : '—'],
          ['Months extracted', s.months_extracted],
          ['Avg monthly units', s.avg_monthly_units + ' units'],
        ];
        document.getElementById('tbl').innerHTML = rows.map(([k,v]) => `<tr><td>${k}</td><td>${v}</td></tr>`).join('');
        document.getElementById('resultBox').style.display = 'block';
        const dlBtn = document.getElementById('dlBtn');
        dlBtn.href = '/download/' + data.session_id;
        dlBtn.style.display = 'block';
        if (data.next_step?.message) {
          const mb = document.getElementById('msgBox');
          mb.textContent = data.next_step.message;
          mb.style.display = 'block';
        }
      } catch(e) {
        status.className = 'status error';
        status.textContent = '❌ Error: ' + e.message;
      }
      btn.disabled = false;
    }
  </script>
</body>
</html>
""")


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
            str(bill_path), str(TEMPLATE_PATH), str(output_path)
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
                f"Average consumption: ~{round(avg_units)} units/month.\n\n"
                f"Would you like:\n"
                f"A) Paid site visit by our expert\n"
                f"B) Free calculator: {CALCULATOR_URL}"
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


@app.get("/health")
def health():
    return {"status": "EnergyBae Agent is running", "version": "1.0"}


if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=int(os.environ.get("PORT", 8000)), reload=False)
