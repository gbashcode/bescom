import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { MapContainer, TileLayer, CircleMarker, Popup, Polyline } from 'react-leaflet';
import 'leaflet/dist/leaflet.css';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip, ResponsiveContainer, ReferenceDot } from 'recharts';
import { Activity, AlertTriangle, Zap, MapPin, X, Send, Bell, Search, UploadCloud, Users } from 'lucide-react';
import './index.css';

const API_BASE = 'http://127.0.0.1:8000';

export default function App() {
  const [riskZones, setRiskZones] = useState([]);
  const [anomalies, setAnomalies] = useState([]);
  const [selectedMeter, setSelectedMeter] = useState(null);
  const [meterData, setMeterData] = useState([]);
  const [stats, setStats] = useState({ totalRisk: 0, overloads: 0 });
  const [activeTab, setActiveTab] = useState('live'); // 'live' or 'admin'
  const [mapView, setMapView] = useState('risk'); // 'risk', 'hotspot', 'route'
  const [auditLogs, setAuditLogs] = useState([]);
  const [adminSettings, setAdminSettings] = useState({ night_ratio_threshold: 0.6, unit_lie_ratio_threshold: 1.5, whitelist: [] });
  const [linemenDir, setLinemenDir] = useState([]);
  const [showLinemenModal, setShowLinemenModal] = useState(false);

  useEffect(() => {
    // Fetch data
    const loadData = async () => {
      try {
        const [zonesRes, anomaliesRes, linemenRes] = await Promise.all([
          axios.get(`${API_BASE}/zones/risk`),
          axios.get(`${API_BASE}/anomalies`),
          axios.get(`${API_BASE}/admin/linemen`)
        ]);
        
        setRiskZones(zonesRes.data);
        setAnomalies(anomaliesRes.data);
        setLinemenDir(linemenRes.data);
        
        // Compute stats
        const totalLoss = anomaliesRes.data.reduce((sum, item) => sum + item.est_loss_day, 0);
        const redOverloads = zonesRes.data.reduce((sum, item) => sum + item.red_dts, 0);
        
        setStats({
          totalRisk: totalLoss,
          overloads: redOverloads
        });
      } catch (err) {
        console.error("Failed to load dashboard data", err);
      }
    };
    loadData();
  }, []);

  useEffect(() => {
    if (activeTab === 'admin') {
      const loadAdminData = async () => {
        try {
          const [auditRes, settingsRes, linemenRes] = await Promise.all([
            axios.get(`${API_BASE}/audit`),
            axios.get(`${API_BASE}/admin/settings`),
            axios.get(`${API_BASE}/admin/linemen`)
          ]);
          setAuditLogs(auditRes.data);
          setAdminSettings(settingsRes.data);
          setLinemenDir(linemenRes.data);
        } catch (err) {
          console.error(err);
        }
      };
      loadAdminData();
    }
  }, [activeTab]);

  const openMeterModal = async (meter) => {
    setSelectedMeter(meter);
    setMeterData([]);
    try {
      const res = await axios.get(`${API_BASE}/meter/curve/${meter.meter_id}`);
      // Inject simulated weather (temp curve peaking at 35C around 14:00)
      const dataWithWeather = res.data.map(d => {
        const hour = parseInt(d.time.split(':')[0]);
        const baseTemp = 24;
        const peakTemp = 36;
        const temp = baseTemp + (peakTemp - baseTemp) * Math.sin(Math.PI * Math.max(0, hour - 6) / 12);
        return { ...d, temp: parseFloat(temp.toFixed(1)) };
      });
      setMeterData(dataWithWeather);
    } catch (err) {
      console.error(err);
    }
  };

  return (
    <div className="dashboard-container">
      <header style={{ marginBottom: '1.5rem', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
          <div style={{ background: 'transparent', border: '2px solid var(--accent)', padding: '0.75rem', borderRadius: '12px', boxShadow: 'inset 0 0 10px var(--accent-glow), 0 0 15px var(--accent-glow)' }}>
            <Activity size={28} color="var(--accent)" />
          </div>
          <div>
            <h1 style={{ margin: 0, fontSize: '2rem', fontWeight: 700, letterSpacing: '-1px', textTransform: 'uppercase', color: '#fff', textShadow: '0 0 15px rgba(255,255,255,0.3)' }}>
              GridSense <span style={{ color: 'var(--accent)', textShadow: '0 0 15px var(--accent-glow)' }}>AI</span>
            </h1>
            <p style={{ color: 'var(--accent)', fontSize: '0.9rem', margin: '0 0 0 0', letterSpacing: '1px', textTransform: 'uppercase' }}>
              Predictive Grid Monitoring // Theft Detection
            </p>
          </div>
        </div>
        
        <div style={{ display: 'flex', gap: '1.5rem', alignItems: 'center' }}>
          <div style={{ display: 'flex', background: 'rgba(255,255,255,0.05)', borderRadius: '8px', padding: '0.25rem', border: '1px solid rgba(255,255,255,0.1)' }}>
            <button onClick={() => setActiveTab('live')} style={{ background: activeTab === 'live' ? 'var(--accent)' : 'transparent', color: activeTab === 'live' ? '#000' : 'var(--text-muted)', border: 'none', padding: '0.5rem 1rem', borderRadius: '6px', fontFamily: 'Space Grotesk', fontWeight: 600, cursor: 'pointer', transition: 'all 0.2s' }}>Live Dashboard</button>
            <button onClick={() => setActiveTab('admin')} style={{ background: activeTab === 'admin' ? 'var(--accent)' : 'transparent', color: activeTab === 'admin' ? '#000' : 'var(--text-muted)', border: 'none', padding: '0.5rem 1rem', borderRadius: '6px', fontFamily: 'Space Grotesk', fontWeight: 600, cursor: 'pointer', transition: 'all 0.2s' }}>Data Scientist / Admin</button>
          </div>
          
          <div style={{ position: 'relative', cursor: 'pointer' }}>
            <Bell size={24} color="var(--text-main)" />
            <div style={{ position: 'absolute', top: '-5px', right: '-5px', background: 'var(--red)', color: 'white', fontSize: '0.7rem', fontWeight: 'bold', padding: '2px 6px', borderRadius: '10px', boxShadow: '0 0 10px var(--red-glow)' }}>
              {anomalies.length}
            </div>
          </div>
          
          <input 
            type="file" 
            id="csvUpload" 
            style={{ display: 'none' }} 
            accept=".csv"
            onChange={async (e) => {
              if (e.target.files.length > 0) {
                const formData = new FormData();
                formData.append('file', e.target.files[0]);
                await axios.post(`${API_BASE}/upload`, formData);
                alert(`✅ ${e.target.files[0].name} ingested successfully! DuckDB processing started.`);
              }
            }}
          />
          <button 
            onClick={() => setShowLinemenModal(true)}
            style={{ background: 'transparent', color: 'var(--amber)', border: '1px solid var(--amber)', padding: '0.5rem 1rem', borderRadius: '8px', fontFamily: 'Space Grotesk', fontWeight: 700, textTransform: 'uppercase', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '0.5rem' }}
          >
            <Users size={18} /> View Roster
          </button>
          <button 
            onClick={() => document.getElementById('csvUpload').click()}
            style={{ background: 'transparent', color: 'var(--accent)', border: '1px solid var(--accent)', padding: '0.5rem 1rem', borderRadius: '8px', fontFamily: 'Space Grotesk', fontWeight: 700, textTransform: 'uppercase', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '0.5rem' }}
          >
            <UploadCloud size={18} /> Upload CSV
          </button>

          <button 
            onClick={() => {
              const csv = 'Meter_ID,Zone,Risk_Level,Est_Loss_Day,Reason\n' + anomalies.map(a => `${a.meter_id},${a.zone},${a.risk_level},${a.est_loss_day},"${a.reason}"`).join('\n');
              const blob = new Blob([csv], { type: 'text/csv' });
              const url = window.URL.createObjectURL(blob);
              const a = document.createElement('a');
              a.href = url; a.download = 'GridSense_Anomalies.csv'; a.click();
            }}
            style={{ background: 'var(--accent)', color: '#000', border: 'none', padding: '0.5rem 1rem', borderRadius: '8px', fontFamily: 'Space Grotesk', fontWeight: 700, textTransform: 'uppercase', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '0.5rem', boxShadow: '0 0 15px var(--accent-glow)' }}
          >
            Download CSV
          </button>
        </div>
      </header>

      {activeTab === 'live' ? (
        <>
          <div className="top-bar">
            <div className="stat-card glass-panel red-border">
              <div style={{ color: 'var(--red)', display: 'flex', alignItems: 'center', gap: '0.5rem', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '1px', fontSize: '0.8rem' }}>
                <AlertTriangle size={16} /> Est. ₹ At Risk Today
              </div>
              <div className="stat-value red">
                ₹{(stats.totalRisk / 100000).toFixed(2)}L
              </div>
            </div>
            <div className="stat-card glass-panel amber-border">
              <div style={{ color: 'var(--amber)', display: 'flex', alignItems: 'center', gap: '0.5rem', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '1px', fontSize: '0.8rem' }}>
                <Zap size={16} /> Overloads Predicted (18:00)
              </div>
              <div className="stat-value amber">
                {stats.overloads} DTs
              </div>
            </div>
            <div className="stat-card glass-panel accent-border">
              <div style={{ color: 'var(--accent)', display: 'flex', alignItems: 'center', gap: '0.5rem', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '1px', fontSize: '0.8rem' }}>
                <MapPin size={16} /> Theft Flags Active
              </div>
              <div className="stat-value" style={{ color: '#fff', textShadow: '0 0 15px rgba(255,255,255,0.4)' }}>
                {anomalies.length}
              </div>
            </div>
          </div>

          <div className="main-grid">
        <div className="glass-panel" style={{ padding: '1.25rem', display: 'flex', flexDirection: 'column' }}>
          <div className="panel-header" style={{ display: 'flex', justifyContent: 'space-between', width: '100%' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <MapPin size={20} color="var(--accent)" style={{ filter: 'drop-shadow(0 0 10px var(--accent))' }} /> Zone Risk Heatmap
            </div>
            <select 
              value={mapView}
              onChange={(e) => setMapView(e.target.value)}
              style={{ background: 'transparent', color: 'var(--text-muted)', border: '1px solid rgba(255,255,255,0.1)', padding: '0.25rem 0.5rem', borderRadius: '4px', fontFamily: 'Space Grotesk', fontSize: '0.75rem', outline: 'none' }}
            >
              <option value="risk">View: Capacity Risk</option>
              <option value="hotspot">View: Theft Hotspots</option>
              <option value="route">View: Inspection Route Map</option>
            </select>
          </div>
          <div style={{ flex: 1, borderRadius: '12px', overflow: 'hidden', border: '1px solid rgba(0,240,255,0.2)', boxShadow: 'inset 0 0 20px rgba(0,240,255,0.05)', minHeight: '300px' }}>
            <MapContainer center={[12.9716, 77.5946]} zoom={11} style={{ height: '100%', width: '100%' }}>
              <TileLayer
                url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
                attribution='&copy; CARTO'
              />
              {mapView === 'route' && riskZones.length > 0 && (
                <Polyline 
                  positions={riskZones.sort((a, b) => b.red_dts - a.red_dts).slice(0, 5).map(z => [z.lat, z.long])} 
                  pathOptions={{ color: 'var(--accent)', weight: 4, dashArray: '10, 10' }} 
                />
              )}
              {riskZones.map((zone, idx) => {
                const color = zone.red_dts > 0 ? '#ff003c' : (zone.amber_dts > 0 ? '#fde047' : '#10b981');
                const radius = 12 + (zone.red_dts * 4);
                return (
                  <CircleMarker 
                    key={idx}
                    center={[zone.lat, zone.long]}
                    radius={radius}
                    pathOptions={{ color, fillColor: color, fillOpacity: 0.6, weight: 3 }}
                  >
                    <Popup>
                      <div style={{ color: 'black', padding: '0.5rem', fontFamily: 'Space Grotesk' }}>
                        <strong style={{ fontSize: '1.2rem', textTransform: 'uppercase' }}>{zone.zone}</strong><br/>
                        <div style={{ marginTop: '0.75rem', fontWeight: 600 }}>🔴 Red DTs: {zone.red_dts}</div>
                        <div style={{ fontWeight: 600 }}>🟠 Amber DTs: {zone.amber_dts}</div>
                      </div>
                    </Popup>
                  </CircleMarker>
                );
              })}
            </MapContainer>
          </div>
        </div>

        <div className="glass-panel" style={{ padding: '1.25rem', display: 'flex', flexDirection: 'column' }}>
          <div className="panel-header" style={{ display: 'flex', justifyContent: 'space-between', width: '100%' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <AlertTriangle size={20} color="var(--red)" style={{ filter: 'drop-shadow(0 0 10px var(--red))' }} /> Top Anomalies (Triage)
            </div>
            <div style={{ display: 'flex', alignItems: 'center', background: 'rgba(255,255,255,0.05)', padding: '0.25rem 0.5rem', borderRadius: '8px', border: '1px solid rgba(255,255,255,0.1)' }}>
              <Search size={14} color="var(--text-muted)" style={{ marginRight: '0.5rem' }} />
              <input type="text" placeholder="Search Meter ID..." style={{ background: 'transparent', border: 'none', color: '#fff', outline: 'none', fontFamily: 'Space Grotesk', fontSize: '0.8rem', width: '120px' }} />
            </div>
          </div>
          <div className="table-container">
            <table>
              <thead>
                <tr>
                  <th>Meter ID</th>
                  <th>Zone</th>
                  <th>Risk</th>
                  <th>Loss/Day</th>
                </tr>
              </thead>
              <tbody>
                {anomalies.map((anom) => (
                  <tr key={anom.meter_id} onClick={() => openMeterModal(anom)}>
                    <td style={{ fontWeight: 700, letterSpacing: '1px' }}>{anom.meter_id}</td>
                    <td style={{ color: 'var(--text-muted)', textTransform: 'uppercase', fontSize: '0.8rem' }}>{anom.zone}</td>
                    <td>
                      <span className={`badge ${anom.risk_level.toLowerCase()}`}>
                        {anom.risk_level}
                      </span>
                    </td>
                    <td style={{ color: 'var(--red)', fontWeight: 700 }}>₹{anom.est_loss_day}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
        </div>
        </>
      ) : (
        <div className="main-grid" style={{ gridTemplateColumns: '1fr', gap: '1.5rem' }}>
          <div className="glass-panel" style={{ padding: '2rem' }}>
            <div className="panel-header">
              <Activity size={24} color="var(--accent)" /> Model Retraining Pipeline (UC10)
            </div>
            <p style={{ color: 'var(--text-muted)' }}>Trigger a manual retrain of the LightGBM & Isolation Forest pipeline using the newly collected feedback from Linemen on the ground.</p>
            <button 
              className="btn btn-primary"
              onClick={async () => {
                const res = await axios.post(`${API_BASE}/admin/retrain`);
                alert(res.data.message);
                const auditRes = await axios.get(`${API_BASE}/audit`);
                setAuditLogs(auditRes.data);
              }}
            >
              <Zap size={20} /> Run Pipeline Re-Training Now
            </button>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.5rem' }}>
            <div className="glass-panel" style={{ padding: '2rem' }}>
              <div className="panel-header">
                <AlertTriangle size={24} color="var(--amber)" /> Rule Thresholds (UC11)
              </div>
              <div style={{ marginBottom: '1rem' }}>
                <label style={{ display: 'block', color: 'var(--text-muted)', marginBottom: '0.5rem' }}>Night Usage Ratio Threshold</label>
                <input type="number" id="night_ratio" defaultValue={adminSettings.night_ratio_threshold} step="0.1" style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.2)', color: '#fff', padding: '0.5rem', borderRadius: '6px', outline: 'none', width: '100%' }} />
              </div>
              <div style={{ marginBottom: '1.5rem' }}>
                <label style={{ display: 'block', color: 'var(--text-muted)', marginBottom: '0.5rem' }}>Unit Lie Ratio Threshold</label>
                <input type="number" id="lie_ratio" defaultValue={adminSettings.unit_lie_ratio_threshold} step="0.1" style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.2)', color: '#fff', padding: '0.5rem', borderRadius: '6px', outline: 'none', width: '100%' }} />
              </div>
              <button 
                className="btn btn-secondary"
                onClick={async () => {
                  const n = parseFloat(document.getElementById('night_ratio').value);
                  const l = parseFloat(document.getElementById('lie_ratio').value);
                  const res = await axios.post(`${API_BASE}/admin/thresholds`, { night_ratio: n, unit_lie_ratio: l });
                  alert(res.data.message);
                  const auditRes = await axios.get(`${API_BASE}/audit`);
                  setAuditLogs(auditRes.data);
                }}
              >
                Update Thresholds
              </button>
            </div>

            <div className="glass-panel" style={{ padding: '2rem' }}>
              <div className="panel-header">
                <MapPin size={24} color="var(--accent)" /> Appliance Whitelist (UC12)
              </div>
              <div style={{ marginBottom: '1rem' }}>
                <input type="text" id="wl_meter" placeholder="Meter ID (e.g. M_8849)" style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.2)', color: '#fff', padding: '0.5rem', borderRadius: '6px', outline: 'none', width: '100%', marginBottom: '1rem' }} />
                <input type="text" id="wl_reason" placeholder="Reason (e.g. Medical Oxygen Concentrator)" style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.2)', color: '#fff', padding: '0.5rem', borderRadius: '6px', outline: 'none', width: '100%' }} />
              </div>
              <button 
                className="btn btn-primary"
                style={{ background: 'var(--accent)', color: 'black' }}
                onClick={async () => {
                  const m = document.getElementById('wl_meter').value;
                  const r = document.getElementById('wl_reason').value;
                  const res = await axios.post(`${API_BASE}/admin/whitelist`, { meter_id: m, reason: r });
                  alert(res.data.message);
                  const auditRes = await axios.get(`${API_BASE}/audit`);
                  setAuditLogs(auditRes.data);
                }}
              >
                Add Exception to Whitelist
              </button>
            </div>
          </div>

          <div className="glass-panel" style={{ padding: '2rem' }}>
            <div className="panel-header">
              <Activity size={24} color="var(--accent)" /> Lineman Roster Management
            </div>
            <div style={{ display: 'flex', gap: '1rem', marginBottom: '1.5rem' }}>
              <input type="text" id="lm_zone" placeholder="Zone (e.g. RR Nagar)" style={{ flex: 1, background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.2)', color: '#fff', padding: '0.5rem', borderRadius: '6px', outline: 'none' }} />
              <input type="text" id="lm_name" placeholder="Name" style={{ flex: 1, background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.2)', color: '#fff', padding: '0.5rem', borderRadius: '6px', outline: 'none' }} />
              <input type="text" id="lm_phone" placeholder="Phone (+91...)" style={{ flex: 1, background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.2)', color: '#fff', padding: '0.5rem', borderRadius: '6px', outline: 'none' }} />
              <button 
                className="btn btn-primary"
                onClick={async () => {
                  const z = document.getElementById('lm_zone').value;
                  const n = document.getElementById('lm_name').value;
                  const p = document.getElementById('lm_phone').value;
                  if (!z || !n || !p) return alert("Fill all fields");
                  const res = await axios.post(`${API_BASE}/admin/linemen`, { zone: z, lineman_name: n, phone_number: p });
                  alert(res.data.message);
                  const [auditRes, linemenRes] = await Promise.all([axios.get(`${API_BASE}/audit`), axios.get(`${API_BASE}/admin/linemen`)]);
                  setAuditLogs(auditRes.data);
                  setLinemenDir(linemenRes.data);
                }}
              >
                Add Lineman
              </button>
            </div>
            <div className="table-container" style={{ maxHeight: '250px' }}>
              <table>
                <thead>
                  <tr>
                    <th>Zone</th>
                    <th>Lineman Name</th>
                    <th>Phone Number</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {linemenDir.map((lm, idx) => (
                    <tr key={idx}>
                      <td style={{ fontWeight: 600, color: 'var(--accent)' }}>{lm.zone}</td>
                      <td>{lm.lineman_name}</td>
                      <td>{lm.phone_number}</td>
                      <td>
                        <button 
                          style={{ background: 'var(--red)', color: '#fff', border: 'none', padding: '0.25rem 0.5rem', borderRadius: '4px', cursor: 'pointer' }}
                          onClick={async () => {
                            if(window.confirm(`Delete lineman for ${lm.zone}?`)) {
                              const res = await axios.delete(`${API_BASE}/admin/linemen/${lm.zone}`);
                              alert(res.data.message);
                              const [auditRes, linemenRes] = await Promise.all([axios.get(`${API_BASE}/audit`), axios.get(`${API_BASE}/admin/linemen`)]);
                              setAuditLogs(auditRes.data);
                              setLinemenDir(linemenRes.data);
                            }
                          }}
                        >
                          <X size={14} /> Remove
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="glass-panel" style={{ padding: '2rem' }}>
            <div className="panel-header">
              <Activity size={24} color="var(--accent)" /> System Audit Logs (UC16)
            </div>
            <div className="table-container" style={{ maxHeight: '300px' }}>
              <table>
                <thead>
                  <tr>
                    <th>Timestamp</th>
                    <th>Action Type</th>
                    <th>User</th>
                    <th>Meter ID</th>
                    <th>Details</th>
                  </tr>
                </thead>
                <tbody>
                  {auditLogs.length > 0 ? auditLogs.map((log, idx) => (
                    <tr key={idx}>
                      <td style={{ color: 'var(--text-muted)' }}>{log.time.split('T')[1].substring(0,8)}</td>
                      <td style={{ fontWeight: 600, color: 'var(--accent)' }}>{log.action}</td>
                      <td>{log.user}</td>
                      <td>{log.meter_id}</td>
                      <td style={{ color: 'var(--text-muted)' }}>{log.is_fraud !== undefined ? `Fraud: ${log.is_fraud}` : (log.reason || '-')}</td>
                    </tr>
                  )) : (
                    <tr><td colSpan="5" style={{ textAlign: 'center', color: 'var(--text-muted)' }}>No audit logs yet. Try sending an SMS or submitting feedback!</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {selectedMeter && (
        <div className="modal-overlay" onClick={() => setSelectedMeter(null)}>
          <div className="modal-content" onClick={e => e.stopPropagation()}>
            <div className="modal-header" style={{ marginBottom: '2rem' }}>
              <h2 style={{ margin: 0, display: 'flex', alignItems: 'center', gap: '0.75rem', fontSize: '2rem', textTransform: 'uppercase', letterSpacing: '1px' }}>
                <Zap color="var(--accent)" size={32} style={{ filter: 'drop-shadow(0 0 15px var(--accent))' }} /> Meter Target: <span style={{ color: 'var(--accent)' }}>{selectedMeter.meter_id}</span>
              </h2>
              <button className="close-btn" onClick={() => setSelectedMeter(null)}><X size={28} /></button>
            </div>
            
            <div className="reason-box">
              <AlertTriangle color="var(--red)" size={28} style={{ filter: 'drop-shadow(0 0 10px var(--red))' }} />
              <div>
                <strong style={{ display: 'block', marginBottom: '0.4rem', color: '#fff', textTransform: 'uppercase', letterSpacing: '1px' }}>Anomaly Detected:</strong> 
                <span style={{ color: 'var(--text-muted)' }}>{selectedMeter.reason}</span>
              </div>
            </div>

            <div style={{ height: '350px', marginTop: '2rem' }}>
              {meterData.length > 0 ? (
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={meterData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(0, 240, 255, 0.1)" vertical={false} />
                    <XAxis dataKey="time" stroke="var(--accent)" tick={{ fill: 'var(--accent)', fontFamily: 'Space Grotesk' }} axisLine={false} tickLine={false} />
                    <YAxis yAxisId="left" stroke="var(--accent)" tick={{ fill: 'var(--accent)', fontFamily: 'Space Grotesk' }} axisLine={false} tickLine={false} />
                    <YAxis yAxisId="right" orientation="right" stroke="var(--amber)" tick={{ fill: 'var(--amber)', fontFamily: 'Space Grotesk' }} axisLine={false} tickLine={false} domain={['dataMin - 2', 'dataMax + 2']} />
                    <RechartsTooltip 
                      contentStyle={{ backgroundColor: 'rgba(3, 3, 5, 0.95)', border: '1px solid var(--accent)', borderRadius: '12px', backdropFilter: 'blur(10px)', boxShadow: '0 0 20px rgba(0,240,255,0.2)' }} 
                    />
                    <Line yAxisId="left" type="monotone" dataKey="kW" stroke="var(--accent)" strokeWidth={4} dot={false} activeDot={{ r: 8, fill: '#fff', stroke: 'var(--accent)', strokeWidth: 3 }} name="Load (kW)" />
                    <Line yAxisId="right" type="monotone" dataKey="temp" stroke="var(--amber)" strokeWidth={2} strokeDasharray="5 5" dot={false} name="Temp (°C)" />
                    
                    {meterData.filter(d => d.tamper).map((point, idx) => (
                      <ReferenceDot 
                        key={idx} 
                        yAxisId="left"
                        x={point.time} 
                        y={point.kW} 
                        r={10} 
                        fill="var(--red)" 
                        stroke="rgba(255, 0, 60, 0.5)" 
                        strokeWidth={8}
                      />
                    ))}
                  </LineChart>
                </ResponsiveContainer>
              ) : (
                <div style={{ color: 'var(--accent)', display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100%', fontSize: '1.4rem', textTransform: 'uppercase', letterSpacing: '2px' }}>
                  <Activity size={32} className="spin" style={{ marginRight: '1.5rem', filter: 'drop-shadow(0 0 15px var(--accent))' }} /> Establishing Link...
                </div>
              )}
            </div>
            
            <div style={{ marginTop: '3rem', display: 'flex', gap: '1.5rem', justifyContent: 'flex-end', alignItems: 'center' }}>
              <input 
                type="text" 
                id="feedbackReason"
                placeholder="Reason (optional)..." 
                style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.2)', color: '#fff', padding: '0.5rem', borderRadius: '6px', outline: 'none', fontFamily: 'Space Grotesk' }}
              />
              <button 
                className="btn btn-secondary"
                onClick={async () => {
                  const reason = document.getElementById('feedbackReason').value;
                  await axios.post(`${API_BASE}/feedback`, { meter_id: selectedMeter.meter_id, is_fraud: false, reason });
                  alert(`✅ Feedback recorded: False Alarm. ML Pipeline will be retrained tonight.`);
                  setSelectedMeter(null);
                }}
              >
                <X size={20} /> Mark False Alarm
              </button>
              <button 
                className="btn"
                style={{ background: 'var(--red)', color: 'white', border: 'none' }}
                onClick={async () => {
                  const reason = document.getElementById('feedbackReason').value;
                  await axios.post(`${API_BASE}/feedback`, { meter_id: selectedMeter.meter_id, is_fraud: true, reason });
                  alert(`🚨 Feedback recorded: Confirmed Fraud. ML Pipeline will increase confidence score.`);
                  setSelectedMeter(null);
                }}
              >
                <AlertTriangle size={20} /> Confirm Fraud
              </button>
              <button 
                className="btn btn-primary"
                onClick={async () => {
                  const res = await axios.post(`${API_BASE}/notify/${selectedMeter.meter_id}`);
                  alert(res.data.message);
                }}
              >
                <Send size={20} /> Dispatch Lineman Alert
              </button>
            </div>
          </div>
        </div>
      )}

      {showLinemenModal && (
        <div className="modal-overlay" onClick={() => setShowLinemenModal(false)}>
          <div className="glass-panel" style={{ width: '600px', padding: '2rem', zIndex: 101, position: 'relative' }} onClick={e => e.stopPropagation()}>
            <button 
              style={{ position: 'absolute', top: '1.5rem', right: '1.5rem', background: 'transparent', border: 'none', color: 'var(--text-muted)', cursor: 'pointer' }}
              onClick={() => setShowLinemenModal(false)}
            >
              <X size={24} />
            </button>
            <div className="panel-header" style={{ marginBottom: '1.5rem' }}>
              <Users size={24} color="var(--amber)" /> Active Lineman Roster
            </div>
            <div className="table-container" style={{ maxHeight: '400px' }}>
              <table>
                <thead>
                  <tr>
                    <th>Assigned Zone</th>
                    <th>Lineman Name</th>
                    <th>Contact Number</th>
                  </tr>
                </thead>
                <tbody>
                  {linemenDir.map((lm, idx) => (
                    <tr key={idx}>
                      <td style={{ fontWeight: 600, color: 'var(--accent)' }}>{lm.zone}</td>
                      <td>{lm.lineman_name}</td>
                      <td style={{ color: 'var(--amber)' }}>{lm.phone_number}</td>
                    </tr>
                  ))}
                  {linemenDir.length === 0 && (
                    <tr><td colSpan="3" style={{ textAlign: 'center', padding: '2rem' }}>No linemen available. Add them in the Admin tab.</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
