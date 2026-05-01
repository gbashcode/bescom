import duckdb
import pandas as pd
import numpy as np

print("Connecting to DuckDB and loading data...")
con = duckdb.connect()

# Read the CSVs
con.execute("""
    CREATE TABLE raw AS SELECT * FROM read_csv_auto('bescom_raw/raw_15min.csv');
    CREATE TABLE meter_master AS SELECT * FROM read_csv_auto('bescom_raw/meter_master.csv');
    CREATE TABLE dt_master AS SELECT * FROM read_csv_auto('bescom_raw/dt_master.csv');
""")

print("Creating dt_hourly table...")
con.execute("""
    CREATE TABLE dt_hourly AS
    WITH hourly_aggs AS (
        SELECT 
            dt_id,
            zone,
            date_trunc('hour', timestamp) AS timestamp_hour,
            SUM(kW)/1000 AS mw,
            AVG(temp) AS temp
        FROM raw
        GROUP BY dt_id, zone, date_trunc('hour', timestamp)
    ),
    dt_caps AS (
        SELECT dt_id, MAX(capacity_kW) AS capacity 
        FROM dt_master 
        GROUP BY dt_id
    )
    SELECT 
        h.dt_id,
        h.zone,
        extract('hour' FROM h.timestamp_hour) AS hour,
        h.timestamp_hour,
        h.mw,
        c.capacity,
        LAG(h.mw, 1) OVER (PARTITION BY h.dt_id ORDER BY h.timestamp_hour) AS mw_lag1,
        LAG(h.mw, 24) OVER (PARTITION BY h.dt_id ORDER BY h.timestamp_hour) AS mw_lag24,
        LAG(h.mw, 168) OVER (PARTITION BY h.dt_id ORDER BY h.timestamp_hour) AS mw_lag168,
        AVG(h.mw) OVER (
            PARTITION BY h.dt_id, extract('hour' FROM h.timestamp_hour)
            ORDER BY h.timestamp_hour 
            RANGE BETWEEN INTERVAL 7 DAYS PRECEDING AND INTERVAL 1 DAY PRECEDING
        ) AS rolling_mean_7d,
        STDDEV_SAMP(h.mw) OVER (
            PARTITION BY h.dt_id, extract('hour' FROM h.timestamp_hour)
            ORDER BY h.timestamp_hour 
            RANGE BETWEEN INTERVAL 7 DAYS PRECEDING AND INTERVAL 1 DAY PRECEDING
        ) AS rolling_std_7d,
        extract('isodow' FROM h.timestamp_hour) AS day_of_week,
        CASE WHEN extract('isodow' FROM h.timestamp_hour) >= 6 THEN 1 ELSE 0 END AS is_weekend,
        CASE WHEN CAST(h.timestamp_hour AS DATE) IN (DATE '2026-04-14', DATE '2026-04-25') THEN 1 ELSE 0 END AS is_holiday,
        h.temp,
        POWER(h.temp, 2) AS temp_squared
    FROM hourly_aggs h
    LEFT JOIN dt_caps c ON h.dt_id = c.dt_id
""")

