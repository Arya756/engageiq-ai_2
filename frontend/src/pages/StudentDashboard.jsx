import React, { useState, useEffect, useCallback, useMemo } from "react";
import axios from "axios";
import api from "../api"; // Adjust path if your project uses '../services/api' or '../lib/api'
import EngagementChart from "../components/EngagementChart";
import FocusStreak from "../components/FocusStreak";
import SessionHistory from "../components/SessionHistory";
import ImprovementTips from "../components/ImprovementTips";
import CurrentSession from "../components/CurrentSession";

// If your project exports shared API endpoints from a config/constants file,
// import them instead of defining this local constant.
const ENDPOINTS = {
  STUDENT_DASHBOARD: "/student/dashboard",
};

const DashboardSkeleton = () => (
  <div className="min-h-screen bg-gray-50 p-4 md:p-6 lg:p-8 animate-pulse">
    <div className="max-w-7xl mx-auto">
      <div className="h-8 bg-gray-200 rounded w-1/4 mb-2"></div>
      <div className="h-4 bg-gray-200 rounded w-1/3 mb-8"></div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        <div className="lg:col-span-8 h-80 bg-gray-200 rounded-xl"></div>
        <div className="lg:col-span-4 h-80 bg-gray-200 rounded-xl"></div>
        <div className="lg:col-span-8 h-80 bg-gray-200 rounded-xl"></div>
        <div className="lg:col-span-4 h-80 bg-gray-200 rounded-xl"></div>
      </div>
    </div>
  </div>
);

const getGreeting = () => {
  const hour = new Date().getHours();
  if (hour < 12) return "Good morning";
  if (hour < 18) return "Good afternoon";
  return "Good evening";
};

const StudentDashboard = () => {
  const [dashboardData, setDashboardData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchDashboardData = useCallback(async (signal) => {
    setLoading(true);
    setError(null);
    try {
      const { data } = await api.get(ENDPOINTS.STUDENT_DASHBOARD, { signal });

      if (!data) {
        throw new Error("Received an invalid response from the server.");
      }

      setDashboardData(data);
    } catch (err) {
      if (axios.isCancel(err) || err.code === "ERR_CANCELED") return;
      setError(err.message || "An unexpected error occurred.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    fetchDashboardData(controller.signal);

    return () => {
      controller.abort();
    };
  }, [fetchDashboardData]);

  const handleRetry = () => {
    const controller = new AbortController();
    fetchDashboardData(controller.signal);
  };

  // Clean extraction with nullish coalescing to prevent repeated inline fallbacks
  const sessionHistory = dashboardData?.sessionHistory ?? [];
  const tips = dashboardData?.tips ?? [];
  const currentSession = dashboardData?.currentSession;

  const hasHistory = useMemo(() => {
    return sessionHistory.length > 0;
  }, [sessionHistory]);

  if (loading) {
    return <DashboardSkeleton />;
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen bg-gray-50 space-y-4 text-center px-4">
        <div className="text-gray-800">
          <p className="font-semibold text-lg">
            Unable to load your dashboard.
          </p>
          <p className="text-gray-500">
            Please check your internet connection.
          </p>
        </div>
        <button
          onClick={handleRetry}
          aria-label="Retry loading dashboard"
          className="px-6 py-2 bg-blue-600 text-white font-medium rounded-md hover:bg-blue-700 transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
        >
          Retry
        </button>
      </div>
    );
  }

  if (!hasHistory && !currentSession) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-gray-50 text-gray-500 italic px-4 text-center">
        No sessions yet. Complete your first lecture to see analytics.
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 p-4 md:p-6 lg:p-8">
      <div className="max-w-7xl mx-auto">
        {/* Page Header */}
        <header className="mb-8">
          <h1 className="text-3xl font-extrabold text-gray-900">
            {getGreeting()}! 👋
          </h1>
          <p className="text-gray-600 mt-1 text-sm md:text-base">
            Here's a breakdown of your recent engagement and focus trends.
          </p>
        </header>

        {/* 12-Column Grid Layout */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          {/* Current Session Panel (Spans full width if active) */}
          {currentSession && (
            <div className="lg:col-span-12">
              <CurrentSession session={currentSession} />
            </div>
          )}

          {/* Top Row: Chart (8 cols) & Tips (4 cols) */}
          <div className="lg:col-span-8">
            <EngagementChart sessions={sessionHistory} />
          </div>
          <div className="lg:col-span-4">
            <ImprovementTips tips={tips} />
          </div>

          {/* Bottom Row: History (8 cols) & Streak (4 cols) */}
          <div className="lg:col-span-8">
            <SessionHistory history={sessionHistory} />
          </div>
          <div className="lg:col-span-4">
            <FocusStreak sessions={sessionHistory} />
          </div>
        </div>
      </div>
    </div>
  );
};

export default StudentDashboard;
