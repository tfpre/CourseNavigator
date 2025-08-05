import { NextRequest, NextResponse } from 'next/server';
import { PrerequisitePathRequest, PrerequisitePathResponse } from '../../../../types/api-types';

const FASTAPI_BASE_URL = process.env.FASTAPI_BASE_URL || 'http://localhost:8000';

export async function POST(request: NextRequest) {
  try {
    const body: PrerequisitePathRequest = await request.json();

    // Validate required fields
    if (!body.course_id || body.course_id.trim().length === 0) {
      return NextResponse.json(
        {
          success: false,
          error: {
            code: 'VALIDATION_ERROR',
            message: 'Course ID is required and cannot be empty',
          }
        } as PrerequisitePathResponse,
        { status: 400 }
      );
    }

    // Forward request to FastAPI gateway
    const response = await fetch(`${FASTAPI_BASE_URL}/api/prerequisite_path`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(body),
    });

    const data: PrerequisitePathResponse = await response.json();

    // Return the response with appropriate status code
    const status = data.success ? 200 : (response.status || 500);
    return NextResponse.json(data, { status });

  } catch (error) {
    console.error('Prerequisite path request failed:', error);
    
    return NextResponse.json(
      {
        success: false,
        error: {
          code: 'REQUEST_FAILED',
          message: 'Failed to get prerequisite path',
          details: { error: error instanceof Error ? error.message : 'Unknown error' }
        }
      } as PrerequisitePathResponse,
      { status: 500 }
    );
  }
}