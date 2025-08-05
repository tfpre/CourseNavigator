"use client";

import React, { useState } from 'react';
import { useCentralityAPI } from '../hooks/useAPI';

interface CourseRanking {
  course_code: string;
  course_title: string;
  centrality_score: number;
  rank: number;
  subject: string;
  level: number;
}

interface CentralityData {
  most_central_courses: CourseRanking[];
  bridge_courses: CourseRanking[];
  gateway_courses: CourseRanking[];
  analysis_metadata: {
    total_courses: number;
    total_prerequisites: number;
    analysis_time_seconds: number;
  };
}

interface CourseRankingsProps {
  className?: string;
}

export default function CourseRankings({ className = "" }: CourseRankingsProps) {
  const { data: centralityData, loading, error, execute: fetchCentralityData } = useCentralityAPI({
    top_n: 15,
    damping_factor: 0.85,
    min_betweenness: 0.01,
    min_in_degree: 2
  });
  
  const [activeTab, setActiveTab] = useState<'central' | 'bridge' | 'gateway'>('central');

  const formatScore = (score: number, type: 'central' | 'bridge' | 'gateway') => {
    if (type === 'gateway') {
      return score.toFixed(0); // In-degree is an integer
    }
    return score.toFixed(4);
  };

  const getScoreLabel = (type: 'central' | 'bridge' | 'gateway') => {
    switch (type) {
      case 'central': return 'Foundation Score';
      case 'bridge': return 'Connection Score';
      case 'gateway': return 'Prerequisites Required';
    }
  };

  const renderCourseList = (courses: CourseRanking[], type: 'central' | 'bridge' | 'gateway') => (
    <div className="space-y-2">
      {courses.map((course, index) => (
        <div
          key={course.course_code}
          className={`p-4 rounded-lg border transition-all duration-200 hover:shadow-md ${
            index === 0 ? 'bg-yellow-50 border-yellow-200' :
            index === 1 ? 'bg-gray-50 border-gray-200' :
            index === 2 ? 'bg-orange-50 border-orange-200' :
            'bg-white border-gray-100'
          }`}
        >
          <div className="flex items-center justify-between">
            <div className="flex-1">
              <div className="flex items-center gap-2">
                <span className={`text-sm font-bold px-2 py-1 rounded-full ${
                  index === 0 ? 'bg-yellow-200 text-yellow-800' :
                  index === 1 ? 'bg-gray-200 text-gray-800' :
                  index === 2 ? 'bg-orange-200 text-orange-800' :
                  'bg-blue-100 text-blue-800'
                }`}>
                  #{course.rank}
                </span>
                <code className="text-sm font-mono bg-gray-100 px-2 py-1 rounded">
                  {course.course_code}
                </code>
                <span className="text-xs text-gray-500">
                  {course.subject} {course.level}
                </span>
              </div>
              <h3 className="font-medium text-gray-900 mt-1 leading-tight">
                {course.course_title}
              </h3>
            </div>
            <div className="text-right ml-4">
              <div className="text-sm text-gray-500">{getScoreLabel(type)}</div>
              <div className="text-lg font-bold text-gray-900">
                {formatScore(course.centrality_score, type)}
              </div>
            </div>
          </div>
        </div>
      ))}
    </div>
  );

  const getTabDescription = (type: 'central' | 'bridge' | 'gateway') => {
    switch (type) {
      case 'central':
        return "Foundation courses that unlock many advanced classes - prioritize these early in your academic journey";
      case 'bridge':
        return "Interdisciplinary courses that connect different fields - great for double majors and broad learning";
      case 'gateway':
        return "Advanced capstone courses that require significant preparation - plan your prerequisite path carefully";
    }
  };

  if (loading) {
    return (
      <div className={`${className}`}>
        <div className="bg-white rounded-lg shadow-sm border p-6">
          <div className="animate-pulse">
            <div className="h-6 bg-gray-200 rounded w-1/3 mb-4"></div>
            <div className="space-y-3">
              {[...Array(5)].map((_, i) => (
                <div key={i} className="h-16 bg-gray-100 rounded"></div>
              ))}
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className={`${className}`}>
        <div className="bg-white rounded-lg shadow-sm border p-6">
          <div className="text-center">
            <div className="text-red-600 mb-2">⚠️ Error Loading Course Rankings</div>
            <p className="text-gray-600 mb-4">{error}</p>
            <button
              onClick={fetchCentralityData}
              className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 transition-colors"
            >
              Retry
            </button>
          </div>
        </div>
      </div>
    );
  }

  if (!centralityData) {
    return null;
  }

  return (
    <div className={`${className}`}>
      <div className="bg-white rounded-lg shadow-sm border">
        {/* Header */}
        <div className="p-6 border-b">
          <h2 className="text-xl font-bold text-gray-900 mb-2">
            Smart Course Recommendations
          </h2>
          <p className="text-gray-600 text-sm">
            AI-powered analysis of {centralityData.analysis_metadata?.total_courses || 0} Cornell courses to help you plan your academic journey
          </p>
        </div>

        {/* Tabs */}
        <div className="border-b">
          <nav className="flex">
            {[
              { id: 'central', label: 'Foundation Courses', count: centralityData.most_central_courses?.length || 0 },
              { id: 'bridge', label: 'Bridge Courses', count: centralityData.bridge_courses?.length || 0 },
              { id: 'gateway', label: 'Capstone Courses', count: centralityData.gateway_courses?.length || 0 }
            ].map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id as any)}
                className={`px-6 py-3 text-sm font-medium border-b-2 transition-colors ${
                  activeTab === tab.id
                    ? 'border-blue-500 text-blue-600 bg-blue-50'
                    : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                }`}
              >
                {tab.label}
                <span className="ml-2 px-2 py-1 text-xs bg-gray-100 text-gray-600 rounded-full">
                  {tab.count}
                </span>
              </button>
            ))}
          </nav>
        </div>

        {/* Tab Content */}
        <div className="p-6">
          <div className="mb-4">
            <p className="text-gray-600 text-sm">
              {getTabDescription(activeTab)}
            </p>
          </div>

          {activeTab === 'central' && renderCourseList(centralityData.most_central_courses || [], 'central')}
          {activeTab === 'bridge' && renderCourseList(centralityData.bridge_courses || [], 'bridge')}
          {activeTab === 'gateway' && renderCourseList(centralityData.gateway_courses || [], 'gateway')}
        </div>

        {/* Footer */}
        <div className="px-6 py-4 bg-gray-50 rounded-b-lg border-t">
          <div className="flex justify-between items-center text-sm text-gray-500">
            <span>
              💡 Tip: Use Foundation courses to unlock advanced classes, Bridge courses for interdisciplinary learning
            </span>
            <button
              onClick={fetchCentralityData}
              disabled={loading}
              className="px-3 py-1 text-blue-600 hover:text-blue-700 transition-colors disabled:opacity-50"
            >
              Refresh
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}