/**
 * A student-facing settings panel for controlling how and when they get nudged.
 * Students can:
 *   - Toggle each nudge channel on/off (notifications, overlay, audio)
 *   - Set quiet hours (no nudges between a start and end time)
 *   - Choose a sensitivity level (controls how quickly nudges fire)
 *
 * Uses light mode with mint/cream/blue colors for a calm, friendly feel.
 */

import { useEffect, useState } from "react";

// The sensitivity options and what they mean to the student
const SENSITIVITY_OPTIONS = [
    { value: "less", label: "Less", description: "Nudge me less often (10 min gap)" },
    { value: "normal", label: "Normal", description: "Balanced nudging (5 min gap)" },
    { value: "more", label: "More", description: "Nudge me sooner (3 min gap)" },
];

export default function NudgePreferences({ userId }) {
    // The current saved preferences loaded from the server
    const [preferences, setPreferences] = useState(null);

    // Whether we are currently saving changes to the server
    const [saving, setSaving] = useState(false);

    // A message to show the user after saving ("Saved!" or an error)
    const [statusMessage, setStatusMessage] = useState(null);

    // Fetch the student's current preferences from the backend when the page loads
    useEffect(() => {
        fetch(`/api/preferences/${userId}`)
            .then((res) => res.json())
            .then((data) => setPreferences(data))
            .catch(() => setStatusMessage({ type: "error", text: "Could not load preferences." }));
    }, [userId]);

    // Called whenever the student changes any setting
    // It immediately saves the change to the backend (live update)
    const saveChange = (updatedFields) => {
        setSaving(true);
        setStatusMessage(null);

        // Update local state immediately so the UI feels instant
        setPreferences((prev) => ({ ...prev, ...updatedFields }));

        // Send only the changed field to the server
        fetch(`/api/preferences/${userId}`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(updatedFields),
        })
            .then((res) => {
                if (!res.ok) throw new Error("Failed to save.");
                return res.json();
            })
            .then(() => {
                setStatusMessage({ type: "success", text: "✓ Saved!" });
                // Clear the success message after 2 seconds
                setTimeout(() => setStatusMessage(null), 2000);
            })
            .catch(() => {
                setStatusMessage({ type: "error", text: "Could not save changes. Please try again." });
            })
            .finally(() => setSaving(false));
    };

    // Show a loading message while preferences are being fetched
    if (!preferences) {
        return <div style={styles.loading}>Loading your preferences...</div>;
    }

    return (
        <div style={styles.page}>
            <div style={styles.card}>
                {/* --- Page Header --- */}
                <div style={styles.header}>
                    <h1 style={styles.title}>Nudge Preferences</h1>
                    <p style={styles.subtitle}>
                        Control exactly how and when EngageIQ reminds you to stay focused.
                    </p>
                </div>

                {/* --- Save Status Banner --- */}
                {statusMessage && (
                    <div style={statusMessage.type === "success" ? styles.bannerSuccess : styles.bannerError}>
                        {statusMessage.text}
                    </div>
                )}

                {/* --- Section 1: Nudge Channels --- */}
                <section style={styles.section}>
                    <h2 style={styles.sectionTitle}>Nudge Channels</h2>
                    <p style={styles.sectionDescription}>
                        Choose how you want to be notified when you seem distracted.
                    </p>

                    <ToggleRow
                        label="Browser Notification"
                        description="A pop-up notification appears in your browser."
                        checked={preferences.notification_enabled}
                        onChange={(val) => saveChange({ notification_enabled: val })}
                        disabled={saving}
                    />
                    <ToggleRow
                        label="Screen Overlay"
                        description="A soft glowing border appears around your screen."
                        checked={preferences.overlay_enabled}
                        onChange={(val) => saveChange({ overlay_enabled: val })}
                        disabled={saving}
                    />
                    <ToggleRow
                        label="Audio Chime"
                        description="A short, quiet chime sound plays."
                        checked={preferences.audio_enabled}
                        onChange={(val) => saveChange({ audio_enabled: val })}
                        disabled={saving}
                    />
                </section>

                <div style={styles.divider} />

                {/* --- Section 2: Quiet Hours --- */}
                <section style={styles.section}>
                    <h2 style={styles.sectionTitle}>Quiet Hours</h2>
                    <p style={styles.sectionDescription}>
                        Set a time window when you do NOT want to be nudged (e.g., late at night).
                        Leave blank to always allow nudges.
                    </p>

                    <div style={styles.timeRow}>
                        <div style={styles.timeField}>
                            <label style={styles.timeLabel}>Start Time</label>
                            <input
                                type="time"
                                style={styles.timeInput}
                                value={preferences.quiet_hours_start || ""}
                                onChange={(e) =>
                                    saveChange({ quiet_hours_start: e.target.value || null })
                                }
                                disabled={saving}
                            />
                        </div>
                        <span style={styles.timeSeparator}>to</span>
                        <div style={styles.timeField}>
                            <label style={styles.timeLabel}>End Time</label>
                            <input
                                type="time"
                                style={styles.timeInput}
                                value={preferences.quiet_hours_end || ""}
                                onChange={(e) =>
                                    saveChange({ quiet_hours_end: e.target.value || null })
                                }
                                disabled={saving}
                            />
                        </div>
                    </div>
                </section>

                <div style={styles.divider} />

                {/* --- Section 3: Sensitivity --- */}
                <section style={styles.section}>
                    <h2 style={styles.sectionTitle}>Sensitivity</h2>
                    <p style={styles.sectionDescription}>
                        How quickly should the system nudge you after detecting distraction?
                    </p>

                    <div style={styles.sensitivityRow}>
                        {SENSITIVITY_OPTIONS.map((option) => (
                            <button
                                key={option.value}
                                style={
                                    preferences.sensitivity === option.value
                                        ? styles.sensitivityBtnActive
                                        : styles.sensitivityBtn
                                }
                                onClick={() => saveChange({ sensitivity: option.value })}
                                disabled={saving}
                                title={option.description}
                            >
                                <span style={styles.sensitivityLabel}>{option.label}</span>
                                <span style={styles.sensitivityDesc}>{option.description}</span>
                            </button>
                        ))}
                    </div>
                </section>
            </div>
        </div>
    );
}

