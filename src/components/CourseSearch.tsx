"use client";

import React, { useState, useEffect, useMemo } from 'react';
import { MagnifyingGlassIcon, FunnelIcon } from '@heroicons/react/24/outline';

interface CourseData {
  course_code: string;
  course_title: string;
  subject: string;
  level: number;
  credits?: number;
  description?: string;
  centrality_score?: number;
}

interface CourseSearchProps {
  className?: string;
  onCourseSelect?: (course: CourseData) => void;
}

export default function CourseSearch({ className = "", onCourseSelect }: CourseSearchProps) {
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedSubject, setSelectedSubject] = useState<string>('all');
  const [selectedLevel, setSelectedLevel] = useState<string>('all');
  const [courses, setCourses] = useState<CourseData[]>([]);
  const [loading, setLoading] = useState(false);
  const [showFilters, setShowFilters] = useState(false);

  // Mock course data for now - will be replaced with API call
  const mockCourses: CourseData[] = [
    { course_code: "CS 1110", course_title: "Introduction to Computing Using Python", subject: "CS", level: 1110, credits: 4 },
    { course_code: "CS 2110", course_title: "Object-Oriented Programming and Data Structures", subject: "CS", level: 2110, credits: 4 },
    { course_code: "CS 2800", course_title: "Discrete Structures", subject: "CS", level: 2800, credits: 4 },
    { course_code: "CS 3110", course_title: "Data Structures and Functional Programming", subject: "CS", level: 3110, credits: 4 },
    { course_code: "CS 4780", course_title: "Machine Learning for Intelligent Systems", subject: "CS", level: 4780, credits: 4 },
    { course_code: "MATH 1910", course_title: "Calculus for Engineers", subject: "MATH", level: 1910, credits: 4 },
    { course_code: "MATH 2930", course_title: "Differential Equations for Engineers", subject: "MATH", level: 2930, credits: 4 },
    { course_code: "ENGRD 2110", course_title: "Object-Oriented Programming and Data Structures", subject: "ENGRD", level: 2110, credits: 4 },
  ];

  useEffect(() => {
    // Simulate loading courses - replace with actual API call
    setLoading(true);
    setTimeout(() => {
      setCourses(mockCourses);
      setLoading(false);
    }, 300);
  }, []);

  // Filter and search courses
  const filteredCourses = useMemo(() => {
    return courses.filter(course => {
      // Text search
      const matchesSearch = searchQuery === '' || 
        course.course_code.toLowerCase().includes(searchQuery.toLowerCase()) ||
        course.course_title.toLowerCase().includes(searchQuery.toLowerCase()) ||
        course.description?.toLowerCase().includes(searchQuery.toLowerCase());

      // Subject filter
      const matchesSubject = selectedSubject === 'all' || course.subject === selectedSubject;

      // Level filter
      const matchesLevel = selectedLevel === 'all' || 
        Math.floor(course.level / 1000) * 1000 === parseInt(selectedLevel);

      return matchesSearch && matchesSubject && matchesLevel;
    });
  }, [courses, searchQuery, selectedSubject, selectedLevel]);

  // Get unique subjects and levels for filters
  const subjects = useMemo(() => {
    const subjectSet = new Set(courses.map(course => course.subject));
    return Array.from(subjectSet).sort();
  }, [courses]);

  const levels = useMemo(() => {
    const levelSet = new Set(courses.map(course => Math.floor(course.level / 1000) * 1000));
    return Array.from(levelSet).sort();
  }, [courses]);

  const handleCourseClick = (course: CourseData) => {
    if (onCourseSelect) {
      onCourseSelect(course);
    }
  };

  return (
    <div className={`${className}`}>
      <div className="bg-white rounded-lg shadow-sm border">
        {/* Header */}
        <div className="p-6 border-b">
          <h2 className="text-xl font-bold text-gray-900 mb-4">
            Course Search
          </h2>
          
          {/* Search Bar */}
          <div className="relative mb-4">
            <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
              <MagnifyingGlassIcon className="h-5 w-5 text-gray-400" />
            </div>
            <input
              type="text"
              placeholder="Search courses by code, title, or description..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="block w-full pl-10 pr-3 py-2 border border-gray-300 rounded-md leading-5 bg-white placeholder-gray-500 focus:outline-none focus:placeholder-gray-400 focus:ring-1 focus:ring-blue-500 focus:border-blue-500"
            />
          </div>

          {/* Filter Toggle */}
          <button
            onClick={() => setShowFilters(!showFilters)}
            className="flex items-center space-x-2 text-sm text-gray-600 hover:text-gray-900 transition-colors"
          >
            <FunnelIcon className="h-4 w-4" />
            <span>Filters</span>
            {(selectedSubject !== 'all' || selectedLevel !== 'all') && (
              <span className="px-2 py-1 text-xs bg-blue-100 text-blue-800 rounded-full">
                Active
              </span>
            )}
          </button>

          {/* Filters */}
          {showFilters && (
            <div className="mt-4 p-4 bg-gray-50 rounded-lg border">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Subject
                  </label>
                  <select
                    value={selectedSubject}
                    onChange={(e) => setSelectedSubject(e.target.value)}
                    className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500 focus:border-blue-500"
                  >
                    <option value="all">All Subjects</option>
                    {subjects.map(subject => (
                      <option key={subject} value={subject}>{subject}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Course Level
                  </label>
                  <select
                    value={selectedLevel}
                    onChange={(e) => setSelectedLevel(e.target.value)}
                    className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500 focus:border-blue-500"
                  >
                    <option value="all">All Levels</option>
                    {levels.map(level => (
                      <option key={level} value={level.toString()}>
                        {level}-level ({level === 1000 ? 'Introductory' : 
                         level === 2000 ? 'Intermediate' : 
                         level === 3000 ? 'Advanced' : 'Graduate'})
                      </option>
                    ))}
                  </select>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Results */}
        <div className="p-6">
          <div className="flex justify-between items-center mb-4">
            <h3 className="text-lg font-medium text-gray-900">
              Search Results
            </h3>
            <span className="text-sm text-gray-500">
              {filteredCourses.length} course{filteredCourses.length !== 1 ? 's' : ''} found
            </span>
          </div>

          {loading ? (
            <div className="space-y-3">
              {[...Array(5)].map((_, i) => (
                <div key={i} className="animate-pulse">
                  <div className="h-16 bg-gray-100 rounded"></div>
                </div>
              ))}
            </div>
          ) : (
            <div className="space-y-3">
              {filteredCourses.length === 0 ? (
                <div className="text-center py-8 text-gray-500">
                  <MagnifyingGlassIcon className="h-12 w-12 mx-auto mb-2 text-gray-300" />
                  <p>No courses found matching your criteria</p>
                  <p className="text-sm">Try adjusting your search or filters</p>
                </div>
              ) : (
                filteredCourses.map((course) => (
                  <div
                    key={course.course_code}
                    onClick={() => handleCourseClick(course)}
                    className="p-4 border border-gray-200 rounded-lg hover:border-blue-300 hover:shadow-md transition-all cursor-pointer"
                  >
                    <div className="flex items-start justify-between">
                      <div className="flex-1">
                        <div className="flex items-center space-x-2 mb-1">
                          <code className="text-sm font-mono bg-gray-100 px-2 py-1 rounded">
                            {course.course_code}
                          </code>
                          <span className="text-xs text-gray-500">
                            {course.subject} • {course.level}-level
                          </span>
                          {course.credits && (
                            <span className="text-xs text-gray-500">
                              • {course.credits} credits
                            </span>
                          )}
                        </div>
                        <h4 className="font-medium text-gray-900 mb-1">
                          {course.course_title}
                        </h4>
                        {course.description && (
                          <p className="text-sm text-gray-600 line-clamp-2">
                            {course.description}
                          </p>
                        )}
                      </div>
                      <div className="ml-4 text-right">
                        <button className="text-blue-600 hover:text-blue-700 text-sm font-medium">
                          View Details →
                        </button>
                      </div>
                    </div>
                  </div>
                ))
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}