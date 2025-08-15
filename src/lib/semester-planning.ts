// Semester Planning Algorithm for Cornell Course Navigator
// Advanced constraint satisfaction and optimization for academic planning

import {
  StudentProfile,
  SemesterPlan,
  PlannedCourse,
  PlanningConflict,
  PlanningWarning,
  CourseOffering,
  TimeSlot,
  DegreeRequirement,
  RequirementRule,
  CourseRecommendation,
  RecommendationReason
} from '../../types/academic-planning';

export interface PlanningOptions {
  target_semester: string;
  max_credits: number;
  min_credits: number;
  preferred_courses: string[];
  avoid_courses: string[];
  include_waitlisted: boolean;
  optimize_for: 'graduation_speed' | 'gpa_maximization' | 'workload_balance' | 'interest_alignment';
}

export interface PlanningResult {
  success: boolean;
  semester_plan: SemesterPlan | null;
  alternative_plans: SemesterPlan[];
  error_message?: string;
  optimization_stats: OptimizationStats;
}

interface OptimizationStats {
  plans_evaluated: number;
  constraints_checked: number;
  optimization_time_ms: number;
  feasibility_score: number; // 0-1
  optimality_score: number; // 0-1
}

interface CourseCandidate {
  course_code: string;
  course_title: string;
  credits: number;
  prerequisites: string[];
  time_slots: TimeSlot[];
  
  // Scoring Components
  requirement_value: number; // How much this advances degree requirements
  preference_match: number; // How well this matches student preferences
  schedule_compatibility: number; // How well this fits with other courses
  difficulty_appropriateness: number; // How appropriate the difficulty level is
  
  // Constraints
  has_prerequisites_satisfied: boolean;
  has_time_conflicts: boolean;
  within_credit_limits: boolean;
  
  // Overall Score
  total_score: number;
}

export class SemesterPlanningEngine {
  constructor(
    private courseDatabase: Map<string, CourseOffering>,
    private degreeRequirements: DegreeRequirement[]
  ) {}

  /**
   * Generate optimal semester plan for a student
   */
  async generateSemesterPlan(
    student: StudentProfile,
    options: PlanningOptions
  ): Promise<PlanningResult> {
    const startTime = Date.now();
    let plansEvaluated = 0;
    let constraintsChecked = 0;

    try {
      // Step 1: Generate course candidates
      const candidates = await this.generateCourseCandidates(student, options);
      
      // Step 2: Apply hard constraints
      const feasibleCandidates = this.applyHardConstraints(candidates, student, options);
      constraintsChecked += feasibleCandidates.length * 4; // 4 main constraint types
      
      if (feasibleCandidates.length === 0) {
        return {
          success: false,
          semester_plan: null,
          alternative_plans: [],
          error_message: "No feasible course combinations found for the given constraints",
          optimization_stats: {
            plans_evaluated: 0,
            constraints_checked: constraintsChecked,
            optimization_time_ms: Date.now() - startTime,
            feasibility_score: 0,
            optimality_score: 0
          }
        };
      }

      // Step 3: Generate and evaluate potential plans
      const candidatePlans = this.generateCandidatePlans(feasibleCandidates, options);
      plansEvaluated = candidatePlans.length;
      
      // Step 4: Score and rank plans
      const scoredPlans = candidatePlans.map(plan => ({
        plan,
        score: this.scorePlan(plan, student, options)
      })).sort((a, b) => b.score - a.score);

      // Step 5: Select best plan and alternatives
      const bestPlan = scoredPlans[0]?.plan;
      const alternativePlans = scoredPlans.slice(1, 4).map(sp => sp.plan);

      if (!bestPlan) {
        throw new Error("No valid plans could be generated");
      }

      // Step 6: Add detailed analysis
      const finalPlan = await this.enrichPlanWithAnalysis(bestPlan, student);

      const optimizationTime = Date.now() - startTime;
      
      return {
        success: true,
        semester_plan: finalPlan,
        alternative_plans: alternativePlans,
        optimization_stats: {
          plans_evaluated: plansEvaluated,
          constraints_checked: constraintsChecked,
          optimization_time_ms: optimizationTime,
          feasibility_score: feasibleCandidates.length / candidates.length,
          optimality_score: scoredPlans[0]?.score || 0
        }
      };

    } catch (error) {
      return {
        success: false,
        semester_plan: null,
        alternative_plans: [],
        error_message: error instanceof Error ? error.message : "Unknown planning error",
        optimization_stats: {
          plans_evaluated: plansEvaluated,
          constraints_checked: constraintsChecked,
          optimization_time_ms: Date.now() - startTime,
          feasibility_score: 0,
          optimality_score: 0
        }
      };
    }
  }