// --- Reusable Toggle Row Component ---
// A single row with a label, description, and an on/off toggle switch
function ToggleRow({ label, description, checked, onChange, disabled }) {
    return (
        <div style={styles.toggleRow}>
            <div style={styles.toggleText}>
                <span style={styles.toggleLabel}>{label}</span>
                <span style={styles.toggleDescription}>{description}</span>
            </div>
            {/* The toggle switch (styled checkbox) */}
            <div
                style={{
                    ...styles.toggleSwitch,
                    backgroundColor: checked ? "#0D9488" : "#CBD5E1",
                    opacity: disabled ? 0.6 : 1,
                    cursor: disabled ? "not-allowed" : "pointer",
                    boxShadow: checked
                        ? "0 2px 8px rgba(13, 148, 136, 0.40), inset 0 1px 2px rgba(255,255,255,0.15)"
                        : "inset 0 2px 4px rgba(0,0,0,0.10)",
                }}
                onClick={() => !disabled && onChange(!checked)}
                role="switch"
                aria-checked={checked}
                tabIndex={0}
                onKeyDown={(e) => e.key === "Enter" && !disabled && onChange(!checked)}
            >
                <div
                    style={{
                        ...styles.toggleKnob,
                        transform: checked ? "translateX(24px)" : "translateX(0px)",
                    }}
                />
            </div>
        </div>
    );
}

