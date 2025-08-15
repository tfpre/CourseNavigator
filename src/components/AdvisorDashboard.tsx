"use client";

import React, { useState, useMemo } from 'react';
import {
  StudentProfile,
  AdvisorDashboard as AdvisorDashboardData,
  DegreeProgress,
  RequirementProgress,
  SemesterAnalysis,
  GraduationOutlook,
  AdvisorRecommendation,
  RiskFactor
} from '../../types/academic-planning';

interface AdvisorDashboardProps {
  student: StudentProfile;
  className?: string;
}

interface ProgressBarProps {
  label: string;
  current: number;
  total: number;
  color?: 'green' | 'blue' | 'yellow' | 'red';
  showPercentage?: boolean;
}

interface MetricCardProps {
  title: string;
  value: string | number;
  trend?: 'up' | 'down' | 'stable';
  trendValue?: string;
  color?: 'blue' | 'green' | 'yellow' | 'red' | 'purple';
  subtitle?: string;
}

interface RiskIndicatorProps {
  risk: RiskFactor;
  onActionClick?: (riskId: string) => void;
}

// Progress Bar Component
function ProgressBar({ 
  label, 
  current, 
  total, 
  color = 'blue', 
  showPercentage = true 
}: ProgressBarProps) {
  const percentage = total > 0 ? (current / total) * 100 : 0;
  const colorClasses = {
    green: 'bg-green-500',
    blue: 'bg-blue-500',
    yellow: 'bg-yellow-500',
    red: 'bg-red-500'
  };

  return (
    <div className="mb-3">
      <div className="flex justify-between items-center mb-1">
        <span className="text-sm font-medium text-gray-700">{label}</span>
        <span className="text-sm text-gray-600">
          {current}/{total}
          {showPercentage && ` (${Math.round(percentage)}%)`}
        </span>
      </div>
      <div className="w-full bg-gray-200 rounded-full h-2">
        <div 
          className={`h-2 rounded-full transition-all duration-500 ${colorClasses[color]}`}
          style={{ width: `${Math.min(percentage, 100)}%` }}
        ></div>
      </div>
    </div>
  );
}

// Metric Card Component
function MetricCard({ 
  title, 
  value, 
  trend, 
  trendValue, 
  color = 'blue', 
  subtitle 
}: MetricCardProps) {
  const colorClasses = {
    blue: 'bg-blue-50 text-blue-900',
    green: 'bg-green-50 text-green-900',
    yellow: 'bg-yellow-50 text-yellow-900',
    red: 'bg-red-50 text-red-900',
    purple: 'bg-purple-50 text-purple-900'
  };

  const trendIcons = {
    up: '↗️',
    down: '↘️',
    stable: '→'
  };

  return (
    <div className={`p-4 rounded-lg ${colorClasses[color]}`}>
      <div className="flex items-center justify-between mb-1">
        <h3 className="text-sm font-medium opacity-75">{title}</h3>
        {trend && trendValue && (
          <span className="text-xs opacity-75 flex items-center">
            {trendIcons[trend]} {trendValue}
          </span>
        )}
      </div>
      <div className="text-2xl font-bold">{value}</div>
      {subtitle && (
        <div className="text-xs opacity-75 mt-1">{subtitle}</div>
      )}
    </div>
  );
}

