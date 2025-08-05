import { NextRequest, NextResponse } from 'next/server';

const FASTAPI_BASE_URL = process.env.FASTAPI_BASE_URL || 'http://localhost:8000';

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    
    // Validate required parameters
    if (!body.target_course) {
      throw new Error('target_course is required');
    }

    const requestData = {
      target_course: body.target_course,
      completed_courses: body.completed_courses || [],
      num_alternatives: body.num_alternatives || 3
    };

    // Validate num_alternatives range
    if (requestData.num_alternatives < 1 || requestData.num_alternatives > 10) {
      throw new Error('num_alternatives must be between 1 and 10');
    }

    const response = await fetch(`${FASTAPI_BASE_URL}/api/alternative_paths`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(requestData),
    });

    if (!response.ok) {
      throw new Error(`FastAPI alternative paths request failed: ${response.status}`);
    }

    const data = await response.json();
    
    return NextResponse.json(data);

  } catch (error) {
    console.error('Alternative paths API error:', error);
    
    return NextResponse.json(
      {
        success: false,
        error: {
          code: 'ALTERNATIVE_PATHS_API_ERROR',
          message: error instanceof Error ? error.message : 'Unknown error occurred',
          details: { timestamp: new Date().toISOString() }
        }
      },
      { status: 500 }
    );
  }
}