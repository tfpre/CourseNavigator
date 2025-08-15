import { NextRequest, NextResponse } from 'next/server';
import {
  DegreeRequirement,
  RequirementRule,
  RequirementProgress,
  AcademicPlanningResponse,
  StudentProfile,
  CompletedCourse
} from '@/types/academic-planning';

interface MajorRequirementsRequest {
  major: string;
  minor?: string;
  student_profile?: StudentProfile;
  include_progress?: boolean;
}

interface RequirementValidationResult {
  requirement_id: string;
  satisfied: boolean;
  progress: number; // 0-1
  satisfied_by: string[];
  remaining_needed: number;
  remaining_options: string[];
  notes: string[];
}

interface MajorRequirementsResponse {
  major: string;
  requirements: DegreeRequirement[];
  total_credits_required: number;
  validation_results?: RequirementValidationResult[];
  overall_progress?: number;
  estimated_graduation_semester?: string;
}

// Comprehensive CS Major Requirements Template
const CS_MAJOR_REQUIREMENTS: DegreeRequirement[] = [
  {
    id: "cs_programming_fundamentals",
    name: "Programming Fundamentals",
    description: "Core programming and data structures foundation",
    type: "major",
    requirements: [
      {
        id: "cs_intro_programming",
        name: "Introduction to Programming",
        description: "Basic programming concepts and problem solving",
        rule_type: "specific_courses",
        required_courses: ["CS 1110"],
        elective_courses: [],
        credits_required: 4,
        courses_required: 1,
        minimum_grade: "C",
        subject_constraints: [],
        level_constraints: [],
        exclusions: [],
        recommended_semester_range: [1, 2],
        prerequisites: []
      },
      {
        id: "cs_data_structures",
        name: "Data Structures and Object-Oriented Programming",
        description: "Advanced programming with data structures",
        rule_type: "course_list",
        required_courses: [],
        elective_courses: ["CS 2110", "ENGRD 2110"],
        credits_required: 4,
        courses_required: 1,
        minimum_grade: "C",
        subject_constraints: [],
        level_constraints: [],
        exclusions: [],
        recommended_semester_range: [2, 4],
        prerequisites: ["cs_intro_programming"]
      }
    ],
    total_credits_required: 8,
    minimum_gpa: 2.0
  },
  {
    id: "cs_mathematical_foundations",
    name: "Mathematical Foundations",
    description: "Mathematics required for computer science",
    type: "major",
    requirements: [
      {
        id: "discrete_mathematics",
        name: "Discrete Mathematics",
        description: "Logic, proofs, and discrete mathematical structures",
        rule_type: "specific_courses",
        required_courses: ["CS 2800"],
        elective_courses: [],
        credits_required: 4,
        courses_required: 1,
        minimum_grade: "C",
        subject_constraints: [],
        level_constraints: [],
        exclusions: [],
        recommended_semester_range: [2, 4],
        prerequisites: ["cs_intro_programming"]
      },
      {
        id: "calculus_requirement",
        name: "Calculus",
        description: "Calculus for engineering or mathematics",
        rule_type: "course_list",
        required_courses: [],
        elective_courses: ["MATH 1910", "MATH 1920", "MATH 2930"],
        credits_required: 4,
        courses_required: 1,
        minimum_grade: "C",
        subject_constraints: [],
        level_constraints: [],
        exclusions: [],
        recommended_semester_range: [1, 3],
        prerequisites: []
      }
    ],
    total_credits_required: 8,
    minimum_gpa: 2.0
  },
  {
    id: "cs_core_systems",
    name: "Core Computer Systems",
    description: "Fundamental systems and theory courses",
    type: "major",
    requirements: [
      {
        id: "functional_programming",
        name: "Functional Programming and Data Structures",
        description: "Advanced programming paradigms and algorithms",
        rule_type: "specific_courses",
        required_courses: ["CS 3110"],
        elective_courses: [],
        credits_required: 4,
        courses_required: 1,
        minimum_grade: "C",
        subject_constraints: [],
        level_constraints: [],
        exclusions: [],
        recommended_semester_range: [3, 5],
        prerequisites: ["cs_data_structures", "discrete_mathematics"]
      },
      {
        id: "computer_systems",
        name: "Computer Systems Organization",
        description: "Low-level computer systems and architecture",
        rule_type: "course_list",
        required_courses: [],
        elective_courses: ["CS 3410", "CS 4410", "ECE 4750"],
        credits_required: 4,
        courses_required: 1,
        minimum_grade: "C",
        subject_constraints: [],
        level_constraints: [],
        exclusions: [],
        recommended_semester_range: [3, 6],
        prerequisites: ["cs_data_structures"]
      }
    ],
    total_credits_required: 8,
    minimum_gpa: 2.0
  },
  {
    id: "cs_algorithms_theory",
    name: "Algorithms and Theory",
    description: "Algorithm design and analysis",
    type: "major",
    requirements: [
      {
        id: "algorithms_analysis",
        name: "Analysis of Algorithms",
        description: "Design and analysis of efficient algorithms",
        rule_type: "specific_courses",
        required_courses: ["CS 4820"],
        elective_courses: [],
        credits_required: 4,
        courses_required: 1,
        minimum_grade: "C",
        subject_constraints: [],
        level_constraints: [],
        exclusions: [],
        recommended_semester_range: [4, 7],
        prerequisites: ["functional_programming", "discrete_mathematics"]
      }
    ],
    total_credits_required: 4,
    minimum_gpa: 2.0
  },
  {
    id: "cs_technical_electives",
    name: "Technical Electives",
    description: "Advanced computer science courses for specialization",
    type: "major",
    requirements: [
      {
        id: "cs_advanced_electives",
        name: "CS Advanced Electives",
        description: "3000+ level CS courses for depth and breadth",
        rule_type: "subject_credits",
        required_courses: [],
        elective_courses: [
          "CS 4780", "CS 4700", "CS 4740", "CS 4670", "CS 4320", "CS 4620",
          "CS 4850", "CS 4787", "CS 4300", "CS 4152", "CS 4754", "CS 4756"
        ],
        credits_required: 15,
        courses_required: 4,
        minimum_grade: "C",
        subject_constraints: [
          {
            subject: "CS",
            credits_required: 15,
            minimum_level: 3000
          }
        ],
        level_constraints: [
          {
            minimum_level: 3000,
            credits_required: 15
          }
        ],
        exclusions: [],
        recommended_semester_range: [4, 8],
        prerequisites: ["functional_programming"]
      },
      {
        id: "related_technical_electives",
        name: "Related Technical Electives",
        description: "Technical courses outside CS that complement the major",
        rule_type: "level_credits",
        required_courses: [],
        elective_courses: [
          "MATH 4260", "MATH 4250", "ECE 3140", "ECE 4760", "ENGRD 2700",
          "ORIE 3150", "ORIE 3500", "PHYS 3360", "ENGRI 1280"
        ],
        credits_required: 9,
        courses_required: 3,
        minimum_grade: "C",
        subject_constraints: [],
        level_constraints: [
          {
            minimum_level: 2000,
            credits_required: 9
          }
        ],
        exclusions: [],
        recommended_semester_range: [3, 8],
        prerequisites: []
      }
    ],
    total_credits_required: 24,
    minimum_gpa: 2.0
  },
  {
    id: "liberal_studies",
    name: "Liberal Studies",
    description: "Liberal arts and social science requirements",
    type: "major",
    requirements: [
      {
        id: "liberal_studies_distribution",
        name: "Liberal Studies Distribution",
        description: "Courses outside engineering for breadth",
        rule_type: "level_credits",
        required_courses: [],
        elective_courses: [], // Would be populated with approved liberal studies courses
        credits_required: 18,
        courses_required: 6,
        minimum_grade: "D",
        subject_constraints: [],
        level_constraints: [],
        exclusions: ["CS", "ENGRD", "ENGRI", "MATH"],
        recommended_semester_range: [1, 8],
        prerequisites: []
      }
    ],
    total_credits_required: 18,
    minimum_gpa: 2.0
  }
];

