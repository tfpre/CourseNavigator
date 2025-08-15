"use client";

import React, { useState, useMemo } from 'react';

interface PrerequisiteCheckResult {
  can_take: boolean;
  missing_prerequisites: string[];
  satisfied_prerequisites: string[];
  alternative_paths?: string[][];
  recommendations: string[];
  details: {
    target_course: string;
    target_title: string;
    total_prerequisites: number;
    satisfied_count: number;
    missing_count: number;
  };
}

interface PrerequisiteCheckerProps {
  className?: string;
}

export default function PrerequisiteChecker({ className = "" }: PrerequisiteCheckerProps) {
  const [targetCourse, setTargetCourse] = useState('');
  const [completedCourses, setCompletedCourses] = useState<string[]>([]);
  const [inProgressCourses, setInProgressCourses] = useState<string[]>([]);
  const [newCompletedCourse, setNewCompletedCourse] = useState('');
  const [newInProgressCourse, setNewInProgressCourse] = useState('');
  const [checkResult, setCheckResult] = useState<PrerequisiteCheckResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Common courses for autocomplete suggestions
  const commonCourses = [
    'CS 1110', 'CS 2110', 'CS 2800', 'CS 3110', 'CS 4780', 'CS 4820',
    'MATH 1910', 'MATH 2930', 'ENGRD 2110', 'PHYS 2213', 'CHEM 2090'
  ];

  const handleAddCompletedCourse = () => {
    if (newCompletedCourse.trim() && !completedCourses.includes(newCompletedCourse.trim())) {
      setCompletedCourses([...completedCourses, newCompletedCourse.trim()]);
      setNewCompletedCourse('');
    }
  };

  const handleAddInProgressCourse = () => {
    if (newInProgressCourse.trim() && !inProgressCourses.includes(newInProgressCourse.trim())) {
      setInProgressCourses([...inProgressCourses, newInProgressCourse.trim()]);
      setNewInProgressCourse('');
    }
  };

  const handleRemoveCompletedCourse = (course: string) => {
    setCompletedCourses(completedCourses.filter(c => c !== course));
  };

  const handleRemoveInProgressCourse = (course: string) => {
    setInProgressCourses(inProgressCourses.filter(c => c !== course));
  };

  const handleCheckPrerequisites = async () => {
    if (!targetCourse.trim()) {
      setError('Please enter a target course');
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const response = await fetch('/api/prerequisite-check', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          target_course: targetCourse,
          completed_courses: completedCourses,
          in_progress_courses: inProgressCourses,
        }),
      });

      const result = await response.json();
      
      if (!result.success) {
        setError(result.error?.message || 'Failed to check prerequisites');
        setCheckResult(null);
        return;
      }

      setCheckResult(result.data);
    } catch (err) {
      setError('Network error - please try again');
      setCheckResult(null);
    } finally {
      setLoading(false);
    }
  };

  const canCheck = targetCourse.trim().length > 0;

  return (
    <div className={`${className}`}>
      <div className="bg-white rounded-lg shadow-sm border">
        {/* Header */}
        <div className="p-6 border-b">
          <h2 className="text-xl font-bold text-gray-900 mb-2">
            Prerequisite Checker
          </h2>
          <p className="text-gray-600 text-sm">
            Check if you can take a course based on your completed and in-progress courses
          </p>
        </div>

        <div className="p-6 space-y-6">
          {/* Target Course Input */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Course you want to take
            </label>
            <input
              type="text"
              placeholder="e.g., CS 4780, MATH 2930"
              value={targetCourse}
              onChange={(e) => setTargetCourse(e.target.value)}
              className="w-full border border-gray-300 rounded-md px-3 py-2 focus:outline-none focus:ring-1 focus:ring-blue-500 focus:border-blue-500"
            />
            <div className="mt-2 flex flex-wrap gap-2">
              {commonCourses.slice(0, 6).map(course => (
                <button
                  key={course}
                  onClick={() => setTargetCourse(course)}
                  className="px-2 py-1 text-xs bg-gray-100 text-gray-700 rounded hover:bg-gray-200 transition-colors"
                >
                  {course}
                </button>
              ))}
            </div>
          </div>

          {/* Completed Courses */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Completed courses
            </label>
            <div className="flex space-x-2 mb-2">
              <input
                type="text"
                placeholder="Add completed course"
                value={newCompletedCourse}
                onChange={(e) => setNewCompletedCourse(e.target.value)}
                onKeyPress={(e) => e.key === 'Enter' && handleAddCompletedCourse()}
                className="flex-1 border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500 focus:border-blue-500"
              />
              <button
                onClick={handleAddCompletedCourse}
                className="px-4 py-2 bg-green-600 text-white text-sm rounded-md hover:bg-green-700 transition-colors"
              >
                Add
              </button>
            </div>
            <div className="flex flex-wrap gap-2">
              {completedCourses.map(course => (
                <span
                  key={course}
                  className="inline-flex items-center px-3 py-1 text-sm bg-green-100 text-green-800 rounded-full"
                >
                  ✅ {course}
                  <button
                    onClick={() => handleRemoveCompletedCourse(course)}
                    className="ml-2 text-green-600 hover:text-green-800"
                  >
                    ×
                  </button>
                </span>
              ))}
            </div>
          </div>

          {/* In Progress Courses */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Currently taking (optional)
            </label>
            <div className="flex space-x-2 mb-2">
              <input
                type="text"
                placeholder="Add current course"
                value={newInProgressCourse}
                onChange={(e) => setNewInProgressCourse(e.target.value)}
                onKeyPress={(e) => e.key === 'Enter' && handleAddInProgressCourse()}
                className="flex-1 border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500 focus:border-blue-500"
              />
              <button
                onClick={handleAddInProgressCourse}
                className="px-4 py-2 bg-blue-600 text-white text-sm rounded-md hover:bg-blue-700 transition-colors"
              >
                Add
              </button>
            </div>
            <div className="flex flex-wrap gap-2">
              {inProgressCourses.map(course => (
                <span
                  key={course}
                  className="inline-flex items-center px-3 py-1 text-sm bg-blue-100 text-blue-800 rounded-full"
                >
                  📚 {course}
                  <button
                    onClick={() => handleRemoveInProgressCourse(course)}
                    className="ml-2 text-blue-600 hover:text-blue-800"
                  >
                    ×
                  </button>
                </span>
              ))}
            </div>
          </div>

          {/* Check Button */}
          <div>
            <button
              onClick={handleCheckPrerequisites}
              disabled={!canCheck || loading}
              className="w-full px-4 py-3 bg-blue-600 text-white font-medium rounded-md hover:bg-blue-700 transition-colors disabled:bg-gray-300 disabled:cursor-not-allowed"
            >
              {loading ? 'Checking...' : 'Check Prerequisites'}
            </button>
          </div>

          {/* Error Display */}
          {error && (
            <div className="p-4 bg-red-50 border border-red-200 rounded-md">
              <p className="text-red-800 text-sm">❌ {error}</p>
            </div>
          )}

          {/* Results */}
          {checkResult && (
            <div className="space-y-4">
              {/* Main Result */}
              <div className={`p-4 rounded-md border ${
                checkResult.can_take 
                  ? 'bg-green-50 border-green-200' 
                  : 'bg-yellow-50 border-yellow-200'
              }`}>
                <div className="flex items-start space-x-3">
                  <div className="text-2xl">
                    {checkResult.can_take ? '✅' : '⚠️'}
                  </div>
                  <div>
                    <h3 className={`font-medium ${
                      checkResult.can_take ? 'text-green-800' : 'text-yellow-800'
                    }`}>
                      {checkResult.details.target_course}: {checkResult.details.target_title}
                    </h3>
                    <p className={`text-sm mt-1 ${
                      checkResult.can_take ? 'text-green-700' : 'text-yellow-700'
                    }`}>
                      {checkResult.can_take 
                        ? 'You can take this course!' 
                        : `Missing ${checkResult.details.missing_count} prerequisite${checkResult.details.missing_count !== 1 ? 's' : ''}`
                      }
                    </p>
                  </div>
                </div>
              </div>

              {/* Prerequisites Breakdown */}
              {checkResult.details.total_prerequisites > 0 && (
                <div className="p-4 bg-gray-50 rounded-md border">
                  <h4 className="font-medium text-gray-900 mb-3">Prerequisites Breakdown</h4>
                  
                  {checkResult.satisfied_prerequisites.length > 0 && (
                    <div className="mb-3">
                      <p className="text-sm font-medium text-green-700 mb-1">✅ Satisfied:</p>
                      <div className="flex flex-wrap gap-2">
                        {checkResult.satisfied_prerequisites.map(course => (
                          <span key={course} className="px-2 py-1 text-xs bg-green-100 text-green-800 rounded">
                            {course}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}

                  {checkResult.missing_prerequisites.length > 0 && (
                    <div>
                      <p className="text-sm font-medium text-red-700 mb-1">❌ Missing:</p>
                      <div className="flex flex-wrap gap-2">
                        {checkResult.missing_prerequisites.map(course => (
                          <span key={course} className="px-2 py-1 text-xs bg-red-100 text-red-800 rounded">
                            {course}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* Recommendations */}
              <div className="p-4 bg-blue-50 rounded-md border border-blue-200">
                <h4 className="font-medium text-blue-900 mb-2">💡 Recommendations</h4>
                <ul className="space-y-1">
                  {checkResult.recommendations.map((rec, index) => (
                    <li key={index} className="text-sm text-blue-800">
                      {rec}
                    </li>
                  ))}
                </ul>
              </div>

              {/* Alternative Paths */}
              {checkResult.alternative_paths && checkResult.alternative_paths.length > 0 && (
                <div className="p-4 bg-purple-50 rounded-md border border-purple-200">
                  <h4 className="font-medium text-purple-900 mb-2">🔄 Alternative Options</h4>
                  {checkResult.alternative_paths.map((path, index) => (
                    <p key={index} className="text-sm text-purple-800">
                      You can take any of: {path.join(' or ')}
                    </p>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}