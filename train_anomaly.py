import pandas as pd
import numpy as np
import joblib
import os
import warnings
from sklearn.ensemble import IsolationForest
from sklearn.metrics import precision_score, recall_score, f1_score

warnings.filterwarnings('ignore')

print("Loading data...")
meter_daily = pd.read_parquet("bescom_raw/meter_daily.parquet")

features = ['unit_lie_ratio', 'night_ratio', 'load_factor', 'tamper_spikes', 'zero_hours', 'voltage_drops', 'peer_zscore']

# Handle NaNs
meter_daily['unit_lie_ratio'] = meter_daily['unit_lie_ratio'].fillna(1.0)
meter_daily[features] = meter_daily[features].fillna(0)
# Ensure infinite values are also 0
meter_daily.replace([np.inf, -np.inf], 0, inplace=True)

unique_dts = meter_daily['dt_id'].unique()

print("Training Isolation Forests...")
scores_day30 = []

for idx, dt_id in enumerate(unique_dts):
    df_dt = meter_daily[meter_daily['dt_id'] == dt_id].copy()
    
    X_train = df_dt[features]
    
    # Train Isolation Forest
    model = IsolationForest(n_estimators=300, contamination=0.03, random_state=42)
    model.fit(X_train)
    
    joblib.dump(model, f"model_store/anomaly_dt_{dt_id}.pkl")
    
    # Predict for April 30th
    df_dt_30 = df_dt[df_dt['date'] == pd.Timestamp('2026-04-30').date()].copy()
    if not df_dt_30.empty:
        X_test = df_dt_30[features]
        # score_samples returns the anomaly score. Lower is more abnormal.
        # We negate it so higher score = more anomalous.
        raw_scores = -model.score_samples(X_test)
        preds = model.predict(X_test)
        
        for i, row in enumerate(df_dt_30.itertuples()):
            scores_day30.append({
                'meter_id': row.meter_id,
                'dt_id': row.dt_id,
                'zone': row.zone,
                'score': raw_scores[i],
                'is_pred_anomaly': 1 if preds[i] == -1 else 0,
                'is_fraud_groundtruth': row.is_fraud_groundtruth
            })
            
    if (idx + 1) % 20 == 0:
        print(f"  Processed {idx + 1}/{len(unique_dts)} DTs...")

print("Computing risk levels...")
results_df = pd.DataFrame(scores_day30)

# Calculate percentiles
p99 = np.percentile(results_df['score'], 99)
p95 = np.percentile(results_df['score'], 95)

def get_risk(score):
    if score >= p99:
        return 'High'
    elif score >= p95:
        return 'Medium'
    else:
        return 'Low'

results_df['risk_level'] = results_df['score'].apply(get_risk)

cols_to_save = ['meter_id', 'dt_id', 'zone', 'score', 'risk_level', 'is_fraud_groundtruth']
results_df[cols_to_save].to_csv("bescom_raw/anomaly_scores.csv", index=False)

# Evaluate Baseline on April 30th
df_30 = meter_daily[meter_daily['date'] == pd.Timestamp('2026-04-30').date()]
baseline_preds = (df_30['unit_lie_ratio'] > 1.5).astype(int)
y_true = df_30['is_fraud_groundtruth']

base_p = precision_score(y_true, baseline_preds) * 100
base_r = recall_score(y_true, baseline_preds) * 100
base_f1 = f1_score(y_true, baseline_preds)

# Evaluate GridSense IF using global 97th percentile of scores (top 3%)
global_threshold = np.percentile(results_df['score'], 97)
if_preds = (results_df['score'] >= global_threshold).astype(int)
if_true = results_df['is_fraud_groundtruth']

if_p = precision_score(if_true, if_preds) * 100
if_r = recall_score(if_true, if_preds) * 100
if_f1 = f1_score(if_true, if_preds)

print("\n" + "="*50)
print("Anomaly Detection Results (2026-04-30)")
print("="*50)
print(f"| Model          | Precision | Recall | F1    |")
print(f"|----------------|-----------|--------|-------|")
print(f"| Rule Baseline  | {base_p:.2f}%    | {base_r:.2f}%| {base_f1:.3f} |")
print(f"| GridSense IF   | {if_p:.2f}%    | {if_r:.2f}%| {if_f1:.3f} |")
print("="*50)

if if_f1 > 0.70:
    print("TARGET MET: F1 > 0.70")
else:
    print("TARGET FAILED: F1 <= 0.70")

h8_meters = results_df[results_df['meter_id'].str.startswith('H8')]
h8_high = h8_meters[h8_meters['risk_level'] == 'High']
h8_med = h8_meters[h8_meters['risk_level'] == 'Medium']

print(f"\nH8* Meters Risk Breakdown:")
print(f"  Total H8* Meters: {len(h8_meters)}")
print(f"  High Risk:   {len(h8_high)}")
print(f"  Medium Risk: {len(h8_med)}")
print(f"  Low Risk:    {len(h8_meters) - len(h8_high) - len(h8_med)}")
