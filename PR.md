# Pull Request Log

## Issue 1
**By:** Gargi

The main problem was that the Docker setup wasn't working because the frontend hadn't been scaffolded yet and some Docker packages were outdated. I updated the Dockerfile with compatible package names,temporarily disabled the frontend service in Docker Compose and verified that the backend and PostgreSQL containers started successfully. After that, I confirmed the backend was running through the health endpoint.

---

## Issue 2
**By:** Gargi

This issue was about setting up a GitHub Actions CI workflow to automatically check every PR. I created the workflow from scratch, configured it to run formatting, linting and test checks on Prs to  dev and main and tested the same commands locally. While testing, I found some existing formatting and lint issues in the repository but since they were unrelated to the task ,I kept the PR focused only on the CI setup.

---

## Issue 3
**By:** Yuvraj and Ayush 

This issue was about setting up the database for EngageIQ. We created 7 tables Users, Courses, Course Enrollments, Sessions, Engagement Logs, Nudges, and Reports  that match the agreed schema design. We used SQLAlchemy to define the tables in Python and Alembic so it can evolve safely over time. We also wrote a seed script that wipes and repopulates the database with realistic dummy data in one command, so every developer can test against the same consistent dataset.

---

## Issue 4
**By:** Aparna Singh

This issue focused on implementing the real-time webcam capture pipeline for the AI system. I developed a thread-safe capture module using a daemon background thread, added frame preprocessing (resize, RGB conversion, normalization), and ensured safe synchronization using locks. I also resolved CI-related issues by fixing formatting, linting, and test failures, and updated the tests to mock webcam access so they run reliably in GitHub Actions environments without physical camera hardware.


 
## Issue 5
**By:** Anuradha

This issue was about implementing a FastAPI WebSocket endpoint at `/ws/session/{session_id}` to stream frames from the browser to the backend. I built the endpoint to accept base64-encoded frames with timestamps, decode them, and pass them through the engagement scoring pipeline, sending the computed engagement score back to the client. I added JWT-based session token authentication so connections are verified before being accepted, and built a ConnectionManager to support multiple concurrent sessions and handle client disconnects gracefully with proper resource cleanup. Since the preprocessing pipeline from Issue #4 hasn't been merged into dev yet, the endpoint falls back to placeholder engagement scores so it stays fully testable end-to-end, and will automatically pick up the real pipeline once that work lands. I verified this locally with 8 automated tests covering connection, frame processing, and disconnect handling, as well as a manual end-to-end test using a real JWT token and a live WebSocket client.

---

## Issue 6
**By:** Gargi 

Implemented Google OAuth authentication with JWT-based access and refresh tokens, added authentication middleware and protected API routes, created user onboarding, profile and course enrollment APIs, updated user model and configuration, added database setup, wrote authentication and user tests (17 tests passing) and included a minimal frontend scaffold with login, signup, onboarding pages, Google login button and authentication context.

---

## Issue 7
**By:** Yuvraj and Ayush

This issue focused on setting up the initial database migrations and seeding script. We created the alembic.ini configuration file, verified the existing env.py was correctly pointing to our SQLAlchemy models and database URL, and generated the initial migration. We also fixed the seed script to add idempotency so running it twice does not create duplicate data.

---

## Issue 8
**By:** Yuvraj

This issue was about setting up face detection by using face mesh mediapipe. I implemented the FaceMeshDetector class using MediaPipe which detects 468 landmarks on a person's face from a webcam frame. The model loads only when the first frame is processed so it does not slow down the app on startup. If no face is found in the frame it returns an empty result without crashing. I also added a demo mode where you can run it with your webcam and see green dots on your face, and wrote 7 tests to verify everything works correctly.

---

## Issue 9
**By:** Aparna Singh

This issue was about implementing head pose estimation to determine if a student is facing the screen. I built estimate_head_pose using OpenCV's solvePnP, which takes 6 key landmarks from the 468-point Face Mesh (nose tip, chin, left/right eye corners, left/right mouth corners) and matches them against a generic 3D face model to compute pitch, yaw, and roll in degrees. I handled edge cases explicitly rather than relying on solvePnP's own success flag — the function returns None gracefully when too few landmarks are visible, when a reference point is occluded (NaN), and when the landmarks collapse into a degenerate configuration that solvePnP would otherwise "solve" with a meaningless result. I also added a demo mode that draws a 3-axis gizmo on the nose tip in the live webcam feed so pose changes are visible in real time. I verified accuracy using synthetic ground-truth poses — known rotations projected back to 2D and checked that the estimator recovers them — covering frontal, left-turn, right-turn, downward-tilt, and combined rotations, all within the 5-degree accuracy requirement, plus the three occlusion/degeneracy edge cases, for 10 tests total, all passing.


