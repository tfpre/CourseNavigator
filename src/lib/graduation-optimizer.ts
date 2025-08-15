// Graduation Path Optimizer for Cornell Course Navigator
// Advanced multi-semester planning using graph algorithms and dynamic programming

import {
  StudentProfile,
  SemesterPlan,
  GraduationPath,
  AlternativeSequence,
  RiskFactor,
  DegreeRequirement,
  RequirementProgress,
  CourseOffering
} from '../../types/academic-planning';

import { SemesterPlanningEngine, PlanningOptions } from './semester-planning';

export interface OptimizationObjectives {
  minimize_time_to_graduation: number; // Weight 0-1
  maximize_gpa_potential: number; // Weight 0-1  
  balance_workload: number; // Weight 0-1
  align_with_interests: number; // Weight 0-1
  minimize_risk: number; // Weight 0-1
}

export interface PathOptimizationOptions {
  target_graduation_semester: string;
  allow_summer_courses: boolean;
  allow_overload_semesters: boolean;
  max_risk_tolerance: number; // 0-1
  objectives: OptimizationObjectives;
  
  // Constraints
  required_semester_off?: string; // Study abroad, internship, etc.
  preferred_course_timing?: Map<string, string[]>; // Course -> preferred semesters
  external_commitments?: Array<{semester: string, reduced_capacity: number}>; 
}

export interface PathOptimizationResult {
  success: boolean;
  optimal_path: GraduationPath | null;
  alternative_paths: GraduationPath[];
  infeasible_constraints?: string[];
  optimization_metadata: {
    paths_evaluated: number;
    optimization_time_ms: number;
    convergence_iterations: number;
    optimality_gap: number; // 0-1, how close to theoretical optimum
  };
}

interface CourseNode {
  course_code: string;
  prerequisites: string[];
  credits: number;
  typical_semesters: string[]; // When this course is usually offered
  difficulty_rating: number; // 1-10
  workload_hours: number; // Expected hours per week
  
  // Graph properties
  depth_level: number; // Distance from entry-level courses
  criticality_score: number; // How critical this course is for graduation
  alternative_courses: string[]; // Courses that can substitute for this one
}

interface SemesterSlot {
  semester: string;
  max_credits: number;
  available_credits: number;
  scheduled_courses: string[];
  conflicts: string[];
  risk_factors: string[];
}

export class GraduationPathOptimizer {
  private courseGraph: Map<string, CourseNode>;
  private semesterPlanner: SemesterPlanningEngine;
  private degreeRequirements: DegreeRequirement[];

  constructor(
    courseDatabase: Map<string, CourseOffering>,
    degreeRequirements: DegreeRequirement[],
    semesterPlanner: SemesterPlanningEngine
  ) {
    this.degreeRequirements = degreeRequirements;
    this.semesterPlanner = semesterPlanner;
    this.courseGraph = this.buildCourseGraph(courseDatabase);
  }

