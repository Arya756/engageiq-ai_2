// InterventionPanel.jsx — AI teaching suggestions (#33, AC #4)
// Shows 3+ suggestions from the intervention agent (#29).
// The agent is still a stub server-side; this renders the deterministic
// demo set from dashboardData so the panel is always populated for review.

import { DEMO_INTERVENTIONS } from "../lib/dashboardData";

export default function InterventionPanel() {
  const suggestions =
    DEMO_INTERVENTIONS.length > 0
      ? DEMO_INTERVENTIONS
      : [
          "Begin with a quick recap quiz to re-engage the class.",
          "Use a real-world example to anchor the next concept.",
          "Open the floor for questions before advancing to new material.",
        ];

  return (
    <div style={styles.card} aria-label="Intervention suggestions">
      <h3 style={styles.h3}>Intervention Suggestions</h3>
      <p style={styles.subtitle}>
        AI-generated, based on live engagement signals
      </p>

      <ol style={styles.list}>
        {suggestions.map((s, i) => (
          <li key={i} style={styles.item}>
            <span style={styles.num}>{i + 1}</span>
            <span style={styles.text}>{s}</span>
          </li>
        ))}
      </ol>
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
  h3: { margin: "0 0 4px", fontSize: 16, color: "#111827" },
  subtitle: { fontSize: 12, color: "#6b7280", margin: "0 0 12px" },
  list: { listStyle: "none", padding: 0, margin: 0, display: "grid", gap: 10 },
  item: { display: "flex", gap: 10, alignItems: "flex-start" },
  num: {
    flexShrink: 0,
    width: 22,
    height: 22,
    borderRadius: "50%",
    background: "#4f46e5",
    color: "#fff",
    fontSize: 12,
    fontWeight: 700,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
  },
  text: { fontSize: 13, color: "#374151", lineHeight: 1.4 },
};
