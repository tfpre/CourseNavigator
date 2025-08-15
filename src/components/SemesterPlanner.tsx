"use client";

import React, { useState, useCallback, useMemo } from 'react';
import { DndProvider, useDrag, useDrop } from 'react-dnd';
import { HTML5Backend } from 'react-dnd-html5-backend';
import {
  StudentProfile,
  SemesterPlan,
  PlannedCourse,
  PlanningConflict,
  GraduationPath,
  CourseRecommendation
} from '../../types/academic-planning';

interface SemesterPlannerProps {
  student: StudentProfile;
  onPlanChange: (plans: SemesterPlan[]) => void;
  className?: string;
}

interface DraggedCourse {
  course_code: string;
  course_title: string;
  credits: number;
  source_semester?: string;
  is_recommendation?: boolean;
}

interface SemesterSlotProps {
  semester: string;
  plan: SemesterPlan;
  recommendations: CourseRecommendation[];
  onCourseDrop: (course: DraggedCourse, targetSemester: string) => void;
  onCourseRemove: (courseCode: string, semester: string) => void;
  maxCredits: number;
}

interface CourseCardProps {
  course: PlannedCourse | CourseRecommendation;
  semester?: string;
  isDragDisabled?: boolean;
  isRecommendation?: boolean;
  conflicts?: PlanningConflict[];
  onRemove?: () => void;
}

const ITEM_TYPES = {
  COURSE: 'course'
};

// Course Card Component with Drag Capability
function CourseCard({ 
  course, 
  semester, 
  isDragDisabled = false, 
  isRecommendation = false,
  conflicts = [],
  onRemove 
}: CourseCardProps) {
  const [{ isDragging }, drag] = useDrag({
    type: ITEM_TYPES.COURSE,
    item: {
      course_code: course.course_code,
      course_title: course.course_title,
      credits: 'credits' in course ? course.credits : 4,
      source_semester: semester,
      is_recommendation: isRecommendation
    } as DraggedCourse,
    canDrag: !isDragDisabled,
    collect: (monitor: any) => ({
      isDragging: monitor.isDragging(),
    }),
  });

  const hasConflicts = conflicts.length > 0;
  const isHighPriority = 'priority' in course && course.priority === 'required';
  const confidenceScore = 'confidence_score' in course ? course.confidence_score : 
                         'relevance_score' in course ? course.relevance_score : 0;

  return (
    <div
      ref={drag as any}
      className={`
        p-3 rounded-lg border cursor-grab transition-all duration-200
        ${isDragging ? 'opacity-50 scale-95' : 'opacity-100 scale-100'}
        ${hasConflicts ? 'border-red-300 bg-red-50' : isRecommendation ? 'border-blue-300 bg-blue-50' : 'border-gray-300 bg-white'}
        ${isHighPriority ? 'border-l-4 border-l-orange-400' : ''}
        hover:shadow-md hover:border-gray-400
        ${isDragDisabled ? 'cursor-not-allowed opacity-60' : ''}
      `}
    >
      <div className="flex items-start justify-between">
        <div className="flex-1 min-w-0">
          <div className="flex items-center space-x-2 mb-1">
            <code className="text-xs font-mono bg-gray-100 px-2 py-1 rounded">
              {course.course_code}
            </code>
            {'credits' in course && (
              <span className="text-xs text-gray-500">{course.credits} cr</span>
            )}
            {isHighPriority && (
              <span className="text-xs bg-orange-100 text-orange-800 px-2 py-1 rounded-full">
                Required
              </span>
            )}
            {isRecommendation && (
              <span className="text-xs bg-blue-100 text-blue-800 px-2 py-1 rounded-full">
                Suggested
              </span>
            )}
          </div>
          
          <h4 className="text-sm font-medium text-gray-900 truncate mb-1">
            {course.course_title}
          </h4>
          
          {confidenceScore > 0 && (
            <div className="flex items-center space-x-2 mb-2">
              <div className="w-16 bg-gray-200 rounded-full h-1.5">
                <div 
                  className="bg-blue-600 h-1.5 rounded-full transition-all duration-300"
                  style={{ width: `${Math.min(confidenceScore * 100, 100)}%` }}
                ></div>
              </div>
              <span className="text-xs text-gray-500">
                {Math.round(confidenceScore * 100)}% match
              </span>
            </div>
          )}

          {/* Conflicts Display */}
          {hasConflicts && (
            <div className="space-y-1">
              {conflicts.slice(0, 2).map((conflict, idx) => (
                <div key={idx} className="text-xs text-red-700 bg-red-100 px-2 py-1 rounded">
                  ⚠️ {conflict.message}
                </div>
              ))}
              {conflicts.length > 2 && (
                <div className="text-xs text-red-600">
                  +{conflicts.length - 2} more issues
                </div>
              )}
            </div>
          )}

          {/* Recommendation Reasons */}
          {isRecommendation && 'recommendation_reasons' in course && (
            <div className="mt-2 space-y-1">
              {course.recommendation_reasons.slice(0, 1).map((reason, idx) => (
                <div key={idx} className="text-xs text-blue-700 bg-blue-100 px-2 py-1 rounded">
                  💡 {reason.description}
                </div>
              ))}
            </div>
          )}
        </div>

        {onRemove && (
          <button
            onClick={onRemove}
            className="ml-2 text-gray-400 hover:text-red-600 transition-colors p-1"
            title="Remove course"
          >
            ×
          </button>
        )}
      </div>
    </div>
  );
}