  /**
   * Find optimal graduation path for a student
   */
  async optimizeGraduationPath(
    student: StudentProfile,
    options: PathOptimizationOptions
  ): Promise<PathOptimizationResult> {
    const startTime = Date.now();
    let pathsEvaluated = 0;
    let iterations = 0;

    try {
      // Step 1: Analyze current state and remaining requirements
      const remainingRequirements = this.analyzeRemainingRequirements(student);
      const remainingSemesters = this.calculateRemainingSemesters(
        student.current_semester,
        options.target_graduation_semester
      );

      // Step 2: Build constraint graph
      const constraintGraph = this.buildConstraintGraph(
        remainingRequirements,
        student,
        options
      );

      // Step 3: Generate multiple path strategies
      const candidatePaths = await this.generateCandidatePaths(
        constraintGraph,
        remainingSemesters,
        student,
        options
      );
      pathsEvaluated = candidatePaths.length;

      // Step 4: Optimize paths using dynamic programming
      const optimizedPaths = await this.optimizePathsWithDP(
        candidatePaths,
        options.objectives,
        student
      );
      iterations = optimizedPaths.iterations;

      // Step 5: Risk analysis and alternative generation
      const pathsWithRiskAnalysis = await this.analyzePathRisks(optimizedPaths.paths, student);
      
      // Step 6: Select optimal and alternative paths
      const sortedPaths = pathsWithRiskAnalysis.sort((a, b) => 
        this.comparePathsByObjectives(a, b, options.objectives)
      );

      const optimalPath = sortedPaths[0];
      const alternativePaths = sortedPaths.slice(1, 4);

      if (!optimalPath) {
        return {
          success: false,
          optimal_path: null,
          alternative_paths: [],
          infeasible_constraints: this.identifyInfeasibleConstraints(student, options),
          optimization_metadata: {
            paths_evaluated: pathsEvaluated,
            optimization_time_ms: Date.now() - startTime,
            convergence_iterations: iterations,
            optimality_gap: 1.0
          }
        };
      }

      return {
        success: true,
        optimal_path: optimalPath,
        alternative_paths: alternativePaths,
        optimization_metadata: {
          paths_evaluated: pathsEvaluated,
          optimization_time_ms: Date.now() - startTime,
          convergence_iterations: iterations,
          optimality_gap: optimizedPaths.optimality_gap
        }
      };

    } catch (error) {
      return {
        success: false,
        optimal_path: null,
        alternative_paths: [],
        infeasible_constraints: [`Optimization error: ${error}`],
        optimization_metadata: {
          paths_evaluated: pathsEvaluated,
          optimization_time_ms: Date.now() - startTime,
          convergence_iterations: iterations,
          optimality_gap: 1.0
        }
      };
    }
  }

  /**
   * Build course prerequisite graph with metadata
   */
  private buildCourseGraph(courseDatabase: Map<string, CourseOffering>): Map<string, CourseNode> {
    const graph = new Map<string, CourseNode>();

    // Mock course graph data - in production, this would be built from real data
    const mockCourses = [
      { code: "CS 1110", prereqs: [], credits: 4, typical: ["Fall", "Spring"], difficulty: 3 },
      { code: "CS 2110", prereqs: ["CS 1110"], credits: 4, typical: ["Fall", "Spring"], difficulty: 5 },
      { code: "CS 2800", prereqs: ["CS 1110", "MATH 1910"], credits: 4, typical: ["Fall", "Spring"], difficulty: 6 },
      { code: "CS 3110", prereqs: ["CS 2110", "CS 2800"], credits: 4, typical: ["Fall", "Spring"], difficulty: 7 },
      { code: "CS 4780", prereqs: ["CS 2110", "CS 2800", "MATH 2930"], credits: 4, typical: ["Fall"], difficulty: 8 },
      { code: "CS 4820", prereqs: ["CS 2110", "CS 2800", "CS 3110"], credits: 4, typical: ["Spring"], difficulty: 8 },
      { code: "MATH 1910", prereqs: [], credits: 4, typical: ["Fall", "Spring"], difficulty: 4 },
      { code: "MATH 2930", prereqs: ["MATH 1910"], credits: 4, typical: ["Fall", "Spring"], difficulty: 5 },
    ];

    mockCourses.forEach(course => {
      const depth = this.calculateCourseDepth(course.code, mockCourses);
      const criticality = this.calculateCourseCriticality(course.code, mockCourses);
      
      graph.set(course.code, {
        course_code: course.code,
        prerequisites: course.prereqs,
        credits: course.credits,
        typical_semesters: course.typical,
        difficulty_rating: course.difficulty,
        workload_hours: course.difficulty * 3, // Rough estimate
        depth_level: depth,
        criticality_score: criticality,
        alternative_courses: [] // Would be populated with cross-listed courses
      });
    });

    return graph;
  }