// Risk Indicator Component
function RiskIndicator({ risk, onActionClick }: RiskIndicatorProps) {
  const severityColors = {
    1: 'border-l-green-400 bg-green-50',
    2: 'border-l-green-400 bg-green-50',
    3: 'border-l-yellow-400 bg-yellow-50',
    4: 'border-l-yellow-400 bg-yellow-50',
    5: 'border-l-orange-400 bg-orange-50',
    6: 'border-l-orange-400 bg-orange-50',
    7: 'border-l-red-400 bg-red-50',
    8: 'border-l-red-400 bg-red-50',
    9: 'border-l-red-500 bg-red-100',
    10: 'border-l-red-500 bg-red-100'
  };

  const severityColor = severityColors[risk.impact_severity as keyof typeof severityColors];

  return (
    <div className={`p-4 border-l-4 rounded-r-lg ${severityColor}`}>
      <div className="flex items-start justify-between">
        <div className="flex-1">
          <div className="flex items-center space-x-2 mb-2">
            <h4 className="font-medium text-gray-900 capitalize">
              {risk.type.replace('_', ' ')}
            </h4>
            <span className={`px-2 py-1 rounded-full text-xs font-medium ${
              risk.impact_severity <= 3 ? 'bg-green-100 text-green-800' :
              risk.impact_severity <= 6 ? 'bg-yellow-100 text-yellow-800' :
              'bg-red-100 text-red-800'
            }`}>
              Impact: {risk.impact_severity}/10
            </span>
            <span className="px-2 py-1 rounded-full text-xs font-medium bg-gray-100 text-gray-700">
              {Math.round(risk.probability * 100)}% likely
            </span>
          </div>
          
          <p className="text-sm text-gray-700 mb-3">
            {risk.description}
          </p>
          
          {risk.mitigation_strategies.length > 0 && (
            <div>
              <p className="text-xs font-medium text-gray-600 mb-1">Mitigation Strategies:</p>
              <ul className="space-y-1">
                {risk.mitigation_strategies.slice(0, 2).map((strategy, idx) => (
                  <li key={idx} className="text-xs text-gray-600">
                    • {strategy}
                  </li>
                ))}
                {risk.mitigation_strategies.length > 2 && (
                  <li className="text-xs text-gray-500">
                    +{risk.mitigation_strategies.length - 2} more strategies
                  </li>
                )}
              </ul>
            </div>
          )}
        </div>
        
        {onActionClick && (
          <button
            onClick={() => onActionClick(risk.type)}
            className="ml-4 px-3 py-1 text-xs bg-white border rounded hover:bg-gray-50 transition-colors"
          >
            Take Action
          </button>
        )}
      </div>
    </div>
  );
}

