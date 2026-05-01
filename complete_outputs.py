"""
GridSense – Complete Missing Outputs
=====================================
Re-generates master tables + charts without re-building raw_15min.csv
Uses the same seed=42 and parameters for consistency.
"""

import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import warnings
warnings.filterwarnings("ignore")

# ─── Configuration (same as main script) ────────────────────────────────────
SEED = 42
np.random.seed(SEED)

NUM_DTS = 100
METERS_PER_DT = 50
TOTAL_METERS = NUM_DTS * METERS_PER_DT

ZONES = ["RR_Nagar", "Jayanagar", "Koramangala", "Whitefield", "Yelahanka"]
DTS_PER_ZONE = NUM_DTS // len(ZONES)

START_DATE = pd.Timestamp("2026-04-01")
END_DATE = pd.Timestamp("2026-04-30 23:45:00")
FREQ = "15min"

HOLIDAYS = [pd.Timestamp("2026-04-14"), pd.Timestamp("2026-04-25")]
OVERLOAD_DTS = ["DT-442", "DT-551"]

LAT_MIN, LAT_MAX = 12.8, 13.1
LON_MIN, LON_MAX = 77.4, 77.8

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bescom_raw")
os.makedirs(OUTPUT_DIR, exist_ok=True)

print("=" * 70)
print("  GridSense - Complete Missing Outputs (master tables + charts)")
print("=" * 70)

# ─── 1. Rebuild DT Master ───────────────────────────────────────────────────
print("\n[1/5] Rebuilding DT master table ...")

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
dt_master["feeder_id"] = [f"FDR-{i // 4 + 1:03d}" for i in range(NUM_DTS)]
print(f"   Done: {len(dt_master)} DTs across {len(ZONES)} zones")

# ─── 2. Rebuild Meter Master ────────────────────────────────────────────────
print("[2/5] Rebuilding meter master table ...")

meter_rows = []
theft_meter_ids = set()
gap_meter_ids = set()

all_meter_indices = list(range(TOTAL_METERS))
np.random.shuffle(all_meter_indices)
num_theft = int(0.03 * TOTAL_METERS)
num_gap = int(0.01 * TOTAL_METERS)

theft_indices = set(all_meter_indices[:num_theft])
gap_indices = set(all_meter_indices[num_theft:num_theft + num_gap])

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

# Compute DT capacity
dt_capacity = meter_master.groupby("dt_id")["sanctioned_load"].sum() * 1.2
dt_master["capacity_kW"] = dt_master["dt_id"].map(dt_capacity).round(1)

print(f"   Done: {len(meter_master)} meters ({num_theft} theft, {num_gap} gap, {num_commercial} commercial)")

# ─── 3. Save Master CSVs ────────────────────────────────────────────────────
print("[3/5] Saving master CSV files ...")

meter_out = meter_master.drop(columns=["is_theft", "is_gap", "is_commercial"])
meter_path = os.path.join(OUTPUT_DIR, "meter_master.csv")
meter_out.to_csv(meter_path, index=False)
print(f"   Saved: {meter_path}")

dt_path = os.path.join(OUTPUT_DIR, "dt_master.csv")
dt_master.to_csv(dt_path, index=False)
print(f"   Saved: {dt_path}")

# ─── 4. Generate Validation Charts ──────────────────────────────────────────
print("[4/5] Loading raw_15min.csv for charts (this may take a minute) ...")

raw_path = os.path.join(OUTPUT_DIR, "raw_15min.csv")
if not os.path.exists(raw_path):
    print("   ERROR: raw_15min.csv not found! Run generate_bescom_data.py first.")
    exit(1)

# Read only necessary columns for charts to save memory
print("   Reading raw data (subset columns) ...")
raw_15min = pd.read_csv(
    raw_path,
    usecols=["meter_id", "dt_id", "timestamp", "kW", "tamper_type", "voltage"],
    parse_dates=["timestamp"],
    dtype={"meter_id": str, "dt_id": str, "tamper_type": str},
)
print(f"   Loaded: {len(raw_15min):,} rows")

# Chart styling
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

# ── Chart 1: DT-442 Apr 20 overload ──
print("   Chart 1: DT-442 overload on Apr 20 ...")
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

breach = dt442_agg[dt442_agg["MW"] > capacity_mw]
if len(breach) > 0:
    ax1.fill_between(
        breach["timestamp"], capacity_mw, breach["MW"],
        alpha=0.4, color="#f85149", label="Overload Breach"
    )

ax1.set_title("DT-442 - 24h Load Curve - April 20, 2026", fontsize=15, fontweight="bold", color="#f0f6fc")
ax1.set_xlabel("Time of Day")
ax1.set_ylabel("Load (MW)")
ax1.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
ax1.legend(loc="upper left", framealpha=0.8)
ax1.grid(True, alpha=0.3)
fig1.tight_layout()
chart1_path = os.path.join(OUTPUT_DIR, "chart_dt442_overload.png")
fig1.savefig(chart1_path, dpi=150)
plt.close(fig1)
print(f"   Saved: {chart1_path}")

