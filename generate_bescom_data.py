"""
GridSense Hackathon – BESCOM Synthetic Data Generator
=====================================================
Generates bescom_raw dataset with:
  • raw_15min   – 15-minute interval readings for 5000 meters over 30 days
  • meter_master – static attributes per meter
  • dt_master    – static attributes per DT

Fraud patterns injected (seed=42):
  A. Normal 95%   B. Theft 3%   C. Overload 2% DTs   D. Festival spikes   E. Data gaps 1%

Outputs:  bescom_raw/raw_15min.csv, meter_master.csv, dt_master.csv
Charts :  chart_dt442_overload.png, chart_H8842_theft.png, chart_apr14_festival.png
"""

import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings("ignore")

# ─── Configuration ───────────────────────────────────────────────────────────
SEED = 42
np.random.seed(SEED)

NUM_DTS = 100
METERS_PER_DT = 50
TOTAL_METERS = NUM_DTS * METERS_PER_DT  # 5000

ZONES = ["RR_Nagar", "Jayanagar", "Koramangala", "Whitefield", "Yelahanka"]
DTS_PER_ZONE = NUM_DTS // len(ZONES)  # 20

START_DATE = pd.Timestamp("2026-04-01")
END_DATE = pd.Timestamp("2026-04-30 23:45:00")
FREQ = "15min"

HOLIDAYS = [pd.Timestamp("2026-04-14"), pd.Timestamp("2026-04-25")]

# Overload DTs
OVERLOAD_DTS = ["DT-442", "DT-551"]

# Bangalore bounding box
LAT_MIN, LAT_MAX = 12.8, 13.1
LON_MIN, LON_MAX = 77.4, 77.8

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bescom_raw")
os.makedirs(OUTPUT_DIR, exist_ok=True)

print("=" * 70)
print("  GridSense – BESCOM Synthetic Data Generator")
print("=" * 70)

# ─── 1. Generate DT Master ──────────────────────────────────────────────────
print("\n[1/7] Generating DT master table …")

dt_ids = []
dt_zones = []
dt_lats = []
dt_lons = []

for z_idx, zone in enumerate(ZONES):
    for d in range(DTS_PER_ZONE):
        global_idx = z_idx * DTS_PER_ZONE + d
        dt_id = f"DT-{global_idx + 400}"
        dt_ids.append(dt_id)
        dt_zones.append(zone)
        # Spread lat/long across Bangalore box per zone
        lat = LAT_MIN + (z_idx + np.random.rand()) * (LAT_MAX - LAT_MIN) / len(ZONES)
        lon = LON_MIN + (d / DTS_PER_ZONE + np.random.rand() * 0.05) * (LON_MAX - LON_MIN)
        dt_lats.append(round(lat, 6))
        dt_lons.append(round(lon, 6))

dt_master = pd.DataFrame({
    "dt_id": dt_ids,
    "zone": dt_zones,
    "lat": dt_lats,
    "long": dt_lons,
})

# Feeder IDs – 4 DTs share a feeder
dt_master["feeder_id"] = [f"FDR-{i // 4 + 1:03d}" for i in range(NUM_DTS)]

print(f"   ✓ {len(dt_master)} DTs across {len(ZONES)} zones")

# ─── 2. Generate Meter Master ───────────────────────────────────────────────
print("[2/7] Generating meter master table …")

meter_rows = []
theft_meter_ids = set()
gap_meter_ids = set()

# Decide which meters are theft (3%) and gap (1%)
all_meter_indices = list(range(TOTAL_METERS))
np.random.shuffle(all_meter_indices)
num_theft = int(0.03 * TOTAL_METERS)  # 150
num_gap = int(0.01 * TOTAL_METERS)    # 50

theft_indices = set(all_meter_indices[:num_theft])
gap_indices = set(all_meter_indices[num_theft:num_theft + num_gap])

# 5% commercial meters
num_commercial = int(0.05 * TOTAL_METERS)
commercial_indices = set(np.random.choice(TOTAL_METERS, num_commercial, replace=False))

