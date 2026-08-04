import React, { useMemo } from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";

const EngagementChart = ({ sessions }) => {
  const chartData = useMemo(() => {
    if (!sessions) return [];
    return (
      sessions
        .map((session) => ({
          ...session,
          // Defensively clamp scores securely between 0 and 100, falling back to 0
          score: Math.max(0, Math.min(100, Number(session.score) || 0)),
        }))
        // Stable sort via Date.parse
        .sort((a, b) => Date.parse(a.date) - Date.parse(b.date))
        .slice(-7)
    );
  }, [sessions]);

  // 1. Handle Empty Data gracefully
  if (!chartData.length) {
    return (
      <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-100 h-full flex flex-col">
        <h2 className="text-lg font-semibold text-gray-800 mb-4">
          Engagement History
        </h2>
        <div className="flex-grow flex items-center justify-center text-gray-500 italic min-h-[16rem]">
          No engagement history available.
        </div>
      </div>
    );
  }

  // 9. Calculate the rolling average of the displayed sessions
  const average = Math.round(
    chartData.reduce((acc, curr) => acc + curr.score, 0) / chartData.length,
  );

  return (
    <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-100 h-full flex flex-col">
      <div className="flex justify-between items-end mb-6">
        <h2 className="text-lg font-semibold text-gray-800">
          Engagement History
        </h2>
        <div className="text-right">
          <span className="text-sm text-gray-500 block font-medium">
            7-Session Avg
          </span>
          <span className="text-2xl font-bold text-blue-600">{average}%</span>
        </div>
      </div>

      <div
        className="flex-grow min-h-[16rem]"
        role="img"
        aria-label="Line chart showing engagement scores over the last 7 sessions"
      >
        <ResponsiveContainer width="100%" height="100%">
          <LineChart
            data={chartData}
            margin={{ top: 5, right: 10, left: -20, bottom: 0 }}
          >
            <CartesianGrid
              strokeDasharray="3 3"
              vertical={false}
              stroke="#e5e7eb"
            />

            <XAxis
              dataKey="date"
              tick={{ fontSize: 12, fill: "#6b7280" }}
              axisLine={false}
              tickLine={false}
              tickFormatter={(value) =>
                new Date(value).toLocaleDateString(undefined, {
                  month: "short",
                  day: "numeric",
                })
              }
            />

            <YAxis
              domain={[0, 100]}
              tick={{ fontSize: 12, fill: "#6b7280" }}
              axisLine={false}
              tickLine={false}
              tickFormatter={(value) => `${value}%`}
            />

            <Tooltip
              formatter={(value) => [`${value}%`, "Engagement"]}
              labelFormatter={(label) =>
                new Date(label).toLocaleDateString(undefined, {
                  weekday: "short",
                  year: "numeric",
                  month: "short",
                  day: "numeric",
                })
              }
              contentStyle={{
                borderRadius: "8px",
                border: "none",
                boxShadow: "0 4px 6px -1px rgba(0, 0, 0, 0.1)",
              }}
            />

            <Line
              type="monotone"
              dataKey="score"
              stroke="#3b82f6"
              strokeWidth={3}
              dot={{ r: 4, fill: "#3b82f6", strokeWidth: 2, stroke: "#fff" }}
              activeDot={{ r: 6 }}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};

export default EngagementChart;