// Engineering Requirements Template
const ENGINEERING_COMMON_REQUIREMENTS: DegreeRequirement[] = [
  {
    id: "engineering_foundations",
    name: "Engineering Foundations",
    description: "Core engineering and science requirements",
    type: "major",
    requirements: [
      {
        id: "engineering_intro",
        name: "Introduction to Engineering",
        description: "Engineering problem solving and design",
        rule_type: "course_list",
        required_courses: [],
        elective_courses: ["ENGRI 1101", "ENGRI 1200", "ENGRI 1280"],
        credits_required: 3,
        courses_required: 1,
        minimum_grade: "C",
        subject_constraints: [],
        level_constraints: [],
        exclusions: [],
        recommended_semester_range: [1, 2],
        prerequisites: []
      },
      {
        id: "physics_mechanics",
        name: "Physics: Mechanics",
        description: "Classical mechanics for engineers",
        rule_type: "specific_courses",
        required_courses: ["PHYS 2213"],
        elective_courses: [],
        credits_required: 4,
        courses_required: 1,
        minimum_grade: "C",
        subject_constraints: [],
        level_constraints: [],
        exclusions: [],
        recommended_semester_range: [1, 3],
        prerequisites: []
      },
      {
        id: "chemistry_requirement",
        name: "General Chemistry",
        description: "Chemistry fundamentals for engineers",
        rule_type: "course_list",
        required_courses: [],
        elective_courses: ["CHEM 2090", "CHEM 2080"],
        credits_required: 4,
        courses_required: 1,
        minimum_grade: "C",
        subject_constraints: [],
        level_constraints: [],
        exclusions: [],
        recommended_semester_range: [1, 4],
        prerequisites: []
      }
    ],
    total_credits_required: 11,
    minimum_gpa: 2.0
  }
];