# ── Chart 2: Theft meter 7-day view ──
print("   Chart 2: Theft meter 7-day view ...")
theft_meters_list = sorted(theft_meter_ids)
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

tamper_pts = h8_data[h8_data["tamper_type"].notna()]
ax2.scatter(tamper_pts["timestamp"], tamper_pts["kW"], color="#f85149", s=30, zorder=5,
            marker="v", label=f"Tamper: neutral_disconnect ({len(tamper_pts)} events)")

ax2.set_title(f"{target_theft} - 7-Day Consumption - Apr 10-16, 2026", fontsize=15, fontweight="bold", color="#f0f6fc")
ax2.set_xlabel("Date")
ax2.set_ylabel("kW")
ax2.xaxis.set_major_formatter(mdates.DateFormatter("%b %d\n%H:%M"))
ax2.legend(loc="upper right", framealpha=0.8)
ax2.grid(True, alpha=0.3)
fig2.tight_layout()
chart2_path = os.path.join(OUTPUT_DIR, "chart_H8842_theft.png")
fig2.savefig(chart2_path, dpi=150)
plt.close(fig2)
print(f"   Saved: {chart2_path}")

# ── Chart 3: Festival day Apr 14 overlay ──
print("   Chart 3: Festival day Apr 14 overlay ...")

# Re-determine festival meters (same seed, same logic)
np.random.seed(SEED)
festival_meter_ids_for_chart = set(
    meter_master.sample(frac=0.30, random_state=SEED)["meter_id"]
)
festival_subset = list(festival_meter_ids_for_chart)[:40]

fig3, ax3 = plt.subplots(figsize=(14, 6))
for i, mid in enumerate(festival_subset):
    m_data = raw_15min[
        (raw_15min["meter_id"] == mid) &
        (raw_15min["timestamp"].dt.date == pd.Timestamp("2026-04-14").date())
    ]
    color = plt.cm.plasma(i / len(festival_subset))
    ax3.plot(m_data["timestamp"], m_data["kW"], color=color, alpha=0.5, linewidth=0.8)

ax3.set_title("Festival Day (Apr 14) - 40 Meters Overlay - 2x kW Spike", fontsize=15, fontweight="bold", color="#f0f6fc")
ax3.set_xlabel("Time of Day")
ax3.set_ylabel("kW")
ax3.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
ax3.grid(True, alpha=0.3)

ax3.annotate("Festival 2x spike zone", xy=(pd.Timestamp("2026-04-14 19:00"), 3.5),
             fontsize=12, color="#ffa657", fontweight="bold",
             arrowprops=dict(arrowstyle="->", color="#ffa657"))

fig3.tight_layout()
chart3_path = os.path.join(OUTPUT_DIR, "chart_apr14_festival.png")
fig3.savefig(chart3_path, dpi=150)
plt.close(fig3)
print(f"   Saved: {chart3_path}")

# ─── 5. Summary ─────────────────────────────────────────────────────────────
print("\n[5/5] Summary")
print("=" * 70)
print(f"  raw_15min.csv    : {len(raw_15min):>12,} rows (already existed)")
print(f"  meter_master.csv : {len(meter_out):>12,} rows  NEW")
print(f"  dt_master.csv    : {len(dt_master):>12,} rows  NEW")
print(f"  Theft meters     : {len(theft_meter_ids):>12,}")
print(f"  Gap meters       : {len(gap_meter_ids):>12,}")
print(f"  Charts generated :")
print(f"    - chart_dt442_overload.png")
print(f"    - chart_H8842_theft.png")
print(f"    - chart_apr14_festival.png")

# DT-442 breach check
dt442_peak = dt442_agg["MW"].max()
print(f"\n  DT-442 peak: {dt442_peak:.4f} MW vs capacity {capacity_mw:.4f} MW")
if dt442_peak > capacity_mw:
    peak_time = dt442_agg.loc[dt442_agg["MW"].idxmax(), "timestamp"]
    print(f"  BREACH confirmed at {peak_time.strftime('%H:%M')}")
else:
    print(f"  WARNING: No breach detected")

# Theft night ratio
if len(h8_data) > 0:
    night_kw = h8_data[(h8_data["timestamp"].dt.hour >= 0) & (h8_data["timestamp"].dt.hour < 5)]["kW"].sum()
    total_kw = h8_data["kW"].sum()
    night_ratio = night_kw / total_kw if total_kw > 0 else 0
    print(f"  {target_theft} night ratio: {night_ratio:.2f} (expected >0.70)")

print(f"\n  Output directory: {OUTPUT_DIR}")
print("=" * 70)
print("  Done!")