  /**
   * Generate candidate courses for consideration
   */
  private async generateCourseCandidates(
    student: StudentProfile,
    options: PlanningOptions
  ): Promise<CourseCandidate[]> {
    const candidates: CourseCandidate[] = [];
    const completedCourses = new Set(student.completed_courses.map(c => c.course_code));
    const inProgressCourses = new Set(student.current_courses.map(c => c.course_code));

    // Get all available courses for the target semester
    for (const [courseCode, offering] of Array.from(this.courseDatabase.entries())) {
      if (offering.semester !== options.target_semester) continue;
      if (completedCourses.has(courseCode) || inProgressCourses.has(courseCode)) continue;

      const candidate = await this.evaluateCourseCandidate(
        courseCode,
        offering,
        student,
        options
      );
      
      if (candidate.total_score > 0.1) { // Minimum viability threshold
        candidates.push(candidate);
      }
    }

    // Sort by total score
    return candidates.sort((a, b) => b.total_score - a.total_score);
  }

  /**
   * Evaluate a single course as a candidate for the semester
   */
  private async evaluateCourseCandidate(
    courseCode: string,
    offering: CourseOffering,
    student: StudentProfile,
    options: PlanningOptions
  ): Promise<CourseCandidate> {
    // Mock course data - in production, this would come from the course database
    const mockCourseData = {
      credits: 4,
      prerequisites: this.getMockPrerequisites(courseCode),
      difficulty_level: this.estimateCourseDifficulty(courseCode),
      time_slots: offering.sections[0]?.time_slots || []
    };

    // Check prerequisite satisfaction
    const hasPrereqsSatisfied = this.checkPrerequisites(
      mockCourseData.prerequisites,
      student.completed_courses.map(c => c.course_code)
    );

    // Calculate scoring components
    const requirementValue = this.calculateRequirementValue(courseCode, student);
    const preferenceMatch = this.calculatePreferenceMatch(courseCode, student, options);
    const scheduleCompatibility = this.calculateScheduleCompatibility(
      mockCourseData.time_slots,
      student.preferences
    );
    const difficultyAppropriateness = this.calculateDifficultyMatch(
      mockCourseData.difficulty_level,
      student.preferences.preferred_course_difficulty
    );

    // Overall score calculation
    const totalScore = (
      requirementValue * 0.4 +
      preferenceMatch * 0.25 +
      scheduleCompatibility * 0.2 +
      difficultyAppropriateness * 0.15
    );

    return {
      course_code: courseCode,
      course_title: offering.course_code, // Mock - would be actual title
      credits: mockCourseData.credits,
      prerequisites: mockCourseData.prerequisites,
      time_slots: mockCourseData.time_slots,
      
      requirement_value: requirementValue,
      preference_match: preferenceMatch,
      schedule_compatibility: scheduleCompatibility,
      difficulty_appropriateness: difficultyAppropriateness,
      
      has_prerequisites_satisfied: hasPrereqsSatisfied,
      has_time_conflicts: false, // Will be calculated during plan generation
      within_credit_limits: true, // Will be calculated during plan generation
      
      total_score: totalScore
    };
  }

  /**
   * Apply hard constraints to filter out infeasible courses
   */
  private applyHardConstraints(
    candidates: CourseCandidate[],
    student: StudentProfile,
    options: PlanningOptions
  ): CourseCandidate[] {
    return candidates.filter(candidate => {
      // Must have prerequisites satisfied
      if (!candidate.has_prerequisites_satisfied) return false;
      
      // Must not conflict with unavailable times
      if (this.hasWorkScheduleConflicts(candidate.time_slots, student.constraints.work_schedule)) {
        return false;
      }
      
      // Must be within student's credit range (will be verified in plan generation)
      return true;
    });
  }