/**
 * Validate student progress against major requirements
 */
function validateRequirements(
  requirements: DegreeRequirement[],
  completedCourses: CompletedCourse[],
  inProgressCourses: string[] = []
): RequirementValidationResult[] {
  const results: RequirementValidationResult[] = [];
  
  for (const degreeReq of requirements) {
    for (const rule of degreeReq.requirements) {
      const result = validateRequirementRule(rule, completedCourses, inProgressCourses);
      results.push(result);
    }
  }
  
  return results;
}

/**
 * Validate a single requirement rule
 */
function validateRequirementRule(
  rule: RequirementRule,
  completedCourses: CompletedCourse[],
  inProgressCourses: string[]
): RequirementValidationResult {
  const completedCodes = new Set(completedCourses.map(c => c.course_code));
  const inProgressCodes = new Set(inProgressCourses);
  const allCodes = new Set([...Array.from(completedCodes), ...Array.from(inProgressCodes)]);
  
  let satisfiedCourses: string[] = [];
  let creditsEarned = 0;
  let coursesCompleted = 0;
  
  // Check specific required courses
  for (const reqCourse of rule.required_courses) {
    if (completedCodes.has(reqCourse)) {
      satisfiedCourses.push(reqCourse);
      const courseData = completedCourses.find(c => c.course_code === reqCourse);
      if (courseData && meetGradeRequirement(courseData.grade, rule.minimum_grade)) {
        creditsEarned += courseData.credits;
        coursesCompleted += 1;
      }
    }
  }
  
  // Check elective courses if needed
  if (rule.elective_courses.length > 0 && coursesCompleted < rule.courses_required) {
    for (const electiveCourse of rule.elective_courses) {
      if (completedCodes.has(electiveCourse) && !satisfiedCourses.includes(electiveCourse)) {
        const courseData = completedCourses.find(c => c.course_code === electiveCourse);
        if (courseData && meetGradeRequirement(courseData.grade, rule.minimum_grade)) {
          satisfiedCourses.push(electiveCourse);
          creditsEarned += courseData.credits;
          coursesCompleted += 1;
          
          if (coursesCompleted >= rule.courses_required && creditsEarned >= rule.credits_required) {
            break;
          }
        }
      }
    }
  }
  
  // Handle subject/level constraints for broader requirements
  if ((rule.subject_constraints?.length || 0) > 0 || (rule.level_constraints?.length || 0) > 0) {
    for (const course of completedCourses) {
      if (satisfiedCourses.includes(course.course_code)) continue;
      
      let meetsConstraints = true;
      
      // Check subject constraints
      for (const constraint of rule.subject_constraints || []) {
        const courseSubject = course.course_code.split(' ')[0];
        if (courseSubject !== constraint.subject) {
          meetsConstraints = false;
          break;
        }
        
        if (constraint.minimum_level) {
          const courseLevel = parseInt(course.course_code.split(' ')[1]);
          if (courseLevel < constraint.minimum_level) {
            meetsConstraints = false;
            break;
          }
        }
      }
      
      // Check level constraints
      for (const constraint of rule.level_constraints || []) {
        const courseLevel = parseInt(course.course_code.split(' ')[1]);
        if (courseLevel < constraint.minimum_level) {
          meetsConstraints = false;
          break;
        }
        if (constraint.maximum_level && courseLevel > constraint.maximum_level) {
          meetsConstraints = false;
          break;
        }
      }
      
      // Check exclusions
      const courseSubject = course.course_code.split(' ')[0];
      if (rule.exclusions.includes(courseSubject) || rule.exclusions.includes(course.course_code)) {
        meetsConstraints = false;
      }
      
      if (meetsConstraints && meetGradeRequirement(course.grade, rule.minimum_grade)) {
        satisfiedCourses.push(course.course_code);
        creditsEarned += course.credits;
        coursesCompleted += 1;
        
        if (coursesCompleted >= rule.courses_required && creditsEarned >= rule.credits_required) {
          break;
        }
      }
    }
  }
  
  const satisfied = creditsEarned >= rule.credits_required && coursesCompleted >= rule.courses_required;
  const progress = Math.min(
    creditsEarned / rule.credits_required,
    coursesCompleted / rule.courses_required
  );
  
  const remainingCredits = Math.max(0, rule.credits_required - creditsEarned);
  const remainingCourses = Math.max(0, rule.courses_required - coursesCompleted);
  
  // Generate remaining options
  const remainingOptions = [
    ...rule.required_courses.filter((c: string) => !satisfiedCourses.includes(c)),
    ...rule.elective_courses.filter((c: string) => !satisfiedCourses.includes(c))
  ].slice(0, 10); // Limit for practical display
  
  const notes: string[] = [];
  if (remainingCredits > 0) {
    notes.push(`Need ${remainingCredits} more credits`);
  }
  if (remainingCourses > 0) {
    notes.push(`Need ${remainingCourses} more course${remainingCourses !== 1 ? 's' : ''}`);
  }
  
  return {
    requirement_id: rule.id,
    satisfied,
    progress,
    satisfied_by: satisfiedCourses,
    remaining_needed: remainingCourses,
    remaining_options: remainingOptions,
    notes
  };
}