// --- All Styles (Light Mode: Turquoise / Mint / Cream palette) ---
const styles = {
    page: {
        minHeight: "100vh",
        backgroundColor: "#F0FDFA",      // soft cream-turquoise background
        display: "flex",
        justifyContent: "center",
        alignItems: "flex-start",
        padding: "40px 16px",
        fontFamily: "'Inter', 'Segoe UI', sans-serif",
    },
    card: {
        backgroundColor: "#FFFFFF",
        borderRadius: "20px",
        // Layered box-shadow: soft outer glow + deeper mid shadow for depth
        boxShadow: "0 2px 6px rgba(13, 148, 136, 0.08), 0 8px 32px rgba(13, 148, 136, 0.14), 0 1px 2px rgba(0,0,0,0.06)",
        padding: "40px",
        width: "100%",
        maxWidth: "640px",
        border: "1.5px solid #99F6E4",   // turquoise border with depth
        outline: "3px solid rgba(13, 148, 136, 0.06)",  // subtle outer glow ring
        outlineOffset: "2px",
    },
    header: {
        marginBottom: "28px",
        paddingBottom: "20px",
        borderBottom: "2px solid #CCFBF1",  // turquoise divider line
    },
    title: {
        fontSize: "26px",
        fontWeight: "700",
        color: "#0F766E",               // deep turquoise
        margin: "0 0 8px 0",
        letterSpacing: "-0.3px",
    },
    subtitle: {
        fontSize: "15px",
        color: "#5EACA4",               // muted turquoise-grey
        margin: "0",
    },
    bannerSuccess: {
        backgroundColor: "#ECFDF5",
        color: "#065F46",
        borderRadius: "10px",
        padding: "10px 16px",
        fontSize: "14px",
        marginBottom: "20px",
        border: "1px solid #6EE7B7",
        boxShadow: "inset 0 1px 3px rgba(6, 95, 70, 0.08)",
    },
    bannerError: {
        backgroundColor: "#FEE2E2",
        color: "#991B1B",
        borderRadius: "10px",
        padding: "10px 16px",
        fontSize: "14px",
        marginBottom: "20px",
        border: "1px solid #FECACA",
        boxShadow: "inset 0 1px 3px rgba(153, 27, 27, 0.08)",
    },
    section: {
        marginBottom: "8px",
    },
    sectionTitle: {
        fontSize: "17px",
        fontWeight: "600",
        color: "#0D9488",               // medium turquoise
        margin: "0 0 4px 0",
    },
    sectionDescription: {
        fontSize: "13px",
        color: "#6BAAA5",               // muted teal-grey
        margin: "0 0 20px 0",
    },
    divider: {
        height: "1px",
        // Two-tone divider for depth effect
        background: "linear-gradient(to right, #CCFBF1, #99F6E4, #CCFBF1)",
        margin: "24px 0",
    },
    // --- Toggle Row ---
    toggleRow: {
        display: "flex",
        alignItems: "center",
        gap: "16px",
        padding: "14px 0",
        borderBottom: "1px solid #E0FAF7",
    },
    toggleText: {
        flex: 1,
        display: "flex",
        flexDirection: "column",
    },
    toggleLabel: {
        fontSize: "15px",
        fontWeight: "500",
        color: "#134E4A",               // deep teal text
    },
    toggleDescription: {
        fontSize: "12px",
        color: "#6BAAA5",
        marginTop: "2px",
    },
    toggleSwitch: {
        width: "52px",
        height: "28px",
        borderRadius: "14px",
        position: "relative",
        transition: "background-color 0.25s ease, box-shadow 0.25s ease",
        flexShrink: 0,
    },
    toggleKnob: {
        position: "absolute",
        top: "4px",
        left: "4px",
        width: "20px",
        height: "20px",
        borderRadius: "50%",
        backgroundColor: "#FFFFFF",
        // Knob has its own shadow for lifted 3D look
        boxShadow: "0 2px 6px rgba(0,0,0,0.25), 0 1px 2px rgba(0,0,0,0.15)",
        transition: "transform 0.25s ease",
    },
    // --- Quiet Hours ---
    timeRow: {
        display: "flex",
        alignItems: "center",
        gap: "16px",
        flexWrap: "wrap",               // wraps on small screens (mobile)
    },
    timeField: {
        display: "flex",
        flexDirection: "column",
        gap: "6px",
    },
    timeLabel: {
        fontSize: "12px",
        fontWeight: "500",
        color: "#5EACA4",
        textTransform: "uppercase",
        letterSpacing: "0.5px",
    },
    timeInput: {
        padding: "10px 14px",
        borderRadius: "10px",
        border: "1.5px solid #5EEAD4",  // turquoise border
        fontSize: "15px",
        color: "#134E4A",
        backgroundColor: "#F0FDFA",     // soft cream-turquoise fill
        outline: "none",
        cursor: "pointer",
        minWidth: "130px",
        // Inset shadow gives the input a sunken / depth feel
        boxShadow: "inset 0 2px 4px rgba(13, 148, 136, 0.08)",
    },
    timeSeparator: {
        color: "#6BAAA5",
        fontSize: "14px",
        marginTop: "22px",
    },
    // --- Sensitivity ---
    sensitivityRow: {
        display: "flex",
        gap: "12px",
        flexWrap: "wrap",               // wraps on small screens (mobile)
    },
    sensitivityBtn: {
        flex: 1,
        minWidth: "140px",
        padding: "14px 12px",
        border: "1.5px solid #99F6E4",  // turquoise border
        borderRadius: "14px",
        backgroundColor: "#F0FDFA",     // cream-turquoise fill
        cursor: "pointer",
        textAlign: "center",
        display: "flex",
        flexDirection: "column",
        gap: "4px",
        transition: "all 0.2s ease",
        // Subtle lift shadow for depth
        boxShadow: "0 1px 4px rgba(13, 148, 136, 0.08), inset 0 1px 2px rgba(255,255,255,0.9)",
    },
    sensitivityBtnActive: {
        flex: 1,
        minWidth: "140px",
        padding: "14px 12px",
        border: "2px solid #0D9488",    // vivid turquoise active border
        borderRadius: "14px",
        backgroundColor: "#CCFBF1",     // light turquoise active fill
        cursor: "pointer",
        textAlign: "center",
        display: "flex",
        flexDirection: "column",
        gap: "4px",
        // Layered: outer glow ring + deeper inner shadow
        boxShadow: "0 0 0 3px rgba(13, 148, 136, 0.15), 0 4px 12px rgba(13, 148, 136, 0.20), inset 0 1px 3px rgba(255,255,255,0.7)",
    },
    sensitivityLabel: {
        fontSize: "15px",
        fontWeight: "600",
        color: "#0F766E",               // deep turquoise
    },
    sensitivityDesc: {
        fontSize: "11px",
        color: "#6BAAA5",
        lineHeight: "1.4",
    },
    loading: {
        padding: "60px",
        textAlign: "center",
        color: "#6BAAA5",
        fontFamily: "'Inter', sans-serif",
        fontSize: "15px",
    },
};
