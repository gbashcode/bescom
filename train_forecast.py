import os
import joblib
import pandas as pd
import numpy as np
import lightgbm as lgb
from sklearn.metrics import mean_absolute_error, mean_absolute_percentage_error
import warnings
warnings.filterwarnings("ignore")

# Load data
print("Loading data...")
dt_hourly = pd.read_parquet("bescom_raw/dt_hourly.parquet")
dt_master = pd.read_csv("bescom_raw/dt_master.csv")

# Ensure datetimes
dt_hourly['timestamp_hour'] = pd.to_datetime(dt_hourly['timestamp_hour'])

# Drop rows with NaNs in features due to lags
features = [
    'mw_lag1', 'mw_lag24', 'mw_lag168', 'rolling_mean_7d', 'rolling_std_7d', 
    'hour', 'day_of_week', 'is_weekend', 'is_holiday', 'temp', 'temp_squared'
]
target = 'mw'

os.makedirs("model_store", exist_ok=True)

test_start = pd.Timestamp("2026-04-24")
test_end = pd.Timestamp("2026-04-30 23:59:59")
pred_day = pd.Timestamp("2026-04-30")

forecast_results = []

all_lgbm_mae = []
all_lgbm_mape = []
all_naive_mae = []
all_naive_mape = []

print("Training models per DT...")
unique_dts = dt_hourly['dt_id'].unique()

for idx, dt_id in enumerate(unique_dts):
    df_dt = dt_hourly[dt_hourly['dt_id'] == dt_id].copy()
    
    # Drop rows with NaNs in features
    df_dt = df_dt.dropna(subset=features + [target, 'mw_lag24'])
    
    train_mask = df_dt['timestamp_hour'] < test_start
    test_mask = (df_dt['timestamp_hour'] >= test_start) & (df_dt['timestamp_hour'] <= test_end)
    
    train_df = df_dt[train_mask]
    test_df = df_dt[test_mask]
    
    X_train, y_train = train_df[features], train_df[target]
    X_test, y_test = test_df[features], test_df[target]
    
    # Train model
    model = lgb.LGBMRegressor(
        n_estimators=100, 
        max_depth=6, 
        learning_rate=0.05, 
        random_state=42,
        n_jobs=1
    )
    model.fit(X_train, y_train)
    
    joblib.dump(model, f"model_store/forecast_dt_{dt_id}.pkl")
    
    # Backtest
    y_pred = model.predict(X_test)
    y_naive = test_df['mw_lag24']
    
    lgbm_mae = mean_absolute_error(y_test, y_pred)
    lgbm_mape = mean_absolute_percentage_error(y_test, y_pred)
    
    naive_mae = mean_absolute_error(y_test, y_naive)
    naive_mape = mean_absolute_percentage_error(y_test, y_naive)
    
    all_lgbm_mae.append(lgbm_mae)
    all_lgbm_mape.append(lgbm_mape)
    all_naive_mae.append(naive_mae)
    all_naive_mape.append(naive_mape)
    
    # Predictions for 2026-04-30
    pred_mask = test_df['timestamp_hour'].dt.date == pred_day.date()
    if pred_mask.sum() == 0:
        continue
        
    pred_df = test_df[pred_mask].copy()
    X_pred = pred_df[features]
    preds_final = model.predict(X_pred)
    
    capacity = pred_df['capacity'].values / 1000.0
    
    # Overload prob: simulate trees
    tree_preds = np.array([
        model.predict(X_pred, num_iteration=i) 
        for i in range(1, 101)
    ])
    overload_prob = np.mean(tree_preds > capacity, axis=0) * 100
    
    # Join with dt_master to get lat, long
    dt_info = dt_master[dt_master['dt_id'] == dt_id].iloc[0]
    lat = dt_info['lat']
    lon = dt_info['long']
    
    for i in range(len(pred_df)):
        mw_p = preds_final[i]
        cap = capacity[i]
        hr = pred_df['hour'].values[i]
        
        if mw_p > 0.9 * cap:
            risk = 'Red'
        elif mw_p > 0.7 * cap:
            risk = 'Amber'
        else:
            risk = 'Green'
            
        forecast_results.append({
            'dt_id': dt_id,
            'zone': dt_info['zone'],
            'lat': lat,
            'long': lon,
            'hour': hr,
            'mw_pred': mw_p,
            'capacity': cap,
            'risk_level': risk,
            'overload_prob': overload_prob[i]
        })
        
    if (idx + 1) % 20 == 0:
        print(f"  Processed {idx + 1}/{len(unique_dts)} DTs...")

print("Saving forecast results...")
results_df = pd.DataFrame(forecast_results)
results_df.to_csv("bescom_raw/forecast_results.csv", index=False)

# Compute average metrics
final_lgbm_mae = np.mean(all_lgbm_mae)
final_lgbm_mape = np.mean(all_lgbm_mape) * 100

final_naive_mae = np.mean(all_naive_mae)
final_naive_mape = np.mean(all_naive_mape) * 100

pct_better = ((final_naive_mae - final_lgbm_mae) / final_naive_mae) * 100

print("\n" + "="*60)
print("Forecast Backtest Results")
print("="*60)
print(f"| Model          | MAE    | MAPE   | % Better than Naive |")
print(f"|----------------|--------|--------|---------------------|")
print(f"| Naive Baseline | {final_naive_mae:.3f}  | {final_naive_mape:.2f}% | -                   |")
print(f"| GridSense LGBM | {final_lgbm_mae:.3f}  | {final_lgbm_mape:.2f}% | {pct_better:.2f}%              |")
print("="*60)

if pct_better > 25:
    print("TARGET MET: Z% > 25%")
else:
    print("TARGET FAILED: Z% <= 25%")

dt442_hr19 = results_df[(results_df['dt_id'] == 'DT-442') & (results_df['hour'] == 19)]
if not dt442_hr19.empty:
    risk = dt442_hr19.iloc[0]['risk_level']
    print(f"DT-442 Hour 19 Risk Level: {risk}")
    if risk == 'Red':
        print("TARGET MET: DT-442 hour 19 is Red")
    else:
        print("TARGET FAILED: DT-442 hour 19 is not Red")
else:
    print("DT-442 Hour 19 not found.")
