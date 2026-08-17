// Shared demo data + live-stream helpers for the Teacher Dashboard (#33).
//
// WHY THIS FILE EXISTS:
// The backend already has the analytics logic (ClassAggregator #24,
// RiskIdentifier #25) but those endpoints are not yet exposed, the
// intervention agent (#29) is still a stub, and the live WebSocket
// currently returns a flat 50.0 (frame_extractor orchestrator is a stub).
// Per the issue scope we do NOT add backend routes here. Instead this
// module supplies realistic, clearly-shaped demo data that mirrors the
// real API contracts, plus a local 2-second simulator so the live graph
// actually moves. Every component below ALSO attempts the real WebSocket
// first and only falls back to this data when the backend is unavailable.

// ---------------------------------------------------------------------------
// Demo datasets (mirror the real SQLAlchemy model shapes)
// ---------------------------------------------------------------------------

export const DEMO_COURSES = [
  { id: 1, name: "Intro to Data Structures", code: "CS201", students: 28, avgEngagement: 72 },
  { id: 2, name: "Machine Learning Foundations", code: "CS340", students: 22, avgEngagement: 64 },
  { id: 3, name: "Operating Systems", code: "CS310", students: 31, avgEngagement: 81 },
];

export const DEMO_SESSIONS = [
  { id: 101, courseId: 1, title: "Lecture 12 - Trees", date: "2026-08-14", avg: 70, durationMin: 50 },
  { id: 102, courseId: 1, title: "Lecture 11 - Graphs", date: "2026-08-12", avg: 68, durationMin: 50 },
  { id: 103, courseId: 2, title: "Lecture 5 - Perceptrons", date: "2026-08-13", avg: 61, durationMin: 55 },
  { id: 104, courseId: 3, title: "Lecture 8 - Deadlocks", date: "2026-08-15", avg: 83, durationMin: 45 },
];

// At-risk students — IDs are already anonymized (matches RiskIdentifier's
// sha256 anon_ scheme). trend: "down" = declining (red), "up" = improving.
export const DEMO_AT_RISK = [
  { anonId: "anon_3f9a2c1b04", trend: "down", avg: 41, reason: "3 consecutive sessions below 50" },
  { anonId: "anon_7c2e91d4a8", trend: "down", avg: 47, reason: "Declining trend -12% week over week" },
  { anonId: "anon_1b8f0c6e22", trend: "up", avg: 58, reason: "Recovering from a low start" },
];

// Intervention suggestions — what the LLM intervention agent (#29) would
// produce. Kept deterministic here since the agent is still a stub.
export const DEMO_INTERVENTIONS = [
  "Pause for a 60-second think-pair-share on the last concept — engagement dipped after the 20-minute mark.",
  "Switch to a live coding demo; confusion signals spiked during the theory slide.",
  "Send a gentle nudge to the back row — 3 students show sustained distraction.",
  "Schedule a 5-minute break; drowsiness markers increased in the last 10 minutes.",
];

// ---------------------------------------------------------------------------
// Lookups used by the panels
// ---------------------------------------------------------------------------

export function getClassOverview(courseId) {
  const course = DEMO_COURSES.find((c) => c.id === courseId) || DEMO_COURSES[0];
  return {
    courseId: course.id,
    courseName: course.name,
    courseCode: course.code,
    studentCount: course.students,
    averageEngagement: course.avgEngagement,
  };
}

export function getSessionReport(sessionId) {
  const session = DEMO_SESSIONS.find((s) => s.id === sessionId);
  if (!session) return null;
  return {
    sessionId: session.id,
    title: session.title,
    date: session.date,
    durationMin: session.durationMin,
    averageEngagement: session.avg,
    stateDistribution: {
      engaged: 52,
      passive: 28,
      distracted: 12,
      drowsy: 5,
      confused: 3,
    },
    topIssues: [
      "Drowsiness rose in the final 10 minutes",
      "Confusion peak during slide 7",
      "3 students distracted for >30s at a time",
    ],
  };
}

// ---------------------------------------------------------------------------
// Live stream: real WebSocket first, local simulator fallback
// ---------------------------------------------------------------------------

// Local 2-second simulator. Emits a realistic random-walk engagement score
// (0-100) and returns a stop() function. Used as a fallback when the backend
// WebSocket is unavailable so the live graph still updates every 2s.
export function startSimulation(onTick, intervalMs = 2000) {
  let score = 68;
  const tick = () => {
    // random walk, clamped to a believable classroom band
    const delta = (Math.random() - 0.5) * 18;
    score = Math.max(35, Math.min(92, score + delta));
    onTick(Math.round(score * 10) / 10);
  };
  tick();
  const handle = setInterval(tick, intervalMs);
  return () => clearInterval(handle);
}

// Attempts the real backend WebSocket (ws://host:8000/ws/session/:id) and
// reports connection status + score ticks. Calls onStatus("live" | "reconnecting"
// | "simulated") and onScore(number). Returns a cleanup function.
//
// The component owns reconnect/backoff; this just wraps one connection
// attempt and reports what happened.
export function connectLiveStream(sessionId, { onStatus, onScore }) {
  let stopped = false;
  let ws = null;
  let fallbackStop = null;
  let reconnectTimer = null;
  let attempt = 0;

  const startFallback = () => {
    if (fallbackStop) return;
    onStatus("simulated");
    fallbackStop = startSimulation(onScore, 2000);
  };

  const connect = () => {
    if (stopped) return;
    const proto = window.location.protocol === "https:" ? "wss" : "ws";
    const url = `${proto}://${window.location.hostname}:8000/ws/session/${sessionId}`;
    try {
      ws = new WebSocket(url);
    } catch (e) {
      onStatus("reconnecting");
      scheduleReconnect();
      return;
    }

    ws.onopen = () => {
      attempt = 0;
      onStatus("live");
    };
    ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data);
        if (typeof msg.engagement_score === "number") {
          if (fallbackStop) {
            fallbackStop();
            fallbackStop = null;
          }
          onStatus("live");
          onScore(msg.engagement_score);
        }
      } catch (_) {
        /* ignore malformed frames */
      }
    };
    ws.onerror = () => {
      // Surface as reconnecting; onclose handles the retry/fallback.
      onStatus("reconnecting");
    };
    ws.onclose = () => {
      if (stopped) return;
      // Backend unavailable: switch to the local demo stream so the graph
      // keeps updating, and surface that state clearly.
      onStatus("simulated");
      startFallback();
      scheduleReconnect();
    };
  };

  const scheduleReconnect = () => {
    if (stopped) return;
    attempt += 1;
    const delay = Math.min(10000, 1000 * 2 ** attempt); // capped exp backoff
    reconnectTimer = setTimeout(connect, delay);
  };

  // Begin: try live first; if it never opens we fall back on close/error.
  connect();

  return () => {
    stopped = true;
    if (reconnectTimer) clearTimeout(reconnectTimer);
    if (fallbackStop) fallbackStop();
    if (ws) {
      try {
        ws.close();
      } catch (_) {
        /* noop */
      }
    }
  };
}
