import { NextRequest, NextResponse } from 'next/server';

interface PrerequisiteCheckRequest {
  target_course: string;
  completed_courses: string[];
  in_progress_courses?: string[];
}

interface PrerequisiteCheckResponse {
  success: boolean;
  data?: {
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
  };
  error?: {
    code: string;
    message: string;
  };
}

// Mock prerequisite data - replace with actual API calls
const MOCK_PREREQUISITES: Record<string, string[]> = {
  "CS 2110": ["CS 1110"],
  "CS 2800": ["CS 1110", "MATH 1910"],
  "CS 3110": ["CS 2110", "CS 2800"],
  "CS 4780": ["CS 2110", "CS 2800", "MATH 2930"],
  "CS 4820": ["CS 2110", "CS 2800", "CS 3110"],
  "MATH 2930": ["MATH 1910"],
  "ENGRD 2110": [], // Cross-listed with CS 2110
};

const MOCK_COURSE_TITLES: Record<string, string> = {
  "CS 1110": "Introduction to Computing Using Python",
  "CS 2110": "Object-Oriented Programming and Data Structures",
  "CS 2800": "Discrete Structures", 
  "CS 3110": "Data Structures and Functional Programming",
  "CS 4780": "Machine Learning for Intelligent Systems",
  "CS 4820": "Introduction to Analysis of Algorithms",
  "MATH 1910": "Calculus for Engineers",
  "MATH 2930": "Differential Equations for Engineers",
  "ENGRD 2110": "Object-Oriented Programming and Data Structures",
};

// Cross-listing equivalences
const COURSE_EQUIVALENCES: Record<string, string[]> = {
  "CS 2110": ["ENGRD 2110"],
  "ENGRD 2110": ["CS 2110"],
};

function normalizeCourseCode(courseCode: string): string {
  return courseCode.trim().toUpperCase();
}

function getEquivalentCourses(courseCode: string): string[] {
  const normalized = normalizeCourseCode(courseCode);
  return COURSE_EQUIVALENCES[normalized] || [];
}

function checkPrerequisites(
  targetCourse: string,
  completedCourses: string[],
  inProgressCourses: string[] = []
): {
  canTake: boolean;
  missingPrereqs: string[];
  satisfiedPrereqs: string[];
  alternativePaths: string[][];
} {
  const normalizedTarget = normalizeCourseCode(targetCourse);
  const normalizedCompleted = completedCourses.map(normalizeCourseCode);
  const normalizedInProgress = inProgressCourses.map(normalizeCourseCode);
  
  // Get all completed and in-progress courses including equivalences
  const allCompletedEquivalents = new Set<string>();
  normalizedCompleted.forEach(course => {
    allCompletedEquivalents.add(course);
    getEquivalentCourses(course).forEach(equiv => allCompletedEquivalents.add(equiv));
  });
  
  const allInProgressEquivalents = new Set<string>();
  normalizedInProgress.forEach(course => {
    allInProgressEquivalents.add(course);
    getEquivalentCourses(course).forEach(equiv => allInProgressEquivalents.add(equiv));
  });

  const prerequisites = MOCK_PREREQUISITES[normalizedTarget] || [];
  const satisfiedPrereqs: string[] = [];
  const missingPrereqs: string[] = [];

  prerequisites.forEach(prereq => {
    const normalizedPrereq = normalizeCourseCode(prereq);
    
    if (allCompletedEquivalents.has(normalizedPrereq) || allInProgressEquivalents.has(normalizedPrereq)) {
      satisfiedPrereqs.push(prereq);
    } else {
      missingPrereqs.push(prereq);
    }
  });

  const canTake = missingPrereqs.length === 0;
  
  // Generate alternative paths for missing prerequisites
  const alternativePaths: string[][] = [];
  missingPrereqs.forEach(missing => {
    const equivalents = getEquivalentCourses(missing);
    if (equivalents.length > 0) {
      alternativePaths.push([missing, ...equivalents]);
    }
  });

  return { canTake, missingPrereqs, satisfiedPrereqs, alternativePaths };
}

function generateRecommendations(
  targetCourse: string,
  missingPrereqs: string[],
  completedCourses: string[]
): string[] {
  const recommendations: string[] = [];
  
  if (missingPrereqs.length === 0) {
    recommendations.push(`✅ You can take ${targetCourse}! All prerequisites are satisfied.`);
    recommendations.push("Consider reviewing the course syllabus and scheduling conflicts.");
  } else if (missingPrereqs.length === 1) {
    recommendations.push(`📚 Complete ${missingPrereqs[0]} first, then you can take ${targetCourse}.`);
    recommendations.push("This is just one course away - plan for next semester!");
  } else {
    recommendations.push(`📋 You need ${missingPrereqs.length} more prerequisites: ${missingPrereqs.join(', ')}`);
    recommendations.push("Consider planning a multi-semester sequence to complete these requirements.");
    
    // Suggest optimal ordering
    const basicPrereqs = missingPrereqs.filter(p => !MOCK_PREREQUISITES[p] || MOCK_PREREQUISITES[p].length === 0);
    if (basicPrereqs.length > 0) {
      recommendations.push(`🎯 Start with foundational courses: ${basicPrereqs.join(', ')}`);
    }
  }

  return recommendations;
}

export async function POST(request: NextRequest) {
  try {
    const body: PrerequisiteCheckRequest = await request.json();
    
    if (!body.target_course) {
      return NextResponse.json({
        success: false,
        error: {
          code: "MISSING_TARGET_COURSE",
          message: "Target course is required"
        }
      } as PrerequisiteCheckResponse, { status: 400 });
    }

    if (!Array.isArray(body.completed_courses)) {
      return NextResponse.json({
        success: false,
        error: {
          code: "INVALID_COMPLETED_COURSES",
          message: "Completed courses must be an array"
        }
      } as PrerequisiteCheckResponse, { status: 400 });
    }

    const normalizedTarget = normalizeCourseCode(body.target_course);
    
    // Check if target course exists
    if (!MOCK_COURSE_TITLES[normalizedTarget]) {
      return NextResponse.json({
        success: false,
        error: {
          code: "COURSE_NOT_FOUND", 
          message: `Course ${body.target_course} not found in catalog`
        }
      } as PrerequisiteCheckResponse, { status: 404 });
    }

    const result = checkPrerequisites(
      body.target_course,
      body.completed_courses,
      body.in_progress_courses
    );

    const recommendations = generateRecommendations(
      normalizedTarget,
      result.missingPrereqs,
      body.completed_courses
    );

    return NextResponse.json({
      success: true,
      data: {
        can_take: result.canTake,
        missing_prerequisites: result.missingPrereqs,
        satisfied_prerequisites: result.satisfiedPrereqs,
        alternative_paths: result.alternativePaths,
        recommendations,
        details: {
          target_course: normalizedTarget,
          target_title: MOCK_COURSE_TITLES[normalizedTarget],
          total_prerequisites: (MOCK_PREREQUISITES[normalizedTarget] || []).length,
          satisfied_count: result.satisfiedPrereqs.length,
          missing_count: result.missingPrereqs.length,
        }
      }
    } as PrerequisiteCheckResponse);

  } catch (error) {
    console.error('Prerequisite check error:', error);
    
    return NextResponse.json({
      success: false,
      error: {
        code: "INTERNAL_ERROR",
        message: "An error occurred while checking prerequisites"
      }
    } as PrerequisiteCheckResponse, { status: 500 });
  }
}