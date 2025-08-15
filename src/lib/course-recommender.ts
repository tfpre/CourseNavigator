// Course Recommendation Engine for Cornell Course Navigator
// Advanced ML-inspired recommendation system for academic course selection

import {
  StudentProfile,
  CourseRecommendation,
  RecommendationReason,
  CourseOffering,
  CompletedCourse
} from '../../types/academic-planning';

export interface RecommendationContext {
  target_semester: string;
  available_credits: number; // How many credits the student has room for
  current_workload: number; // Current semester difficulty level
  academic_goals: string[]; // ["graduate_school", "industry", "research"]
  course_preferences: CoursePreferences;
  exclusions: string[]; // Courses to exclude from recommendations
}

export interface CoursePreferences {
  preferred_subjects: string[]; // ["CS", "MATH", "ECE"]
  avoided_subjects: string[];
  preferred_difficulty: "easy" | "moderate" | "challenging" | "any";
  preferred_class_size: "small" | "medium" | "large" | "any";
  preferred_time_slots: string[]; // ["morning", "afternoon", "evening"]
  prefer_new_topics: boolean; // Explore new areas vs stick to strengths
}

export interface RecommendationRequest {
  student: StudentProfile;
  context: RecommendationContext;
  num_recommendations: number;
  include_reasoning: boolean;
  recommendation_types: RecommendationType[];
}

export type RecommendationType = 
  | "next_in_sequence"     // Natural prerequisite progression
  | "breadth_exploration"  // Explore new subjects/areas
  | "depth_specialization" // Go deeper in existing areas
  | "career_aligned"       // Aligned with career goals
  | "peer_success"         // What similar students succeeded in
  | "fill_requirements"    // Complete degree requirements
  | "balance_workload"     // Complement current semester difficulty

export interface RecommendationResult {
  recommendations: CourseRecommendation[];
  recommendation_metadata: {
    total_candidates_evaluated: number;
    filtering_applied: string[];
    recommendation_strategies_used: RecommendationType[];
    confidence_distribution: { [key in 'high' | 'medium' | 'low']: number };
  };
}

interface CourseFeatures {
  course_code: string;
  subject: string;
  level: number;
  credits: number;
  difficulty_rating: number; // 1-10
  workload_intensity: number; // 1-10
  
  // Content features
  topics: string[]; // ["algorithms", "machine_learning", "theory"]
  skills_developed: string[]; // ["programming", "mathematical_reasoning"]
  career_relevance: { [career: string]: number }; // career -> relevance score
  
  // Historical data
  average_grade: number; // GPA
  success_rate: number; // % students who complete successfully
  prerequisite_success_correlation: number; // How well prereqs predict success
  
  // Offering metadata
  typical_semesters: string[]; // When usually offered
  class_size: "small" | "medium" | "large";
  instructor_rating: number; // 1-10
}

interface StudentFeatureVector {
  // Academic performance
  gpa_by_subject: { [subject: string]: number };
  gpa_by_difficulty: { [difficulty: string]: number };
  course_completion_rate: number;
  
  // Academic interests (inferred from course history)
  subject_affinity: { [subject: string]: number };
  topic_interests: { [topic: string]: number };
  difficulty_preference: "easy" | "moderate" | "challenging";
  
  // Learning patterns
  typical_credit_load: number;
  workload_tolerance: number;
  prerequisite_adherence: number; // How closely they follow prereq chains
  
  // Career alignment
  career_focus_scores: { [career: string]: number };
}

export class CourseRecommendationEngine {
  private courseFeatures: Map<string, CourseFeatures>;
  private studentSimilarityGraph: Map<string, Map<string, number>>; // student -> similar students with similarity scores
  private courseDatabase: Map<string, CourseOffering>;

  constructor(courseDatabase: Map<string, CourseOffering>) {
    this.courseDatabase = courseDatabase;
    this.courseFeatures = this.buildCourseFeatures(courseDatabase);
    this.studentSimilarityGraph = new Map(); // Would be populated from historical data
  }