meter_idx = 0
for dt_row_idx in range(NUM_DTS):
    dt_id = dt_master.loc[dt_row_idx, "dt_id"]
    dt_zone = dt_master.loc[dt_row_idx, "zone"]
    dt_lat = dt_master.loc[dt_row_idx, "lat"]
    dt_lon = dt_master.loc[dt_row_idx, "long"]
    feeder_id = dt_master.loc[dt_row_idx, "feeder_id"]

    for m in range(METERS_PER_DT):
        is_theft = meter_idx in theft_indices
        is_gap = meter_idx in gap_indices
        is_commercial = meter_idx in commercial_indices

        # Theft meters start with H8
        if is_theft:
            mid = f"H8{meter_idx:04d}"
        else:
            mid = f"M{meter_idx:05d}"

        if is_commercial:
            sanctioned_load = round(np.random.uniform(10, 50), 1)
            tariff = "LT5-commercial"
        else:
            sanctioned_load = round(np.random.uniform(1, 5), 1)
            tariff = "LT2-domestic"

        m_lat = round(dt_lat + np.random.normal(0, 0.001), 6)
        m_lon = round(dt_lon + np.random.normal(0, 0.001), 6)

        meter_rows.append({
            "meter_id": mid,
            "dt_id": dt_id,
            "feeder_id": feeder_id,
            "zone": dt_zone,
            "sanctioned_load": sanctioned_load,
            "tariff_type": tariff,
            "lat": m_lat,
            "long": m_lon,
            "is_theft": is_theft,
            "is_gap": is_gap,
            "is_commercial": is_commercial,
        })

        if is_theft:
            theft_meter_ids.add(mid)
        if is_gap:
            gap_meter_ids.add(mid)

        meter_idx += 1

meter_master = pd.DataFrame(meter_rows)
print(f"   ✓ {len(meter_master)} meters ({num_theft} theft, {num_gap} gap, {num_commercial} commercial)")

# ─── 3. Compute DT Capacity ─────────────────────────────────────────────────
print("[3/7] Computing DT capacities …")

dt_capacity = meter_master.groupby("dt_id")["sanctioned_load"].sum() * 1.2
dt_master["capacity_kW"] = dt_master["dt_id"].map(dt_capacity).round(1)
print(f"   ✓ DT capacities computed (mean={dt_master['capacity_kW'].mean():.1f} kW)")

# ─── 4. Generate Time-series Data ───────────────────────────────────────────
print("[4/7] Generating 15-min interval data (this may take a few minutes) …")

timestamps = pd.date_range(START_DATE, END_DATE, freq=FREQ)
num_slots = len(timestamps)  # 2880
print(f"   Time range: {timestamps[0]} → {timestamps[-1]}, {num_slots} slots/meter")

hours = timestamps.hour + timestamps.minute / 60.0
day_of_month = timestamps.day
weekday = timestamps.weekday  # 0=Mon … 6=Sun
is_weekend = (weekday >= 5).astype(int)

# Pre-compute holiday mask
holiday_dates = set(h.date() for h in HOLIDAYS)
is_holiday_ts = np.array([1 if t.date() in holiday_dates else 0 for t in timestamps])

# Temperature: 25-35°C, higher on weekends
base_temp = 28.0 + 4.0 * np.sin(2 * np.pi * (hours - 14) / 24)  # peak at 2PM
temp_arr = base_temp + is_weekend * 2.0 + np.random.normal(0, 0.5, num_slots)
temp_arr = np.clip(temp_arr, 25, 35)

# Identify overload DT meters
overload_meter_ids = set(
    meter_master.loc[meter_master["dt_id"].isin(OVERLOAD_DTS), "meter_id"]
)

# Festival: 30% random meters get 2x on holidays
festival_meter_ids = set(
    meter_master.sample(frac=0.30, random_state=SEED)["meter_id"]
)