// Main Advisor Dashboard Component
export default function AdvisorDashboard({ 
  student, 
  className = "" 
}: AdvisorDashboardProps) {
  const [activeTab, setActiveTab] = useState<'overview' | 'progress' | 'planning' | 'risks'>('overview');
  const [timeRange, setTimeRange] = useState<'semester' | 'year' | 'all'>('semester');

  // Mock advisor dashboard data - in production, would come from API
  const dashboardData: AdvisorDashboardData = useMemo(() => ({
    student_profile: student,
    degree_progress: {
      major_progress: [
        {
          requirement_id: "cs_core",
          requirement_name: "CS Core Requirements",
          completion_percentage: 0.6,
          satisfied_by: ["CS 1110", "CS 2110"],
          remaining_options: ["CS 2800", "CS 3110", "CS 4780"],
          status: "in_progress",
          notes: "On track for timely completion"
        },
        {
          requirement_id: "math_requirements", 
          requirement_name: "Mathematics Requirements",
          completion_percentage: 0.4,
          satisfied_by: ["MATH 1910"],
          remaining_options: ["MATH 2930", "MATH 2940"],
          status: "in_progress",
          notes: "Need to complete differential equations"
        },
        {
          requirement_id: "technical_electives",
          requirement_name: "Technical Electives",
          completion_percentage: 0.2,
          satisfied_by: [],
          remaining_options: ["CS 4780", "CS 4820", "ECE 3140"],
          status: "not_started",
          notes: "Wide range of options available"
        }
      ],
      minor_progress: [],
      overall_completion: 0.45,
      credits_completed: student.total_credits_completed,
      credits_required: 120,
      credits_in_progress: student.total_credits_in_progress,
      projected_graduation: student.expected_graduation,
      on_track: true
    },
    current_semester_analysis: {
      current_semester: student.current_semester,
      enrolled_courses: student.current_courses,
      credit_load: student.total_credits_in_progress,
      workload_assessment: student.total_credits_in_progress > 16 ? "heavy" : 
                          student.total_credits_in_progress > 12 ? "moderate" : "light",
      schedule_conflicts: [],
      academic_risks: ["High credit load this semester"],
      opportunities: ["Strong performance trend", "Good prerequisite preparation"]
    },
    graduation_outlook: {
      projected_graduation_semester: student.expected_graduation,
      graduation_probability: 0.92,
      remaining_requirements: [
        {
          requirement_id: "cs_core",
          requirement_name: "CS Core Requirements", 
          completion_percentage: 0.6,
          satisfied_by: ["CS 1110", "CS 2110"],
          remaining_options: ["CS 2800", "CS 3110"],
          status: "in_progress"
        }
      ],
      critical_path_courses: ["CS 2800", "CS 3110", "CS 4780"],
      potential_delays: [
        {
          type: "course_availability",
          description: "CS 4780 only offered in Fall - creates scheduling constraint",
          probability: 0.3,
          impact_severity: 4,
          mitigation_strategies: [
            "Plan CS 4780 for Fall 2026",
            "Consider alternative ML course",
            "Adjust overall sequence timing"
          ]
        }
      ],
      acceleration_opportunities: [
        "Summer course options available",
        "Advanced placement possible for some requirements"
      ]
    },
    recommendations: [
      {
        type: "course_selection",
        priority: "high", 
        title: "Complete CS 2800 Next Semester",
        description: "CS 2800 (Discrete Structures) is a prerequisite for most advanced CS courses. Completing it next semester will unlock more options.",
        action_items: [
          "Register for CS 2800 in Fall 2025",
          "Review mathematics prerequisites",
          "Consider CS 2800 study groups"
        ],
        deadline: "Registration deadline: April 15",
        follow_up_needed: true
      },
      {
        type: "schedule_adjustment",
        priority: "medium",
        title: "Balance Course Difficulty",
        description: "Current semester has high workload. Consider balancing challenging courses with lighter electives.",
        action_items: [
          "Review current course difficulty levels", 
          "Consider audit option for one course",
          "Plan easier electives for spring"
        ],
        follow_up_needed: false
      }
    ]
  }), [student]);

  const tabs = [
    { id: 'overview', label: 'Overview', icon: '📊' },
    { id: 'progress', label: 'Degree Progress', icon: '🎓' },
    { id: 'planning', label: 'Planning', icon: '📅' },
    { id: 'risks', label: 'Risk Assessment', icon: '⚠️' }
  ];

  return (
    <div className={`${className}`}>
      {/* Header */}
      <div className="mb-6 p-6 bg-white rounded-lg shadow-sm border">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">
              Academic Advisor Dashboard
            </h1>
            <p className="text-gray-600">
              {student.name} • {student.primary_major} Major • {student.current_semester}
            </p>
          </div>
          
          <div className="flex items-center space-x-3">
            <select 
              value={timeRange}
              onChange={(e) => setTimeRange(e.target.value as any)}
              className="px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="semester">This Semester</option>
              <option value="year">This Year</option>
              <option value="all">All Time</option>
            </select>
            
            <button className="px-4 py-2 bg-blue-600 text-white font-medium rounded-lg hover:bg-blue-700 transition-colors">
              Schedule Meeting
            </button>
          </div>
        </div>

        {/* Tab Navigation */}
        <div className="flex space-x-1 bg-gray-100 rounded-lg p-1">
          {tabs.map(tab => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id as any)}
              className={`flex items-center space-x-2 px-4 py-2 font-medium text-sm rounded-md transition-all ${
                activeTab === tab.id 
                  ? 'bg-white text-blue-600 shadow-sm' 
                  : 'text-gray-600 hover:text-gray-900'
              }`}
            >
              <span>{tab.icon}</span>
              <span>{tab.label}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Tab Content */}
      {activeTab === 'overview' && (
        <div className="space-y-6">
          {/* Key Metrics */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <MetricCard
              title="Overall Progress"
              value={`${Math.round(dashboardData.degree_progress.overall_completion * 100)}%`}
              color="blue"
              trend="up"
              trendValue="5% this semester"
              subtitle={`${dashboardData.degree_progress.credits_completed}/${dashboardData.degree_progress.credits_required} credits`}
            />
            
            <MetricCard
              title="Current GPA"
              value={student.cumulative_gpa?.toFixed(2) || "N/A"}
              color="green"
              trend="stable"
              trendValue="0.1 this semester"
              subtitle="Above major average"
            />
            
            <MetricCard
              title="Graduation Timeline"
              value={dashboardData.graduation_outlook.graduation_probability > 0.9 ? "On Track" : "At Risk"}
              color={dashboardData.graduation_outlook.graduation_probability > 0.9 ? "green" : "yellow"}
              subtitle={dashboardData.graduation_outlook.projected_graduation_semester}
            />
            
            <MetricCard
              title="Current Load"
              value={`${dashboardData.current_semester_analysis.credit_load} credits`}
              color={
                dashboardData.current_semester_analysis.workload_assessment === "heavy" ? "red" :
                dashboardData.current_semester_analysis.workload_assessment === "moderate" ? "yellow" : "green"
              }
              subtitle={`${dashboardData.current_semester_analysis.workload_assessment} workload`}
            />
          </div>

          {/* Quick Actions & Alerts */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Priority Recommendations */}
            <div className="bg-white rounded-lg shadow-sm border p-6">
              <h3 className="text-lg font-semibold text-gray-900 mb-4">
                🎯 Priority Recommendations
              </h3>
              <div className="space-y-4">
                {dashboardData.recommendations
                  .filter(rec => rec.priority === 'high')
                  .slice(0, 3)
                  .map((rec, index) => (
                    <div key={index} className="p-4 border-l-4 border-l-orange-400 bg-orange-50 rounded-r-lg">
                      <h4 className="font-medium text-orange-900 mb-1">{rec.title}</h4>
                      <p className="text-sm text-orange-700 mb-2">{rec.description}</p>
                      {rec.deadline && (
                        <p className="text-xs text-orange-600 font-medium">⏰ {rec.deadline}</p>
                      )}
                    </div>
                  ))}
              </div>
            </div>

            {/* Recent Activity & Trends */}
            <div className="bg-white rounded-lg shadow-sm border p-6">
              <h3 className="text-lg font-semibold text-gray-900 mb-4">
                📈 Academic Trends
              </h3>
              <div className="space-y-4">
                <div className="flex items-center justify-between p-3 bg-green-50 rounded-lg">
                  <div>
                    <p className="font-medium text-green-900">Strong Prerequisite Performance</p>
                    <p className="text-sm text-green-700">Excellent foundation for advanced courses</p>
                  </div>
                  <span className="text-2xl">📚</span>
                </div>
                
                <div className="flex items-center justify-between p-3 bg-blue-50 rounded-lg">
                  <div>
                    <p className="font-medium text-blue-900">Consistent Credit Load</p>
                    <p className="text-sm text-blue-700">Maintaining sustainable pace</p>
                  </div>
                  <span className="text-2xl">⚖️</span>
                </div>
                
                <div className="flex items-center justify-between p-3 bg-yellow-50 rounded-lg">
                  <div>
                    <p className="font-medium text-yellow-900">Course Selection Opportunity</p>
                    <p className="text-sm text-yellow-700">Consider technical electives soon</p>
                  </div>
                  <span className="text-2xl">💡</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {activeTab === 'progress' && (
        <div className="space-y-6">
          {/* Degree Progress Overview */}
          <div className="bg-white rounded-lg shadow-sm border p-6">
            <h3 className="text-lg font-semibold text-gray-900 mb-6">
              🎓 Degree Requirements Progress
            </h3>
            
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
              {/* Major Requirements */}
              <div>
                <h4 className="font-medium text-gray-800 mb-4">
                  {student.primary_major} Major Requirements
                </h4>
                <div className="space-y-4">
                  {dashboardData.degree_progress.major_progress.map((req, index) => (
                    <div key={index}>
                      <ProgressBar
                        label={req.requirement_name}
                        current={req.satisfied_by.length}
                        total={req.satisfied_by.length + req.remaining_options.length}
                        color={
                          req.status === 'completed' ? 'green' :
                          req.status === 'in_progress' ? 'blue' :
                          req.status === 'at_risk' ? 'red' : 'yellow'
                        }
                      />
                      
                      <div className="ml-4 space-y-2 text-sm">
                        {req.satisfied_by.length > 0 && (
                          <div>
                            <span className="text-green-600 font-medium">✅ Completed: </span>
                            <span className="text-gray-700">{req.satisfied_by.join(', ')}</span>
                          </div>
                        )}
                        
                        {req.remaining_options.length > 0 && (
                          <div>
                            <span className="text-blue-600 font-medium">📋 Remaining: </span>
                            <span className="text-gray-700">{req.remaining_options.slice(0, 3).join(', ')}</span>
                            {req.remaining_options.length > 3 && (
                              <span className="text-gray-500"> (+{req.remaining_options.length - 3} more)</span>
                            )}
                          </div>
                        )}
                        
                        {req.notes && (
                          <div>
                            <span className="text-gray-500 font-medium">💭 Note: </span>
                            <span className="text-gray-600">{req.notes}</span>
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Credit Progress */}
              <div>
                <h4 className="font-medium text-gray-800 mb-4">Credit Progress</h4>
                
                <ProgressBar
                  label="Total Degree Credits"
                  current={dashboardData.degree_progress.credits_completed + dashboardData.degree_progress.credits_in_progress}
                  total={dashboardData.degree_progress.credits_required}
                  color="blue"
                />
                
                <div className="mt-4 space-y-3 text-sm">
                  <div className="flex justify-between">
                    <span className="text-gray-600">Credits Completed:</span>
                    <span className="font-medium">{dashboardData.degree_progress.credits_completed}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-600">Credits In Progress:</span>
                    <span className="font-medium">{dashboardData.degree_progress.credits_in_progress}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-600">Credits Remaining:</span>
                    <span className="font-medium">
                      {dashboardData.degree_progress.credits_required - 
                       dashboardData.degree_progress.credits_completed - 
                       dashboardData.degree_progress.credits_in_progress}
                    </span>
                  </div>
                  <div className="flex justify-between border-t pt-2 mt-2">
                    <span className="text-gray-800 font-medium">Graduation Timeline:</span>
                    <span className={`font-medium ${
                      dashboardData.degree_progress.on_track ? 'text-green-600' : 'text-yellow-600'
                    }`}>
                      {dashboardData.degree_progress.projected_graduation}
                    </span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {activeTab === 'planning' && (
        <div className="space-y-6">
          <div className="bg-white rounded-lg shadow-sm border p-6">
            <h3 className="text-lg font-semibold text-gray-900 mb-6">
              📅 Academic Planning & Timeline
            </h3>
            
            {/* Current Semester Analysis */}
            <div className="mb-8">
              <h4 className="font-medium text-gray-800 mb-4">Current Semester Analysis</h4>
              
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <MetricCard
                  title="Credit Load"
                  value={dashboardData.current_semester_analysis.credit_load}
                  color={
                    dashboardData.current_semester_analysis.workload_assessment === "heavy" ? "red" :
                    dashboardData.current_semester_analysis.workload_assessment === "moderate" ? "yellow" : "green"
                  }
                  subtitle={`${dashboardData.current_semester_analysis.workload_assessment} workload`}
                />
                
                <MetricCard
                  title="Enrolled Courses"
                  value={dashboardData.current_semester_analysis.enrolled_courses.length}
                  color="blue"
                  subtitle="active registrations"
                />
                
                <MetricCard
                  title="Schedule Health"
                  value={dashboardData.current_semester_analysis.schedule_conflicts.length === 0 ? "Good" : "Issues"}
                  color={dashboardData.current_semester_analysis.schedule_conflicts.length === 0 ? "green" : "red"}
                  subtitle={`${dashboardData.current_semester_analysis.schedule_conflicts.length} conflicts`}
                />
              </div>
              
              {/* Opportunities & Risks */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mt-6">
                <div>
                  <h5 className="font-medium text-green-800 mb-3">🌟 Opportunities</h5>
                  <div className="space-y-2">
                    {dashboardData.current_semester_analysis.opportunities.map((opp, idx) => (
                      <div key={idx} className="p-3 bg-green-50 rounded-lg border-l-4 border-l-green-400">
                        <p className="text-sm text-green-800">{opp}</p>
                      </div>
                    ))}
                  </div>
                </div>
                
                <div>
                  <h5 className="font-medium text-yellow-800 mb-3">⚠️ Areas of Attention</h5>
                  <div className="space-y-2">
                    {dashboardData.current_semester_analysis.academic_risks.map((risk, idx) => (
                      <div key={idx} className="p-3 bg-yellow-50 rounded-lg border-l-4 border-l-yellow-400">
                        <p className="text-sm text-yellow-800">{risk}</p>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>

            {/* Critical Path Courses */}
            <div>
              <h4 className="font-medium text-gray-800 mb-4">📍 Critical Path to Graduation</h4>
              <div className="bg-blue-50 rounded-lg p-4 border-l-4 border-l-blue-400">
                <p className="text-blue-800 font-medium mb-2">
                  Key courses that must be completed for on-time graduation:
                </p>
                <div className="flex flex-wrap gap-2">
                  {dashboardData.graduation_outlook.critical_path_courses.map((course, idx) => (
                    <span key={idx} className="px-3 py-1 bg-blue-100 text-blue-800 rounded-full text-sm font-medium">
                      {course}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {activeTab === 'risks' && (
        <div className="space-y-6">
          <div className="bg-white rounded-lg shadow-sm border p-6">
            <h3 className="text-lg font-semibold text-gray-900 mb-6">
              ⚠️ Risk Assessment & Mitigation
            </h3>
            
            {/* Risk Overview */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
              <MetricCard
                title="Graduation Probability"
                value={`${Math.round(dashboardData.graduation_outlook.graduation_probability * 100)}%`}
                color={dashboardData.graduation_outlook.graduation_probability > 0.9 ? "green" : 
                       dashboardData.graduation_outlook.graduation_probability > 0.7 ? "yellow" : "red"}
                subtitle="on-time completion"
              />
              
              <MetricCard
                title="Identified Risks"
                value={dashboardData.graduation_outlook.potential_delays.length}
                color={dashboardData.graduation_outlook.potential_delays.length === 0 ? "green" : 
                       dashboardData.graduation_outlook.potential_delays.length <= 2 ? "yellow" : "red"}
                subtitle="requiring attention"
              />
              
              <MetricCard
                title="Acceleration Options"
                value={dashboardData.graduation_outlook.acceleration_opportunities.length}
                color="purple"
                subtitle="available pathways"
              />
            </div>

            {/* Risk Details */}
            <div className="space-y-4">
              <h4 className="font-medium text-gray-800">Risk Factors & Mitigation Strategies</h4>
              
              {dashboardData.graduation_outlook.potential_delays.length === 0 ? (
                <div className="p-6 bg-green-50 rounded-lg border text-center">
                  <span className="text-4xl mb-2 block">✅</span>
                  <p className="text-green-800 font-medium">No significant risks identified</p>
                  <p className="text-green-700 text-sm">Student is on track for timely graduation</p>
                </div>
              ) : (
                <div className="space-y-4">
                  {dashboardData.graduation_outlook.potential_delays.map((risk, idx) => (
                    <RiskIndicator
                      key={idx}
                      risk={risk}
                      onActionClick={(riskId) => console.log(`Taking action on risk: ${riskId}`)}
                    />
                  ))}
                </div>
              )}
            </div>

            {/* Acceleration Opportunities */}
            {dashboardData.graduation_outlook.acceleration_opportunities.length > 0 && (
              <div className="mt-8">
                <h4 className="font-medium text-gray-800 mb-4">🚀 Acceleration Opportunities</h4>
                <div className="space-y-3">
                  {dashboardData.graduation_outlook.acceleration_opportunities.map((opp, idx) => (
                    <div key={idx} className="p-4 bg-purple-50 rounded-lg border-l-4 border-l-purple-400">
                      <p className="text-purple-800">{opp}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Action Items Footer */}
      <div className="mt-8 p-6 bg-gray-50 rounded-lg border">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="font-semibold text-gray-900">Next Actions Required</h3>
            <p className="text-sm text-gray-600">
              {dashboardData.recommendations.filter(r => r.follow_up_needed).length} items need follow-up
            </p>
          </div>
          <div className="flex space-x-3">
            <button className="px-4 py-2 bg-blue-600 text-white font-medium rounded-lg hover:bg-blue-700 transition-colors">
              Generate Action Plan
            </button>
            <button className="px-4 py-2 border border-gray-300 text-gray-700 font-medium rounded-lg hover:bg-white transition-colors">
              Export Report
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}