  /**
   * Generate personalized course recommendations for a student
   */
  async generateRecommendations(request: RecommendationRequest): Promise<RecommendationResult> {
    const { student, context, num_recommendations, recommendation_types } = request;
    
    // Step 1: Build student feature vector
    const studentFeatures = this.buildStudentFeatureVector(student);
    
    // Step 2: Get candidate courses
    const candidates = this.getCandidateCourses(student, context);
    
    // Step 3: Apply multiple recommendation strategies
    const strategyRecommendations = new Map<RecommendationType, CourseRecommendation[]>();
    
    for (const strategy of recommendation_types) {
      const recommendations = await this.applyRecommendationStrategy(
        strategy,
        candidates,
        student,
        studentFeatures,
        context
      );
      strategyRecommendations.set(strategy, recommendations);
    }
    
    // Step 4: Combine and rank recommendations
    const combinedRecommendations = this.combineStrategyRecommendations(
      strategyRecommendations,
      num_recommendations
    );
    
    // Step 5: Add detailed reasoning if requested
    if (request.include_reasoning) {
      await this.enrichRecommendationsWithReasoning(
        combinedRecommendations,
        student,
        studentFeatures,
        context
      );
    }
    
    return {
      recommendations: combinedRecommendations,
      recommendation_metadata: {
        total_candidates_evaluated: candidates.length,
        filtering_applied: this.getAppliedFilters(context),
        recommendation_strategies_used: recommendation_types,
        confidence_distribution: this.analyzeConfidenceDistribution(combinedRecommendations)
      }
    };
  }

  /**
   * Build feature vector representing student's academic profile
   */
  private buildStudentFeatureVector(student: StudentProfile): StudentFeatureVector {
    const completedCourses = student.completed_courses;
    
    // Calculate GPA by subject
    const gpaBySubject: { [subject: string]: number } = {};
    const subjectCourses: { [subject: string]: CompletedCourse[] } = {};
    
    completedCourses.forEach(course => {
      const subject = course.course_code.split(' ')[0];
      if (!subjectCourses[subject]) subjectCourses[subject] = [];
      subjectCourses[subject].push(course);
    });
    
    Object.entries(subjectCourses).forEach(([subject, courses]) => {
      const avgGpa = courses.reduce((sum, c) => sum + this.gradeToGPA(c.grade), 0) / courses.length;
      gpaBySubject[subject] = avgGpa;
    });
    
    // Calculate subject affinity (how much they gravitate toward each subject)
    const subjectAffinity: { [subject: string]: number } = {};
    const totalCourses = completedCourses.length;
    
    Object.entries(subjectCourses).forEach(([subject, courses]) => {
      const proportion = courses.length / totalCourses;
      const avgGrade = gpaBySubject[subject];
      subjectAffinity[subject] = proportion * avgGrade; // Weighted by performance
    });
    
    // Infer difficulty preference
    const difficultyScores = completedCourses.map(course => {
      const difficulty = this.estimateCourseDifficulty(course.course_code);
      const grade = this.gradeToGPA(course.grade);
      return { difficulty, grade };
    });
    
    const avgDifficultyGrade = difficultyScores.reduce((sum, d) => sum + d.grade, 0) / difficultyScores.length;
    const difficultyPreference = avgDifficultyGrade > 3.5 ? "challenging" : 
                                avgDifficultyGrade > 3.0 ? "moderate" : "easy";
    
    return {
      gpa_by_subject: gpaBySubject,
      gpa_by_difficulty: { "easy": 3.5, "moderate": 3.3, "challenging": 3.1 }, // Mock calculation
      course_completion_rate: 0.95, // Mock - would calculate from data
      subject_affinity: subjectAffinity,
      topic_interests: this.inferTopicInterests(completedCourses),
      difficulty_preference: difficultyPreference,
      typical_credit_load: student.preferences.max_credits_per_semester,
      workload_tolerance: student.preferences.preferred_course_difficulty === 'challenging' ? 8 : 6,
      prerequisite_adherence: 0.9, // Mock - how closely they follow prereq chains
      career_focus_scores: this.inferCareerFocus(student)
    };
  }

  /**
   * Get candidate courses for recommendation
   */
  private getCandidateCourses(student: StudentProfile, context: RecommendationContext): string[] {
    const completedCourses = new Set(student.completed_courses.map(c => c.course_code));
    const inProgressCourses = new Set(student.current_courses.map(c => c.course_code));
    const excludedCourses = new Set(context.exclusions);
    
    const candidates: string[] = [];
    
    // Get all courses offered in target semester
    for (const [courseCode, offering] of Array.from(this.courseDatabase.entries())) {
      if (offering.semester !== context.target_semester) continue;
      if (completedCourses.has(courseCode)) continue;
      if (inProgressCourses.has(courseCode)) continue;
      if (excludedCourses.has(courseCode)) continue;
      
      // Check if student meets prerequisites
      const courseFeatures = this.courseFeatures.get(courseCode);
      if (courseFeatures && this.hasPrerequisitesSatisfied(courseCode, student)) {
        candidates.push(courseCode);
      }
    }
    
    return candidates;
  }

