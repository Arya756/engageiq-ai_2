// LiveEngagement.jsx — real-time engagement graph (#33, AC #2 + #6)
//
// Reads the live engagement stream via connectLiveStream (real backend
// WebSocket when available, local 2s simulator otherwise) and renders a
// lightweight zero-dependency SVG line graph that advances every 2 seconds.
// Reconnect/backoff + simulator fallback are handled in dashboardData.js,
// surfaced here as a status pill.

import { useEffect, useRef, useState } from "react";
import { connectLiveStream } from "../lib/dashboardData";

const MAX_POINTS = 30; // ~60s of history at 2s ticks
const W = 640;
const H = 220;
const PAD = 28;

function buildPath(scores) {
  if (scores.length === 0) return "";
  const stepX = (W - PAD * 2) / Math.max(1, MAX_POINTS - 1);
  const yFor = (s) => H - PAD - (s / 100) * (H - PAD * 2);
  return scores
    .map((s, i) => {
      const x = PAD + i * stepX;
      const y = yFor(s);
      return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
}

const STATUS_LABEL = {
  live: { text: "LIVE", color: "#16a34a" },
  reconnecting: { text: "RECONNECTING", color: "#f59e0b" },
  simulated: { text: "DEMO STREAM", color: "#6366f1" },
};

export default function LiveEngagement({ sessionId = 101 }) {
  const [scores, setScores] = useState([]);
  const [status, setStatus] = useState("reconnecting");
  const [lastUpdate, setLastUpdate] = useState(null);
  const cleanupRef = useRef(null);

  useEffect(() => {
    setScores([]);
    setStatus("reconnecting");
    cleanupRef.current = connectLiveStream(sessionId, {
      onStatus: setStatus,
      onScore: (s) => {
        setScores((prev) => {
          const next = [...prev, s];
          return next.slice(-MAX_POINTS);
        });
        setLastUpdate(new Date());
      },
    });
    return () => {
      if (cleanupRef.current) cleanupRef.current();
    };
  }, [sessionId]);

  const current = scores.length ? scores[scores.length - 1] : null;
  const badge = STATUS_LABEL[status] || STATUS_LABEL.simulated;

  return (
    <div
      style={styles.card}
      role="region"
      aria-label="Live engagement graph"
    >
      <div style={styles.header}>
        <h3 style={styles.h3}>Live Engagement</h3>
        <span style={{ ...styles.badge, background: badge.color }}>
          {badge.text}
        </span>
      </div>

      <div style={styles.readout}>
        <span style={styles.score}>
          {current !== null ? current.toFixed(1) : "—"}
        </span>
        <span style={styles.scoreLabel}>current score / 100</span>
        {lastUpdate && (
          <span style={styles.lastUpdate}>
            updated {lastUpdate.toLocaleTimeString()}
          </span>
        )}
      </div>

      {scores.length === 0 ? (
        <div style={styles.loading}>Connecting to live stream…</div>
      ) : (
        <svg
          viewBox={`0 0 ${W} ${H}`}
          width="100%"
          height={H}
          preserveAspectRatio="xMidYMid meet"
          style={{ display: "block" }}
        >
          {/* gridlines every 25 */}
          {[0, 25, 50, 75, 100].map((g) => {
            const y = H - PAD - (g / 100) * (H - PAD * 2);
            return (
              <g key={g}>
                <line
                  x1={PAD}
                  y1={y}
                  x2={W - PAD}
                  y2={y}
                  stroke="#e5e7eb"
                  strokeWidth="1"
                />
                <text x={4} y={y + 4} fontSize="10" fill="#9ca3af">
                  {g}
                </text>
              </g>
            );
          })}
          {/* the live line */}
          {scores.length > 1 && (
            <path
              d={buildPath(scores)}
              fill="none"
              stroke="#6366f1"
              strokeWidth="2.5"
              strokeLinejoin="round"
              strokeLinecap="round"
            />
          )}
          {/* leading dot */}
          {scores.length > 0 && (
            <circle
              cx={PAD + (scores.length - 1) * ((W - PAD * 2) / Math.max(1, MAX_POINTS - 1))}
              cy={H - PAD - (scores[scores.length - 1] / 100) * (H - PAD * 2)}
              r="4"
              fill="#4f46e5"
            />
          )}
        </svg>
      )}
      <p style={styles.note}>
        Updates every 2s. Auto-reconnects on disconnect; falls back to a local
        demo stream when the backend is offline.
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
  header: { display: "flex", alignItems: "center", justifyContent: "space-between" },
  h3: { margin: 0, fontSize: 16, color: "#111827" },
  badge: {
    color: "#fff",
    fontSize: 11,
    fontWeight: 700,
    letterSpacing: 0.5,
    padding: "3px 8px",
    borderRadius: 999,
  },
  readout: { display: "flex", alignItems: "baseline", gap: 8, margin: "8px 0" },
  score: { fontSize: 32, fontWeight: 800, color: "#4f46e5" },
  scoreLabel: { fontSize: 12, color: "#6b7280" },
  lastUpdate: { fontSize: 11, color: "#9ca3af", marginLeft: "auto" },
  loading: {
    height: H,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    color: "#9ca3af",
    fontSize: 14,
  },
  note: { fontSize: 11, color: "#9ca3af", marginTop: 8, marginBottom: 0 },
};
