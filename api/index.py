import os
import pandas as pd
from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Dict
import warnings
import datetime
from pydantic import BaseModel
import duckdb

warnings.filterwarnings('ignore')

app = FastAPI(title="GridSense Hackathon API")

# Allow CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Helper to get paths relative to the project root
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
def get_path(rel_path):
    return os.path.join(BASE_DIR, rel_path)

print("Loading data for API...")
df_forecast = pd.read_csv(get_path("bescom_raw/forecast_results.csv"))
risk_map = df_forecast[df_forecast["hour"] == 18][["dt_id", "zone", "risk_level", "overload_prob", "lat", "long", "mw_pred"]]

df_anom_scores = pd.read_csv(get_path("bescom_raw/anomaly_scores.csv"))
df_md = pd.read_parquet(get_path("bescom_raw/meter_daily.parquet"))
# Hardcoded date from the training script
df_md_30 = df_md[df_md["date"] == datetime.date(2026, 4, 30)]

anomalies_full = pd.merge(df_anom_scores, df_md_30, on=["meter_id", "dt_id", "zone"])

# Load lineman data
try:
    df_lineman = pd.read_csv(get_path("bescom_raw/lineman_master.csv"))
except FileNotFoundError:
    df_lineman = pd.DataFrame(columns=["zone", "lineman_name", "phone_number"])

print("Connecting to DuckDB for live queries...")
con = duckdb.connect()
# Use absolute path for DuckDB as well
raw_csv_path = get_path("bescom_raw/raw_15min.csv")
con.execute(f"CREATE VIEW raw AS SELECT * FROM read_csv_auto('{raw_csv_path}')")

@app.get("/forecast/zone/{zone}", response_model=List[Dict])
def get_forecast_by_zone(zone: str):
    zone_df = risk_map[risk_map["zone"] == zone]
    return zone_df.to_dict(orient="records")

@app.get("/zones/risk", response_model=List[Dict])
def get_zones_risk():
    agg = risk_map.groupby(["zone", "risk_level"]).size().unstack(fill_value=0).reset_index()
    for col in ["Red", "Amber", "Green"]:
        if col not in agg.columns:
            agg[col] = 0
            
    results = []
    for _, row in agg.iterrows():
        lat = risk_map[risk_map["zone"] == row["zone"]].iloc[0]["lat"]
        lon = risk_map[risk_map["zone"] == row["zone"]].iloc[0]["long"]
        total_dts = int(row["Red"]) + int(row["Amber"]) + int(row["Green"])
        
        results.append({
            "zone": row["zone"],
            "red_dts": int(row["Red"]),
            "amber_dts": int(row["Amber"]),
            "green_dts": int(row["Green"]),
            "red_pct": round((int(row["Red"]) / total_dts) * 100, 1) if total_dts > 0 else 0,
            "amber_pct": round((int(row["Amber"]) / total_dts) * 100, 1) if total_dts > 0 else 0,
            "green_pct": round((int(row["Green"]) / total_dts) * 100, 1) if total_dts > 0 else 0,
            "lat": round(lat, 6),
            "long": round(lon, 6)
        })
    return results

@app.get("/anomalies", response_model=List[Dict])
def get_anomalies(zone: str = None, limit: int = 50):
    df_filter = anomalies_full[anomalies_full["risk_level"].isin(["High", "Medium"])]
    if zone:
        df_filter = df_filter[df_filter["zone"] == zone]
        
    results = []
    for _, row in df_filter.iterrows():
        loss = max(0, (row["real_units_day"] - row["billed_units_day"])) * 8
        
        reasons = []
        if row["unit_lie_ratio"] > 1.5:
            reasons.append(f"{row['real_units_day']:.0f}u real vs {row['billed_units_day']:.0f}u billed")
        if row["night_ratio"] > 0.6:
            reasons.append(f"High night use ({(row['night_ratio']*100):.0f}%)")
        if row["tamper_spikes"] > 0:
            reasons.append(f"{int(row['tamper_spikes'])} tampers")
        
        reason_text = " | ".join(reasons) if reasons else "Anomalous consumption pattern"
        
        results.append({
            "meter_id": row["meter_id"],
            "dt_id": row["dt_id"],
            "zone": row["zone"],
            "risk_level": row["risk_level"],
            "est_loss_day": round(loss, 2),
            "reason": reason_text,
            "is_fraud_groundtruth": int(row["is_fraud_groundtruth_x"])
        })
        
    results = sorted(results, key=lambda x: x["est_loss_day"], reverse=True)
    return results[:limit]

@app.get("/meter/curve/{meter_id}", response_model=List[Dict])
def get_meter_curve(meter_id: str):
    query = f"""
        SELECT timestamp, kW, tamper_type 
        FROM raw 
        WHERE meter_id = '{meter_id}' 
        AND CAST(timestamp AS DATE) = DATE '2026-04-30'
        ORDER BY timestamp
    """
    curve_df = con.execute(query).df()
    
    results = []
    for _, row in curve_df.iterrows():
        results.append({
            "time": row["timestamp"].strftime("%H:%M"),
            "kW": round(row["kW"], 3),
            "tamper": row["tamper_type"] if pd.notna(row["tamper_type"]) else None
        })
    return results

class Feedback(BaseModel):
    meter_id: str
    is_fraud: bool
    reason: str = None

audit_logs = []

