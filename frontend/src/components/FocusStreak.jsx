import React, { useMemo } from "react";

const FocusStreak = ({ sessions = [] }) => {
  const currentStreak = useMemo(() => {
    let streak = 0;

    // Stable sort from newest to oldest using Date.parse
    const sortedDesc = [...sessions].sort(
      (a, b) => Date.parse(b.date) - Date.parse(a.date),
    );

    for (const session of sortedDesc) {
      // Defensively parse the score, defaulting to 0
      if ((Number(session.score) || 0) > 70) {
        streak++;
      } else {
        break; // Streak broken
      }
    }
    return streak;
  }, [sessions]);

  // 4. Handle Empty State gracefully
  if (!sessions.length) {
    return (
      <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-100 flex flex-col h-full">
        <h2 className="text-lg font-semibold text-gray-800 mb-4 w-full text-left">
          Focus Streak
        </h2>
        <div className="flex-grow flex items-center justify-center text-gray-500 italic text-center">
          No sessions completed yet.
        </div>
      </div>
    );
  }

  // 5. Dynamic Motivation Message
  const motivationMessage =
    currentStreak === 0
      ? "Complete a focused session to start your streak!"
      : currentStreak < 3
        ? "Great start! Keep your focus up."
        : currentStreak < 7
          ? "You're on a roll! Keep it going!"
          : "Amazing consistency! You're unstoppable.";

  return (
    <div
      className="bg-white p-6 rounded-xl shadow-sm border border-gray-100 flex flex-col items-center text-center h-full"
      role="status"
      aria-live="polite"
    >
      <h2 className="text-lg font-semibold text-gray-800 mb-4 w-full text-left">
        Focus Streak
      </h2>

      <div className="flex-grow flex flex-col items-center justify-center">
        {/* 8. Professional SVG Icon instead of emoji */}
        <svg
          xmlns="http://www.w3.org/2000/svg"
          viewBox="0 0 24 24"
          fill="currentColor"
          className="w-12 h-12 text-orange-500 mb-3"
          aria-hidden="true"
        >
          <path
            fillRule="evenodd"
            d="M12.963 2.286a.75.75 0 0 0-1.071-.136 9.742 9.742 0 0 0-3.539 6.176 7.547 7.547 0 0 1-1.705-1.715.75.75 0 0 0-1.152-.082A9 9 0 1 0 15.68 4.534a7.46 7.46 0 0 1-2.717-2.248ZM15.75 14.25a3.75 3.75 0 1 1-7.313-1.172c.628.465 1.35.81 2.133 1a5.99 5.99 0 0 1 1.925-3.546 3.75 3.75 0 0 1 3.255 3.718Z"
            clipRule="evenodd"
          />
        </svg>

        <div className="text-5xl font-extrabold text-gray-900 mb-1 tracking-tight">
          {currentStreak}
        </div>
        <p className="text-gray-600 font-medium text-lg mb-3">
          Session{currentStreak !== 1 ? "s" : ""}
        </p>

        {/* 5. Display the dynamic motivation message */}
        <p className="text-sm font-medium text-blue-600 bg-blue-50 py-1.5 px-3 rounded-full mt-2">
          {motivationMessage}
        </p>
      </div>
    </div>
  );
};

export default FocusStreak;
