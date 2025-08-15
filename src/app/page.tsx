import CourseRankings from '../components/CourseRankings';
import CourseGraphVisualization from '../components/CourseGraphVisualization';
import CourseSearch from '../components/CourseSearch';
import PrerequisiteChecker from '../components/PrerequisiteChecker';
import CourseAdvisorChat from '../components/CourseAdvisorChat';

export default function Home() {
  return (
    <main className="container mx-auto px-4 py-8">
      <div className="text-center mb-12">
        <h1 className="text-4xl font-bold text-cornell-red mb-4">
          Cornell Course Navigator
        </h1>
        <p className="text-lg text-gray-600 mb-8 max-w-2xl mx-auto">
          AI-powered course advisor with conversational intelligence. Get personalized recommendations 
          through natural language conversation, backed by graph algorithms and multi-context analysis.
        </p>
      </div>

      {/* Course Advisor Chat Section */}
      <section className="mb-12">
        <div className="max-w-5xl mx-auto">
          <h2 className="text-2xl font-bold text-gray-900 mb-4 text-center">
            AI Course Advisor Chat
          </h2>
          <p className="text-gray-600 text-center mb-6">
            Ask questions about courses, prerequisites, professor ratings, and academic planning. 
            Get personalized recommendations with real-time context from multiple sources.
          </p>
          <div className="h-[600px]">
            <CourseAdvisorChat />
          </div>
        </div>
      </section>

      {/* Course Search Section */}
      <section className="mb-12">
        <CourseSearch className="max-w-4xl mx-auto" />
      </section>

      {/* Prerequisite Checker Section */}
      <section className="mb-12">
        <PrerequisiteChecker className="max-w-4xl mx-auto" />
      </section>

      {/* Course Rankings Section */}
      <section className="mb-12">
        <CourseRankings className="max-w-4xl mx-auto" />
      </section>

      {/* Graph Visualization Section */}
      <section className="mb-12">
        <div className="max-w-6xl mx-auto">
          <h2 className="text-2xl font-bold text-gray-900 mb-4 text-center">
            Interactive Course Graph
          </h2>
          <p className="text-gray-600 text-center mb-6">
            Explore course relationships, communities, and centrality scores through an interactive network visualization
          </p>
          <CourseGraphVisualization />
        </div>
      </section>
        
      {/* Feature Cards */}
      <section className="mb-12">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div className="card">
            <h3 className="text-xl font-semibold mb-3 text-cornell-red">PageRank Analysis</h3>
            <p className="text-gray-600">
              Identify the most central courses in Cornell's curriculum using Google's PageRank algorithm 
              applied to prerequisite relationships.
            </p>
          </div>
          
          <div className="card">
            <h3 className="text-xl font-semibold mb-3 text-cornell-red">Community Detection</h3>
            <p className="text-gray-600">
              Discover natural course clusters and cross-departmental connections using 
              Louvain community detection algorithms.
            </p>
          </div>
          
          <div className="card">
            <h3 className="text-xl font-semibold mb-3 text-cornell-red">Path Optimization</h3>
            <p className="text-gray-600">
              Find optimal prerequisite paths and semester planning using shortest path 
              algorithms and constraint satisfaction.
            </p>
          </div>
        </div>
      </section>
        
      {/* Development Status */}
      <section className="mt-12 p-6 bg-blue-50 border border-blue-200 rounded-lg">
        <h2 className="text-2xl font-bold text-blue-800 mb-2 text-center">Phase 2: Conversational AI Complete ✅</h2>
        <p className="text-blue-700 text-center mb-4">
          ChatGPT-style course advisor with multi-context fusion, streaming responses, and personalized recommendations
        </p>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
          <div className="flex items-center space-x-2">
            <span className="w-2 h-2 bg-blue-500 rounded-full"></span>
            <span className="text-blue-700">Chat Orchestrator API</span>
          </div>
          <div className="flex items-center space-x-2">
            <span className="w-2 h-2 bg-blue-500 rounded-full"></span>
            <span className="text-blue-700">SSE Streaming</span>
          </div>
          <div className="flex items-center space-x-2">
            <span className="w-2 h-2 bg-blue-500 rounded-full"></span>
            <span className="text-blue-700">Professor Intelligence</span>
          </div>
          <div className="flex items-center space-x-2">
            <span className="w-2 h-2 bg-blue-500 rounded-full"></span>
            <span className="text-blue-700">Course Difficulty Data</span>
          </div>
          <div className="flex items-center space-x-2">
            <span className="w-2 h-2 bg-blue-500 rounded-full"></span>
            <span className="text-blue-700">Enrollment Predictions</span>
          </div>
          <div className="flex items-center space-x-2">
            <span className="w-2 h-2 bg-blue-500 rounded-full"></span>
            <span className="text-blue-700">Multi-Context Fusion</span>
          </div>
          <div className="flex items-center space-x-2">
            <span className="w-2 h-2 bg-blue-500 rounded-full"></span>
            <span className="text-blue-700">Token Budget Management</span>
          </div>
          <div className="flex items-center space-x-2">
            <span className="w-2 h-2 bg-blue-500 rounded-full"></span>
            <span className="text-blue-700">Conversation State</span>
          </div>
        </div>
        <div className="mt-4 p-3 bg-blue-100 rounded text-center">
          <p className="text-blue-800 font-medium">
            🎯 Friend's Architecture Implemented: &lt;500ms perceived latency with deterministic context fusion
          </p>
        </div>
        
        {/* Legacy Features Still Available */}
        <div className="mt-4 pt-4 border-t border-blue-200">
          <p className="text-sm text-blue-600 text-center mb-2 font-medium">Foundation Features (Still Available)</p>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
            <div className="flex items-center space-x-1">
              <span className="w-1.5 h-1.5 bg-green-400 rounded-full"></span>
              <span className="text-green-600">PageRank Analysis</span>
            </div>
            <div className="flex items-center space-x-1">
              <span className="w-1.5 h-1.5 bg-green-400 rounded-full"></span>
              <span className="text-green-600">Graph Visualization</span>
            </div>
            <div className="flex items-center space-x-1">
              <span className="w-1.5 h-1.5 bg-green-400 rounded-full"></span>
              <span className="text-green-600">Community Detection</span>
            </div>
            <div className="flex items-center space-x-1">
              <span className="w-1.5 h-1.5 bg-green-400 rounded-full"></span>
              <span className="text-green-600">Prerequisite Paths</span>
            </div>
          </div>
        </div>
      </section>
    </main>
  );
}