# GridSense AI – Complete Project Documentation

This document outlines the entire end-to-end pipeline developed for the GridSense hackathon, including synthetic data generation, highly optimized feature engineering, baseline evaluation, predictive modeling, anomaly detection, and the live API deployment.

---

## 1. Synthetic Data Generation (`bescom_raw/`)
We simulated a massive, highly realistic 30-day electricity consumption dataset representing 5,000 smart meters across 100 Distribution Transformers (DTs) in Bangalore. 

### Core Outputs
* **`raw_15min.csv` (2.04 GB)**: Contains 14.4 million rows of 15-minute interval readings (kW, voltage, temp) for 30 days.
* **`meter_master.csv`**: Metadata for 5,000 meters, including `sanctioned_load`, `tariff_type` (domestic/commercial), and coordinates.
* **`dt_master.csv`**: Metadata for 100 DTs, mapping them to 5 geographical zones and calculating total theoretical capacity.

### Injected Anomalies (Seed = 42)
* **Theft (3% of meters)**: High nighttime consumption (>70% of daily load) and neutral disconnect tamper markers.
* **Overload (2% of DTs)**: Injected massive 3.0 kW spikes during evening hours (18:00 - 22:00) causing DT capacity breaches.
* **Festival Spikes**: Synchronized 2x load spikes on selected holidays (e.g., April 14).
* **Data Quality Gaps (1%)**: Dropped out 20% of intervals randomly to simulate connectivity drops.

*(Note: Validation charts for the Overload, Theft, and Festival spikes are saved as PNGs in the `bescom_raw` directory).*

---

## 2. Feature Engineering & Baselines (`feature_engineering.py`)
To process the 2GB raw dataset without hitting out-of-memory errors, we utilized **DuckDB** for blazing-fast, out-of-core SQL execution. 

### Feature Tables Created
1. **`dt_hourly.parquet`**: 
   * **Target**: `mw` (Hourly Aggregated Megawatts)
   * **Lag Features**: `mw_lag1`, `mw_lag24`, `mw_lag168`
   * **Rolling Stats**: 7-day rolling mean and std-dev for the *same hour*.
   * **Calendar/Weather**: `hour`, `day_of_week`, `is_weekend`, `is_holiday`, `temp`, `temp_squared`.

2. **`meter_daily.parquet`**:
   * **Fraud Features**: `unit_lie_ratio` (Real vs. Billed units), `night_ratio` (00:00 - 05:00 load ratio), `tamper_spikes`, and `voltage_drops`.
   * **Statistical Features**: `peer_zscore` comparing daily units against meters with the same prefix.
   * **Gaps & Islands**: Computed exact consecutive zero-load streaks (`zero_hours` > 16 slots).

### Baseline Evaluation (April 24 - 30)
* **Naive Forecast**: Achieved a **0.010 MW** Mean Absolute Error (MAE), beating the 1.0 MW target.
* **Rule-based Anomaly**: Achieved **61.65% Precision** and **100% Recall**, beating the >60% precision target.

---

## 3. Machine Learning Models (`train_forecast.py` & `train_anomaly.py`)

### LightGBM Forecasting Pipeline
* **Models**: 100 independent LightGBM Regressors (one for each DT).
* **Performance**: Slashed the Naive Baseline MAE by **55.72%** (achieving 0.004 MW MAE and 3.15% MAPE).
* **Real-time Risk**: Computed `risk_level` categories (**Red** > 90% capacity, **Amber** > 70% capacity, **Green**) stored in `forecast_results.csv`. Successfully flagged `DT-442` at Hour 19 with a **🔴 Red** risk level.

### Isolation Forest Anomaly Detection
* Combines **Isolation Forest** algorithms with strict rule-based thresholds (e.g. Unit Lie Ratio).
* Analyzes patterns dynamically to score and rank anomalies based on estimated financial loss.
* Generates `anomaly_scores.csv` assigning High/Medium/Low risks globally.

---

## 4. API Backend & System Actions (`api.py`)
A fully functioning FastAPI backend operationalizes the predictions and anomaly flags for end-users (AEEs and Linemen). It utilizes live DuckDB connections for ultra-fast, on-the-fly analytical queries.

### Operational Endpoints
* **`GET /zones/risk`**: Aggregates the Red/Amber/Green DT counts per geographical zone.
* **`GET /forecast/zone/{zone}`**: Granular 24-hour predictive forecast mapped to a specific zone.
* **`GET /anomalies`**: Returns a prioritized list of anomalies sorted by estimated ₹ loss per day, complete with an **Auto-Reason Text** (e.g., *"340u real vs 180u billed | High night use (80%)"*).
* **`GET /meter/curve/{meter_id}`**: Dynamically queries DuckDB to return the full 24-hour raw load curve and tamper flags.

### Action & Dispatch Endpoints (Lineman Workflows)
* **`POST /notify/{meter_id}`**: Dispatches SMS notification and routing info to the assigned lineman for the specific zone.
* **`POST /feedback`**: Linemen submit ground-truth field inspection feedback via mobile.
* **`GET /audit`**: Comprehensive system action and tracking log (SMS sent, feedback registered).

### Administrative Endpoints
* **`GET /admin/settings`** & **`POST /admin/thresholds`**: Tune rule engine parameters dynamically.
* **`GET /admin/linemen`**, **`POST /admin/linemen`**, **`DELETE /admin/linemen/{zone}`**: Full CRUD management of the lineman dispatch roster.
* **`POST /admin/retrain`**: Forces ML pipeline to actively retrain using the newly ingested field feedback, natively improving F1 scores.
* **`POST /admin/whitelist`**: Exempt specific high-load commercial meters from anomaly detection to combat false positives.

---

## 5. React Dashboard (`dashboard/`)
The primary interface for BESCOM Executive Engineers.
* **Top Stats Strip**: Live aggregation of "₹ At Risk Today", "Overloads Predicted", and "Active Theft Flags".
* **Leaflet Heatmap**: Interactive map plotting DT clusters. Radius and color (Red/Amber/Green) scale dynamically based on zone overload predictions.
* **Anomaly Triage Table**: Operators sort high-risk meters by ROI (estimated recoverable loss) and trigger immediate SMS dispatch to linemen.
* **Drill-down Modal**: Clicking a meter fetches its live load curve, plotting red dots explicitly where `neutral_disconnect` tampers occurred.

---

## 6. Business Impact (Bangalore Scale)
Based on a standard cluster scale of ~10,000 DTs:
- **Overload Prevention:** Preventing 5% of Red-Zone DT overloads saves approx. ₹2.4Cr/month.
- **Fraud Recovery:** Flagging and recovering 2% of distribution theft saves approx. ₹1.5Cr/month.
- **Total Projected ROI:** **~₹3.9Cr / month.**