  /**
   * Apply specific recommendation strategy
   */
  private async applyRecommendationStrategy(
    strategy: RecommendationType,
    candidates: string[],
    student: StudentProfile,
    features: StudentFeatureVector,
    context: RecommendationContext
  ): Promise<CourseRecommendation[]> {
    
    switch (strategy) {
      case "next_in_sequence":
        return this.recommendNextInSequence(candidates, student, features);
      
      case "breadth_exploration":
        return this.recommendBreadthExploration(candidates, student, features);
      
      case "depth_specialization":
        return this.recommendDepthSpecialization(candidates, student, features);
      
      case "career_aligned":
        return this.recommendCareerAligned(candidates, student, features, context);
      
      case "peer_success":
        return this.recommendBasedOnPeerSuccess(candidates, student, features);
      
      case "fill_requirements":
        return this.recommendRequirementFulfillment(candidates, student, features);
      
      case "balance_workload":
        return this.recommendWorkloadBalance(candidates, student, features, context);
      
      default:
        return [];
    }
  }

  /**
   * Recommend courses that are natural next steps in prerequisite chains
   */
  private recommendNextInSequence(
    candidates: string[],
    student: StudentProfile,
    features: StudentFeatureVector
  ): CourseRecommendation[] {
    const recommendations: CourseRecommendation[] = [];
    const completedCourses = new Set(student.completed_courses.map(c => c.course_code));
    
    for (const courseCode of candidates) {
      const courseFeatures = this.courseFeatures.get(courseCode);
      if (!courseFeatures) continue;
      
      // Calculate how well this course fits the natural progression
      let sequenceScore = 0;
      
      // Check if this course is a direct continuation of completed courses
      completedCourses.forEach(completedCourse => {
        if (this.isDirectPrerequisite(completedCourse, courseCode)) {
          const completedGrade = student.completed_courses.find(c => c.course_code === completedCourse)?.grade;
          const gradeScore = this.gradeToGPA(completedGrade || 'B') / 4.0;
          sequenceScore += 0.8 * gradeScore;
        }
      });
      
      // Bonus for courses in subjects where student has shown success
      const subject = courseCode.split(' ')[0];
      const subjectGPA = features.gpa_by_subject[subject] || 3.0;
      sequenceScore += 0.2 * (subjectGPA / 4.0);
      
      if (sequenceScore > 0.3) {
        recommendations.push({
          course_code: courseCode,
          course_title: this.getCourseTitle(courseCode),
          relevance_score: sequenceScore,
          difficulty_match: this.calculateDifficultyMatch(courseFeatures, features),
          schedule_compatibility: 0.8, // Mock - would calculate from actual schedule
          recommendation_reasons: [{
            type: "academic_progression",
            description: `Natural next step after completing ${Array.from(completedCourses).filter(c => this.isDirectPrerequisite(c, courseCode)).join(', ')}`,
            weight: sequenceScore
          }],
          potential_concerns: this.identifyPotentialConcerns(courseFeatures, features),
          recommended_semester: student.current_semester,
          alternative_semesters: [],
          related_courses: []
        });
      }
    }
    
    return recommendations.sort((a, b) => b.relevance_score - a.relevance_score).slice(0, 5);
  }

  /**
   * Recommend courses to explore new subjects/areas
   */
  private recommendBreadthExploration(
    candidates: string[],
    student: StudentProfile,
    features: StudentFeatureVector
  ): CourseRecommendation[] {
    const recommendations: CourseRecommendation[] = [];
    const experiencedSubjects = new Set(Object.keys(features.subject_affinity));
    
    for (const courseCode of candidates) {
      const subject = courseCode.split(' ')[0];
      const courseFeatures = this.courseFeatures.get(courseCode);
      if (!courseFeatures) continue;
      
      // Prioritize subjects student hasn't explored much
      if (!experiencedSubjects.has(subject) || features.subject_affinity[subject] < 0.2) {
        const explorationScore = 1 - (features.subject_affinity[subject] || 0);
        const accessibilityScore = this.calculateAccessibilityScore(courseFeatures, features);
        
        const overallScore = 0.6 * explorationScore + 0.4 * accessibilityScore;
        
        if (overallScore > 0.4) {
          recommendations.push({
            course_code: courseCode,
            course_title: this.getCourseTitle(courseCode),
            relevance_score: overallScore,
            difficulty_match: this.calculateDifficultyMatch(courseFeatures, features),
            schedule_compatibility: 0.8,
            recommendation_reasons: [{
              type: "interest_match",
              description: `Explore new area: ${subject} - broaden your academic perspective`,
              weight: explorationScore
            }],
            potential_concerns: ["New subject area - may require adjustment period"],
            recommended_semester: student.current_semester,
            alternative_semesters: [],
            related_courses: []
          });
        }
      }
    }
    
    return recommendations.sort((a, b) => b.relevance_score - a.relevance_score).slice(0, 3);
  }