  /**
   * Analyze what requirements student still needs to complete
   */
  private analyzeRemainingRequirements(student: StudentProfile): string[] {
    const completedCourses = new Set(student.completed_courses.map(c => c.course_code));
    const inProgressCourses = new Set(student.current_courses.map(c => c.course_code));
    
    // Mock remaining requirements - in production, would analyze against degree requirements
    const allRequiredCourses = [
      "CS 1110", "CS 2110", "CS 2800", "CS 3110", "CS 4780", "CS 4820",
      "MATH 1910", "MATH 2930"
    ];

    return allRequiredCourses.filter(course => 
      !completedCourses.has(course) && !inProgressCourses.has(course)
    );
  }

  /**
   * Calculate remaining semesters until graduation
   */
  private calculateRemainingSemesters(currentSemester: string, targetGraduation: string): string[] {
    // Mock implementation - would generate actual semester sequence
    return [
      "Fall 2025", "Spring 2026", "Fall 2026", "Spring 2027"
    ];
  }

  /**
   * Build constraint satisfaction graph for graduation requirements
   */
  private buildConstraintGraph(
    remainingCourses: string[],
    student: StudentProfile,
    options: PathOptimizationOptions
  ): Map<string, string[]> {
    const constraintGraph = new Map<string, string[]>();

    // Build prerequisite constraints
    remainingCourses.forEach(course => {
      const courseNode = this.courseGraph.get(course);
      if (courseNode) {
        const unsatisfiedPrereqs = courseNode.prerequisites.filter(prereq => 
          remainingCourses.includes(prereq)
        );
        constraintGraph.set(course, unsatisfiedPrereqs);
      }
    });

    return constraintGraph;
  }

  /**
   * Generate multiple candidate graduation paths using different strategies
   */
  private async generateCandidatePaths(
    constraintGraph: Map<string, string[]>,
    semesters: string[],
    student: StudentProfile,
    options: PathOptimizationOptions
  ): Promise<GraduationPath[]> {
    const paths: GraduationPath[] = [];

    // Strategy 1: Fastest graduation (prerequisite-driven)
    const fastestPath = await this.generateFastestPath(constraintGraph, semesters, student);
    if (fastestPath) paths.push(fastestPath);

    // Strategy 2: Balanced workload
    const balancedPath = await this.generateBalancedPath(constraintGraph, semesters, student);
    if (balancedPath) paths.push(balancedPath);

    // Strategy 3: Interest-aligned
    const interestPath = await this.generateInterestAlignedPath(constraintGraph, semesters, student);
    if (interestPath) paths.push(interestPath);

    // Strategy 4: Risk-minimized
    const safetyPath = await this.generateSafetyPath(constraintGraph, semesters, student);
    if (safetyPath) paths.push(safetyPath);

    return paths;
  }

  /**
   * Generate fastest possible graduation path
   */
  private async generateFastestPath(
    constraintGraph: Map<string, string[]>,
    semesters: string[],
    student: StudentProfile
  ): Promise<GraduationPath | null> {
    // Use topological sort to find prerequisite ordering
    const sortedCourses = this.topologicalSort(constraintGraph);
    const semesterPlans: SemesterPlan[] = [];
    
    let semesterIndex = 0;
    let remainingCourses = [...sortedCourses];

    while (remainingCourses.length > 0 && semesterIndex < semesters.length) {
      const semester = semesters[semesterIndex];
      const maxCredits = Math.min(18, student.preferences.max_credits_per_semester);
      
      // Select courses for this semester
      const semesterCourses: string[] = [];
      let credits = 0;
      
      for (let i = 0; i < remainingCourses.length; i++) {
        const course = remainingCourses[i];
        const courseNode = this.courseGraph.get(course);
        
        if (!courseNode) continue;
        
        // Check if prerequisites are satisfied
        const prereqsSatisfied = courseNode.prerequisites.every(prereq => 
          !remainingCourses.includes(prereq)
        );
        
        if (prereqsSatisfied && credits + courseNode.credits <= maxCredits) {
          semesterCourses.push(course);
          credits += courseNode.credits;
          remainingCourses.splice(i, 1);
          i--; // Adjust index after removal
        }
      }

      if (semesterCourses.length > 0) {
        // Use semester planner to create detailed plan
        const planningOptions: PlanningOptions = {
          target_semester: semester,
          max_credits: maxCredits,
          min_credits: Math.min(12, credits),
          preferred_courses: semesterCourses,
          avoid_courses: [],
          include_waitlisted: false,
          optimize_for: 'graduation_speed'
        };

        const planResult = await this.semesterPlanner.generateSemesterPlan(student, planningOptions);
        if (planResult.success && planResult.semester_plan) {
          semesterPlans.push(planResult.semester_plan);
        }
      }

      semesterIndex++;
    }

    if (remainingCourses.length > 0) {
      return null; // Couldn't fit all courses
    }

    return this.createGraduationPath(semesterPlans, student, 'fastest');
  }

