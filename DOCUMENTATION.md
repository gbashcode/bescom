# GridSense AI: Complete Project Documentation

## 1. Project Overview

**GridSense AI** is a predictive and anomaly detection layer designed to sit on top of BESCOM's existing Meter Data Acquisition System (MDAS). It requires **no meter hardware changes**. By ingesting 15-minute smart meter interval data daily, GridSense provides two critical actionable intelligence modules:
1. **Predictive Layer (Part A):** An hour-ahead load forecast per Distribution Transformer (DT) to predict and map grid-stress and overload risks.
2. **Anomaly Layer (Part B):** A real-time, ROI-sorted anomaly detection system to flag potential electricity theft, meter bypass, and fraudulent zero-reading scenarios.

All insights are fully explainable, allowing Actionable Executive Engineers (AEEs) and linesmen to take precise physical actions (e.g., "Inspect Meter H8842 tonight for night-time neutral disconnect theft").

---

## 2. System Architecture & Components

The platform operates using a modern, locally hosted, and highly optimized tech stack.

### 2.1. Tech Stack
- **Data Engine:** DuckDB, Pandas
- **Machine Learning:** LightGBM (Forecasting), Scikit-Learn / Isolation Forest (Anomaly Detection)
- **Backend API:** FastAPI (Python)
- **Frontend Dashboard:** React, Vite, CSS (Tailwind/Vanilla)

### 2.2. Core Modules (Scripts)

1. **`generate_bescom_data.py` / `complete_outputs.py` (Data Generators)**
   - Simulates 15-minute interval smart meter data for 5,000 meters across 100 DTs in Bangalore.
   - Inject real-world data quality issues like gaps, tampers, and specific consumption patterns (festival spikes, commercial vs. residential).
   - Generates `raw_15min.csv`, `meter_master.csv`, and `dt_master.csv`.
   
2. **`feature_engineering.py` (Data Pipeline)**
   - Leverages **DuckDB** to quickly process the massive `raw_15min.csv` dataset.
   - Aggregates the 15-minute raw interval data into hourly DT loads (`dt_hourly.parquet`) and daily meter summaries (`meter_daily.parquet`).
   - Extracts time-series features essential for ML model training.

3. **`train_forecast.py` (Predictive Modeler)**
   - Uses **LightGBM** to train time-series forecasting models for each DT.
   - Predicts the next 24 hours of load based on historical trends, time of day, and holiday status.
   - Outputs `forecast_results.csv` detailing the overload probabilities and assigning risk levels (Red, Amber, Green).

4. **`train_anomaly.py` (Fraud Detection Modeler)**
   - Implements an **Isolation Forest** combined with a strictly tuned **Rule Engine**.
   - Evaluates "Night Ratio" (abnormal night-time consumption), "Unit Lie Ratio" (discrepancy between interval load and daily billed units), and tamper flag frequency.
   - Outputs `anomaly_scores.csv` assigning risk levels (High, Medium, Low) to all meters.

5. **`api.py` (FastAPI Backend)**
   - Serves the machine learning inferences via RESTful endpoints.
   - Connects live to the DuckDB instance for ultra-fast, on-the-fly analytical queries.
   - Handles the SMS notification routing, lineman roster management, and auditing log functions.

6. **`dashboard/` (Vite + React Frontend)**
   - Visualizes DT overload heatmaps and granular consumption curves.
   - Acts as the operational center for BESCOM AEEs to issue lineman dispatch commands.

---

## 3. Data Flow in Production

1. **01:00 AM:** Scheduled cron job exports MDAS interval data to `15min.csv` and uploads it to secure storage (S3/local).
2. **01:30 AM:** `feature_engineering.py` processes the data using DuckDB, saving optimized `.parquet` feature tables.
3. **02:00 AM (Batch Inference):**
   - `train_forecast.py` executes predictions across 100 DT LightGBM models.
   - `train_anomaly.py` flags anomalous and potentially fraudulent meters globally.
4. **02:30 AM:** Risk aggregates are stored, and `api.py` spins up to serve the generated datasets.
5. **09:00 AM:** BESCOM officials log into the GridSense dashboard to review the daily threat landscape.

---

## 4. API Endpoints Reference

The FastAPI backend runs by default at `http://localhost:8000`.

### Operational Endpoints
- **`GET /zones/risk`**: Returns an aggregated count of Red/Amber/Green DTs per geographical zone.
- **`GET /forecast/zone/{zone}`**: Returns the granular 24-hour predictive forecast mapped to a specific zone.
- **`GET /anomalies`**: Fetches the top 50 highest-risk meters, sorted by estimated financial loss per day.
- **`GET /meter/curve/{meter_id}`**: Returns the raw 15-minute load curve for a specific meter to draw the UI charts.

### Action & Dispatch Endpoints
- **`POST /notify/{meter_id}`**: Triggers a notification to the assigned lineman for the zone.
- **`POST /feedback`**: Submits field-verified inspection feedback back into the system to improve the ML models.
- **`GET /audit`**: Retrieves the history of system actions and SMS dispatches.

### Administrative Endpoints
- **`GET /admin/settings` / `POST /admin/thresholds`**: Adjust backend rules (e.g., Night Use thresholds).
- **`GET /admin/linemen` / `POST /admin/linemen` / `DELETE /admin/linemen/{zone}`**: CRUD operations for managing the lineman dispatch roster.
- **`POST /admin/retrain`**: Forces the ML pipeline to retrain using freshly submitted ground-truth feedback.
- **`POST /admin/whitelist`**: Add specific commercial or heavy-load meters to an anomaly whitelist to avoid false positives.

---

## 5. Local Execution Guide

To run GridSense AI on a local environment for demonstration or testing:

1. **Install Requirements**
   Make sure you have Python 3.9+ and Node.js installed.
   ```bash
   pip install pandas duckdb lightgbm scikit-learn fastapi uvicorn matplotlib
   ```

2. **Generate the Synthetic Ecosystem**
   ```bash
   python generate_bescom_data.py
   python feature_engineering.py
   ```

3. **Train Models and Start the API**
   ```bash
   python train_forecast.py
   python train_anomaly.py
   python api.py
   ```
   *The backend will now be active at `http://127.0.0.1:8000`*

4. **Launch the Frontend UI**
   Open a new terminal session.
   ```bash
   cd dashboard
   npm install
   npm run dev
   ```
   *Access the dashboard at `http://localhost:5173`*

---

## 6. Expected Business Impact (Bangalore Simulation)

Based on a standard cluster scale of ~10,000 DTs:
- **Overload Prevention:** Identifying and preventing 5% of Red-Zone DT overloads saves approx. ₹2.4Cr/month in hardware replacement costs.
- **Fraud Recovery:** Flagging and recovering 2% of distribution theft saves approx. ₹1.5Cr/month.
- **Total Projected ROI:** **~₹3.9Cr / month.**

GridSense transforms idle smart-meter interval data into tangible grid reliability and revenue assurance without physical infrastructural changes.
