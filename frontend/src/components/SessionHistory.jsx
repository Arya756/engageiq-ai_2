import React, { useMemo } from "react";

// 5. Extract SVG for cleaner component organization
const CourseIcon = () => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    className="h-5 w-5"
    viewBox="0 0 20 20"
    fill="currentColor"
    aria-hidden="true"
  >
    <path d="M10.394 2.08a1 1 0 00-.788 0l-7 3a1 1 0 000 1.84L5.25 8.051a.999.999 0 01.356-.257l4-1.714a1 1 0 11.788 1.838L7.667 9.088l1.94.831a1 1 0 00.787 0l7-3a1 1 0 000-1.838l-7-3zM3.31 9.397L5 10.12v4.102a8.969 8.969 0 00-1.05-.174 1 1 0 01-.89-.89 11.115 11.115 0 01.25-3.762zM9.3 16.573A9.026 9.026 0 007 14.935v-3.957l1.818.78a3 3 0 002.364 0l5.508-2.361a11.026 11.026 0 01.25 3.762 1 1 0 01-.89.89 8.968 8.968 0 00-5.35 2.524 1 1 0 01-1.4 0zM6 18a1 1 0 001-1v-2.065a8.935 8.935 0 00-2-.712V17a1 1 0 001 1z" />
  </svg>
);

const SessionHistory = ({ history = [] }) => {
  const sortedHistory = useMemo(() => {
    return (
      history
        .map((session) => {
          // 4. Precompute formatted dates here to save render cycles
          const formattedDate = session.date
            ? new Date(session.date).toLocaleDateString(undefined, {
                month: "short",
                day: "numeric",
                year: "numeric",
              })
            : "Unknown Date";

          return {
            ...session,
            score: Math.max(0, Math.min(100, Number(session.score) || 0)),
            formattedDate,
          };
        })
        // 2. Safe sorting for invalid dates
        .sort((a, b) => (Date.parse(b.date) || 0) - (Date.parse(a.date) || 0))
    );
  }, [history]);

  // 1. Check length directly against the computed array
  if (sortedHistory.length === 0) {
    return (
      <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-100 h-full flex flex-col">
        <h2 className="text-lg font-semibold text-gray-800 mb-4">
          Recent Sessions
        </h2>
        <div className="flex-grow flex items-center justify-center text-gray-500 italic min-h-[16rem]">
          No session history available.
        </div>
      </div>
    );
  }

  return (
    <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-100 h-full flex flex-col">
      <h2 className="text-lg font-semibold text-gray-800 mb-4">
        Recent Sessions
      </h2>

      <div
        className="max-h-80 overflow-y-auto pr-2 space-y-2 custom-scrollbar"
        role="list"
      >
        {sortedHistory.map((session) => {
          const isHigh = session.score >= 70;
          const badgeColors = isHigh
            ? "bg-emerald-100 text-emerald-700 border-emerald-200"
            : "bg-amber-100 text-amber-700 border-amber-200";

          // 3. Dynamic pluralization for duration
          const duration = Number(session.duration) || 0;
          const durationText = `${duration} ${duration === 1 ? "min" : "mins"}`;

          return (
            <div
              key={session.id || `${session.course}-${session.date}`}
              role="listitem"
              className="flex justify-between items-center p-3 border border-gray-100 hover:border-blue-100 hover:shadow-sm hover:bg-blue-50/30 transition-all rounded-lg"
            >
              <div className="flex items-center space-x-4">
                <div className="flex-shrink-0 w-10 h-10 rounded-full bg-blue-100 flex items-center justify-center text-blue-600">
                  <CourseIcon />
                </div>

                <div>
                  <p className="font-medium text-gray-900">
                    {session.course ?? "Unknown Course"}
                  </p>
                  <p className="text-sm text-gray-500">
                    {session.formattedDate} • {durationText}
                  </p>
                </div>
              </div>

              <div className="flex items-center">
                <span
                  className={`px-3 py-1 rounded-full text-sm font-bold border ${badgeColors}`}
                >
                  {session.score}%
                </span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default SessionHistory;