  /**
   * Recommend courses for deeper specialization in existing strengths
   */
  private recommendDepthSpecialization(
    candidates: string[],
    student: StudentProfile,
    features: StudentFeatureVector
  ): CourseRecommendation[] {
    const recommendations: CourseRecommendation[] = [];
    
    // Find student's strongest subjects
    const strongSubjects = Object.entries(features.subject_affinity)
      .filter(([_, affinity]) => affinity > 0.3)
      .sort(([_, a], [__, b]) => b - a)
      .slice(0, 2)
      .map(([subject, _]) => subject);
    
    for (const courseCode of candidates) {
      const subject = courseCode.split(' ')[0];
      const courseFeatures = this.courseFeatures.get(courseCode);
      if (!courseFeatures) continue;
      
      if (strongSubjects.includes(subject)) {
        const subjectStrength = features.subject_affinity[subject];
        const advancedLevel = courseFeatures.level >= 3000 ? 1 : 0.5;
        const specializationScore = 0.7 * subjectStrength + 0.3 * advancedLevel;
        
        if (specializationScore > 0.5) {
          recommendations.push({
            course_code: courseCode,
            course_title: this.getCourseTitle(courseCode),
            relevance_score: specializationScore,
            difficulty_match: this.calculateDifficultyMatch(courseFeatures, features),
            schedule_compatibility: 0.8,
            recommendation_reasons: [{
              type: "academic_progression",
              description: `Deepen expertise in ${subject} - build on your strong foundation`,
              weight: specializationScore
            }],
            potential_concerns: this.identifyPotentialConcerns(courseFeatures, features),
            recommended_semester: student.current_semester,
            alternative_semesters: [],
            related_courses: []
          });
        }
      }
    }
    
    return recommendations.sort((a, b) => b.relevance_score - a.relevance_score).slice(0, 4);
  }

  /**
   * Recommend courses aligned with career goals
   */
  private recommendCareerAligned(
    candidates: string[],
    student: StudentProfile,
    features: StudentFeatureVector,
    context: RecommendationContext
  ): CourseRecommendation[] {
    const recommendations: CourseRecommendation[] = [];
    
    for (const courseCode of candidates) {
      const courseFeatures = this.courseFeatures.get(courseCode);
      if (!courseFeatures) continue;
      
      let careerAlignmentScore = 0;
      const alignedCareers: string[] = [];
      
      // Calculate alignment with each career goal
      context.academic_goals.forEach(goal => {
        const careerRelevance = courseFeatures.career_relevance[goal] || 0;
        const studentCareerFocus = features.career_focus_scores[goal] || 0;
        const alignmentContribution = careerRelevance * studentCareerFocus;
        
        careerAlignmentScore += alignmentContribution;
        if (careerRelevance > 0.6) {
          alignedCareers.push(goal);
        }
      });
      
      if (careerAlignmentScore > 0.4 && alignedCareers.length > 0) {
        recommendations.push({
          course_code: courseCode,
          course_title: this.getCourseTitle(courseCode),
          relevance_score: careerAlignmentScore,
          difficulty_match: this.calculateDifficultyMatch(courseFeatures, features),
          schedule_compatibility: 0.8,
          recommendation_reasons: [{
            type: "career_alignment",
            description: `Highly relevant for ${alignedCareers.join(' and ')} career path${alignedCareers.length > 1 ? 's' : ''}`,
            weight: careerAlignmentScore
          }],
          potential_concerns: this.identifyPotentialConcerns(courseFeatures, features),
          recommended_semester: student.current_semester,
          alternative_semesters: [],
          related_courses: []
        });
      }
    }
    
    return recommendations.sort((a, b) => b.relevance_score - a.relevance_score).slice(0, 4);
  }