# Build data in chunks to manage memory
all_chunks = []
total_done = 0
chunk_report = max(1, TOTAL_METERS // 10)

for _, mrow in meter_master.iterrows():
    mid = mrow["meter_id"]
    is_theft = mrow["is_theft"]
    is_gap_meter = mrow["is_gap"]
    sanctioned = mrow["sanctioned_load"]

    # ── Base load ──
    kw = np.full(num_slots, 0.2) + np.random.uniform(0, 0.1, num_slots)

    # ── Day pattern (6AM–10PM) ──
    day_mask = (hours >= 6) & (hours <= 22)
    # Create realistic daily curve: morning peak 7-9, evening peak 18-21
    morning_peak = np.exp(-0.5 * ((hours - 8) / 1.5) ** 2)
    evening_peak = np.exp(-0.5 * ((hours - 19.5) / 2.0) ** 2)
    day_curve = 0.5 * morning_peak + 1.5 * evening_peak
    kw += day_mask * day_curve * np.random.uniform(0.5, 1.0)

    # ── Voltage ──
    voltage = np.random.uniform(220, 240, num_slots)

    # ── Tamper type ──
    tamper = np.full(num_slots, None, dtype=object)

    # ── Pattern A: Normal (default) ──
    # already set above

    # ── Pattern B: Theft ──
    if is_theft:
        # Night ratio > 0.7: heavy consumption 0-5AM
        night_mask = (hours >= 0) & (hours < 5)
        kw[night_mask] += np.random.uniform(1.5, 3.0, night_mask.sum())

        # Reduce daytime to make night_ratio > 0.7
        day_only = day_mask & ~night_mask
        kw[day_only] *= 0.3

        # Tamper events: kW > 1.5 during 1-4AM
        tamper_window = (hours >= 1) & (hours < 4)
        tamper_cond = tamper_window & (kw > 1.5)
        tamper[tamper_cond] = "neutral_disconnect"

        # Voltage drops during tamper
        voltage[tamper_cond] = np.random.uniform(180, 200, tamper_cond.sum())

    # ── Pattern C: Overload ──
    if mid in overload_meter_ids:
        evening_window = (hours >= 18) & (hours < 22)
        kw[evening_window] += 3.0

    # ── Pattern D: Festival ──
    if mid in festival_meter_ids:
        for hd in HOLIDAYS:
            hol_mask = np.array([t.date() == hd.date() for t in timestamps])
            kw[hol_mask] *= 2.0

    # Clip kW to reasonable range
    kw = np.clip(kw, 0, sanctioned * 3)

    # ── Compute billed_monthly_units ──
    real_units = kw.sum() * 0.25  # kWh (15 min = 0.25 hr)
    if is_theft:
        billed_monthly_units = round(real_units / 1.8, 1)
    else:
        billed_monthly_units = round(real_units * np.random.uniform(0.9, 1.1), 1)

    # ── Pattern E: Data gaps ──
    gap_mask = np.zeros(num_slots, dtype=bool)
    if is_gap_meter:
        num_missing = int(0.20 * num_slots)
        gap_idx = np.random.choice(num_slots, num_missing, replace=False)
        gap_mask[gap_idx] = True

    # Build DataFrame chunk
    chunk = pd.DataFrame({
        "meter_id": mid,
        "dt_id": mrow["dt_id"],
        "feeder_id": mrow["feeder_id"],
        "zone": mrow["zone"],
        "timestamp": timestamps,
        "kW": kw,
        "voltage": voltage,
        "tamper_type": tamper,
        "sanctioned_load": sanctioned,
        "tariff_type": mrow["tariff_type"],
        "billed_monthly_units": billed_monthly_units,
        "temp": np.round(temp_arr, 1),
        "is_holiday": is_holiday_ts,
        "lat": mrow["lat"],
        "long": mrow["long"],
    })

    # Apply data gaps
    if is_gap_meter:
        chunk.loc[gap_mask, "kW"] = np.nan
        chunk.loc[gap_mask, "voltage"] = np.nan

    all_chunks.append(chunk)
    total_done += 1
    if total_done % chunk_report == 0:
        print(f"   … {total_done}/{TOTAL_METERS} meters done ({100*total_done/TOTAL_METERS:.0f}%)")

print("   Concatenating all chunks …")
raw_15min = pd.concat(all_chunks, ignore_index=True)
print(f"   ✓ raw_15min: {len(raw_15min):,} rows × {len(raw_15min.columns)} columns")

# ─── 5. Save CSVs ───────────────────────────────────────────────────────────
print("[5/7] Saving CSV files …")

raw_path = os.path.join(OUTPUT_DIR, "raw_15min.csv")
raw_15min.to_csv(raw_path, index=False)
print(f"   ✓ {raw_path} ({os.path.getsize(raw_path) / 1e6:.1f} MB)")

# Clean meter_master for output (drop internal flags)
meter_out = meter_master.drop(columns=["is_theft", "is_gap", "is_commercial"])
meter_path = os.path.join(OUTPUT_DIR, "meter_master.csv")
meter_out.to_csv(meter_path, index=False)
print(f"   ✓ {meter_path}")

dt_path = os.path.join(OUTPUT_DIR, "dt_master.csv")
dt_master.to_csv(dt_path, index=False)
print(f"   ✓ {dt_path}")

# ─── 6. Validation Charts ───────────────────────────────────────────────────
print("[6/7] Generating validation charts …")

plt.rcParams.update({
    "figure.facecolor": "#0d1117",
    "axes.facecolor": "#161b22",
    "axes.edgecolor": "#30363d",
    "axes.labelcolor": "#c9d1d9",
    "text.color": "#c9d1d9",
    "xtick.color": "#8b949e",
    "ytick.color": "#8b949e",
    "grid.color": "#21262d",
    "font.family": "sans-serif",
    "font.size": 11,
})

# ── Chart 1: DT-442 Apr 20 – 24h MW curve ──
print("   Chart 1: DT-442 overload on Apr 20 …")
dt442_data = raw_15min[
    (raw_15min["dt_id"] == "DT-442") &
    (raw_15min["timestamp"].dt.date == pd.Timestamp("2026-04-20").date())
].copy()
dt442_agg = dt442_data.groupby("timestamp")["kW"].sum().reset_index()
dt442_agg["MW"] = dt442_agg["kW"] / 1000.0
capacity_kw = dt_master.loc[dt_master["dt_id"] == "DT-442", "capacity_kW"].values[0]
capacity_mw = capacity_kw / 1000.0

fig1, ax1 = plt.subplots(figsize=(14, 6))
ax1.fill_between(dt442_agg["timestamp"], dt442_agg["MW"], alpha=0.3, color="#58a6ff")
ax1.plot(dt442_agg["timestamp"], dt442_agg["MW"], color="#58a6ff", linewidth=2, label="DT-442 Load (MW)")
ax1.axhline(y=capacity_mw, color="#f85149", linewidth=2, linestyle="--", label=f"Capacity = {capacity_mw:.3f} MW")

# Mark breach zone
breach = dt442_agg[dt442_agg["MW"] > capacity_mw]
if len(breach) > 0:
    ax1.fill_between(
        breach["timestamp"], capacity_mw, breach["MW"],
        alpha=0.4, color="#f85149", label="Overload Breach"
    )

ax1.set_title("DT-442 • 24h Load Curve • April 20, 2026", fontsize=15, fontweight="bold", color="#f0f6fc")
ax1.set_xlabel("Time of Day")
ax1.set_ylabel("Load (MW)")
ax1.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
ax1.legend(loc="upper left", framealpha=0.8)
ax1.grid(True, alpha=0.3)
fig1.tight_layout()
chart1_path = os.path.join(OUTPUT_DIR, "chart_dt442_overload.png")
fig1.savefig(chart1_path, dpi=150)
plt.close(fig1)
print(f"   ✓ {chart1_path}")

# ── Chart 2: H8842 – 7-day kW with tamper markers ──
print("   Chart 2: Theft meter H8842 7-day view …")

# Find a theft meter – look for H8842 specifically or closest
theft_meters_list = sorted(theft_meter_ids)
# H8842 format: we need to find the meter id that is H8 + 0842 or similar
target_theft = None
for tm in theft_meters_list:
    if "842" in tm:
        target_theft = tm
        break
if target_theft is None:
    target_theft = theft_meters_list[0]
print(f"   Using theft meter: {target_theft}")

h8_data = raw_15min[
    (raw_15min["meter_id"] == target_theft) &
    (raw_15min["timestamp"] >= pd.Timestamp("2026-04-10")) &
    (raw_15min["timestamp"] < pd.Timestamp("2026-04-17"))
].copy()

fig2, ax2 = plt.subplots(figsize=(14, 6))
ax2.plot(h8_data["timestamp"], h8_data["kW"], color="#7ee787", linewidth=1, alpha=0.8, label=f"{target_theft} kW")

# Red markers for tamper events
tamper_pts = h8_data[h8_data["tamper_type"].notna()]
ax2.scatter(tamper_pts["timestamp"], tamper_pts["kW"], color="#f85149", s=30, zorder=5,
            marker="v", label=f"Tamper: neutral_disconnect ({len(tamper_pts)} events)")

ax2.set_title(f"{target_theft} • 7-Day Consumption • Apr 10–16, 2026", fontsize=15, fontweight="bold", color="#f0f6fc")
ax2.set_xlabel("Date")
ax2.set_ylabel("kW")
ax2.xaxis.set_major_formatter(mdates.DateFormatter("%b %d\n%H:%M"))
ax2.legend(loc="upper right", framealpha=0.8)
ax2.grid(True, alpha=0.3)
fig2.tight_layout()
chart2_path = os.path.join(OUTPUT_DIR, "chart_H8842_theft.png")
fig2.savefig(chart2_path, dpi=150)
plt.close(fig2)
print(f"   ✓ {chart2_path}")

# ── Chart 3: Apr 14 – Overlay 40 random meters ──
print("   Chart 3: Festival day Apr 14 overlay …")
festival_subset = list(festival_meter_ids)[:40]

fig3, ax3 = plt.subplots(figsize=(14, 6))
for i, mid in enumerate(festival_subset):
    m_data = raw_15min[
        (raw_15min["meter_id"] == mid) &
        (raw_15min["timestamp"].dt.date == pd.Timestamp("2026-04-14").date())
    ]
    color = plt.cm.plasma(i / len(festival_subset))
    ax3.plot(m_data["timestamp"], m_data["kW"], color=color, alpha=0.5, linewidth=0.8)

ax3.set_title("Festival Day (Apr 14) • 40 Meters Overlay • 2× kW Spike", fontsize=15, fontweight="bold", color="#f0f6fc")
ax3.set_xlabel("Time of Day")
ax3.set_ylabel("kW")
ax3.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
ax3.grid(True, alpha=0.3)

# Add annotation
ax3.annotate("Festival 2× spike zone", xy=(pd.Timestamp("2026-04-14 19:00"), 3.5),
             fontsize=12, color="#ffa657", fontweight="bold",
             arrowprops=dict(arrowstyle="->", color="#ffa657"))

fig3.tight_layout()
chart3_path = os.path.join(OUTPUT_DIR, "chart_apr14_festival.png")
fig3.savefig(chart3_path, dpi=150)
plt.close(fig3)
print(f"   ✓ {chart3_path}")

# ─── 7. Summary ─────────────────────────────────────────────────────────────
print("\n[7/7] Final Summary")
print("=" * 70)
print(f"  raw_15min    : {len(raw_15min):>12,} rows  ({raw_15min['meter_id'].nunique()} meters × {num_slots} slots)")
print(f"  meter_master : {len(meter_out):>12,} rows")
print(f"  dt_master    : {len(dt_master):>12,} rows")
print(f"  Theft meters : {len(theft_meter_ids):>12,} ({100*len(theft_meter_ids)/TOTAL_METERS:.1f}%)")
print(f"  Gap meters   : {len(gap_meter_ids):>12,} ({100*len(gap_meter_ids)/TOTAL_METERS:.1f}%)")
print(f"  Null kW rows : {raw_15min['kW'].isna().sum():>12,}")
print(f"  Tamper events: {(raw_15min['tamper_type'].notna()).sum():>12,}")
print(f"  Holiday slots: {(raw_15min['is_holiday'] == 1).sum():>12,}")
print("=" * 70)

# Quick DT-442 breach verification
dt442_peak = dt442_agg["MW"].max()
print(f"\n  DT-442 peak load: {dt442_peak:.4f} MW vs capacity {capacity_mw:.4f} MW")
if dt442_peak > capacity_mw:
    peak_time = dt442_agg.loc[dt442_agg["MW"].idxmax(), "timestamp"]
    print(f"  ✓ BREACH confirmed at {peak_time.strftime('%H:%M')} (expected ~19:00)")
else:
    print(f"  ✗ WARNING: No breach detected – check overload injection")

# Theft night ratio verification
if len(h8_data) > 0:
    night_kw = h8_data[(h8_data["timestamp"].dt.hour >= 0) & (h8_data["timestamp"].dt.hour < 5)]["kW"].sum()
    total_kw = h8_data["kW"].sum()
    night_ratio = night_kw / total_kw if total_kw > 0 else 0
    print(f"  {target_theft} night ratio: {night_ratio:.2f} (expected >0.70)")

print(f"\n  Output directory: {OUTPUT_DIR}")
print("  ✅ Done!")