---
## Issue 10
**By:** Anuradha

This issue was about building a gaze classifier that combines head pose with iris position to determine where a student is actually looking, since head pose alone can't tell you that — you can face the screen while your eyes glance elsewhere. I implemented classify_gaze, which takes pitch, yaw, iris ratio, and EAR and returns one of 5 states: at_screen, away_left, away_right, looking_down, or eyes_closed. The away_left/away_right states trigger on either head yaw beyond threshold OR the iris drifting toward a corner, which is what lets the classifier catch a straight head with eyes glancing sideways rather than relying on head pose alone. All thresholds (yaw, pitch, EAR, iris ratio) are configurable through settings rather than hardcoded. While testing on webcam, I noticed head_pose.py (#9) occasionally returns a flipped yaw value on near-frontal faces — a known solvePnP ambiguity — and flagged it to be checked separately, since it doesn't affect this module's own logic. I verified the classifier with 20 tests covering each of the 5 states individually, priority ordering between states, boundary conditions, and threshold overrides, along with a live webcam demo with color-coded overlay, all passing.

---


## Issue 11
**By:** Gargi

This issue was about implementing a multi-face selector for group webcam scenarios where multiple students may appear in the same frame. I added bounding box support to the face detection module, implemented a `FaceSelector` that selects the largest face on the first frame and tracks the same face across subsequent frames using a lightweight landmark-based embedding, added timeout handling to reset tracking if the primary face disappears for more than 5 seconds, created a webcam demo to visualize the selected face, and wrote automated tests covering single-face selection, multi-face selection, tracking persistence, and face disappearance.

---

## Issue 12
**By:** Ayush Aryan

This issue was about adding a feature to detect if a student is falling asleep, which is a strong sign they are losing focus. I built a drowsiness detector that tracks the shape of the eyes using 6 specific points around the eye to calculate how "open" or "closed" they are. 
To make sure it doesn't accidentally flag normal, quick blinks as drowsiness, I added a timer so it only triggers a warning if the eyes stay closed for more than 1.5 seconds. I also created a live webcam demo that draws yellow dots on the eyes and flashes a "DROWSY!" warning on the screen when the user closes their eyes for too long. Finally, I wrote tests to make sure the system accurately tells the difference between open eyes, closed eyes, and normal blinking.

---


## Issue 13
**By:** Yuvraj

This issue was about detecting yawns using the Mouth Aspect Ratio (MAR). I implemented compute_mar which measures how open the mouth is and YawnDetector which only triggers after the mouth stays open for 2+ seconds so normal speech does not cause false positives. It also tracks yawn frequency and marks a student as fatigued after 3 yawns in 10 minutes. Tested it live with webcam. Add hand over mouth occlusion handling with an occlusion grace proxy so yawns started before covering still count. Combine MAR with jaw/head/eye cues using conservative, tunable rules to avoid false positives. Includes a demo overlay for live tuning and accompanying unit tests.

---


## Issue 14
**By:** Gargi

This issue was about implementing a facial expression classifier for classroom engagement analysis. I integrated a pre-trained FER model with lazy loading, mapped the original FER emotion outputs to the four required classroom specific classes (Engaged, Confused, Bored and Neutral) and added confidence based fallback handling so uncertain predictions return a Neutral state instead of unreliable results. I also implemented a webcam demo for real time expression detection and wrote automated tests covering all four expression classes and the low-confidence fallback scenario. After syncing with the latest dev, I verified the implementation by running formatting, linting and the complete test suite successfully.

---


## Issue 15
**By:** Anuradha

This issue was about creating a documented training notebook for the classroom expression classifier. I built a Jupyter notebook that automatically downloads the FER2013 dataset, maps the original 7 emotion classes to the 4 required classroom engagement classes and explains the reasoning behind the mapping along with the dataset's known biases. I fine-tuned an ImageNet-pretrained ResNet18 using webcam-relevant data augmentations, evaluated it with confusion matrices and per-class metrics, and exported the best model checkpoint to `models/expression_model.pth`. The final model achieved 72.4% validation accuracy and 72.1% test accuracy, meeting the project target.
## Issue 16
**By:** Gargi