  /**
   * Recommend based on peer success patterns (collaborative filtering)
   */
  private recommendBasedOnPeerSuccess(
    candidates: string[],
    student: StudentProfile,
    features: StudentFeatureVector
  ): CourseRecommendation[] {
    // Mock implementation - in production, would use actual collaborative filtering
    const recommendations: CourseRecommendation[] = [];
    
    // Simulate finding similar students and their successful courses
    const mockSimilarStudentCourses = ["CS 4780", "CS 4820", "MATH 2930"];
    
    for (const courseCode of candidates) {
      if (mockSimilarStudentCourses.includes(courseCode)) {
        recommendations.push({
          course_code: courseCode,
          course_title: this.getCourseTitle(courseCode),
          relevance_score: 0.7,
          difficulty_match: 0.8,
          schedule_compatibility: 0.8,
          recommendation_reasons: [{
            type: "peer_success",
            description: "Students with similar academic profiles have succeeded in this course",
            weight: 0.7
          }],
          potential_concerns: [],
          recommended_semester: student.current_semester,
          alternative_semesters: [],
          related_courses: []
        });
      }
    }
    
    return recommendations;
  }

  /**
   * Recommend courses to fulfill degree requirements
   */
  private recommendRequirementFulfillment(
    candidates: string[],
    student: StudentProfile,
    features: StudentFeatureVector
  ): CourseRecommendation[] {
    const recommendations: CourseRecommendation[] = [];
    
    // Mock degree requirements - in production, would check against actual requirements
    const requiredCourses = ["CS 2110", "CS 2800", "CS 3110", "MATH 1910", "MATH 2930"];
    const completedRequired = new Set(student.completed_courses.map(c => c.course_code));
    
    for (const courseCode of candidates) {
      if (requiredCourses.includes(courseCode) && !completedRequired.has(courseCode)) {
        const courseFeatures = this.courseFeatures.get(courseCode);
        const urgencyScore = this.calculateRequirementUrgency(courseCode, student);
        
        recommendations.push({
          course_code: courseCode,
          course_title: this.getCourseTitle(courseCode),
          relevance_score: 0.9 * urgencyScore,
          difficulty_match: this.calculateDifficultyMatch(courseFeatures!, features),
          schedule_compatibility: 0.8,
          recommendation_reasons: [{
            type: "requirement_satisfaction",
            description: `Required course for ${student.primary_major} major`,
            weight: urgencyScore
          }],
          potential_concerns: this.identifyPotentialConcerns(courseFeatures!, features),
          recommended_semester: student.current_semester,
          alternative_semesters: [],
          related_courses: []
        });
      }
    }
    
    return recommendations.sort((a, b) => b.relevance_score - a.relevance_score);
  }

  /**
   * Recommend courses to balance current semester workload
   */
  private recommendWorkloadBalance(
    candidates: string[],
    student: StudentProfile,
    features: StudentFeatureVector,
    context: RecommendationContext
  ): CourseRecommendation[] {
    const recommendations: CourseRecommendation[] = [];
    const targetWorkload = features.workload_tolerance;
    const currentWorkload = context.current_workload;
    const workloadGap = targetWorkload - currentWorkload;
    
    for (const courseCode of candidates) {
      const courseFeatures = this.courseFeatures.get(courseCode);
      if (!courseFeatures) continue;
      
      const courseWorkload = courseFeatures.workload_intensity;
      const workloadFit = 1 - Math.abs(courseWorkload - workloadGap) / 10;
      
      if (workloadFit > 0.5) {
        recommendations.push({
          course_code: courseCode,
          course_title: this.getCourseTitle(courseCode),
          relevance_score: workloadFit,
          difficulty_match: this.calculateDifficultyMatch(courseFeatures, features),
          schedule_compatibility: 0.8,
          recommendation_reasons: [{
            type: "academic_progression",
            description: `Good workload balance - complements your current semester difficulty`,
            weight: workloadFit
          }],
          potential_concerns: [],
          recommended_semester: student.current_semester,
          alternative_semesters: [],
          related_courses: []
        });
      }
    }
    
    return recommendations.sort((a, b) => b.relevance_score - a.relevance_score).slice(0, 3);
  }