// Semester Slot Component with Drop Capability
function SemesterSlot({ 
  semester, 
  plan, 
  recommendations, 
  onCourseDrop, 
  onCourseRemove, 
  maxCredits 
}: SemesterSlotProps) {
  const [{ isOver, canDrop }, drop] = useDrop({
    accept: ITEM_TYPES.COURSE,
    drop: (item: DraggedCourse) => {
      onCourseDrop(item, semester);
    },
    canDrop: (item: DraggedCourse) => {
      // Don't allow dropping on same semester
      return item.source_semester !== semester;
    },
    collect: (monitor: any) => ({
      isOver: monitor.isOver(),
      canDrop: monitor.canDrop(),
    }),
  });

  const creditUtilization = plan.total_credits / maxCredits;
  const isOverloaded = plan.total_credits > maxCredits;
  const semesterRecommendations = recommendations.filter(rec => 
    rec.recommended_semester === semester || 
    rec.alternative_semesters.includes(semester)
  );

  return (
    <div className="bg-white rounded-lg border shadow-sm">
      {/* Semester Header */}
      <div className="p-4 border-b bg-gray-50 rounded-t-lg">
        <div className="flex items-center justify-between">
          <h3 className="text-lg font-semibold text-gray-900">{semester}</h3>
          <div className="flex items-center space-x-3">
            <div className="text-sm text-gray-600">
              {plan.total_credits}/{maxCredits} credits
            </div>
            <div className="w-20 bg-gray-200 rounded-full h-2">
              <div 
                className={`h-2 rounded-full transition-all duration-300 ${
                  isOverloaded ? 'bg-red-500' : 
                  creditUtilization > 0.8 ? 'bg-yellow-500' : 'bg-green-500'
                }`}
                style={{ width: `${Math.min(creditUtilization * 100, 100)}%` }}
              ></div>
            </div>
          </div>
        </div>
        
        {/* Workload and Conflicts Summary */}
        <div className="mt-2 flex items-center justify-between text-sm">
          <div className="flex items-center space-x-4">
            <span className={`px-2 py-1 rounded text-xs ${
              plan.estimated_workload <= 5 ? 'bg-green-100 text-green-800' :
              plan.estimated_workload <= 7 ? 'bg-yellow-100 text-yellow-800' :
              'bg-red-100 text-red-800'
            }`}>
              Workload: {plan.estimated_workload}/10
            </span>
            
            {plan.conflicts.length > 0 && (
              <span className="px-2 py-1 rounded text-xs bg-red-100 text-red-800">
                {plan.conflicts.length} conflict{plan.conflicts.length !== 1 ? 's' : ''}
              </span>
            )}
            
            {plan.warnings.length > 0 && (
              <span className="px-2 py-1 rounded text-xs bg-yellow-100 text-yellow-800">
                {plan.warnings.length} warning{plan.warnings.length !== 1 ? 's' : ''}
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Drop Zone */}
      <div
        ref={drop as any}
        className={`p-4 min-h-[300px] transition-colors duration-200 ${
          isOver && canDrop ? 'bg-blue-50 border-blue-300' : 
          isOver && !canDrop ? 'bg-red-50 border-red-300' : 
          'bg-white'
        }`}
      >
        {/* Enrolled Courses */}
        <div className="space-y-3 mb-6">
          {plan.courses.map((course) => {
            const courseConflicts = plan.conflicts.filter(c => 
              c.affected_courses.includes(course.course_code)
            );
            
            return (
              <CourseCard
                key={course.course_code}
                course={course}
                semester={semester}
                conflicts={courseConflicts}
                onRemove={() => onCourseRemove(course.course_code, semester)}
              />
            );
          })}
        </div>

        {/* Course Recommendations */}
        {semesterRecommendations.length > 0 && (
          <div>
            <h4 className="text-sm font-medium text-gray-700 mb-3 flex items-center">
              💡 Recommended Courses
              <span className="ml-2 text-xs text-gray-500">
                ({semesterRecommendations.length})
              </span>
            </h4>
            <div className="space-y-2">
              {semesterRecommendations.slice(0, 3).map((rec) => (
                <CourseCard
                  key={rec.course_code}
                  course={rec}
                  isRecommendation={true}
                />
              ))}
              {semesterRecommendations.length > 3 && (
                <div className="text-xs text-gray-500 text-center py-2">
                  +{semesterRecommendations.length - 3} more recommendations
                </div>
              )}
            </div>
          </div>
        )}

        {/* Empty State */}
        {plan.courses.length === 0 && semesterRecommendations.length === 0 && (
          <div className="text-center text-gray-400 py-12">
            <div className="text-4xl mb-2">📚</div>
            <p>Drop courses here or view recommendations</p>
            <p className="text-sm">Drag from other semesters or recommendations</p>
          </div>
        )}
      </div>
    </div>
  );
}

// Main Semester Planner Component
export default function SemesterPlanner({ 
  student, 
  onPlanChange, 
  className = "" 
}: SemesterPlannerProps) {
  // Mock initial data - in production, would load from API
  const [semesterPlans, setSemesterPlans] = useState<SemesterPlan[]>([
    {
      student_id: student.id,
      semester: "Fall 2025",
      courses: [
        {
          course_code: "CS 2110",
          course_title: "Object-Oriented Programming and Data Structures",
          intended_semester: "Fall 2025",
          credits: 4,
          priority: "required",
          confidence_score: 0.9,
          alternative_courses: ["ENGRD 2110"],
          notes: "Core CS requirement"
        },
        {
          course_code: "MATH 2930",
          course_title: "Differential Equations for Engineers",
          intended_semester: "Fall 2025",
          credits: 4,
          priority: "required",
          confidence_score: 0.8,
          alternative_courses: [],
          notes: "Math requirement"
        }
      ],
      total_credits: 8,
      estimated_workload: 6,
      conflicts: [],
      warnings: [],
      recommendations: ["Consider adding an elective to reach 12+ credits"],
      created_at: new Date().toISOString(),
      last_modified: new Date().toISOString(),
      version: 1,
      is_committed: false
    },
    {
      student_id: student.id,
      semester: "Spring 2026",
      courses: [],
      total_credits: 0,
      estimated_workload: 0,
      conflicts: [],
      warnings: [],
      recommendations: [],
      created_at: new Date().toISOString(),
      last_modified: new Date().toISOString(),
      version: 1,
      is_committed: false
    },
    {
      student_id: student.id,
      semester: "Fall 2026",
      courses: [],
      total_credits: 0,
      estimated_workload: 0,
      conflicts: [],
      warnings: [],
      recommendations: [],
      created_at: new Date().toISOString(),
      last_modified: new Date().toISOString(),
      version: 1,
      is_committed: false
    },
    {
      student_id: student.id,
      semester: "Spring 2027",
      courses: [],
      total_credits: 0,
      estimated_workload: 0,
      conflicts: [],
      warnings: [],
      recommendations: [],
      created_at: new Date().toISOString(),
      last_modified: new Date().toISOString(),
      version: 1,
      is_committed: false
    }
  ]);

  // Mock recommendations - in production, would come from recommendation engine
  const [recommendations] = useState<CourseRecommendation[]>([
    {
      course_code: "CS 3110",
      course_title: "Data Structures and Functional Programming",
      relevance_score: 0.9,
      difficulty_match: 0.8,
      schedule_compatibility: 0.9,
      recommendation_reasons: [{
        type: "academic_progression",
        description: "Natural next step after CS 2110",
        weight: 0.9
      }],
      potential_concerns: ["Challenging course - ensure strong CS 2110 foundation"],
      recommended_semester: "Spring 2026",
      alternative_semesters: ["Fall 2026"],
      related_courses: ["CS 2110", "CS 2800"]
    },
    {
      course_code: "CS 4780",
      course_title: "Machine Learning for Intelligent Systems",
      relevance_score: 0.85,
      difficulty_match: 0.7,
      schedule_compatibility: 0.8,
      recommendation_reasons: [{
        type: "career_alignment",
        description: "Excellent for software engineering and data science careers",
        weight: 0.85
      }],
      potential_concerns: ["Prerequisites: CS 2110, CS 2800, MATH 2930"],
      recommended_semester: "Fall 2026",
      alternative_semesters: ["Spring 2027"],
      related_courses: ["CS 2110", "CS 2800", "MATH 2930"]
    }
  ]);

  const [viewMode, setViewMode] = useState<'semester' | 'timeline'>('semester');
  const [selectedSemester, setSelectedSemester] = useState<string | null>(null);

  const maxCreditsPerSemester = student.preferences.max_credits_per_semester;

  // Handle course drag and drop
  const handleCourseDrop = useCallback((draggedCourse: DraggedCourse, targetSemester: string) => {
    setSemesterPlans(prevPlans => {
      const newPlans = [...prevPlans];
      
      // Remove from source semester if it exists
      if (draggedCourse.source_semester) {
        const sourcePlanIndex = newPlans.findIndex(p => p.semester === draggedCourse.source_semester);
        if (sourcePlanIndex >= 0) {
          newPlans[sourcePlanIndex] = {
            ...newPlans[sourcePlanIndex],
            courses: newPlans[sourcePlanIndex].courses.filter(c => c.course_code !== draggedCourse.course_code)
          };
          // Recalculate totals
          newPlans[sourcePlanIndex].total_credits = newPlans[sourcePlanIndex].courses.reduce((sum, c) => sum + c.credits, 0);
        }
      }
      
      // Add to target semester
      const targetPlanIndex = newPlans.findIndex(p => p.semester === targetSemester);
      if (targetPlanIndex >= 0) {
        const newCourse: PlannedCourse = {
          course_code: draggedCourse.course_code,
          course_title: draggedCourse.course_title,
          intended_semester: targetSemester,
          credits: draggedCourse.credits,
          priority: draggedCourse.is_recommendation ? "recommended" : "elective",
          confidence_score: 0.8,
          alternative_courses: [],
          notes: draggedCourse.is_recommendation ? "Added from recommendation" : "Moved between semesters"
        };
        
        newPlans[targetPlanIndex] = {
          ...newPlans[targetPlanIndex],
          courses: [...newPlans[targetPlanIndex].courses, newCourse]
        };
        // Recalculate totals
        newPlans[targetPlanIndex].total_credits = newPlans[targetPlanIndex].courses.reduce((sum, c) => sum + c.credits, 0);
        newPlans[targetPlanIndex].estimated_workload = Math.min(10, newPlans[targetPlanIndex].courses.length * 1.5);
      }
      
      return newPlans;
    });
  }, []);

  // Handle course removal
  const handleCourseRemove = useCallback((courseCode: string, semester: string) => {
    setSemesterPlans(prevPlans => {
      const newPlans = [...prevPlans];
      const planIndex = newPlans.findIndex(p => p.semester === semester);
      
      if (planIndex >= 0) {
        newPlans[planIndex] = {
          ...newPlans[planIndex],
          courses: newPlans[planIndex].courses.filter(c => c.course_code !== courseCode)
        };
        // Recalculate totals
        newPlans[planIndex].total_credits = newPlans[planIndex].courses.reduce((sum, c) => sum + c.credits, 0);
        newPlans[planIndex].estimated_workload = Math.min(10, newPlans[planIndex].courses.length * 1.5);
      }
      
      return newPlans;
    });
  }, []);

  // Calculate graduation overview stats
  const graduationStats = useMemo(() => {
    const totalCredits = semesterPlans.reduce((sum, plan) => sum + plan.total_credits, 0);
    const completedCredits = student.completed_courses.reduce((sum, course) => sum + course.credits, 0);
    const totalProjectedCredits = totalCredits + completedCredits;
    const creditsNeeded = 120; // Typical bachelor's degree requirement
    
    return {
      totalProjectedCredits,
      creditsNeeded,
      creditsRemaining: Math.max(0, creditsNeeded - totalProjectedCredits),
      onTrackForGraduation: totalProjectedCredits >= creditsNeeded,
      averageCreditsPerSemester: totalCredits / semesterPlans.length,
      semestersWithCourses: semesterPlans.filter(p => p.courses.length > 0).length
    };
  }, [semesterPlans, student.completed_courses]);

  // Notify parent component of changes
  React.useEffect(() => {
    onPlanChange(semesterPlans);
  }, [semesterPlans, onPlanChange]);

  return (
    <DndProvider backend={HTML5Backend}>
      <div className={`${className}`}>
        {/* Header with Controls */}
        <div className="mb-6 p-6 bg-white rounded-lg shadow-sm border">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-2xl font-bold text-gray-900">Semester Planner</h2>
            <div className="flex items-center space-x-4">
              <div className="flex bg-gray-100 rounded-lg">
                <button
                  onClick={() => setViewMode('semester')}
                  className={`px-4 py-2 text-sm font-medium rounded-l-lg transition-colors ${
                    viewMode === 'semester' ? 'bg-blue-600 text-white' : 'text-gray-700 hover:text-gray-900'
                  }`}
                >
                  Semester View
                </button>
                <button
                  onClick={() => setViewMode('timeline')}
                  className={`px-4 py-2 text-sm font-medium rounded-r-lg transition-colors ${
                    viewMode === 'timeline' ? 'bg-blue-600 text-white' : 'text-gray-700 hover:text-gray-900'
                  }`}
                >
                  Timeline View
                </button>
              </div>
              
              <button className="px-4 py-2 bg-green-600 text-white text-sm font-medium rounded-lg hover:bg-green-700 transition-colors">
                Generate Optimal Plan
              </button>
            </div>
          </div>

          {/* Graduation Progress Overview */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
            <div className="p-3 bg-blue-50 rounded-lg">
              <div className="text-blue-600 font-medium">Total Credits</div>
              <div className="text-xl font-bold text-blue-900">
                {graduationStats.totalProjectedCredits}/{graduationStats.creditsNeeded}
              </div>
            </div>
            
            <div className="p-3 bg-green-50 rounded-lg">
              <div className="text-green-600 font-medium">Graduation Status</div>
              <div className={`text-xl font-bold ${
                graduationStats.onTrackForGraduation ? 'text-green-900' : 'text-yellow-900'
              }`}>
                {graduationStats.onTrackForGraduation ? 'On Track' : 'Need Planning'}
              </div>
            </div>
            
            <div className="p-3 bg-orange-50 rounded-lg">
              <div className="text-orange-600 font-medium">Avg Credits/Semester</div>
              <div className="text-xl font-bold text-orange-900">
                {graduationStats.averageCreditsPerSemester.toFixed(1)}
              </div>
            </div>
            
            <div className="p-3 bg-purple-50 rounded-lg">
              <div className="text-purple-600 font-medium">Planned Semesters</div>
              <div className="text-xl font-bold text-purple-900">
                {graduationStats.semestersWithCourses}/{semesterPlans.length}
              </div>
            </div>
          </div>
        </div>

        {/* Semester Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {semesterPlans.map((plan, index) => (
            <SemesterSlot
              key={plan.semester}
              semester={plan.semester}
              plan={plan}
              recommendations={recommendations}
              onCourseDrop={handleCourseDrop}
              onCourseRemove={handleCourseRemove}
              maxCredits={maxCreditsPerSemester}
            />
          ))}
        </div>

        {/* Action Buttons */}
        <div className="mt-8 flex justify-center space-x-4">
          <button className="px-6 py-3 bg-blue-600 text-white font-medium rounded-lg hover:bg-blue-700 transition-colors">
            Save Plan
          </button>
          <button className="px-6 py-3 border border-gray-300 text-gray-700 font-medium rounded-lg hover:bg-gray-50 transition-colors">
            Export to Calendar
          </button>
          <button className="px-6 py-3 border border-gray-300 text-gray-700 font-medium rounded-lg hover:bg-gray-50 transition-colors">
            Share with Advisor
          </button>
        </div>
      </div>
    </DndProvider>
  );
}