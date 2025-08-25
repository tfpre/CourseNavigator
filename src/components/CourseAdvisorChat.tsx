// Course Advisor Chat - Conversational AI Interface with SSE Streaming
// Implements friend's newfix.md specifications: <500ms perceived latency, multi-context responses

'use client';

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Loader2, Send, User, Bot, AlertCircle, Info } from 'lucide-react';
import { Alert, AlertDescription } from '@/components/ui/alert';

// Type definitions matching the FastAPI models
interface ChatMessage {
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: string;
  metadata?: Record<string, any>;
}

interface ChatStreamChunk {
  chunk_id: number;
  content: string;
  chunk_type: 'token' | 'course_highlight' | 'context_info' | 'thinking' | 'error' | 'done';
  metadata: Record<string, any>;
  timestamp: string;
}

interface StudentProfile {
  student_id: string;
  major?: string;
  year?: 'freshman' | 'sophomore' | 'junior' | 'senior' | 'graduate';
  completed_courses: string[];
  current_courses: string[];
  interests: string[];
}

interface CourseAdvisorChatProps {
  initialProfile?: StudentProfile;
  onCourseRecommendation?: (courseCode: string, reasoning: string) => void;
  className?: string;
}

const CourseAdvisorChat: React.FC<CourseAdvisorChatProps> = ({
  initialProfile,
  onCourseRecommendation,
  className = ''
}) => {
  // State management
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [currentMessage, setCurrentMessage] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamingContent, setStreamingContent] = useState('');
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [contextInfo, setContextInfo] = useState<string>('');
  const [recommendedCourses, setRecommendedCourses] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [lastResponseProvenance, setLastResponseProvenance] = useState<ChatMessage['provenance'] | null>(null);
  
  // Student profile management
  const [studentProfile, setStudentProfile] = useState<StudentProfile>(
    initialProfile || {
      student_id: `demo_student_${Date.now()}`,
      major: 'Computer Science',
      year: 'sophomore',
      completed_courses: ['CS 1110', 'MATH 1910'],
      current_courses: ['CS 2110'],
      interests: ['Machine Learning', 'Software Engineering']
    }
  );

  // Refs for auto-scrolling and EventSource management
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const eventSourceRef = useRef<EventSource | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Auto-scroll to bottom when new messages arrive
  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, streamingContent, scrollToBottom]);

  // Cleanup EventSource on unmount
  useEffect(() => {
    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }
    };
  }, []);

  // Handle SSE streaming chat request
  const sendChatMessage = async (message: string) => {
    if (!message.trim() || isStreaming) return;

    setError(null);
    setCurrentMessage('');
    setContextInfo('');
    setStreamingContent('');
    setIsStreaming(true);

    // Add user message to chat
    const userMessage: ChatMessage = {
      role: 'user',
      content: message.trim(),
      timestamp: new Date().toISOString()
    };
    setMessages(prev => [...prev, userMessage]);

    try {
      // Prepare chat request
      const chatRequest = {
        message: message.trim(),
        conversation_id: conversationId,
        student_profile: studentProfile,
        context_preferences: {
          include_prerequisites: true,
          include_professor_ratings: true,
          include_difficulty_info: true,
          include_enrollment_data: true,
          include_similar_courses: true,
          include_conflict_detection: true
        },
        stream: true,
        max_recommendations: 5
      };

      // Establish SSE connection
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'text/event-stream',
          'Cache-Control': 'no-cache'
        },
        body: JSON.stringify(chatRequest)
      });

      if (!response.ok) {
        throw new Error(`Chat request failed: ${response.status}`);
      }

      if (!response.body) {
        throw new Error('No response body received');
      }

      // Process SSE stream
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let assistantResponse = '';
      let chunkBuffer = '';

      while (true) {
        const { done, value } = await reader.read();
        
        if (done) break;

        chunkBuffer += decoder.decode(value, { stream: true });
        
        // Process complete SSE events
        const events = chunkBuffer.split('\n\n');
        chunkBuffer = events.pop() || ''; // Keep incomplete event in buffer

        for (const event of events) {
          if (event.trim() === '') continue;

          try {
            // Parse SSE event
            const dataMatch = event.match(/^data: (.+)$/m);
            if (!dataMatch) continue;

            const eventData = dataMatch[1];
            if (eventData === '{}') continue; // Empty close event

            const chunk: ChatStreamChunk = JSON.parse(eventData);
            
            // Handle different chunk types
            switch (chunk.chunk_type) {
              case 'context_info':
                if (chunk.metadata.status) {
                  setContextInfo(`${chunk.metadata.status}...`);
                }
                break;

              case 'token':
                assistantResponse += chunk.content;
                setStreamingContent(assistantResponse);
                break;

              case 'course_highlight':
                // Course codes highlighted in the response
                if (chunk.metadata.course_code) {
                  setRecommendedCourses(prev => [...Array.from(new Set([...prev, chunk.metadata.course_code]))]);
                  
                  // Trigger callback for course recommendation
                  if (onCourseRecommendation) {
                    onCourseRecommendation(chunk.metadata.course_code, chunk.metadata.reasoning || '');
                  }
                }
                break;

              case 'error':
                setError(chunk.content || 'An error occurred during processing');
                break;

              case 'done':
                // Stream completed - finalize message
                const finalMessage: ChatMessage = {
                  role: 'assistant',
                  content: assistantResponse,
                  timestamp: new Date().toISOString(),
                  metadata: chunk.metadata,
                  provenance: chunk.metadata.provenance_info || undefined
                };

                setMessages(prev => [...prev, finalMessage]);
                
                // Store provenance for display
                if (chunk.metadata.provenance_info) {
                  setLastResponseProvenance(chunk.metadata.provenance_info);
                }
                
                // Update conversation state
                if (chunk.metadata.conversation_id) {
                  setConversationId(chunk.metadata.conversation_id);
                }
                
                if (chunk.metadata.recommended_courses) {
                  setRecommendedCourses(chunk.metadata.recommended_courses.map((rec: any) => rec.course_code));
                }
                
                setContextInfo('');
                setStreamingContent('');
                setIsStreaming(false);
                return;
            }
          } catch (parseError) {
            console.error('Failed to parse SSE chunk:', parseError);
          }
        }
      }

    } catch (error) {
      console.error('Chat stream error:', error);
      setError(error instanceof Error ? error.message : 'Failed to send message');
      setIsStreaming(false);
      setStreamingContent('');
      setContextInfo('');
    }
  };

  // Handle form submission
  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (currentMessage.trim()) {
      sendChatMessage(currentMessage);
    }
  };

  // Handle quick question buttons
  const handleQuickQuestion = (question: string) => {
    sendChatMessage(question);
  };

  // Render course code highlights in message content
  const renderMessageContent = (content: string) => {
    // Regex to find course codes like **CS 2110**
    const courseCodeRegex = /\*\*([A-Z]{2,4}\s+\d{4})\*\*/g;
    
    const parts = content.split(courseCodeRegex);
    return parts.map((part, index) => {
      // Every odd index is a course code match
      if (index % 2 === 1) {
        return (
          <Badge key={index} variant="secondary" className="mx-1">
            {part}
          </Badge>
        );
      }
      return part;
    });
  };

  return (
    <div className={`flex flex-col h-full max-h-[600px] ${className}`}>
      <Card className="flex-1 flex flex-col">
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2">
            <Bot className="h-5 w-5" />
            Cornell Course Advisor
          </CardTitle>
          {studentProfile && (
            <div className="text-sm text-muted-foreground">
              {studentProfile.major} • {studentProfile.year} • {studentProfile.completed_courses.length} courses completed
            </div>
          )}
        </CardHeader>

        <CardContent className="flex-1 flex flex-col space-y-4">
          {/* Error Alert */}
          {error && (
            <Alert variant="destructive">
              <AlertCircle className="h-4 w-4" />
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}

          {/* Messages Container */}
          <div className="flex-1 overflow-y-auto space-y-4 pr-2">
            {messages.length === 0 && (
              <div className="text-center text-muted-foreground py-8">
                <Bot className="h-12 w-12 mx-auto mb-4 opacity-50" />
                <p className="mb-2">Hi! I'm your Cornell Course Advisor.</p>
                <p>Ask me about course recommendations, prerequisites, or academic planning.</p>
              </div>
            )}

            {messages.map((message, index) => (
              <div key={index} className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                <div className={`max-w-[80%] rounded-lg px-4 py-2 ${
                  message.role === 'user' 
                    ? 'bg-blue-500 text-white' 
                    : 'bg-muted text-foreground'
                }`}>
                  <div className="flex items-start gap-2">
                    {message.role === 'assistant' && <Bot className="h-4 w-4 mt-1 flex-shrink-0" />}
                    {message.role === 'user' && <User className="h-4 w-4 mt-1 flex-shrink-0" />}
                    <div className="flex-1">
                      <div className="text-sm">
                        {renderMessageContent(message.content)}
                      </div>
                      <div className="text-xs opacity-70 mt-1">
                        {new Date(message.timestamp).toLocaleTimeString()}
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            ))}

            {/* Streaming Message */}
            {isStreaming && (
              <div className="flex justify-start">
                <div className="max-w-[80%] rounded-lg px-4 py-2 bg-muted text-foreground">
                  <div className="flex items-start gap-2">
                    <Bot className="h-4 w-4 mt-1 flex-shrink-0" />
                    <div className="flex-1">
                      <div className="text-sm">
                        {streamingContent && renderMessageContent(streamingContent)}
                        {!streamingContent && contextInfo && (
                          <div className="flex items-center gap-2 text-muted-foreground">
                            <Loader2 className="h-3 w-3 animate-spin" />
                            {contextInfo}
                          </div>
                        )}
                        <span className="inline-block w-2 h-4 bg-current animate-pulse ml-1" />
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>

          {/* Quick Questions */}
          {messages.length === 0 && (
            <div className="space-y-2">
              <p className="text-sm text-muted-foreground">Quick questions:</p>
              <div className="flex flex-wrap gap-2">
                <Button 
                  variant="outline" 
                  size="sm" 
                  onClick={() => handleQuickQuestion("What CS courses should I take next semester?")}
                  disabled={isStreaming}
                >
                  CS course recommendations
                </Button>
                <Button 
                  variant="outline" 
                  size="sm" 
                  onClick={() => handleQuickQuestion("What are the prerequisites for CS 3110?")}
                  disabled={isStreaming}
                >
                  Check prerequisites  
                </Button>
                <Button 
                  variant="outline" 
                  size="sm" 
                  onClick={() => handleQuickQuestion("Which courses have the best professors?")}
                  disabled={isStreaming}
                >
                  Professor ratings
                </Button>
              </div>
            </div>
          )}

          {/* Context Info */}
          {contextInfo && (
            <Alert>
              <Info className="h-4 w-4" />
              <AlertDescription>{contextInfo}</AlertDescription>
            </Alert>
          )}

          {/* Recommended Courses */}
          {recommendedCourses.length > 0 && (
            <div className="border-t pt-3">
              <p className="text-sm text-muted-foreground mb-2">Recommended courses from this conversation:</p>
              <div className="flex flex-wrap gap-1">
                {recommendedCourses.map(courseCode => (
                  <Badge key={courseCode} variant="outline">
                    {courseCode}
                  </Badge>
                ))}
              </div>
            </div>
          )}

          {/* Data Provenance Display */}
          {lastResponseProvenance && lastResponseProvenance.data_freshness && (
            <div className="border-t pt-3">
              <p className="text-xs text-muted-foreground mb-2 flex items-center gap-1">
                <Info className="h-3 w-3" />
                Data sources used in last response:
              </p>
              <div className="flex flex-wrap gap-1">
                {Object.entries(lastResponseProvenance.data_freshness).map(([source, freshness]) => (
                  <Badge key={source} variant="secondary" className="text-xs px-2 py-1">
                    {freshness}
                  </Badge>
                ))}
              </div>
              
              {/* Professor Selection Reasons */}
              {lastResponseProvenance.professor_selections && Object.keys(lastResponseProvenance.professor_selections).length > 0 && (
                <div className="mt-2">
                  <p className="text-xs text-muted-foreground mb-1">Professor selection criteria:</p>
                  <div className="flex flex-wrap gap-1">
                    {Object.entries(lastResponseProvenance.professor_selections).map(([course, reason]) => (
                      <Badge key={course} variant="outline" className="text-xs px-2 py-1" title={`${course}: ${reason}`}>
                        {course}: {reason}
                      </Badge>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Input Form */}
          <form onSubmit={handleSubmit} className="flex gap-2 border-t pt-3">
            <Input
              ref={inputRef}
              value={currentMessage}
              onChange={(e) => setCurrentMessage(e.target.value)}
              placeholder="Ask about courses, prerequisites, or academic planning..."
              disabled={isStreaming}
              className="flex-1"
            />
            <Button 
              type="submit" 
              disabled={!currentMessage.trim() || isStreaming}
              size="sm"
            >
              {isStreaming ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Send className="h-4 w-4" />
              )}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
};

export default CourseAdvisorChat;