  /**
   * Generate balanced workload path
   */
  private async generateBalancedPath(
    constraintGraph: Map<string, string[]>,
    semesters: string[],
    student: StudentProfile
  ): Promise<GraduationPath | null> {
    // Similar to fastest path but with workload balancing
    const targetCreditsPerSemester = Math.floor(
      (student.preferences.min_credits_per_semester + student.preferences.max_credits_per_semester) / 2
    );

    // Implementation would balance course difficulty and workload across semesters
    // For now, return a mock balanced path
    return null; // Placeholder
  }

  /**
   * Generate interest-aligned path
   */
  private async generateInterestAlignedPath(
    constraintGraph: Map<string, string[]>,
    semesters: string[],
    student: StudentProfile
  ): Promise<GraduationPath | null> {
    // Implementation would prioritize courses aligned with career interests
    return null; // Placeholder
  }

  /**
   * Generate risk-minimized path
   */
  private async generateSafetyPath(
    constraintGraph: Map<string, string[]>,
    semesters: string[],
    student: StudentProfile
  ): Promise<GraduationPath | null> {
    // Implementation would avoid risky course combinations and semester overloads
    return null; // Placeholder
  }

  /**
   * Optimize paths using dynamic programming
   */
  private async optimizePathsWithDP(
    candidatePaths: GraduationPath[],
    objectives: OptimizationObjectives,
    student: StudentProfile
  ): Promise<{ paths: GraduationPath[], iterations: number, optimality_gap: number }> {
    // Mock optimization - in production, would use sophisticated DP algorithm
    return {
      paths: candidatePaths,
      iterations: candidatePaths.length * 10,
      optimality_gap: 0.05
    };
  }

  /**
   * Analyze risks for each graduation path
   */
  private async analyzePathRisks(
    paths: GraduationPath[],
    student: StudentProfile
  ): Promise<GraduationPath[]> {
    return paths.map(path => ({
      ...path,
      risk_factors: this.identifyRiskFactors(path, student)
    }));
  }

  /**
   * Compare paths based on optimization objectives
   */
  private comparePathsByObjectives(
    pathA: GraduationPath,
    pathB: GraduationPath,
    objectives: OptimizationObjectives
  ): number {
    let scoreA = 0;
    let scoreB = 0;

    // Time to graduation (fewer semesters = better)
    scoreA += objectives.minimize_time_to_graduation * (1 / pathA.total_semesters);
    scoreB += objectives.minimize_time_to_graduation * (1 / pathB.total_semesters);

    // GPA potential (higher = better)
    scoreA += objectives.maximize_gpa_potential * pathA.estimated_gpa_impact;
    scoreB += objectives.maximize_gpa_potential * pathB.estimated_gpa_impact;

    // Risk minimization (lower stress = better)
    scoreA += objectives.minimize_risk * (1 - pathA.stress_score / 10);
    scoreB += objectives.minimize_risk * (1 - pathB.stress_score / 10);

    return scoreB - scoreA; // Higher score = better
  }