print("Creating meter_daily table...")
con.execute("""
    CREATE TABLE meter_daily AS
    WITH daily_aggs AS (
        SELECT 
            meter_id,
            dt_id,
            MAX(zone) AS zone,
            CAST(timestamp AS DATE) AS date,
            MAX(tariff_type) AS tariff_type,
            MAX(sanctioned_load) AS sanctioned_load,
            SUM(kW)*0.25 AS real_units_day,
            MAX(billed_monthly_units)/30.0 AS billed_units_day,
            SUM(CASE WHEN extract('hour' FROM timestamp) BETWEEN 0 AND 5 THEN kW ELSE 0 END)*0.25 AS night_units,
            MAX(kW) AS max_kw,
            COUNT(CASE WHEN tamper_type IS NOT NULL AND kW > 1 THEN 1 END) AS tamper_spikes,
            COUNT(CASE WHEN voltage < 180 AND kW > 1 THEN 1 END) AS voltage_drops,
        FROM raw
        GROUP BY meter_id, dt_id, CAST(timestamp AS DATE)
    ),
    streaks AS (
        SELECT 
            meter_id, 
            CAST(timestamp AS DATE) AS date,
            kW < 0.05 AS is_zero,
            row_number() OVER (PARTITION BY meter_id, CAST(timestamp AS DATE) ORDER BY timestamp) 
            - row_number() OVER (PARTITION BY meter_id, CAST(timestamp AS DATE), kW < 0.05 ORDER BY timestamp) AS grp
        FROM raw
    ),
    streak_counts AS (
        SELECT meter_id, date, COUNT(*) AS streak_len
        FROM streaks
        WHERE is_zero = true
        GROUP BY meter_id, date, grp
    ),
    zero_hours_agg AS (
        SELECT meter_id, date, COUNT(*) AS zero_hours
        FROM streak_counts
        WHERE streak_len > 16
        GROUP BY meter_id, date
    )
    SELECT 
        d.meter_id,
        d.dt_id,
        d.zone,
        d.date,
        d.tariff_type,
        d.sanctioned_load,
        d.real_units_day,
        d.billed_units_day,
        d.real_units_day / NULLIF(d.billed_units_day, 0) AS unit_lie_ratio,
        d.night_units / NULLIF(d.real_units_day, 0) AS night_ratio,
        d.max_kw,
        d.max_kw / NULLIF(d.sanctioned_load, 0) AS load_factor,
        d.tamper_spikes,
        COALESCE(z.zero_hours, 0) AS zero_hours,
        d.voltage_drops,
        (d.real_units_day - AVG(d.real_units_day) OVER (PARTITION BY substr(d.meter_id, 1, 3), d.date)) 
            / NULLIF(STDDEV_SAMP(d.real_units_day) OVER (PARTITION BY substr(d.meter_id, 1, 3), d.date), 0) AS peer_zscore,
        CASE WHEN d.meter_id LIKE 'H8%' THEN 1 ELSE 0 END AS is_fraud_groundtruth
    FROM daily_aggs d
    LEFT JOIN zero_hours_agg z ON d.meter_id = z.meter_id AND d.date = z.date
""")

print("Computing Baseline 1: Naive Forecast...")
forecast_res = con.execute("""
    SELECT 
        AVG(ABS(mw - mw_lag24)) AS mae,
        AVG(ABS(mw - mw_lag24) / NULLIF(mw, 0)) * 100 AS mape
    FROM dt_hourly
    WHERE timestamp_hour >= '2026-04-24'
""").fetchone()

mae = forecast_res[0]
mape = forecast_res[1]

print("Computing Baseline 2: Rule Anomaly...")
anomaly_res = con.execute("""
    WITH preds AS (
        SELECT 
            is_fraud_groundtruth,
            CASE WHEN unit_lie_ratio > 1.5 THEN 1 ELSE 0 END AS is_pred
        FROM meter_daily
    )
    SELECT 
        SUM(CASE WHEN is_pred = 1 AND is_fraud_groundtruth = 1 THEN 1 ELSE 0 END) AS tp,
        SUM(CASE WHEN is_pred = 1 AND is_fraud_groundtruth = 0 THEN 1 ELSE 0 END) AS fp,
        SUM(CASE WHEN is_pred = 0 AND is_fraud_groundtruth = 1 THEN 1 ELSE 0 END) AS fn
    FROM preds
""").fetchone()

tp, fp, fn = anomaly_res
precision = tp / (tp + fp) * 100 if (tp + fp) > 0 else 0.0
recall = tp / (tp + fn) * 100 if (tp + fn) > 0 else 0.0

print("\n" + "="*50)
print("Day1_Baselines")
print("="*50)
print(f"| Task     | Model    | MAE    | MAPE   | Precision | Recall |")
print(f"|----------|----------|--------|--------|-----------|--------|")
print(f"| Forecast | Naive    | {mae:.3f}  | {mape:.2f}% | -         | -      |")
print(f"| Anomaly  | Rule>1.5 | -      | -      | {precision:.2f}%    | {recall:.2f}% |")
print("="*50)

if mae < 1.0 and precision > 60:
    print("TARGET MET! Naive MAE < 1.0MW and Rule Precision > 60%.")
else:
    print("TARGET NOT MET. Debug data gen.")

# Save tables as parquet for downstream
print("Saving feature tables to parquet...")
con.execute("COPY dt_hourly TO 'bescom_raw/dt_hourly.parquet' (FORMAT PARQUET)")
con.execute("COPY meter_daily TO 'bescom_raw/meter_daily.parquet' (FORMAT PARQUET)")
print("Done!")