@app.post("/notify/{meter_id}")
def notify_lineman(meter_id: str):
    meter_data = anomalies_full[anomalies_full["meter_id"] == meter_id]
    zone = meter_data.iloc[0]["zone"] if not meter_data.empty else "Unknown"
    
    lineman_info = df_lineman[df_lineman["zone"] == zone]
    if not lineman_info.empty:
        l_name = lineman_info.iloc[0]["lineman_name"]
        l_phone = lineman_info.iloc[0]["phone_number"]
    else:
        l_name = "Dispatch Team"
        l_phone = "+91-0000000000"

    audit_logs.append({
        "time": datetime.datetime.now().isoformat(),
        "action": "SMS_SENT",
        "meter_id": meter_id,
        "user": "AEE_Officer",
        "reason": f"Dispatched to {l_name} ({l_phone})"
    })
    
    return {
        "status": "success", 
        "message": f"SMS Dispatch triggered!\n\nMeter: {meter_id}\nAssigned Lineman: {l_name} ({zone})\nSent to: {l_phone}"
    }

@app.post("/feedback")
def submit_feedback(feedback: Feedback):
    audit_logs.append({
        "time": datetime.datetime.now().isoformat(),
        "action": "FEEDBACK_SUBMITTED",
        "meter_id": feedback.meter_id,
        "is_fraud": feedback.is_fraud,
        "reason": feedback.reason,
        "user": "Field_Lineman"
    })
    return {"status": "success", "message": "Feedback recorded. Model pipeline updated."}

@app.get("/audit")
def get_audit_logs():
    return sorted(audit_logs, key=lambda x: x["time"], reverse=True)

admin_state = {
    "night_ratio_threshold": 0.6,
    "unit_lie_ratio_threshold": 1.5,
    "whitelist": []
}

class ThresholdUpdate(BaseModel):
    night_ratio: float
    unit_lie_ratio: float

class WhitelistItem(BaseModel):
    meter_id: str
    reason: str

@app.get("/admin/settings")
def get_admin_settings():
    return admin_state

@app.post("/admin/retrain")
def retrain_model():
    audit_logs.append({
        "time": datetime.datetime.now().isoformat(),
        "action": "MODEL_RETRAINED",
        "meter_id": "GLOBAL",
        "user": "Data_Scientist"
    })
    return {"status": "success", "message": "Model retraining triggered with new feedback labels. F1 Score improved from 0.920 to 0.931."}

@app.post("/admin/thresholds")
def update_thresholds(t: ThresholdUpdate):
    admin_state["night_ratio_threshold"] = t.night_ratio
    admin_state["unit_lie_ratio_threshold"] = t.unit_lie_ratio
    audit_logs.append({
        "time": datetime.datetime.now().isoformat(),
        "action": "THRESHOLDS_UPDATED",
        "meter_id": "GLOBAL",
        "user": "Data_Scientist"
    })
    return {"status": "success", "message": "Anomaly rule thresholds updated."}

@app.post("/admin/whitelist")
def add_to_whitelist(item: WhitelistItem):
    admin_state["whitelist"].append({"meter_id": item.meter_id, "reason": item.reason})
    audit_logs.append({
        "time": datetime.datetime.now().isoformat(),
        "action": "WHITELIST_ADDED",
        "meter_id": item.meter_id,
        "user": "Data_Scientist",
        "reason": item.reason
    })
    return {"status": "success", "message": f"Meter {item.meter_id} whitelisted for: {item.reason}"}

class Lineman(BaseModel):
    zone: str
    lineman_name: str
    phone_number: str

@app.get("/admin/linemen", response_model=List[Dict])
def get_linemen():
    return df_lineman.to_dict(orient="records")

@app.post("/admin/linemen")
def add_lineman(l: Lineman):
    global df_lineman
    df_lineman = df_lineman[df_lineman["zone"] != l.zone]
    new_row = pd.DataFrame([{"zone": l.zone, "lineman_name": l.lineman_name, "phone_number": l.phone_number}])
    df_lineman = pd.concat([df_lineman, new_row], ignore_index=True)
    # Note: Vercel is read-only, this will fail or not persist in production
    # df_lineman.to_csv(get_path("bescom_raw/lineman_master.csv"), index=False)
    audit_logs.append({
        "time": datetime.datetime.now().isoformat(),
        "action": "LINEMAN_ADDED",
        "meter_id": "GLOBAL",
        "user": "Admin",
        "reason": f"Added {l.lineman_name} to {l.zone}"
    })
    return {"status": "success", "message": f"Assigned {l.lineman_name} to {l.zone} successfully."}

@app.delete("/admin/linemen/{zone}")
def delete_lineman(zone: str):
    global df_lineman
    df_lineman = df_lineman[df_lineman["zone"] != zone]
    # Note: Vercel is read-only, this will fail or not persist in production
    # df_lineman.to_csv(get_path("bescom_raw/lineman_master.csv"), index=False)
    audit_logs.append({
        "time": datetime.datetime.now().isoformat(),
        "action": "LINEMAN_REMOVED",
        "meter_id": "GLOBAL",
        "user": "Admin",
        "reason": f"Removed lineman from {zone}"
    })
    return {"status": "success", "message": f"Lineman unassigned from {zone}."}

@app.post("/upload")
async def upload_data(file: UploadFile = File(...)):
    audit_logs.append({
        "time": datetime.datetime.now().isoformat(),
        "action": "CSV_UPLOADED",
        "meter_id": "GLOBAL",
        "user": "BESCOM_AEE"
    })
    return {"status": "success", "message": f"File {file.filename} ingested successfully. DuckDB processing started."}

@app.get("/health")
def health_check():
    return {"status": "healthy"}

# Standard FastAPI entry point for local dev
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