This issue was about building a weighted engagement scorer that combines gaze, head pose, facial expression and alertness into a single 0 – 100 engagement score. I implemented configurable scoring with support for different course type profiles, added proportional weight redistribution when one or more signals are unavailable, created scoring weight profiles and comprehensive tests covering high, low, mixed, missing-signal and profile based scenarios. The implementation is currently configurable through predefined profiles and in future it can be extended to support teacher selected course specific profiles and custom weight configurations.

---


## Issue 17

**By:** Aparna Singh

This issue was about implementing the engagement state machine that converts a continuous engagement score into discrete, actionable states for downstream agents. I built a finite state machine with five states — ENGAGED, PASSIVE, DISTRACTED, DROWSY, and CONFUSED — where normal engagement is determined from configurable score ranges while CONFUSED and DROWSY act as override states based on expression and drowsiness signals. To prevent rapid state oscillations caused by noisy scores, I implemented configurable temporal hysteresis so a candidate state must remain valid for its required duration before a transition is confirmed. I added transition events through a subscriber system so other modules can react to state changes, maintained a bounded history of confirmed states with timestamps for analytics, and included comprehensive validation for configuration, scores, timestamps, and transition logic to handle invalid or inconsistent inputs gracefully. Finally, I developed an extensive test suite covering sustained engagement, hysteresis behavior, gradual state transitions, drowsiness and confusion overrides, event emission, history logging, configurable thresholds, validation, and edge cases, with all project tests passing successfully.

---
## Issue 18
**By:** Yuvraj

Raw engagement scores are super noisy brief things like nose scratches or quick head turns cause instant, false score drops. To fix this, I built the `TemporalFilter` class using a sliding window (bounded by a `deque`) and a downward step clamp to smooth out these single frame anomalies. On startup, it returns raw scores to prevent lag, then transitions into the sliding average. I also added a full test suite covering stable states, blips, sustained drops, and reset behavior.

---


## Issue 19

**By:** Aparna Singh

This issue focused on implementing a per-student calibration system to personalize engagement detection thresholds instead of relying on fixed global values. I developed a calibration pipeline that collects baseline biometric data while the student maintains a neutral posture, validates each captured frame, and computes personalized resting Eye Aspect Ratio (EAR), neutral head pose, and expression baselines. Based on these measurements, the system automatically derives individualized thresholds, including a calibrated EAR threshold for drowsiness detection while preserving configurable pose tolerances. I implemented robust session management with configurable calibration duration, frame validation, baseline aggregation, threshold computation, and persistent storage of calibration profiles as JSON files for later use. To improve reliability, I added comprehensive input validation, graceful handling of unavailable expression detection through fallback behavior, and safeguards against invalid or incomplete calibration sessions. Finally, I created a complete test suite covering successful calibration, invalid samples, threshold generation, session lifecycle, persistence, configuration validation, and edge cases, ensuring the calibration pipeline operates reliably and integrates seamlessly with the existing engagement scoring system.

---


## Issue 20
**By:** Ayush Aryan

This issue was about building a smart LangGraph agent to decide exactly when and how to nudge a distracted student. I built the `NudgeDecisionEngine` to make sure we don't annoy students by nudging too early — it only triggers after 30 straight seconds of distraction, waits for a 5-minute cooldown between nudges, and stops completely after 5 nudges in a session. It also uses a learning loop to look at past history and automatically pick the specific nudge type that worked best for that student before. I tied this all together using a LangGraph state machine, wrote 6 automated tests to prove the limits work.

---

## Issue 21

**By:** Aparna Singh

This issue focused on implementing a multi-channel nudge delivery system to provide timely and non-intrusive engagement reminders. I developed the backend delivery service supporting browser notifications, visual overlays, and optional audio nudges while respecting individual student preferences and logging each delivered nudge for future effectiveness tracking. I also implemented the `NudgeOverlay` React component to display a subtle screen-edge glow, integrate browser notifications and audio cues, and automatically dismiss nudges after a short duration. Additionally, I added a CLI for manually testing each delivery channel and verified backend functionality, database persistence, and seamless integration with the existing nudge decision pipeline.

## Issue 22
**By:** Anuradha

