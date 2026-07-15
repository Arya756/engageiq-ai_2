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


## Issue 16
**By:** Gargi

This issue was about building a weighted engagement scorer that combines gaze, head pose, facial expression and alertness into a single 0 – 100 engagement score. I implemented configurable scoring with support for different course type profiles, added proportional weight redistribution when one or more signals are unavailable, created scoring weight profiles and comprehensive tests covering high, low, mixed, missing-signal and profile based scenarios. The implementation is currently configurable through predefined profiles and in future it can be extended to support teacher selected course specific profiles and custom weight configurations.

---


## Issue 17

**By:** Aparna Singh

This issue was about implementing the engagement state machine that converts a continuous engagement score into discrete, actionable states for downstream agents. I built a finite state machine with five states — ENGAGED, PASSIVE, DISTRACTED, DROWSY, and CONFUSED — where normal engagement is determined from configurable score ranges while CONFUSED and DROWSY act as override states based on expression and drowsiness signals. To prevent rapid state oscillations caused by noisy scores, I implemented configurable temporal hysteresis so a candidate state must remain valid for its required duration before a transition is confirmed. I added transition events through a subscriber system so other modules can react to state changes, maintained a bounded history of confirmed states with timestamps for analytics, and included comprehensive validation for configuration, scores, timestamps, and transition logic to handle invalid or inconsistent inputs gracefully. Finally, I developed an extensive test suite covering sustained engagement, hysteresis behavior, gradual state transitions, drowsiness and confusion overrides, event emission, history logging, configurable thresholds, validation, and edge cases, with all project tests passing successfully.

---