  /**
   * Generate multiple candidate semester plans using different strategies
   */
  private generateCandidatePlans(
    candidates: CourseCandidate[],
    options: PlanningOptions
  ): SemesterPlan[] {
    const plans: SemesterPlan[] = [];
    
    // Strategy 1: Greedy by total score
    const greedyPlan = this.generateGreedyPlan(candidates, options, 'total_score');
    if (greedyPlan) plans.push(greedyPlan);
    
    // Strategy 2: Requirement-focused
    const requirementPlan = this.generateGreedyPlan(candidates, options, 'requirement_value');
    if (requirementPlan) plans.push(requirementPlan);
    
    // Strategy 3: Preference-focused
    const preferencePlan = this.generateGreedyPlan(candidates, options, 'preference_match');
    if (preferencePlan) plans.push(preferencePlan);
    
    // Strategy 4: Balanced approach with different credit targets
    for (const creditTarget of [options.min_credits, Math.floor((options.min_credits + options.max_credits) / 2), options.max_credits]) {
      const balancedPlan = this.generateBalancedPlan(candidates, { ...options, target_credits: creditTarget });
      if (balancedPlan) plans.push(balancedPlan);
    }
    
    return plans;
  }

  /**
   * Generate a plan using greedy selection based on a specific criterion
   */
  private generateGreedyPlan(
    candidates: CourseCandidate[],
    options: PlanningOptions,
    criterion: keyof CourseCandidate
  ): SemesterPlan | null {
    const sortedCandidates = [...candidates].sort((a, b) => {
      const aValue = typeof a[criterion] === 'number' ? a[criterion] as number : 0;
      const bValue = typeof b[criterion] === 'number' ? b[criterion] as number : 0;
      return bValue - aValue;
    });

    const selectedCourses: PlannedCourse[] = [];
    let totalCredits = 0;
    const usedTimeSlots: TimeSlot[] = [];

    for (const candidate of sortedCandidates) {
      // Check credit limits
      if (totalCredits + candidate.credits > options.max_credits) continue;
      
      // Check time conflicts
      if (this.hasTimeConflicts(candidate.time_slots, usedTimeSlots)) continue;
      
      // Add course to plan
      selectedCourses.push({
        course_code: candidate.course_code,
        course_title: candidate.course_title,
        intended_semester: options.target_semester,
        credits: candidate.credits,
        priority: this.determinePriority(candidate),
        confidence_score: candidate.total_score,
        alternative_courses: [],
        notes: `Selected via ${criterion} criterion`
      });
      
      totalCredits += candidate.credits;
      usedTimeSlots.push(...candidate.time_slots);
      
      // Stop if we've reached the maximum credits or have enough courses
      if (totalCredits >= options.max_credits || selectedCourses.length >= 6) break;
    }

    // Check if we meet minimum credit requirements
    if (totalCredits < options.min_credits) return null;

    return {
      student_id: "mock_student", // Would be provided in actual implementation
      semester: options.target_semester,
      courses: selectedCourses,
      total_credits: totalCredits,
      estimated_workload: this.estimateWorkload(selectedCourses),
      conflicts: [],
      warnings: [],
      recommendations: [],
      created_at: new Date().toISOString(),
      last_modified: new Date().toISOString(),
      version: 1,
      is_committed: false
    };
  }