  /**
   * Combine recommendations from multiple strategies
   */
  private combineStrategyRecommendations(
    strategyRecommendations: Map<RecommendationType, CourseRecommendation[]>,
    numRecommendations: number
  ): CourseRecommendation[] {
    const courseScores = new Map<string, { recommendation: CourseRecommendation, totalScore: number, strategies: RecommendationType[] }>();
    
    // Aggregate scores across strategies
    strategyRecommendations.forEach((recommendations, strategy) => {
      recommendations.forEach(rec => {
        if (courseScores.has(rec.course_code)) {
          const existing = courseScores.get(rec.course_code)!;
          existing.totalScore += rec.relevance_score;
          existing.strategies.push(strategy);
        } else {
          courseScores.set(rec.course_code, {
            recommendation: rec,
            totalScore: rec.relevance_score,
            strategies: [strategy]
          });
        }
      });
    });
    
    // Sort by total score and return top recommendations
    const sortedRecommendations = Array.from(courseScores.values())
      .sort((a, b) => b.totalScore - a.totalScore)
      .slice(0, numRecommendations)
      .map(entry => ({
        ...entry.recommendation,
        relevance_score: entry.totalScore / entry.strategies.length // Average score
      }));
    
    return sortedRecommendations;
  }

  // Helper Methods
  private buildCourseFeatures(courseDatabase: Map<string, CourseOffering>): Map<string, CourseFeatures> {
    const features = new Map<string, CourseFeatures>();
    
    // Mock course features - in production, would be built from historical data
    const mockFeatures = [
      {
        course_code: "CS 1110",
        subject: "CS",
        level: 1110,
        credits: 4,
        difficulty_rating: 3,
        workload_intensity: 4,
        topics: ["programming", "python", "problem_solving"],
        skills_developed: ["programming", "computational_thinking"],
        career_relevance: { "software_engineering": 0.9, "data_science": 0.7, "research": 0.6 },
        average_grade: 3.2,
        success_rate: 0.92,
        prerequisite_success_correlation: 0.0,
        typical_semesters: ["Fall", "Spring"],
        class_size: "large",
        instructor_rating: 8.5
      },
      {
        course_code: "CS 4780",
        subject: "CS",
        level: 4780,
        credits: 4,
        difficulty_rating: 8,
        workload_intensity: 9,
        topics: ["machine_learning", "artificial_intelligence", "data_analysis"],
        skills_developed: ["machine_learning", "statistical_analysis", "python"],
        career_relevance: { "data_science": 0.95, "research": 0.9, "software_engineering": 0.7 },
        average_grade: 3.4,
        success_rate: 0.88,
        prerequisite_success_correlation: 0.7,
        typical_semesters: ["Fall"],
        class_size: "medium",
        instructor_rating: 9.2
      }
      // Add more mock courses as needed
    ];
    
    mockFeatures.forEach(feature => {
      features.set(feature.course_code, feature as CourseFeatures);
    });
    
    return features;
  }

  private gradeToGPA(grade: string): number {
    const gradeMap: { [grade: string]: number } = {
      "A+": 4.0, "A": 4.0, "A-": 3.7,
      "B+": 3.3, "B": 3.0, "B-": 2.7,
      "C+": 2.3, "C": 2.0, "C-": 1.7,
      "D+": 1.3, "D": 1.0, "D-": 0.7,
      "F": 0.0, "S": 3.0, "U": 0.0
    };
    return gradeMap[grade] || 3.0;
  }

  private estimateCourseDifficulty(courseCode: string): number {
    const level = parseInt(courseCode.split(' ')[1]);
    if (level < 2000) return 0.3;
    if (level < 3000) return 0.5;
    if (level < 4000) return 0.7;
    return 0.9;
  }

  private inferTopicInterests(completedCourses: CompletedCourse[]): { [topic: string]: number } {
    // Mock implementation - would analyze course descriptions and syllabi
    return {
      "programming": 0.8,
      "mathematics": 0.6,
      "theory": 0.4,
      "systems": 0.3
    };
  }

  private inferCareerFocus(student: StudentProfile): { [career: string]: number } {
    const careerInterests = student.preferences.career_interests;
    const scores: { [career: string]: number } = {};
    
    careerInterests.forEach(interest => {
      scores[interest] = 0.8;
    });
    
    return scores;
  }

