"use client";

import React, { useState, useEffect, useCallback, useMemo } from 'react';
import ReactFlow, {
  Node,
  Edge,
  addEdge,
  useNodesState,
  useEdgesState,
  Connection,
  Background,
  Controls,
  MiniMap,
  Panel,
  NodeProps,
  Handle,
  Position,
} from 'reactflow';
import 'reactflow/dist/style.css';
import Graph from 'graphology';
import { circular, random } from 'graphology-layout';
import forceAtlas2 from 'graphology-layout-forceatlas2';

// Performance optimization: Layout position cache
// Key: (layoutType,maxNodes,maxEdges,graphVersion) -> positions
type LayoutCacheKey = string;
interface CachedLayout {
  positions: { [nodeId: string]: { x: number; y: number } };
  timestamp: number;
  nodes: number;
  edges: number;
}

const layoutCache = new Map<LayoutCacheKey, CachedLayout>();
const CACHE_TTL = 10 * 60 * 1000; // 10 minutes

interface CourseData {
  course_code: string;
  course_title: string;
  subject: string;
  level: number;
  centrality_score?: number;
  community_id?: number;
}

interface GraphData {
  courses: CourseData[];
  prerequisites: {
    from_course: string;
    to_course: string;
    relationship_type: string;
  }[];
  centrality_scores?: Record<string, number>;
  communities?: Record<string, number>;
}

// Custom course node component
function CourseNode({ data, selected }: NodeProps) {
  const { course_code, course_title, subject, level, centrality_score, community_id } = data;
  
  // Color based on community or subject
  const getNodeColor = () => {
    if (community_id !== undefined) {
      const colors = [
        '#3B82F6', '#EF4444', '#10B981', '#F59E0B', '#8B5CF6',
        '#EC4899', '#06B6D4', '#84CC16', '#F97316', '#6366F1'
      ];
      return colors[community_id % colors.length];
    }
    
    // Fallback to subject-based colors
    const subjectColors: Record<string, string> = {
      'CS': '#3B82F6',
      'MATH': '#EF4444',
      'ENGRD': '#10B981',
      'ENGRI': '#F59E0B',
      'PHYS': '#8B5CF6',
      'CHEM': '#EC4899',
    };
    return subjectColors[subject] || '#6B7280';
  };

  // Size based on centrality score
  const getNodeSize = () => {
    if (centrality_score) {
      const baseSize = 40;
      const sizeMultiplier = Math.min(centrality_score * 1000, 3); // Cap the multiplier
      return baseSize + (sizeMultiplier * 20);
    }
    return 60;
  };

  const nodeSize = getNodeSize();
  const nodeColor = getNodeColor();

  return (
    <div
      className={`px-3 py-2 shadow-lg rounded-lg border-2 bg-white transition-all duration-200 ${
        selected ? 'border-blue-500 shadow-xl' : 'border-gray-200'
      }`}
      style={{
        width: nodeSize,
        height: nodeSize,
        borderColor: selected ? '#3B82F6' : nodeColor,
        borderWidth: selected ? 3 : 2,
      }}
    >
      <Handle type="target" position={Position.Top} className="w-2 h-2" />
      
      <div className="text-center h-full flex flex-col justify-center">
        <div 
          className="text-xs font-bold text-white px-1 py-0.5 rounded mb-1"
          style={{ backgroundColor: nodeColor }}
        >
          {course_code}
        </div>
        {nodeSize > 60 && (
          <div className="text-xs text-gray-600 leading-tight">
            {course_title.length > 20 ? course_title.substring(0, 17) + '...' : course_title}
          </div>
        )}
        {centrality_score && nodeSize > 80 && (
          <div className="text-xs text-gray-500 mt-1">
            {centrality_score.toFixed(3)}
          </div>
        )}
      </div>
      
      <Handle type="source" position={Position.Bottom} className="w-2 h-2" />
    </div>
  );
}

const nodeTypes = {
  course: CourseNode,
};

interface CourseGraphVisualizationProps {
  className?: string;
}

