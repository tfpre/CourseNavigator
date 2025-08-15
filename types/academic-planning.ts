// Academic Planning Types for Cornell Course Navigator
// Comprehensive data models for semester planning, graduation optimization, and academic advising

export interface StudentProfile {
  id: string;
  name: string;
  email: string;
  student_id?: string;
  
  // Academic Timeline
  admission_semester: string; // "Fall 2022"
  current_semester: string; // "Spring 2025"
  expected_graduation: string; // "Spring 2026"
  total_semesters_enrolled: number;
  
  // Academic Standing
  cumulative_gpa?: number;
  total_credits_completed: number;
  total_credits_in_progress: number;
  
  // Program Information
  primary_major: string; // "Computer Science"
  secondary_major?: string;
  minors: string[];
  concentration?: string; // "Machine Learning"
  
  // Course History
  completed_courses: CompletedCourse[];
  current_courses: EnrolledCourse[];
  planned_courses: PlannedCourse[];
  
  // Preferences & Constraints
  preferences: StudentPreferences;
  constraints: StudentConstraints;
}

export interface CompletedCourse {
  course_code: string;
  course_title: string;
  semester: string; // "Fall 2023"
  grade: string; // "A", "B+", "S", etc.
  credits: number;
  transfer_credit?: boolean;
  
  // For degree requirement tracking
  satisfies_requirements: string[]; // ["CS_CORE", "MATH_ELECTIVE", "TECH_ELECTIVE"]
}

export interface EnrolledCourse {
  course_code: string;
  course_title: string;
  semester: string;
  credits: number;
  status: "enrolled" | "waitlisted" | "audit";
  
  // Schedule Information
  time_slots: TimeSlot[];
  instructor?: string;
  location?: string;
}

export interface PlannedCourse {
  course_code: string;
  course_title: string;
  intended_semester: string;
  credits: number;
  priority: "required" | "recommended" | "elective" | "optional";
  
  // Planning Metadata
  confidence_score: number; // 0-1, likelihood of taking this course
  alternative_courses: string[]; // Other courses that satisfy same requirement
  notes?: string;
}

export interface TimeSlot {
  days: string[]; // ["MWF", "TR"]
  start_time: string; // "10:10"
  end_time: string; // "11:00"
  location?: string; // "Gates G01"
}

export interface StudentPreferences {
  // Scheduling Preferences
  preferred_class_times: string[]; // ["morning", "afternoon", "evening"]
  max_credits_per_semester: number;
  min_credits_per_semester: number;
  avoid_friday_classes: boolean;
  
  // Academic Preferences
  preferred_course_difficulty: "challenging" | "moderate" | "manageable";
  preferred_class_size: "small" | "medium" | "large" | "no_preference";
  preferred_instructors: string[];
  avoid_instructors: string[];
  
  // Career Goals
  career_interests: string[]; // ["software_engineering", "research", "data_science"]
  graduate_school_plans: boolean;
  industry_focus: string[]; // ["tech", "finance", "healthcare"]
}

export interface StudentConstraints {
  // Hard Constraints
  work_schedule: TimeSlot[];
  unavailable_semesters: string[]; // Study abroad, internships, etc.
  required_graduation_semester: string;
  
  // Financial Constraints
  budget_per_semester?: number;
  financial_aid_requirements?: string[];
  
  // Academic Constraints
  minimum_gpa_requirement?: number;
  maximum_course_load?: number;
  prerequisite_overrides: string[]; // Courses they can take without normal prereqs
}

// Degree Requirements System
export interface DegreeRequirement {
  id: string;
  name: string; // "CS Major Core Requirements"
  description: string;
  type: "major" | "minor" | "concentration" | "general_ed" | "elective";
  
  requirements: RequirementRule[];
  total_credits_required: number;
  minimum_gpa?: number;
}

export interface RequirementRule {
  id: string;
  name: string; // "Programming Fundamentals"
  description: string;
  
  // Course Selection Rules
  rule_type: "specific_courses" | "course_list" | "subject_credits" | "level_credits";
  required_courses: string[]; // Specific courses that must be taken
  elective_courses: string[]; // Courses that can satisfy this requirement
  
  // Credit and Selection Constraints
  credits_required: number;
  courses_required: number; // Number of courses to select from elective_courses
  minimum_grade?: string;
  
  // Advanced Rules
  subject_constraints?: SubjectConstraint[];
  level_constraints?: LevelConstraint[];
  exclusions: string[]; // Courses that cannot be used to satisfy this requirement
  
  // Prerequisite Information
  recommended_semester_range: [number, number]; // [3, 6] for semesters 3-6
  prerequisites: string[]; // Other requirements that should be completed first
}

export interface SubjectConstraint {
  subject: string; // "CS", "MATH", "ENGRD"
  credits_required: number;
  minimum_level?: number; // 3000 for 3000+ level courses
}

export interface LevelConstraint {
  minimum_level: number; // 3000
  maximum_level?: number; // 4999
  credits_required: number;
}

// Semester Planning System
export interface SemesterPlan {
  student_id: string;
  semester: string; // "Fall 2025"
  
  courses: PlannedCourse[];
  total_credits: number;
  estimated_workload: number; // 1-10 scale
  
  // Validation Results
  conflicts: PlanningConflict[];
  warnings: PlanningWarning[];
  recommendations: string[];
  
  // Metadata
  created_at: string;
  last_modified: string;
  version: number;
  is_committed: boolean; // Whether student has actually registered
}

