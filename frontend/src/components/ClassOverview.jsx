// ClassOverview.jsx — class summary (#33, AC #1)
// Course selector + student count + average engagement.

import { DEMO_COURSES, getClassOverview } from "../lib/dashboardData";

export default function ClassOverview({ courseId, onSelectCourse }) {
  const overview = getClassOverview(courseId);
  const avg = overview.averageEngagement;

  return (
    <div style={styles.card} aria-label="Class overview">
      <h3 style={styles.h3}>Class Overview</h3>

      <label style={styles.label} htmlFor="course-select">
        Course
      </label>
      <select
        id="course-select"
        style={styles.select}
        value={courseId}
        onChange={(e) => onSelectCourse(Number(e.target.value))}
      >
        {DEMO_COURSES.map((c) => (
          <option key={c.id} value={c.id}>
            {c.name} ({c.code})
          </option>
        ))}
      </select>

      <div style={styles.stats}>
        <div style={styles.stat}>
          <div style={styles.statValue}>{overview.studentCount}</div>
          <div style={styles.statLabel}>Students</div>
        </div>
        <div style={styles.stat}>
          <div style={{ ...styles.statValue, color: avgColor(avg) }}>
            {avg}%
          </div>
          <div style={styles.statLabel}>Avg Engagement</div>
        </div>
      </div>

      {/* progress bar for avg engagement */}
      <div style={styles.barTrack}>
        <div
          style={{
            ...styles.barFill,
            width: `${avg}%`,
            background: avgColor(avg),
          }}
        />
      </div>
      <p style={styles.subtitle}>{overview.courseName}</p>
    </div>
  );
}

function avgColor(v) {
  if (v >= 70) return "#16a34a";
  if (v >= 50) return "#f59e0b";
  return "#dc2626";
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
  label: { fontSize: 12, color: "#6b7280", display: "block", marginBottom: 4 },
  select: {
    width: "100%",
    padding: "8px 10px",
    borderRadius: 8,
    border: "1px solid #d1d5db",
    fontSize: 14,
    marginBottom: 14,
  },
  stats: { display: "flex", gap: 24 },
  stat: { flex: 1 },
  statValue: { fontSize: 28, fontWeight: 800, color: "#111827" },
  statLabel: { fontSize: 12, color: "#6b7280" },
  barTrack: {
    marginTop: 12,
    height: 8,
    background: "#f3f4f6",
    borderRadius: 999,
    overflow: "hidden",
  },
  barFill: { height: "100%", borderRadius: 999, transition: "width 0.4s ease" },
  subtitle: { fontSize: 12, color: "#9ca3af", marginTop: 8, marginBottom: 0 },
};