export default function CourseGraphVisualization({ className = "" }: CourseGraphVisualizationProps) {
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [graphData, setGraphData] = useState<GraphData | null>(null);
  const [showCommunities, setShowCommunities] = useState(true);
  const [showCentrality, setShowCentrality] = useState(true);
  const [selectedNode, setSelectedNode] = useState<string | null>(null);
  const [layoutType, setLayoutType] = useState<'circular' | 'force' | 'hierarchical'>('hierarchical');
  const [maxNodes, setMaxNodes] = useState(50);
  const [maxEdges, setMaxEdges] = useState(100);
  
  // NEW: Student personalization state
  const [personalized, setPersonalized] = useState(false);
  const [studentMajor, setStudentMajor] = useState("Computer Science");
  const [completedCourses, setCompletedCourses] = useState(["CS 1110", "MATH 1910"]);
  const [currentCourses, setCurrentCourses] = useState(["CS 2110", "MATH 2930"]);

  // Fetch graph subgraph data from the new endpoint
  const fetchGraphData = async () => {
    setLoading(true);
    setError(null);
    
    try {
      // Build fields array based on what's actually being displayed
      const fields = ['course_code', 'course_title', 'subject', 'level'];
      if (showCentrality) fields.push('centrality_scores');
      if (showCommunities) fields.push('communities');
      
      // Fetch subgraph data using optimized field selection and personalization
      const response = await fetch('/api/graph/subgraph', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          max_nodes: maxNodes,
          max_edges: maxEdges,
          include_centrality: showCentrality,
          include_communities: showCommunities,
          fields: fields, // Only request needed data (saves ~200KB when toggled off)
          
          // NEW: Student personalization parameters
          personalized: personalized,
          student_id: personalized ? "demo_student" : null,
          major: personalized ? studentMajor : null,
          completed_courses: personalized ? completedCourses : [],
          current_courses: personalized ? currentCourses : []
        }),
      });

      if (!response.ok) {
        const errorMsg = `Failed to fetch graph data (HTTP ${response.status})`;
        setError(errorMsg);
        console.error('Graph API error:', errorMsg);
        return;
      }

      const result = await response.json();
      
      if (!result.success) {
        const errorMsg = result.error?.message || 'Failed to load graph data';
        setError(errorMsg);
        console.error('Graph API error:', result.error);
        return;
      }

      // Process the data - it's already in the correct format
      const processedData: GraphData = {
        courses: result.data.courses,
        prerequisites: result.data.prerequisites,
        centrality_scores: result.data.centrality_scores,
        communities: result.data.communities,
      };

      // PRIORITY 3 FIX: Extract graph_version for cache invalidation
      const graphVersion = result.graph_version || 1;
      console.log(`Fetched graph data with version v${graphVersion}`);

      setGraphData(processedData);
      generateNodesAndEdges(processedData, graphVersion);

    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred');
      console.error('Graph data fetch error:', err);
    } finally {
      setLoading(false);
    }
  };

  // Generate deterministic layout using Graphology with caching for performance
  const generateLayout = (data: GraphData, graphVersion?: number) => {
    // PRIORITY 3 FIX: Include graph_version in cache key (Friend's recommendation)
    // This prevents stale layout cache after ETL updates
    const version = graphVersion || 1;
    const cacheKey = `v${version}-${layoutType}-${data.courses.length}-${data.prerequisites.length}-${showCentrality}-${showCommunities}`;
    
    // Check if we have a valid cached layout
    const cached = layoutCache.get(cacheKey);
    if (cached && Date.now() - cached.timestamp < CACHE_TTL) {
      console.log(`Using cached layout for ${cacheKey} (graph v${version})`);
      return cached.positions;
    }
    
    console.log(`Computing new layout for ${cacheKey} (graph v${version})`);
    
    // Create graphology graph
    const graph = new Graph();
    
    // Add nodes
    data.courses.forEach(course => {
      graph.addNode(course.course_code, {
        ...course,
        centrality_score: showCentrality ? course.centrality_score : undefined,
        community_id: showCommunities ? course.community_id : undefined,
      });
    });
    
    // Add edges
    data.prerequisites.forEach(prereq => {
      if (graph.hasNode(prereq.from_course) && graph.hasNode(prereq.to_course)) {
        graph.addEdge(prereq.from_course, prereq.to_course, {
          relationship_type: prereq.relationship_type,
        });
      }
    });
    
    // Apply layout algorithm based on user selection
    if (graph.order > 0) {
      if (layoutType === 'circular') {
        circular.assign(graph, { scale: 200 });
      } else if (layoutType === 'hierarchical') {
        // Hierarchical layout: left-to-right prerequisite flow with level grouping
        const nodes = graph.nodes();
        
        // Group courses by academic level (1000, 2000, 3000, 4000)
        const levelGroups: Record<number, string[]> = {};
        nodes.forEach(nodeId => {
          const nodeData = graph.getNodeAttributes(nodeId);
          const level = Math.floor(nodeData.level / 1000) * 1000;
          if (!levelGroups[level]) levelGroups[level] = [];
          levelGroups[level].push(nodeId);
        });
        
        // Calculate prerequisite depth for left-to-right positioning
        const getPrereqDepth = (nodeId: string, visited = new Set<string>()): number => {
          if (visited.has(nodeId)) return 0;
          visited.add(nodeId);
          
          const incomingEdges = graph.inboundEdges(nodeId);
          if (incomingEdges.length === 0) return 0;
          
          const prereqDepths = incomingEdges.map(edge => {
            const sourceNode = graph.source(edge);
            return getPrereqDepth(sourceNode, new Set(visited)) + 1;
          });
          
          return Math.max(...prereqDepths);
        };
        
        // Position nodes hierarchically
        const levelSpacing = 300;
        const depthSpacing = 200;
        const nodeSpacing = 80;
        
        Object.keys(levelGroups).forEach((levelStr, levelIndex) => {
          const level = parseInt(levelStr);
          const levelNodes = levelGroups[level];
          
          // Sort nodes by prerequisite depth (left to right)
          const nodesWithDepth = levelNodes.map(nodeId => ({
            nodeId,
            depth: getPrereqDepth(nodeId)
          })).sort((a, b) => a.depth - b.depth);
          
          // Position nodes within the level
          nodesWithDepth.forEach((nodeInfo, nodeIndex) => {
            const x = nodeInfo.depth * depthSpacing;
            const y = levelIndex * levelSpacing + (nodeIndex - levelNodes.length / 2) * nodeSpacing;
            
            graph.setNodeAttribute(nodeInfo.nodeId, 'x', x);
            graph.setNodeAttribute(nodeInfo.nodeId, 'y', y);
          });
        });
      } else {
        // Initialize with random positions for force-directed layout
        random.assign(graph, { scale: 100 });
        
        // Apply force-directed layout
        const settings = forceAtlas2.inferSettings(graph);
        forceAtlas2.assign(graph, {
          iterations: 100,
          settings: {
            ...settings,
            gravity: 1,
            scalingRatio: 10,
            strongGravityMode: true,
            outboundAttractionDistribution: false,
          }
        });
      }
    }
    
    // Cache the computed positions
    const positions: { [nodeId: string]: { x: number; y: number } } = {};
    graph.nodes().forEach(nodeId => {
      const attrs = graph.getNodeAttributes(nodeId);
      positions[nodeId] = { x: attrs.x || 0, y: attrs.y || 0 };
    });
    
    // Store in cache
    layoutCache.set(cacheKey, {
      positions,
      timestamp: Date.now(),
      nodes: data.courses.length,
      edges: data.prerequisites.length
    });
    
    // Clean up old cache entries (basic LRU)
    if (layoutCache.size > 50) {
      const entries = Array.from(layoutCache.entries());
      entries.sort((a, b) => a[1].timestamp - b[1].timestamp);
      entries.slice(0, 10).forEach(([key]) => layoutCache.delete(key));
    }
    
    return graph;
  };

  // Generate React Flow nodes and edges from graph data
  const generateNodesAndEdges = (data: GraphData, graphVersion?: number) => {
    // Sort courses by centrality score (most important first)
    const sortedCourses = [...data.courses].sort((a, b) => {
      const scoreA = a.centrality_score || 0;
      const scoreB = b.centrality_score || 0;
      return scoreB - scoreA;
    });
    
    // Limit to maxNodes most central courses
    const filteredCourses = sortedCourses.slice(0, maxNodes);
    const filteredCourseIds = new Set(filteredCourses.map(c => c.course_code));
    
    // Generate layout with filtered data and graph version for cache key
    const filteredData = { ...data, courses: filteredCourses };
    const layoutGraph = generateLayout(filteredData, graphVersion);
    
    // Create nodes with deterministic positions
    const newNodes: Node[] = filteredCourses.map((course) => {
      let nodeAttributes = { x: 0, y: 0 };
      try {
        if ((layoutGraph as any).hasNode && (layoutGraph as any).hasNode(course.course_code)) {
          const attrs = (layoutGraph as any).getNodeAttributes(course.course_code);
          nodeAttributes = typeof attrs === 'object' && attrs.x !== undefined ? attrs : { x: 0, y: 0 };
        }
      } catch (e) {
        // Fallback position if node doesn't exist
        nodeAttributes = { x: 0, y: 0 };
      }
      
      return {
        id: course.course_code,
        type: 'course',
        position: {
          x: nodeAttributes.x || 0,
          y: nodeAttributes.y || 0,
        },
        data: {
          ...course,
          centrality_score: showCentrality ? course.centrality_score : undefined,
          community_id: showCommunities ? course.community_id : undefined,
        },
      };
    });

    // Create edges - only between visible nodes and limit total count
    const validEdges = data.prerequisites
      .filter(prereq => 
        filteredCourseIds.has(prereq.from_course) && 
        filteredCourseIds.has(prereq.to_course)
      )
      .slice(0, maxEdges); // Limit total edge count
      
    const newEdges: Edge[] = validEdges.map((prereq, index) => ({
      id: `${prereq.from_course}-${prereq.to_course}`,
      source: prereq.from_course,
      target: prereq.to_course,
      type: 'smoothstep',
      animated: prereq.relationship_type === 'COREQUISITE',
      style: {
        stroke: prereq.relationship_type === 'COREQUISITE' ? '#F59E0B' : '#6B7280',
        strokeWidth: 2,
      },
      label: prereq.relationship_type === 'COREQUISITE' ? 'Co-req' : undefined,
      labelStyle: { fontSize: 10, fontWeight: 600 },
    }));

    setNodes(newNodes);
    setEdges(newEdges);
  };

  // Update nodes when display options change
  useEffect(() => {
    if (graphData) {
      generateNodesAndEdges(graphData);
    }
  }, [showCommunities, showCentrality, layoutType, maxNodes, maxEdges, graphData]);
  
  // Refetch data when personalization settings change
  useEffect(() => {
    fetchGraphData();
  }, [personalized, studentMajor, completedCourses, currentCourses]);

  const onConnect = useCallback(
    (params: Connection) => setEdges((eds) => addEdge(params, eds)),
    [setEdges]
  );

  const onNodeClick = useCallback((event: React.MouseEvent, node: Node) => {
    setSelectedNode(node.id === selectedNode ? null : node.id);
  }, [selectedNode]);

  // Initial data load
  useEffect(() => {
    fetchGraphData();
  }, []);

  if (loading) {
    return (
      <div className={`${className} h-96 flex items-center justify-center`}>
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto mb-4"></div>
          <p className="text-gray-600">Loading course graph...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className={`${className} h-96 flex items-center justify-center`}>
        <div className="text-center">
          <div className="text-red-600 mb-2">⚠️ Error Loading Graph</div>
          <p className="text-gray-600 mb-4">{error}</p>
          <button
            onClick={fetchGraphData}
            className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 transition-colors"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className={`${className} bg-white rounded-lg shadow-sm border overflow-hidden`}>
      <div className="h-96 w-full">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={onConnect}
          onNodeClick={onNodeClick}
          nodeTypes={nodeTypes}
          fitView
          attributionPosition="bottom-left"
        >
          <Background />
          <Controls />
          <MiniMap 
            nodeColor={(node) => {
              if (node.data.community_id !== undefined && showCommunities) {
                const colors = [
                  '#3B82F6', '#EF4444', '#10B981', '#F59E0B', '#8B5CF6',
                  '#EC4899', '#06B6D4', '#84CC16', '#F97316', '#6366F1'
                ];
                return colors[node.data.community_id % colors.length];
              }
              return '#6B7280';
            }}
            maskColor="rgb(240, 240, 240, 0.6)"
          />
          
          <Panel position="top-right" className="bg-white p-3 rounded shadow-lg border">
            <div className="space-y-2">
              <h3 className="font-medium text-sm">Display Options</h3>
              <label className="flex items-center text-sm">
                <input
                  type="checkbox"
                  checked={showCommunities}
                  onChange={(e) => setShowCommunities(e.target.checked)}
                  className="mr-2"
                />
                Show Communities
              </label>
              <label className="flex items-center text-sm">
                <input
                  type="checkbox"
                  checked={showCentrality}
                  onChange={(e) => setShowCentrality(e.target.checked)}
                  className="mr-2"
                />
                Show Centrality
              </label>
              
              {/* NEW: Personalization toggle - Key demo feature */}
              <div className="border-t pt-2">
                <h4 className="font-medium text-xs text-gray-600 mb-1">
                  🎯 Personalization 
                  {personalized && <span className="text-green-600 ml-1">ACTIVE</span>}
                </h4>
                <label className="flex items-center text-sm">
                  <input
                    type="checkbox"
                    checked={personalized}
                    onChange={(e) => setPersonalized(e.target.checked)}
                    className="mr-2"
                  />
                  My Academic Pathway
                </label>
                
                {personalized && (
                  <div className="mt-2 space-y-2 text-xs bg-blue-50 p-2 rounded">
                    <div>
                      <label className="block font-medium text-gray-700">Major:</label>
                      <select
                        value={studentMajor}
                        onChange={(e) => setStudentMajor(e.target.value)}
                        className="w-full text-xs border border-gray-300 rounded px-1 py-0.5"
                      >
                        <option value="Computer Science">Computer Science</option>
                        <option value="Mathematics">Mathematics</option>
                        <option value="Electrical Engineering">Electrical Engineering</option>
                      </select>
                    </div>
                    
                    <div className="text-xs text-gray-600">
                      <div><strong>Completed:</strong> {completedCourses.join(', ')}</div>
                      <div><strong>Current:</strong> {currentCourses.join(', ')}</div>
                      <div className="mt-1 text-green-600">
                        📊 Graph personalized to show YOUR most relevant courses
                      </div>
                    </div>
                  </div>
                )}
              </div>
              
              <div className="border-t pt-2">
                <h4 className="font-medium text-xs text-gray-600 mb-1">Layout</h4>
                <select
                  value={layoutType}
                  onChange={(e) => setLayoutType(e.target.value as 'circular' | 'force' | 'hierarchical')}
                  className="w-full text-xs border border-gray-300 rounded px-1 py-0.5"
                >
                  <option value="hierarchical">Hierarchical (Recommended)</option>
                  <option value="force">Force-Directed</option>
                  <option value="circular">Circular</option>
                </select>
              </div>
              
              <div className="border-t pt-2">
                <h4 className="font-medium text-xs text-gray-600 mb-1">Performance</h4>
                <div className="space-y-1">
                  <label className="block text-xs">
                    Max Nodes: {maxNodes}
                    <input
                      type="range"
                      min="10"
                      max="200"
                      value={maxNodes}
                      onChange={(e) => setMaxNodes(parseInt(e.target.value))}
                      className="w-full text-xs"
                    />
                  </label>
                  <label className="block text-xs">
                    Max Edges: {maxEdges}
                    <input
                      type="range"
                      min="20"
                      max="500"
                      value={maxEdges}
                      onChange={(e) => setMaxEdges(parseInt(e.target.value))}
                      className="w-full text-xs"
                    />
                  </label>
                </div>
              </div>
              
              <button
                onClick={fetchGraphData}
                className="w-full px-2 py-1 text-xs bg-blue-600 text-white rounded hover:bg-blue-700 transition-colors"
              >
                Refresh
              </button>
            </div>
          </Panel>

          {selectedNode && (
            <Panel position="bottom-left" className="bg-white p-3 rounded shadow-lg border max-w-xs">
              <div className="text-sm">
                <h4 className="font-medium mb-1">Selected Course</h4>
                <p className="text-gray-600">{selectedNode}</p>
                {graphData?.courses.find(c => c.course_code === selectedNode)?.course_title && (
                  <p className="text-gray-500 text-xs mt-1">
                    {graphData.courses.find(c => c.course_code === selectedNode)?.course_title}
                  </p>
                )}
              </div>
            </Panel>
          )}
        </ReactFlow>
      </div>
    </div>
  );
}