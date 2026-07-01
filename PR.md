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