  /**
   * Generate a balanced plan considering multiple objectives
   */
  private generateBalancedPlan(
    candidates: CourseCandidate[],
    options: PlanningOptions & { target_credits: number }
  ): SemesterPlan | null {
    // Use a more sophisticated selection that balances different criteria
    const selectedCourses: PlannedCourse[] = [];
    let totalCredits = 0;
    const usedTimeSlots: TimeSlot[] = [];
    
    // Try to balance requirement progress, preferences, and workload
    let requirementCourses = 0;
    let electiveCourses = 0;
    
    for (const candidate of candidates) {
      if (totalCredits + candidate.credits > options.target_credits) continue;
      if (this.hasTimeConflicts(candidate.time_slots, usedTimeSlots)) continue;
      
      // Balance between requirements and electives
      const isRequirementCourse = candidate.requirement_value > 0.7;
      if (isRequirementCourse && requirementCourses >= 3) continue;
      if (!isRequirementCourse && electiveCourses >= 2) continue;
      
      selectedCourses.push({
        course_code: candidate.course_code,
        course_title: candidate.course_title,
        intended_semester: options.target_semester,
        credits: candidate.credits,
        priority: this.determinePriority(candidate),
        confidence_score: candidate.total_score,
        alternative_courses: [],
        notes: "Selected via balanced optimization"
      });
      
      totalCredits += candidate.credits;
      usedTimeSlots.push(...candidate.time_slots);
      
      if (isRequirementCourse) requirementCourses++;
      else electiveCourses++;
      
      if (totalCredits >= options.target_credits) break;
    }

    if (totalCredits < options.min_credits) return null;

    return {
      student_id: "mock_student",
      semester: options.target_semester,
      courses: selectedCourses,
      total_credits: totalCredits,
      estimated_workload: this.estimateWorkload(selectedCourses),
      conflicts: [],
      warnings: [],
      recommendations: [],
      created_at: new Date().toISOString(),
      last_modified: new Date().toISOString(),
      version: 1,
      is_committed: false
    };
  }

  /**
   * Score a complete semester plan
   */
  private scorePlan(plan: SemesterPlan, student: StudentProfile, options: PlanningOptions): number {
    let score = 0;

    // Credit utilization score (prefer closer to max credits)
    const creditUtilization = plan.total_credits / options.max_credits;
    score += creditUtilization * 0.2;

    // Requirement progress score
    const requirementProgress = plan.courses.reduce((sum, course) => 
      sum + (course.priority === 'required' ? 1 : 0.5), 0) / plan.courses.length;
    score += requirementProgress * 0.3;

    // Schedule optimization score
    const scheduleScore = this.calculateScheduleQuality(plan.courses);
    score += scheduleScore * 0.2;

    // Workload balance score
    const workloadScore = this.calculateWorkloadBalance(plan.estimated_workload, student.preferences);
    score += workloadScore * 0.15;

    // Preference alignment score
    const preferenceScore = plan.courses.reduce((sum, course) => sum + course.confidence_score, 0) / plan.courses.length;
    score += preferenceScore * 0.15;

    return Math.min(score, 1.0); // Cap at 1.0
  }

  /**
   * Add detailed analysis to a semester plan
   */
  private async enrichPlanWithAnalysis(plan: SemesterPlan, student: StudentProfile): Promise<SemesterPlan> {
    const conflicts = this.detectConflicts(plan, student);
    const warnings = this.generateWarnings(plan, student);
    const recommendations = this.generateRecommendations(plan, student);

    return {
      ...plan,
      conflicts,
      warnings,
      recommendations
    };
  }

  // Helper Methods
  private getMockPrerequisites(courseCode: string): string[] {
    const prereqMap: Record<string, string[]> = {
      "CS 2110": ["CS 1110"],
      "CS 2800": ["CS 1110", "MATH 1910"],
      "CS 3110": ["CS 2110", "CS 2800"],
      "CS 4780": ["CS 2110", "CS 2800", "MATH 2930"],
      "CS 4820": ["CS 2110", "CS 2800", "CS 3110"],
    };
    return prereqMap[courseCode] || [];
  }

  private checkPrerequisites(prerequisites: string[], completedCourses: string[]): boolean {
    return prerequisites.every(prereq => completedCourses.includes(prereq));
  }

  private calculateRequirementValue(courseCode: string, student: StudentProfile): number {
    // Mock calculation - in production, would check against degree requirements
    const requiredCourses = ["CS 2110", "CS 2800", "CS 3110", "MATH 1910", "MATH 2930"];
    return requiredCourses.includes(courseCode) ? 0.9 : 0.3;
  }

  private calculatePreferenceMatch(courseCode: string, student: StudentProfile, options: PlanningOptions): number {
    let score = 0.5; // Base score
    
    if (options.preferred_courses.includes(courseCode)) score += 0.4;
    if (options.avoid_courses.includes(courseCode)) score -= 0.5;
    
    // Mock subject preference calculation
    const subject = courseCode.split(' ')[0];
    if (student.preferences.career_interests.includes('software_engineering') && subject === 'CS') {
      score += 0.2;
    }
    
    return Math.max(0, Math.min(1, score));
  }