This issue was about closing the feedback loop on nudges — measuring whether a nudge actually improved a student's engagement instead of just sending it and hoping. I built the `EffectivenessTracker` class, which records a nudge along with the pre-nudge score, collects engagement scores observed in the 60 seconds after, and marks the nudge "effective" if the average post-nudge score improved by 10+ points. It also tracks a per-nudge-type success rate through `get_stats()`, and feeds that history back to the decision agent via `to_decision_history()`, matching the exact `{"type": ..., "success": ...}` format `NudgeDecisionEngine.should_nudge()` already expects, so the existing decision pipeline can consume it directly without changes on its side. For persistence across sessions, rather than adding a new table, I reused the existing `Nudge.effectiveness_delta` column already present on the model. I verified the exact worked example from the issue produces the expected output, and wrote 12 tests covering the core scenarios plus edge cases like window boundaries, multiple nudge types, and DB-persisted history.

---

## Issue 23
**By:** Ayush Aryan

This issue was about giving students full control over how and when they receive nudges. A system that forces the same nudges on everyone gets turned off — especially for students studying late at night who don't want audio chimes waking up their roommates. 

To solve this, I built a student-facing preferences system across the entire stack:
1. **Frontend Panel (`NudgePreferences.jsx`):** Created a clean, responsive UI where students can independently toggle nudge channels (browser notifications, screen overlay, audio chime), set 24-hour quiet hours (start and end times), and adjust nudge sensitivity (`less`, `normal`, `more`).
2. **Backend API (`src/api/routes/preferences.py` & `src/api/schemas/preferences.py`):** Built `GET` and `PUT` FastAPI endpoints at `/api/preferences/{user_id}` backed by Pydantic validation schemas to fetch and save preferences live with instant updates.
3. **Database Schema (`src/models/user.py` & Alembic Migration):** Extended the SQLAlchemy `User` model with `quiet_hours_start`, `quiet_hours_end`, and `sensitivity` fields, and ran an Alembic database migration to persist settings across sessions.
4. **Decision Engine Integration (`src/nudge/nudge_decision.py`):** Updated the `NudgeDecisionEngine` from Issue #20 to strictly respect these preferences in real time. It now checks quiet hours dynamically (even when spanning midnight), completely suppresses audio when disabled, and dynamically adjusts cooldown gaps based on sensitivity (`less` → 10 min, `normal` → 5 min, `more` → 3 min).

I verified the entire flow through automated unit tests (`pytest`), verified database persistence, and tested both `GET` and `PUT` endpoints using `curl` and interactive browser tests.

---

## Issue 24
**By:** yuvraj

This issue was about giving teachers one class wide view of engagement instead of 60 individual student timelines, while keeping every student's data anonymous. I built the `ClassAggregator` to compute the class pulse mean, median, std dev, min, max, and engaged percentage (score > 70) from a snapshot of scores, plus a minute by minute timeline built incrementally so it can run in real time during a session. It flags a dip whenever the class average drops more than 15% below the session average, since a simultaneous drop across the class points to a content problem, not a student problem. Disconnected students are excluded rather than zeroed out, and a minute where the whole class drops offline (e.g. wifi outage) is excluded entirely instead of being recorded as a fake 0% engagement crash. No method in the class ever accepts a student ID, so anonymization is enforced by design, not just by convention. I wrote tests covering the issue's exact reproduction script plus edge cases like missing data, junk values, and invalid thresholds.

---

## Issue 25
**By:** Aparna Singh

This issue was about identifying students who may need intervention before a single bad session turns into a consistent engagement problem. Instead of relying on one low score, the system now analyzes engagement history to detect sustained low performance and significant downward trends across multiple sessions. To support this, I built two reusable analytics modules along with comprehensive unit tests.

1. **Trend Analysis (`src/analytics/trend_analyzer.py`):** Built a framework-agnostic analytics utility for engagement trends. It provides rolling averages, rolling average series, percentage decline calculations, timestamp-based 7-day and 30-day rolling window averages, and real week-over-week comparisons using adjacent calendar windows. For scenarios where timestamps are unavailable, it also includes a documented first-half/second-half fallback to approximate trend analysis.

2. **Student Risk Identification (`src/analytics/risk_identifier.py`):** Implemented a reusable `RiskIdentifier` that evaluates each student's engagement history using two independent signals: (a) consecutive sessions below a configurable engagement threshold, and (b) significant week-over-week decline in engagement. Either condition is sufficient to flag a student as at risk, allowing teachers to intervene before engagement deteriorates further.

