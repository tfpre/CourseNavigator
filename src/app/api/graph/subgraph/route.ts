import { NextRequest, NextResponse } from 'next/server';

// Mock student filtering for demonstration (until Python gateway implements it)
function applyMockStudentFiltering(data: any, requestData: any) {
  const { major, completed_courses, current_courses } = requestData;
  
  // Student-specific course relevance by major
  const majorSubjects: { [key: string]: string[] } = {
    "Computer Science": ["CS", "ENGRD", "MATH", "ECE"],
    "Mathematics": ["MATH", "CS", "PHYS", "ORIE"],
    "Electrical Engineering": ["ECE", "ENGRD", "MATH", "PHYS", "CS"]
  };
  
  const relevantSubjects = majorSubjects[major] || ["CS", "MATH"];
  const completedSet = new Set(completed_courses || []);
  const currentSet = new Set(current_courses || []);
  
  // Filter courses based on student relevance
  const filteredCourses = data.data?.courses?.map((course: any) => {
    // Calculate student-specific metadata
    const isCompleted = completedSet.has(course.course_code);
    const isInProgress = currentSet.has(course.course_code);
    const isRelevantToMajor = relevantSubjects.includes(course.subject);
    const isCore = ["CS", "ENGRD"].includes(course.subject) && major === "Computer Science";
    
    // Adjust centrality score based on student relevance
    let personalizedScore = course.centrality_score || 0;
    if (isCore) personalizedScore *= 1.5;  // Boost core courses
    if (isCompleted) personalizedScore *= 0.1;  // De-emphasize completed
    if (isInProgress) personalizedScore *= 0.3; // De-emphasize current
    if (!isRelevantToMajor) personalizedScore *= 0.2; // De-emphasize irrelevant
    
    return {
      ...course,
      centrality_score: personalizedScore,
      student_metadata: {
        status: isCompleted ? 'completed' : isInProgress ? 'in_progress' : 'available',
        relevant_to_major: isRelevantToMajor,
        is_core_requirement: isCore,
        personalized_priority: personalizedScore
      }
    };
  }).filter((course: any) => 
    // Keep completed/current courses for context, plus most relevant available courses
    completedSet.has(course.course_code) || 
    currentSet.has(course.course_code) ||
    relevantSubjects.includes(course.subject)
  ).sort((a: any, b: any) => b.centrality_score - a.centrality_score) // Sort by personalized score
  .slice(0, requestData.max_nodes); // Respect max_nodes limit
  
  // Filter prerequisites to only include relationships between filtered courses
  const courseIds = new Set(filteredCourses.map((c: any) => c.course_code));
  const filteredPrerequisites = data.data?.prerequisites?.filter((prereq: any) =>
    courseIds.has(prereq.from_course) && courseIds.has(prereq.to_course)
  ) || [];
  
  return {
    ...data,
    data: {
      ...data.data,
      courses: filteredCourses,
      prerequisites: filteredPrerequisites,
      personalization: {
        student_id: requestData.student_id,
        major: requestData.major,
        completed_courses: completed_courses || [],
        current_courses: current_courses || [],
        filtering_applied: true,
        relevant_subjects: relevantSubjects,
        courses_filtered: filteredCourses.length,
        personalization_boost: "Core courses boosted by 50%, irrelevant courses reduced by 80%"
      }
    },
    metadata: {
      ...data.metadata,
      personalized: true,
      filtering_method: "mock_student_centric",
      demo_note: "Real implementation will use GraphService.filter_for_student() with Neo4j"
    }
  };
}

interface SubgraphRequest {
  max_nodes?: number;
  max_edges?: number;
  include_centrality?: boolean;
  include_communities?: boolean;
  filter_by_subject?: string[];
  fields?: string[]; // NEW: Selective field loading for performance optimization
  
  // NEW: Student-centric personalization parameters  
  student_id?: string;
  major?: string;
  completed_courses?: string[];
  current_courses?: string[];
  personalized?: boolean; // Toggle between global and personalized view
}

export async function POST(request: NextRequest) {
  try {
    // Handle empty request bodies gracefully
    let body: SubgraphRequest = {};
    try {
      const rawBody = await request.text();
      if (rawBody.trim()) {
        body = JSON.parse(rawBody);
      }
    } catch (parseError) {
      console.warn('Failed to parse request body, using defaults:', parseError);
      body = {};
    }
    
    // Validate request parameters
    const requestData = {
      max_nodes: Math.min(Math.max(body.max_nodes || 50, 5), 200),
      max_edges: Math.min(Math.max(body.max_edges || 100, 10), 500),
      include_centrality: body.include_centrality !== false,
      include_communities: body.include_communities !== false,
      filter_by_subject: body.filter_by_subject || null,
      fields: body.fields || null, // Forward fields parameter for selective data loading
      
      // NEW: Student personalization parameters
      student_id: body.student_id || null,
      major: body.major || null,
      completed_courses: body.completed_courses || [],
      current_courses: body.current_courses || [],
      personalized: body.personalized || false
    };

    // Get gateway URL from environment (consistent with other APIs)
    const gatewayUrl = process.env.FASTAPI_BASE_URL || 'http://localhost:8000';
    
    // Forward request to Python gateway
    const response = await fetch(`${gatewayUrl}/api/graph/subgraph`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(requestData),
    });

    if (!response.ok) {
      console.error(`Gateway responded with status ${response.status}`);
      return NextResponse.json(
        { 
          success: false, 
          error: { 
            code: 'GATEWAY_ERROR',
            message: 'Failed to fetch subgraph data from gateway',
            details: { status: response.status }
          }
        },
        { status: response.status }
      );
    }

    let data = await response.json();
    
    // MOCK: Add student-centric filtering until Python gateway supports it
    if (requestData.personalized && requestData.major) {
      data = applyMockStudentFiltering(data, requestData);
    }
    
    return NextResponse.json(data);

  } catch (error) {
    console.error('Subgraph API error:', error);
    
    return NextResponse.json(
      {
        success: false,
        error: {
          code: 'API_ERROR',
          message: 'Failed to process subgraph request',
          details: { error: error instanceof Error ? error.message : 'Unknown error' }
        }
      },
      { status: 500 }
    );
  }
}

export async function GET() {
  // Default GET request for basic subgraph data
  return POST(new NextRequest('http://localhost:3000/api/graph/subgraph', {
    method: 'POST',
    body: JSON.stringify({
      max_nodes: 50,
      max_edges: 100,
      include_centrality: true,
      include_communities: true
    }),
    headers: { 'Content-Type': 'application/json' }
  }));
}