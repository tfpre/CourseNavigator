import { NextRequest, NextResponse } from 'next/server';

const FASTAPI_BASE_URL = process.env.FASTAPI_BASE_URL || 'http://localhost:8000';

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    
    // Validate required parameters
    if (!body.course_code) {
      throw new Error('course_code is required');
    }

    const requestData = {
      course_code: body.course_code,
      num_recommendations: body.num_recommendations || 5
    };

    // Validate num_recommendations range
    if (requestData.num_recommendations < 1 || requestData.num_recommendations > 20) {
      throw new Error('num_recommendations must be between 1 and 20');
    }

    const response = await fetch(`${FASTAPI_BASE_URL}/api/course_recommendations`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(requestData),
    });

    if (!response.ok) {
      throw new Error(`FastAPI course recommendations request failed: ${response.status}`);
    }

    const data = await response.json();
    
    return NextResponse.json(data);

  } catch (error) {
    console.error('Course recommendations API error:', error);
    
    return NextResponse.json(
      {
        success: false,
        error: {
          code: 'COURSE_RECOMMENDATIONS_API_ERROR',
          message: error instanceof Error ? error.message : 'Unknown error occurred',
          details: { timestamp: new Date().toISOString() }
        }
      },
      { status: 500 }
    );
  }
}