  private hasPrerequisitesSatisfied(courseCode: string, student: StudentProfile): boolean {
    // Mock implementation - would check against actual prerequisites
    const completedCourses = new Set(student.completed_courses.map(c => c.course_code));
    const inProgressCourses = new Set(student.current_courses.map(c => c.course_code));
    
    const prereqMap: { [course: string]: string[] } = {
      "CS 2110": ["CS 1110"],
      "CS 2800": ["CS 1110", "MATH 1910"],
      "CS 3110": ["CS 2110", "CS 2800"],
      "CS 4780": ["CS 2110", "CS 2800", "MATH 2930"],
      "CS 4820": ["CS 2110", "CS 2800", "CS 3110"]
    };
    
    const prerequisites = prereqMap[courseCode] || [];
    return prerequisites.every(prereq => 
      completedCourses.has(prereq) || inProgressCourses.has(prereq)
    );
  }

  private isDirectPrerequisite(prerequisite: string, course: string): boolean {
    // Mock implementation
    const prereqMap: { [course: string]: string[] } = {
      "CS 2110": ["CS 1110"],
      "CS 3110": ["CS 2110", "CS 2800"],
      "CS 4780": ["CS 2110", "CS 2800", "MATH 2930"]
    };
    return prereqMap[course]?.includes(prerequisite) || false;
  }

  private getCourseTitle(courseCode: string): string {
    const titleMap: { [code: string]: string } = {
      "CS 1110": "Introduction to Computing Using Python",
      "CS 2110": "Object-Oriented Programming and Data Structures",
      "CS 2800": "Discrete Structures",
      "CS 3110": "Data Structures and Functional Programming",
      "CS 4780": "Machine Learning for Intelligent Systems",
      "CS 4820": "Introduction to Analysis of Algorithms"
    };
    return titleMap[courseCode] || courseCode;
  }

  private calculateDifficultyMatch(courseFeatures: CourseFeatures, studentFeatures: StudentFeatureVector): number {
    const courseDifficulty = courseFeatures.difficulty_rating / 10;
    const studentPreference = studentFeatures.difficulty_preference;
    
    const preferenceMap = { "easy": 0.3, "moderate": 0.6, "challenging": 0.9 };
    const targetDifficulty = preferenceMap[studentPreference];
    
    return 1 - Math.abs(courseDifficulty - targetDifficulty);
  }

  private calculateAccessibilityScore(courseFeatures: CourseFeatures, studentFeatures: StudentFeatureVector): number {
    // How accessible/manageable this course would be for the student
    const difficultyScore = 1 - (courseFeatures.difficulty_rating / 10);
    const successRateScore = courseFeatures.success_rate;
    
    return 0.6 * difficultyScore + 0.4 * successRateScore;
  }

  private identifyPotentialConcerns(courseFeatures: CourseFeatures, studentFeatures: StudentFeatureVector): string[] {
    const concerns: string[] = [];
    
    if (courseFeatures.difficulty_rating >= 8) {
      concerns.push("High difficulty course - ensure adequate preparation");
    }
    
    if (courseFeatures.workload_intensity >= 8) {
      concerns.push("Heavy workload - may impact other courses");
    }
    
    if (courseFeatures.success_rate < 0.8) {
      concerns.push("Lower success rate - consider prerequisite strength");
    }
    
    return concerns;
  }

  private calculateRequirementUrgency(courseCode: string, student: StudentProfile): number {
    // Mock calculation - in production, would check graduation timeline and prereq chains
    return 0.8;
  }

  private async enrichRecommendationsWithReasoning(
    recommendations: CourseRecommendation[],
    student: StudentProfile,
    features: StudentFeatureVector,
    context: RecommendationContext
  ): Promise<void> {
    // Additional reasoning enrichment would go here
    // For now, recommendations already have basic reasoning from strategy methods
  }

  private getAppliedFilters(context: RecommendationContext): string[] {
    const filters: string[] = [];
    
    if (context.exclusions.length > 0) {
      filters.push("Excluded courses filter");
    }
    
    if (context.available_credits < 20) {
      filters.push("Credit limit filter");
    }
    
    return filters;
  }

  private analyzeConfidenceDistribution(recommendations: CourseRecommendation[]): { [key in 'high' | 'medium' | 'low']: number } {
    const distribution = { high: 0, medium: 0, low: 0 };
    
    recommendations.forEach(rec => {
      if (rec.relevance_score >= 0.7) distribution.high++;
      else if (rec.relevance_score >= 0.4) distribution.medium++;
      else distribution.low++;
    });
    
    return distribution;
  }
}

export default CourseRecommendationEngine;