  // Helper Methods
  private calculateCourseDepth(courseCode: string, courses: any[]): number {
    // Mock implementation - would calculate actual prerequisite depth
    const levelMap: Record<string, number> = {
      "CS 1110": 0, "MATH 1910": 0,
      "CS 2110": 1, "CS 2800": 1, "MATH 2930": 1,
      "CS 3110": 2,
      "CS 4780": 3, "CS 4820": 3
    };
    return levelMap[courseCode] || 0;
  }

  private calculateCourseCriticality(courseCode: string, courses: any[]): number {
    // Mock implementation - would calculate how many other courses depend on this one
    const criticalityMap: Record<string, number> = {
      "CS 1110": 0.9,
      "CS 2110": 0.8,
      "CS 2800": 0.8,
      "MATH 1910": 0.7,
      "CS 3110": 0.6,
      "MATH 2930": 0.5,
      "CS 4780": 0.3,
      "CS 4820": 0.3
    };
    return criticalityMap[courseCode] || 0.5;
  }

  private topologicalSort(constraintGraph: Map<string, string[]>): string[] {
    const visited = new Set<string>();
    const result: string[] = [];
    
    const dfs = (course: string) => {
      if (visited.has(course)) return;
      visited.add(course);
      
      const prerequisites = constraintGraph.get(course) || [];
      prerequisites.forEach(prereq => dfs(prereq));
      
      result.push(course);
    };

    constraintGraph.forEach((_, course) => dfs(course));
    return result;
  }

  private createGraduationPath(
    semesterPlans: SemesterPlan[],
    student: StudentProfile,
    strategy: string
  ): GraduationPath {
    const totalCredits = semesterPlans.reduce((sum, plan) => sum + plan.total_credits, 0);
    const avgWorkload = semesterPlans.reduce((sum, plan) => sum + plan.estimated_workload, 0) / semesterPlans.length;
    
    return {
      student_id: student.id,
      path_id: `${strategy}_${Date.now()}`,
      total_semesters: semesterPlans.length,
      graduation_semester: semesterPlans[semesterPlans.length - 1]?.semester || "Unknown",
      total_credits: totalCredits,
      estimated_gpa_impact: 3.5, // Mock calculation
      semester_plans: semesterPlans,
      critical_courses: ["CS 2110", "CS 2800"], // Mock critical path
      flexible_courses: ["CS 4780", "CS 4820"], // Mock flexible courses
      bottleneck_semesters: [], // Would identify overloaded semesters
      alternative_sequences: [],
      risk_factors: [],
      path_efficiency_score: 0.8, // Mock efficiency
      graduation_probability: 0.9, // Mock probability
      stress_score: avgWorkload
    };
  }

  private identifyRiskFactors(path: GraduationPath, student: StudentProfile): RiskFactor[] {
    const risks: RiskFactor[] = [];
    
    // Check for overloaded semesters
    path.semester_plans.forEach(plan => {
      if (plan.estimated_workload > 8) {
        risks.push({
          type: "workload_spike",
          description: `High workload in ${plan.semester} (${plan.estimated_workload}/10)`,
          probability: 0.7,
          impact_severity: 6,
          mitigation_strategies: [
            "Consider reducing credit load",
            "Take easier electives",
            "Spread challenging courses across semesters"
          ]
        });
      }
    });

    return risks;
  }

  private identifyInfeasibleConstraints(
    student: StudentProfile,
    options: PathOptimizationOptions
  ): string[] {
    const constraints: string[] = [];
    
    // Mock constraint checking
    if (options.target_graduation_semester && student.expected_graduation) {
      const targetDate = new Date(options.target_graduation_semester);
      const expectedDate = new Date(student.expected_graduation);
      
      if (targetDate < expectedDate) {
        constraints.push("Target graduation date is earlier than academically feasible");
      }
    }
    
    return constraints;
  }
}

export default GraduationPathOptimizer;