  private calculateScheduleCompatibility(timeSlots: TimeSlot[], preferences: any): number {
    let score = 0.5; // Base score
    
    // Mock implementation - would check against actual preferences
    if (preferences.avoid_friday_classes) {
      const hasFridayClasses = timeSlots.some(slot => slot.days.some(day => day.includes('F')));
      if (hasFridayClasses) score -= 0.3;
    }
    
    return Math.max(0, Math.min(1, score));
  }

  private calculateDifficultyMatch(courseDifficulty: number, preferredDifficulty: string): number {
    const difficultyMap = { "manageable": 0.3, "moderate": 0.6, "challenging": 0.9 };
    const targetDifficulty = difficultyMap[preferredDifficulty as keyof typeof difficultyMap] || 0.6;
    
    // Return higher score for closer matches
    return 1 - Math.abs(courseDifficulty - targetDifficulty);
  }

  private estimateCourseDifficulty(courseCode: string): number {
    // Mock difficulty estimation based on course level
    const level = parseInt(courseCode.split(' ')[1]);
    if (level < 2000) return 0.3;
    if (level < 3000) return 0.5;
    if (level < 4000) return 0.7;
    return 0.9;
  }

  private hasWorkScheduleConflicts(courseSlots: TimeSlot[], workSchedule: TimeSlot[]): boolean {
    // Mock implementation - would check for actual time overlaps
    return false;
  }

  private hasTimeConflicts(newSlots: TimeSlot[], existingSlots: TimeSlot[]): boolean {
    // Mock implementation - would check for time overlaps
    return false;
  }

  private determinePriority(candidate: CourseCandidate): "required" | "recommended" | "elective" | "optional" {
    if (candidate.requirement_value > 0.8) return "required";
    if (candidate.requirement_value > 0.5) return "recommended";
    return "elective";
  }

  private estimateWorkload(courses: PlannedCourse[]): number {
    // Mock workload calculation (1-10 scale)
    return Math.min(10, courses.length * 1.5 + courses.reduce((sum, c) => sum + c.credits, 0) * 0.2);
  }

  private calculateScheduleQuality(courses: PlannedCourse[]): number {
    // Mock schedule quality score
    return 0.7;
  }

  private calculateWorkloadBalance(workload: number, preferences: any): number {
    // Mock workload balance calculation
    const idealWorkload = preferences.preferred_course_difficulty === 'challenging' ? 8 : 6;
    return 1 - Math.abs(workload - idealWorkload) / 10;
  }

  private detectConflicts(plan: SemesterPlan, student: StudentProfile): PlanningConflict[] {
    const conflicts: PlanningConflict[] = [];
    
    // Check for credit overload
    if (plan.total_credits > student.preferences.max_credits_per_semester) {
      conflicts.push({
        type: "credit_overload",
        severity: "warning",
        message: `Credit load (${plan.total_credits}) exceeds preferred maximum (${student.preferences.max_credits_per_semester})`,
        affected_courses: plan.courses.map(c => c.course_code),
        suggested_solutions: ["Remove one elective course", "Consider audit option for one course"]
      });
    }
    
    return conflicts;
  }

  private generateWarnings(plan: SemesterPlan, student: StudentProfile): PlanningWarning[] {
    const warnings: PlanningWarning[] = [];
    
    if (plan.estimated_workload > 8) {
      warnings.push({
        type: "heavy_workload",
        message: `High workload semester (${plan.estimated_workload}/10) - consider course difficulty balance`,
        affected_courses: plan.courses.map(c => c.course_code),
        impact_assessment: "May impact GPA or require significant time commitment"
      });
    }
    
    return warnings;
  }

  private generateRecommendations(plan: SemesterPlan, student: StudentProfile): string[] {
    const recommendations: string[] = [];
    
    recommendations.push("Review course syllabi and contact instructors for detailed expectations");
    recommendations.push("Consider forming study groups for challenging courses");
    
    if (plan.total_credits < student.preferences.max_credits_per_semester) {
      recommendations.push("You have room for additional credits - consider adding an elective");
    }
    
    return recommendations;
  }
}

export default SemesterPlanningEngine;