/**
 * Check if a grade meets the minimum requirement
 */
function meetGradeRequirement(grade: string, minimumGrade?: string): boolean {
  if (!minimumGrade) return true;
  
  const gradeValues: { [grade: string]: number } = {
    "A+": 4.3, "A": 4.0, "A-": 3.7,
    "B+": 3.3, "B": 3.0, "B-": 2.7,
    "C+": 2.3, "C": 2.0, "C-": 1.7,
    "D+": 1.3, "D": 1.0, "D-": 0.7,
    "F": 0.0
  };
  
  const gradeValue = gradeValues[grade] || 0;
  const minValue = gradeValues[minimumGrade] || 0;
  
  return gradeValue >= minValue;
}

/**
 * Get major requirements template
 */
function getMajorRequirements(major: string): DegreeRequirement[] {
  switch (major.toLowerCase()) {
    case "computer science":
    case "cs":
      return CS_MAJOR_REQUIREMENTS;
    case "engineering":
    case "general engineering":
      return ENGINEERING_COMMON_REQUIREMENTS;
    default:
      // Return a generic template or empty array
      return [];
  }
}

/**
 * Calculate overall progress percentage
 */
function calculateOverallProgress(validationResults: RequirementValidationResult[]): number {
  if (validationResults.length === 0) return 0;
  
  const totalProgress = validationResults.reduce((sum, result) => sum + result.progress, 0);
  return totalProgress / validationResults.length;
}

/**
 * Estimate graduation semester based on progress and typical timeline
 */