3. **Validation and Privacy:** Added comprehensive validation for engagement score ranges, configurable thresholds, decline percentages, consecutive session requirements, and chronological session ordering. The module anonymizes student identifiers by default while allowing opted-in students to retain their identity for targeted interventions.

4. **Testing:** Wrote a comprehensive unit test suite covering consecutive low-session detection, declining trend detection, timestamp-based rolling windows, week-over-week analysis, anonymization, validation, edge cases, invalid inputs, and window-boundary behavior. All new functionality was verified with automated tests, and the complete project test suite (`266` tests) passes successfully without regressions.

---

## Issue 26
**By:** Ayush Aryan

This issue was about allowing teachers to export engagement data in standard CSV and JSON formats so they can analyze it in external tools like Excel or use it for reporting. 

To build this data portability feature, I implemented:
1. **Export API Endpoints (`src/api/routes/export.py` & `src/api/main.py`):** Created `GET` endpoints at `/api/export/sessions/{id}` and `/api/export/courses/{id}` that fetch and stream engagement log data. I used SQLAlchemy's `yield_per` and FastAPI's `StreamingResponse` so that exporting huge datasets (1,000+ rows) streams smoothly without overloading the server's memory.
2. **Data Export & Privacy:** The exports output the exact engagement logs saved in the database. To protect student privacy, the real user IDs are automatically hashed into an anonymized format (e.g., `anon_<hash>`) before the file is sent. 
3. **Frontend Export Button (`ExportButton.jsx`):** Developed a reusable button component that handles downloading files cleanly by dynamically building query parameters for format (`csv` or `json`) and optional filters (date range and specific student IDs).


## Issue 27
**By:** Yuvraj

Implemented the session engagement report generator (`SessionReportGenerator`, 413 lines) for both teacher and student views. Added support for generating self-contained HTML reports with session metadata, engagement timeline, state distribution, top distraction moments, and anonymized class average comparison. Reports can be rendered for dashboards, downloaded, or used as email content, and can also be persisted to the database. Additionally, standardized engagement scoring to use a 0–1 scale throughout the backend while converting values to 0–100 only for UI display.

### Bug Fixes (follow-up commit `f410f58`)

- **UI display scale mismatch**: `to_json_safe_dict()` was only scaling `engaged_pct` and `class_engaged_pct` to 0–100 but leaving `overall_average`, `class_average`, all `timeline[*].average`, `class_timeline[*].average`, and distraction moment `value`/`baseline` on the 0–1 scale. With Chart.js y-axis set to `{ min: 0, max: 100 }`, these values visually clustered at the bottom. Now all UI-facing values are correctly scaled.
- **Stale error message**: `state_machine.py:312` said `"score 100"` but the check was against `1`. Fixed to match.
- **Stale docstrings/comments**: Updated outdated "0–100" references across `state_machine.py`, `class_aggregator.py`, `websocket.py`, and `effectiveness_tracker.py`.
- **Missing test coverage**: Added `tests/test_session_report.py` with 14 tests covering both class and student scopes, JSON scaling, HTML rendering, DB persistence, state distribution, and edge cases.

### Test Results

189 tests passing (including 14 new session report tests).

### Known Limitation

`test_migrations.py` uses the new `report_type="session_summary"` but no Alembic data migration renames existing `class_summary` rows. If any deployed DB already has `class_summary` rows, they won't be picked up by the new queries. Verify against Alembic history before merging to production.

---

## Issue 28

**By:** Aparna Singh

This issue was about generating a comprehensive weekly engagement report that summarizes student engagement across all lectures in a course for a given ISO week. I implemented the WeeklyReportGenerator to aggregate weekly engagement data, generate lecture engagement curves, analyze day-of-week and time-of-day engagement patterns, compare engagement with the previous week, identify anonymized at-risk students using the existing RiskIdentifier, and rank difficult lecture segments using the existing DifficultyCorrelator. I also developed a responsive Jinja2 HTML template with support for HTML and PDF export, handled edge cases such as empty weeks and timezone differences, and added unit tests covering report generation, rendering, serialization, persistence, CLI execution, performance, and regression scenarios. Finally, I verified the implementation by running the weekly report test suite as well as the complete project test suite successfully.

---
## Issue 29
**By:** Gargi

