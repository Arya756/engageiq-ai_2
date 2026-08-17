// AtRiskPanel.jsx — at-risk students (#33, AC #5)
// Anonymized student IDs with trend arrows (up = improving, down = declining).

import { DEMO_AT_RISK } from "../lib/dashboardData";

export default function AtRiskPanel() {
  return (
    <div style={styles.card} aria-label="At-risk students">
      <h3 style={styles.h3}>At-Risk Students</h3>

      {DEMO_AT_RISK.length === 0 ? (
        <div style={styles.empty}>No at-risk students detected 🎉</div>
      ) : (
        <ul style={styles.list}>
          {DEMO_AT_RISK.map((s) => {
            const down = s.trend === "down";
            return (
              <li key={s.anonId} style={styles.row}>
                <span
                  style={{
                    ...styles.arrow,
                    color: down ? "#dc2626" : "#16a34a",
                  }}
                  aria-label={down ? "declining" : "improving"}
                >
                  {down ? "▼" : "▲"}
                </span>
                <div style={{ flex: 1 }}>
                  <div style={styles.id}>{s.anonId}</div>
                  <div style={styles.reason}>{s.reason}</div>
                </div>
                <span
                  style={{
                    ...styles.avg,
                    color: s.avg < 50 ? "#dc2626" : "#f59e0b",
                  }}
                >
                  {s.avg}%
                </span>
              </li>
            );
          })}
        </ul>
      )}
      <p style={styles.note}>
        IDs are anonymized per the privacy-first design. Teachers never see raw
        student identity here.
      </p>
    </div>
  );
}

const styles = {
  card: {
    background: "#fff",
    border: "1px solid #e5e7eb",
    borderRadius: 12,
    padding: 16,
    boxShadow: "0 1px 2px rgba(0,0,0,0.04)",
  },
  h3: { margin: "0 0 12px", fontSize: 16, color: "#111827" },
  list: { listStyle: "none", padding: 0, margin: 0, display: "grid", gap: 10 },
  row: { display: "flex", alignItems: "center", gap: 10 },
  arrow: { fontSize: 16, fontWeight: 800, width: 16, textAlign: "center" },
  id: { fontSize: 13, fontFamily: "monospace", color: "#374151" },
  reason: { fontSize: 11, color: "#9ca3af" },
  avg: { fontSize: 16, fontWeight: 700 },
  empty: {
    padding: 24,
    textAlign: "center",
    color: "#16a34a",
    fontSize: 14,
    background: "#f0fdf4",
    borderRadius: 8,
  },
  note: { fontSize: 11, color: "#9ca3af", marginTop: 12, marginBottom: 0 },
};
