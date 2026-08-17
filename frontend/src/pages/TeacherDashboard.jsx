// TeacherDashboard.jsx — main dashboard (#33)
// Orchestrates ClassOverview, LiveEngagement, session history, AtRiskPanel
// and InterventionPanel. Handles loading + empty states (AC #7) and is
// responsive for laptop and tablet (AC #8).

import { useEffect, useState } from "react";
import ClassOverview from "../components/ClassOverview";
import LiveEngagement from "../components/LiveEngagement";
import AtRiskPanel from "../components/AtRiskPanel";
import InterventionPanel from "../components/InterventionPanel";
import { DEMO_SESSIONS, getSessionReport } from "../lib/dashboardData";

export default function TeacherDashboard() {
  const [loading, setLoading] = useState(true);
  const [courseId, setCourseId] = useState(1);
  const [selectedSession, setSelectedSession] = useState(null);
  const [report, setReport] = useState(null);

  // Simulate initial data load so the loading state is real and demonstrable.
  useEffect(() => {
    const t = setTimeout(() => setLoading(false), 900);
    return () => clearTimeout(t);
  }, []);

  const openSession = (id) => {
    setSelectedSession(id);
    setReport(getSessionReport(id));
  };

  if (loading) {
    return (
      <div style={styles.page}>
        <div style={styles.skeleton}>Loading dashboard…</div>
      </div>
    );
  }

  return (
    <div style={styles.page}>
      <style>{responsive}</style>
      <header style={styles.header}>
        <h1 style={styles.title}>Teacher Dashboard</h1>
        <p style={styles.tagline}>
          Real-time engagement monitoring &amp; AI teaching insights
        </p>
      </header>

      <div style={styles.grid} data-dashboard-grid="">
        {/* Left column: overview + live + history */}
        <div style={styles.col}>
          <ClassOverview courseId={courseId} onSelectCourse={setCourseId} />
          <LiveEngagement sessionId={selectedSession || 101} />

          <section style={styles.card} aria-label="Session history">
            <h3 style={styles.h3}>Session History</h3>
            {DEMO_SESSIONS.length === 0 ? (
              <div style={styles.empty}>No past sessions yet.</div>
            ) : (
              <ul style={styles.sessions}>
                {DEMO_SESSIONS.map((s) => (
                  <li key={s.id}>
                    <button
                      style={{
                        ...styles.sessionBtn,
                        ...(selectedSession === s.id ? styles.sessionBtnActive : {}),
                      }}
                      onClick={() => openSession(s.id)}
                    >
                      <span style={styles.sessionTitle}>{s.title}</span>
                      <span style={styles.sessionMeta}>
                        {s.date} · {s.durationMin}m · avg {s.avg}%
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}

            {report ? (
              <div style={styles.reportBox}>
                <div style={styles.reportHead}>{report.title} — Report</div>
                <div style={styles.reportGrid}>
                  <ReportStat label="Avg Engagement" value={`${report.averageEngagement}%`} />
                  <ReportStat label="Duration" value={`${report.durationMin}m`} />
                </div>
                <div style={styles.distLabel}>State distribution</div>
                <div style={styles.distRow}>
                  {Object.entries(report.stateDistribution).map(([k, v]) => (
                    <div key={k} style={styles.distCell}>
                      <span style={styles.distPct}>{v}%</span>
                      <span style={styles.distName}>{k}</span>
                    </div>
                  ))}
                </div>
                <div style={styles.reportIssues}>
                  {report.topIssues.map((iss, i) => (
                    <div key={i}>• {iss}</div>
                  ))}
                </div>
              </div>
            ) : (
              <div style={styles.reportHint}>
                Select a session above to view its report.
              </div>
            )}
          </section>
        </div>

        {/* Right column: at-risk + interventions */}
        <div style={styles.col}>
          <AtRiskPanel />
          <InterventionPanel />
        </div>
      </div>
    </div>
  );
}

function ReportStat({ label, value }) {
  return (
    <div style={styles.reportStat}>
      <div style={styles.reportStatValue}>{value}</div>
      <div style={styles.reportStatLabel}>{label}</div>
    </div>
  );
}

// ---------- styles ----------
const styles = {
  page: { maxWidth: 1200, margin: "0 auto", padding: "24px 16px", color: "#111827" },
  header: { marginBottom: 20 },
  title: { margin: 0, fontSize: 24, fontWeight: 800 },
  tagline: { margin: "4px 0 0", color: "#6b7280", fontSize: 14 },
  skeleton: {
    height: 320,
    borderRadius: 12,
    background: "linear-gradient(90deg,#f3f4f6,#e5e7eb,#f3f4f6)",
    backgroundSize: "200% 100%",
    animation: "pulse 1.4s infinite",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    color: "#9ca3af",
  },
  grid: {
    display: "grid",
    gridTemplateColumns: "minmax(0, 1.4fr) minmax(0, 1fr)",
    gap: 16,
    alignItems: "start",
  },
  col: { display: "grid", gap: 16 },
  card: {
    background: "#fff",
    border: "1px solid #e5e7eb",
    borderRadius: 12,
    padding: 16,
    boxShadow: "0 1px 2px rgba(0,0,0,0.04)",
  },
  h3: { margin: "0 0 12px", fontSize: 16 },
  empty: {
    padding: 20,
    textAlign: "center",
    color: "#9ca3af",
    background: "#f9fafb",
    borderRadius: 8,
  },
  sessions: { listStyle: "none", padding: 0, margin: "0 0 12px", display: "grid", gap: 8 },
  sessionBtn: {
    width: "100%",
    textAlign: "left",
    border: "1px solid #e5e7eb",
    background: "#fff",
    borderRadius: 8,
    padding: "8px 10px",
    cursor: "pointer",
    display: "flex",
    flexDirection: "column",
    gap: 2,
  },
  sessionBtnActive: { borderColor: "#4f46e5", background: "#eef2ff" },
  sessionTitle: { fontSize: 13, fontWeight: 600, color: "#111827" },
  sessionMeta: { fontSize: 11, color: "#9ca3af" },
  reportHint: { fontSize: 12, color: "#9ca3af", marginTop: 8 },
  reportBox: {
    marginTop: 8,
    borderTop: "1px solid #f3f4f6",
    paddingTop: 12,
  },
  reportHead: { fontWeight: 700, fontSize: 14, marginBottom: 8 },
  reportGrid: { display: "flex", gap: 24, marginBottom: 10 },
  reportStat: {},
  reportStatValue: { fontSize: 20, fontWeight: 800, color: "#4f46e5" },
  reportStatLabel: { fontSize: 11, color: "#6b7280" },
  distLabel: { fontSize: 12, color: "#6b7280", margin: "4px 0 6px" },
  distRow: { display: "flex", flexWrap: "wrap", gap: 8 },
  distCell: {
    background: "#f9fafb",
    borderRadius: 8,
    padding: "6px 10px",
    textAlign: "center",
    minWidth: 56,
  },
  distPct: { display: "block", fontSize: 14, fontWeight: 700, color: "#374151" },
  distName: { fontSize: 10, color: "#9ca3af", textTransform: "capitalize" },
  reportIssues: { fontSize: 12, color: "#4b5563", marginTop: 10, lineHeight: 1.6 },
};

// Responsive: stack to single column on tablet/narrow widths.
const responsive = `
@media (max-width: 900px) {
  [data-dashboard-grid] { grid-template-columns: 1fr !important; }
}
@keyframes pulse {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}
`;