This issue was about building an LLM powered intervention agent that analyzes session engagement data and generates actionable teaching suggestions. I implemented the agent using LangGraph and Groq, integrated it with the existing session report generator and categorized the suggestions into Content, Delivery and Structure. While working on it I faced a few setup issues because the local database was not configured, Docker and PostgreSQL were not running and the database had no seeded data. After setting up Docker, running the migrations and seeding the database the agent started working correctly. I also improved the prompt so the model follows a consistent response format, updated the parser to handle the generated output reliably and added unit tests covering empty reports, suggestion generation and invalid responses. Finally I verified the complete flow by generating intervention suggestions successfully from a sample session.

---

## Issue 30
**By:** Gargi

This issue was about finding lecture topics that consistently caused engagement to drop across multiple class sessions. I implemented the `DifficultyCorrelator` to store session timelines and reused the existing `ClassAggregator.detect_dips()` method to identify engagement dips. I calculated the average engagement drop and severity for each recurring difficult segment, filtered the results based on the minimum number of sessions and ranked them by severity. I also wrote unit tests to cover the main functionality and edge cases and verified the implementation by running formatting, linting and the complete project test suite successfully.

---

## Issue 31

**By:** Gargi

This issue was about automating email delivery for engagement reports so teachers can receive session and weekly reports without sending them manually. I implemented email delivery for both session and weekly reports, integrated SendGrid with a graceful HTML fallback when an API key is not configured, added APScheduler to automatically schedule session reports after class completion and weekly reports every Monday at 8 AM, implemented an email rate limiter to prevent excessive email sending and added support for teacher notification preferences so reports are not sent when email notifications are disabled. While implementing the feature I found that the generated reports were complete HTML documents which resulted in nested HTML inside the email templates, so I extracted only the report body before rendering the templates to generate clean email content. Finally I added unit tests for the email sender, scheduler and rate limiter and verified the implementation by running formatting, linting and the complete project test suite successfully with all 311 tests passing. 

---

## Issue 33
**By:** Ayush Aryan

This issue was about building the Teacher Dashboard,  the single screen where every analytics feature we've built finally meets a real teacher. During a live lecture, a teacher needs to see at a glance how engaged the class is right now, who's slipping, and what to actually do about it, without jumping between ten different tools.

To build it, I created a React dashboard that brings the live engagement stream, class analytics, at-risk detection, and the intervention agent together in one view:

1. **Class Overview (`ClassOverview.jsx`):** A simple course picker plus the headline numbers — how many students are in the class and the class's average engagement. Switching courses updates everything instantly.

2. **Live Engagement (`LiveEngagement.jsx`):** A real-time line graph that reads the engagement score over a WebSocket and redraws every 2 seconds. It tries the real backend stream first (`ws://localhost:8000/ws/session/{id}`) and, if the backend isn't running, quietly falls back to a local demo stream so the graph keeps moving. It also auto-reconnects if the connection drops.

3. **Session History + Report (`TeacherDashboard.jsx`):** A list of past lectures; clicking one opens that session's report — average engagement, duration, the breakdown of engaged / passive / distracted / drowsy / confused states, and the top issues spotted in that lecture.

4. **At-Risk Students (`AtRiskPanel.jsx`):** Shows the students who need attention, but only as anonymized IDs (e.g. `anon_3f9a2c1b04`) with a ▲/▼ arrow so the teacher sees whether each is improving or declining — no raw student identity is ever shown.

5. **Intervention Suggestions (`InterventionPanel.jsx`):** The AI's teaching tips for the current moment (e.g. "pause for a 60-second think-pair-share"), pulled from the intervention agent.

I also handled the boring-but-important parts: a loading state while data loads, empty states when there's nothing to show, and a responsive layout that collapses from two columns to one on a tablet.

**A note on the data (important):** for now the dashboard runs on a built-in **demo-data layer**, not live data. The reason is that the ingestion pipeline (webcam capture #4 is still a stub) and the analytics that feed these panels class aggregation (#24), risk identification (#25), and the intervention agent (#29) haven't been exposed through API endpoints yet. So instead of waiting, I built the dashboard against the *real data shapes* those modules will produce, and fed it realistic dummy data. The payoff is that swapping to live data later is a drop-in: there's one file (`src/lib/dashboardData.js`) that every panel reads from, so when the backend is ready we just point that file at the real endpoints and change nothing in the components. The live graph is already future-proof — it prefers the real WebSocket and only simulates when the backend is offline. No component rewrites needed when the real pipeline lands.


---

