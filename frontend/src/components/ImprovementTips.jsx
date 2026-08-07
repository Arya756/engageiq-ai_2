import React from "react";

const ImprovementTips = ({ tips = [] }) => {
  if (!tips.length) {
    return (
      <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-100 h-full flex flex-col">
        <h2 className="text-lg font-semibold text-gray-800 mb-4">
          Improvement Tips
        </h2>
        <div className="flex-grow flex items-center justify-center text-gray-500 italic text-center min-h-[16rem]">
          No recommendations yet. Keep up the good work!
        </div>
      </div>
    );
  }

  return (
    <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-100 h-full flex flex-col">
      <h2 className="text-lg font-semibold text-gray-800 mb-4">
        Improvement Tips
      </h2>

      {/* 3 & 4. Semantic HTML (ul) and slightly better breathing room (space-y-4) */}
      <ul className="max-h-80 overflow-y-auto pr-2 space-y-4 custom-scrollbar">
        {tips.map((tip, index) => {
          // 2. Handle whitespace-only strings defensively
          const title = tip?.title?.trim() || "Engagement Tip";
          const explanation =
            tip?.explanation?.trim() ||
            "Stay focused to improve your learning outcomes.";

          return (
            <li
              // 1. Better fallback key avoiding raw index
              key={tip?.id ?? `${title}-${index}`}
              className="flex items-start p-4 bg-indigo-50/50 rounded-lg border border-indigo-100/50 hover:bg-indigo-50 transition-colors"
            >
              <div className="flex-shrink-0 w-8 h-8 rounded-full bg-indigo-100 flex items-center justify-center text-indigo-600 mr-3 mt-0.5">
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  viewBox="0 0 24 24"
                  fill="currentColor"
                  className="w-5 h-5"
                  aria-hidden="true"
                >
                  <path d="M12 2.25a.75.75 0 0 1 .75.75v2.25a.75.75 0 0 1-1.5 0V3a.75.75 0 0 1 .75-.75ZM7.5 12a4.5 4.5 0 1 1 8.224 2.124.75.75 0 0 1-.281.434l-1.943 1.458v.484a.75.75 0 0 1-.75.75H11.25a.75.75 0 0 1-.75-.75v-.484l-1.943-1.458a.75.75 0 0 1-.281-.434A4.48 4.48 0 0 1 7.5 12ZM13.5 20.25v-1.5H10.5v1.5a.75.75 0 0 0 .75.75h1.5a.75.75 0 0 0 .75-.75ZM4.912 6.57a.75.75 0 0 1 1.06 0l1.591 1.59a.75.75 0 1 1-1.06 1.06l-1.59-1.59a.75.75 0 0 1 0-1.06ZM19.088 6.57a.75.75 0 0 1 0 1.06l-1.591 1.59a.75.75 0 1 1-1.06-1.06l1.59-1.59a.75.75 0 0 1 1.06 0ZM3 11.25a.75.75 0 0 1 .75-.75h2.25a.75.75 0 0 1 0 1.5H3.75a.75.75 0 0 1-.75-.75ZM18 11.25a.75.75 0 0 1 .75-.75h2.25a.75.75 0 0 1 0 1.5H18.75a.75.75 0 0 1-.75-.75Z" />
                </svg>
              </div>

              <div>
                {/* 5. Strong semantic heading hierarchy */}
                <h3 className="font-semibold text-gray-900 leading-tight">
                  {title}
                </h3>
                <p className="text-sm text-gray-600 mt-1 leading-relaxed">
                  {explanation}
                </p>
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
};

export default ImprovementTips;
