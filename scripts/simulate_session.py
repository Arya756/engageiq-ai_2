"""simulate_session.py — emits a live engagement WebSocket stream.

Issue #33 acceptance test:
    python scripts/simulate_session.py --students 3 --duration 60
    # Dashboard should show live graph updating every 2 seconds

This stands in for a real lecture session. It opens a WebSocket server
on ws://0.0.0.0:8000/ws/session/<session_id> and, for each connected
client, emits one JSON frame every 2 seconds (matching the contract the
backend's src/api/websocket.py uses):

    {"session_id": <int>, "timestamp": <float>, "engagement_score": <float>}

Run it before opening the dashboard if you want the graph to show a real
(live) WS connection instead of the built-in demo simulator. Each student
gets an independent random-walk score so the multiple-connection path is
exercised too.

Requires: `pip install websockets`.

Usage:
    python scripts/simulate_session.py --students 3 --duration 60 --session-id 101
    python scripts/simulate_session.py --port 8000            # Ctrl-C to stop
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import random
import time

try:
    import websockets
except ImportError:  # pragma: no cover - dependency guard
    raise SystemExit(
        "Missing dependency: install with `pip install websockets` "
        "(this script is only needed for live-demo testing)."
    )


def make_walker(start: float):
    """Random-walk generator producing a believable classroom score 0-100."""
    score = start

    def step() -> float:
        nonlocal score
        score += (random.random() - 0.5) * 14
        score = max(35.0, min(93.0, score))
        return round(score, 1)

    return step


async def handler(websocket, session_id: int, walkers: list):
    import itertools

    turn = itertools.count()
    walker = random.choice(walkers)
    try:
        while True:
            await asyncio.sleep(2)
            payload = {
                "session_id": session_id,
                "timestamp": time.time(),
                "engagement_score": walker(),
            }
            await websocket.send(json.dumps(payload))
    except websockets.ConnectionClosed:
        return


async def main_async(args):
    session_id = args.session_id
    walkers = [make_walker(random.uniform(55, 78)) for _ in range(args.students)]

    # One handler factory bound to this session's walkers.
    async def factory(ws):
        await handler(ws, session_id, walkers)

    path = f"/ws/session/{session_id}"
    print(
        f"Simulating session {session_id} for {args.students} students.\n"
        f"Serving WebSocket frames at ws://localhost:{args.port}{path}\n"
        f"Open the dashboard, then press Ctrl-C to stop."
    )

    async with websockets.serve(factory, "0.0.0.0", args.port, subprotocols=None):
        if args.duration > 0:
            await asyncio.sleep(args.duration)
            print(f"\nDuration {args.duration}s elapsed — stopping.")
        else:
            await asyncio.Future()  # run forever until Ctrl-C


def main():
    p = argparse.ArgumentParser(description="Simulate a live engagement session.")
    p.add_argument("--students", type=int, default=3, help="Number of student streams")
    p.add_argument("--duration", type=int, default=0, help="Seconds to run (0 = forever)")
    p.add_argument("--session-id", type=int, default=101, help="Session id to broadcast")
    p.add_argument("--port", type=int, default=8000, help="WebSocket port")
    args = p.parse_args()
    try:
        asyncio.run(main_async(args))
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