export interface PlanningConflict {
  type: "time_conflict" | "prerequisite_missing" | "credit_overload" | "requirement_violation";
  severity: "error" | "warning" | "info";
  message: string;
  affected_courses: string[];
  suggested_solutions: string[];
}

export interface PlanningWarning {
  type: "heavy_workload" | "difficult_combination" | "scheduling_risk" | "graduation_delay";
  message: string;
  affected_courses: string[];
  impact_assessment: string;
}

// Graduation Path Optimization
export interface GraduationPath {
  student_id: string;
  path_id: string;
  
  // Path Metadata
  total_semesters: number;
  graduation_semester: string;
  total_credits: number;
  estimated_gpa_impact: number;
  
  // Semester-by-Semester Plan
  semester_plans: SemesterPlan[];
  
  // Path Analysis
  critical_courses: string[]; // Courses that cannot be delayed
  flexible_courses: string[]; // Courses with multiple scheduling options
  bottleneck_semesters: string[]; // Semesters with heavy requirements
  
  // Alternative Paths
  alternative_sequences: AlternativeSequence[];
  risk_factors: RiskFactor[];
  
  // Optimization Metrics
  path_efficiency_score: number; // 0-1, how optimal this path is
  graduation_probability: number; // 0-1, likelihood of completing on time
  stress_score: number; // 0-10, estimated academic stress
}

export interface AlternativeSequence {
  description: string; // "Take CS 3110 in Fall instead of Spring"
  affected_semesters: string[];
  trade_offs: string[];
  impact_on_graduation: number; // Semesters delayed/accelerated
}

export interface RiskFactor {
  type: "course_availability" | "prerequisite_chain" | "workload_spike" | "external_constraint";
  description: string;
  probability: number; // 0-1
  impact_severity: number; // 1-10
  mitigation_strategies: string[];
}

// Course Recommendation System
export interface CourseRecommendation {
  course_code: string;
  course_title: string;
  
  // Recommendation Scoring
  relevance_score: number; // 0-1, how relevant to student's goals
  difficulty_match: number; // 0-1, how well it matches preferred difficulty
  schedule_compatibility: number; // 0-1, how well it fits their schedule
  
  // Reasoning
  recommendation_reasons: RecommendationReason[];
  potential_concerns: string[];
  
  // Context
  recommended_semester: string;
  alternative_semesters: string[];
  related_courses: string[];
}

export interface RecommendationReason {
  type: "career_alignment" | "academic_progression" | "interest_match" | "requirement_satisfaction" | "peer_success";
  description: string;
  weight: number; // How much this reason contributed to the recommendation
}

// Academic Advisor Dashboard Data
export interface AdvisorDashboard {
  student_profile: StudentProfile;
  degree_progress: DegreeProgress;
  current_semester_analysis: SemesterAnalysis;
  graduation_outlook: GraduationOutlook;
  recommendations: AdvisorRecommendation[];
}

export interface DegreeProgress {
  major_progress: RequirementProgress[];
  minor_progress: RequirementProgress[];
  overall_completion: number; // 0-1
  
  credits_completed: number;
  credits_required: number;
  credits_in_progress: number;
  
  projected_graduation: string;
  on_track: boolean;
}

export interface RequirementProgress {
  requirement_id: string;
  requirement_name: string;
  completion_percentage: number; // 0-1
  
  satisfied_by: string[]; // Course codes that satisfy this requirement
  remaining_options: string[]; // Courses that could still satisfy this requirement
  
  status: "completed" | "in_progress" | "not_started" | "at_risk";
  notes?: string;
}

export interface SemesterAnalysis {
  current_semester: string;
  enrolled_courses: EnrolledCourse[];
  
  credit_load: number;
  workload_assessment: "light" | "moderate" | "heavy" | "overloaded";
  
  schedule_conflicts: PlanningConflict[];
  academic_risks: string[];
  opportunities: string[];
}

export interface GraduationOutlook {
  projected_graduation_semester: string;
  graduation_probability: number; // 0-1
  
  remaining_requirements: RequirementProgress[];
  critical_path_courses: string[];
  
  potential_delays: RiskFactor[];
  acceleration_opportunities: string[];
}

export interface AdvisorRecommendation {
  type: "course_selection" | "schedule_adjustment" | "requirement_planning" | "career_preparation";
  priority: "urgent" | "high" | "medium" | "low";
  
  title: string;
  description: string;
  action_items: string[];
  
  deadline?: string;
  follow_up_needed: boolean;
}

// API Response Types
export interface AcademicPlanningResponse<T> {
  success: boolean;
  data?: T;
  error?: {
    code: string;
    message: string;
    details?: any;
  };
  metadata?: {
    generated_at: string;
    version: string;
    processing_time_ms: number;
  };
}

// Common Utility Types
export type Semester = string; // "Fall 2025", "Spring 2026", "Summer 2026"
export type CourseCode = string; // "CS 2110", "MATH 1910"
export type Grade = "A+" | "A" | "A-" | "B+" | "B" | "B-" | "C+" | "C" | "C-" | "D+" | "D" | "D-" | "F" | "S" | "U" | "W" | "I";

export interface CourseOffering {
  course_code: string;
  semester: string;
  sections: CourseSection[];
  enrollment_capacity: number;
  waitlist_size: number;
  historical_demand: number; // 0-1, how quickly this course fills up
}

export interface CourseSection {
  section_id: string;
  instructor: string;
  time_slots: TimeSlot[];
  enrollment_limit: number;
  current_enrollment: number;
  mode: "in_person" | "online" | "hybrid";
}