function estimateGraduationSemester(
  student?: StudentProfile,
  overallProgress?: number
): string {
  if (!student || !overallProgress) {
    return "Spring 2027"; // Default estimate
  }
  
  const currentSemester = student.current_semester;
  const remainingProgress = 1 - overallProgress;
  const semestersRemaining = Math.ceil(remainingProgress * 8); // Assume 8 semester program
  
  // Simple semester calculation (would be more sophisticated in production)
  const currentYear = parseInt(currentSemester.split(' ')[1]);
  const isSpring = currentSemester.includes('Spring');
  
  let graduationYear = currentYear;
  let graduationSeason = isSpring ? 'Fall' : 'Spring';
  
  for (let i = 0; i < semestersRemaining; i++) {
    if (graduationSeason === 'Spring') {
      graduationSeason = 'Fall';
    } else {
      graduationSeason = 'Spring';
      graduationYear++;
    }
  }
  
  return `${graduationSeason} ${graduationYear}`;
}

/**
 * API Route Handler
 */
export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const major = searchParams.get('major');
    
    if (!major) {
      return NextResponse.json({
        success: false,
        error: {
          code: "MISSING_MAJOR",
          message: "Major parameter is required"
        }
      } as AcademicPlanningResponse<MajorRequirementsResponse>, { status: 400 });
    }
    
    const requirements = getMajorRequirements(major);
    
    if (requirements.length === 0) {
      return NextResponse.json({
        success: false,
        error: {
          code: "MAJOR_NOT_FOUND",
          message: `Requirements for major '${major}' not found`
        }
      } as AcademicPlanningResponse<MajorRequirementsResponse>, { status: 404 });
    }
    
    const totalCredits = requirements.reduce((sum, req) => sum + req.total_credits_required, 0);
    
    return NextResponse.json({
      success: true,
      data: {
        major,
        requirements,
        total_credits_required: totalCredits
      },
      metadata: {
        generated_at: new Date().toISOString(),
        version: "1.0.0",
        processing_time_ms: 0
      }
    } as AcademicPlanningResponse<MajorRequirementsResponse>);
    
  } catch (error) {
    console.error('Major requirements API error:', error);
    
    return NextResponse.json({
      success: false,
      error: {
        code: "INTERNAL_ERROR",
        message: "An error occurred while fetching major requirements"
      }
    } as AcademicPlanningResponse<MajorRequirementsResponse>, { status: 500 });
  }
}

/**
 * POST: Validate student progress against major requirements
 */
export async function POST(request: NextRequest) {
  try {
    const body: MajorRequirementsRequest = await request.json();
    
    if (!body.major) {
      return NextResponse.json({
        success: false,
        error: {
          code: "MISSING_MAJOR",
          message: "Major is required"
        }
      } as AcademicPlanningResponse<MajorRequirementsResponse>, { status: 400 });
    }
    
    const requirements = getMajorRequirements(body.major);
    
    if (requirements.length === 0) {
      return NextResponse.json({
        success: false,
        error: {
          code: "MAJOR_NOT_FOUND",
          message: `Requirements for major '${body.major}' not found`
        }
      } as AcademicPlanningResponse<MajorRequirementsResponse>, { status: 404 });
    }
    
    const totalCredits = requirements.reduce((sum, req) => sum + req.total_credits_required, 0);
    
    let validationResults: RequirementValidationResult[] | undefined;
    let overallProgress: number | undefined;
    let estimatedGraduation: string | undefined;
    
    // If student profile provided, validate progress
    if (body.student_profile && body.include_progress) {
      const completedCourses = body.student_profile.completed_courses;
      const inProgressCourses = body.student_profile.current_courses.map((c: any) => c.course_code);
      
      validationResults = validateRequirements(requirements, completedCourses, inProgressCourses);
      overallProgress = calculateOverallProgress(validationResults);
      estimatedGraduation = estimateGraduationSemester(body.student_profile, overallProgress);
    }
    
    return NextResponse.json({
      success: true,
      data: {
        major: body.major,
        requirements,
        total_credits_required: totalCredits,
        validation_results: validationResults,
        overall_progress: overallProgress,
        estimated_graduation_semester: estimatedGraduation
      },
      metadata: {
        generated_at: new Date().toISOString(),
        version: "1.0.0",
        processing_time_ms: 0
      }
    } as AcademicPlanningResponse<MajorRequirementsResponse>);
    
  } catch (error) {
    console.error('Major requirements validation error:', error);
    
    return NextResponse.json({
      success: false,
      error: {
        code: "INTERNAL_ERROR",
        message: "An error occurred while validating major requirements"
      }
    } as AcademicPlanningResponse<MajorRequirementsResponse>, { status: 500 });
  }
}