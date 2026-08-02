import React, { useState } from 'react';

/**
 * A simple button that downloads a CSV or JSON file from our API.
 */
const ExportButton = ({
    entityType = 'sessions', // Either 'sessions' or 'courses'
    entityId,                // The ID of the session or course
    format = 'csv',          // The format you want ('csv' or 'json')
    startDate = '',          // Optional: start date filter (ISO format)
    endDate = '',            // Optional: end date filter (ISO format)
    studentId = ''           // Optional: specific student ID to filter by
}) => {
    const [isExporting, setIsExporting] = useState(false);

    // This function runs when the user clicks the button
    const handleExport = () => {
        setIsExporting(true);

        try {
            // Build the URL to our backend endpoint
            const baseUrl = `http://localhost:8000/api/export/${entityType}/${entityId}`;
            const params = new URLSearchParams({ format });

            // Add optional filters to the URL if they exist
            if (startDate) params.append('start', startDate);
            if (endDate) params.append('end', endDate);
            if (studentId) params.append('student_id', studentId);

            const fullUrl = `${baseUrl}?${params.toString()}`;

            // We trigger the download by pretending to click a hidden link.
            // This lets the browser handle the file stream smoothly.
            const link = document.createElement('a');
            link.href = fullUrl;
            link.click();

        } catch (error) {
            console.error("Export failed", error);
            alert("Failed to start the export.");
        } finally {
            setIsExporting(false);
        }
    };

    return (
        <button
            onClick={handleExport}
            disabled={isExporting}
            className={`px-4 py-2 rounded font-medium text-white transition-colors
        ${isExporting
                    ? 'bg-gray-400 cursor-not-allowed'
                    : 'bg-blue-600 hover:bg-blue-700'
                }`}
        >
            {isExporting ? 'Exporting...' : `Export as ${format.toUpperCase()}`}
        </button>
    );
};

export default ExportButton;
