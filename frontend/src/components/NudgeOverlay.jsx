/**
 * NudgeOverlay.jsx — Issue #21
 *
 * Renders the three student-facing nudge channels:
 *   - browser notification (via the Notification API)
 *   - visual overlay: a subtle, non-blocking screen-edge glow
 *   - audio: a short (<2s), quiet chime
 *
 * This component does NOT open its own WebSocket / SSE connection. It
 * expects to receive nudge events from whatever already owns the app's
 * single WebSocket connection (the existing ConnectionManager on the
 * backend, consumed here through a `useNudgeSocket`-style hook or context
 * that the app already has). Wire it up like:
 *
 *   <NudgeOverlay nudge={latestNudgeEvent} onDismiss={() => setLatestNudgeEvent(null)} />
 *
 * where `latestNudgeEvent` is set whenever the app's existing WS message
 * handler receives a `{ event: "nudge", channel, message, ... }` payload
 * (see src/nudge/nudge_delivery.py for the payload shapes).
 */

import { useEffect, useRef, useState } from "react";
import PropTypes from "prop-types"; // remove this import + the propTypes block below if the project doesn't use prop-types
import "./NudgeOverlay.css";

// Keep in sync with the `4000ms` animation-duration values in NudgeOverlay.css.
const OVERLAY_VISIBLE_MS = 4000;

// TODO: confirm how this repo serves static audio (public/ vs src/assets/
// vs an existing CDN/asset pipeline) and point this at a real short
// (<2s), quiet chime file. Left unset on purpose rather than inventing a
// path that may not exist in the real project.
const CHIME_SRC = null; // e.g. "/sounds/gentle-chime.mp3" once an asset exists

/**
 * @param {Object} props
 * @param {{channel: string, message?: string, nudge_type?: string, edge?: string, volume?: number, duration_ms?: number} | null} props.nudge
 *   The most recent nudge payload received over the existing WebSocket, or null.
 * @param {() => void} [props.onDismiss] - called once the overlay has finished showing.
 */
export default function NudgeOverlay({ nudge, onDismiss }) {
    const [visible, setVisible] = useState(false);
    const audioRef = useRef(null);

    useEffect(() => {
        if (!nudge) return;

        if (nudge.channel === "overlay") {
            setVisible(true);
            const timer = setTimeout(() => {
                setVisible(false);
                onDismiss?.();
            }, OVERLAY_VISIBLE_MS);
            return () => clearTimeout(timer);
        }

        if (nudge.channel === "notification") {
            showBrowserNotification(nudge.title || "EngageIQ", nudge.message);
            onDismiss?.();
        }

        if (nudge.channel === "audio") {
            playChime(nudge.volume ?? 0.3, audioRef);
            onDismiss?.();
        }
    }, [nudge, onDismiss]);

    const edge = nudge?.edge || "right";
    const showOverlay = visible && nudge?.channel === "overlay";

    return (
        <>
            {CHIME_SRC && <audio ref={audioRef} src={CHIME_SRC} preload="auto" hidden />}

            {showOverlay && (
                <>
                    <div
                        className={`nudge-overlay-glow nudge-overlay-glow--${edge}`}
                        role="status"
                        aria-live="polite"
                        aria-label={nudge.message || "You seem distracted"}
                    />
                    {nudge.message && (
                        <div className={`nudge-overlay-caption nudge-overlay-caption--${edge}`}>
                            {nudge.message}
                        </div>
                    )}
                </>
            )}
        </>
    );
}

NudgeOverlay.propTypes = {
    nudge: PropTypes.shape({
        channel: PropTypes.oneOf(["notification", "overlay", "audio"]).isRequired,
        message: PropTypes.string,
        nudge_type: PropTypes.string,
        title: PropTypes.string,
        edge: PropTypes.oneOf(["top", "bottom", "left", "right"]),
        volume: PropTypes.number,
        duration_ms: PropTypes.number,
    }),
    onDismiss: PropTypes.func,
};

NudgeOverlay.defaultProps = {
    nudge: null,
    onDismiss: undefined,
};

function showBrowserNotification(title, message) {
    if (typeof window === "undefined" || !("Notification" in window)) return;

    if (Notification.permission === "granted") {
        new Notification(title, { body: message, silent: true });
        return;
    }

    if (Notification.permission === "default") {
        Notification.requestPermission().then((permission) => {
            if (permission === "granted") {
                new Notification(title, { body: message, silent: true });
            }
        });
    }
}

function playChime(volume, audioRef) {
    const el = audioRef.current;
    if (!el) return; // no chime asset wired up yet (see CHIME_SRC TODO above)
    try {
        el.volume = Math.min(Math.max(volume, 0), 1);
        el.currentTime = 0;
        // Autoplay can be blocked until the user has interacted with the page;
        // fail silently rather than throwing in the UI.
        void el.play().catch(() => { });
    } catch {
        // no-op — a missed chime should never break the page
    }
}