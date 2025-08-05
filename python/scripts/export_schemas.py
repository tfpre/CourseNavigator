#!/usr/bin/env python3
"""
Export Pydantic models to JSON Schema for TypeScript sync.
Prevents schema drift between Python data pipeline and Next.js frontend.
"""

import json
import sys
from pathlib import Path
from typing import Dict, Any

# Add the parent directory to the path so we can import gateway models
sys.path.append(str(Path(__file__).parent.parent))

from gateway.models import (
    SearchMode, CourseInfo, PrerequisiteEdge, GraphContext,
    RAGRequest, PrerequisitePathRequest, ErrorDetail,
    RAGResponse, PrerequisitePathResponse, HealthResponse,
    CentralityRequest, CentralityResponse,
    CommunityRequest, CommunityResponse,
    ShortestPathRequest, ShortestPathResponse,
    CourseRecommendationRequest, CourseRecommendationResponse,
    AlternativePathsRequest, AlternativePathsResponse,
    GraphSubgraphRequest, GraphSubgraphResponse
)

def export_model_schemas() -> Dict[str, Any]:
    """Export all Pydantic models to JSON Schema format"""
    
    schemas = {}
    
    # List of models to export
    models_to_export = [
        ("SearchMode", SearchMode),
        ("CourseInfo", CourseInfo),
        ("PrerequisiteEdge", PrerequisiteEdge), 
        ("GraphContext", GraphContext),
        ("RAGRequest", RAGRequest),
        ("PrerequisitePathRequest", PrerequisitePathRequest),
        ("ErrorDetail", ErrorDetail),
        ("RAGResponse", RAGResponse),
        ("PrerequisitePathResponse", PrerequisitePathResponse),
        ("HealthResponse", HealthResponse),
        ("CentralityRequest", CentralityRequest),
        ("CentralityResponse", CentralityResponse),
        ("CommunityRequest", CommunityRequest),
        ("CommunityResponse", CommunityResponse),
        ("ShortestPathRequest", ShortestPathRequest),
        ("ShortestPathResponse", ShortestPathResponse),
        ("CourseRecommendationRequest", CourseRecommendationRequest),
        ("CourseRecommendationResponse", CourseRecommendationResponse),
        ("AlternativePathsRequest", AlternativePathsRequest),
        ("AlternativePathsResponse", AlternativePathsResponse),
        ("GraphSubgraphRequest", GraphSubgraphRequest),
        ("GraphSubgraphResponse", GraphSubgraphResponse)
    ]
    
    for model_name, model_class in models_to_export:
        try:
            # Get JSON schema from Pydantic model
            schema = model_class.model_json_schema()
            schemas[model_name] = schema
            print(f"✅ Exported schema for {model_name}")
        except Exception as e:
            print(f"❌ Failed to export schema for {model_name}: {e}")
    
    return schemas

def generate_typescript_types(schemas: Dict[str, Any]) -> str:
    """Generate TypeScript type definitions from JSON schemas"""
    
    typescript_lines = [
        "// Auto-generated TypeScript types from Python Pydantic models",
        "// DO NOT EDIT - Run `poetry run python scripts/export_schemas.py` to regenerate",
        "",
        "// Enum types",
        "export enum SearchMode {",
        "  SEMANTIC = 'semantic',",
        "  GRAPH_AWARE = 'graph_aware',",
        "  PREREQUISITE_PATH = 'prereq_path'",
        "}",
        "",
        "// Interface types"
    ]
    
    # Define TypeScript mappings for common JSON Schema types
    type_mappings = {
        "string": "string",
        "number": "number", 
        "integer": "number",
        "boolean": "boolean",
        "array": "Array",
        "object": "object"
    }
    
    # Generate interfaces for main models (simplified version)
    interface_models = [
        "CourseInfo", "PrerequisiteEdge", "GraphContext",
        "RAGRequest", "PrerequisitePathRequest", "ErrorDetail", 
        "RAGResponse", "PrerequisitePathResponse", "HealthResponse",
        "CentralityRequest", "CentralityResponse",
        "CommunityRequest", "CommunityResponse",
        "ShortestPathRequest", "ShortestPathResponse",
        "CourseRecommendationRequest", "CourseRecommendationResponse",
        "AlternativePathsRequest", "AlternativePathsResponse",
        "GraphSubgraphRequest", "GraphSubgraphResponse"
    ]
    
    for model_name in interface_models:
        if model_name in schemas:
            schema = schemas[model_name]
            properties = schema.get("properties", {})
            required = set(schema.get("required", []))
            
            typescript_lines.append(f"export interface {model_name} {{")
            
            for prop_name, prop_schema in properties.items():
                prop_type = prop_schema.get("type", "any")
                ts_type = type_mappings.get(prop_type, "any")
                
                # Handle special cases
                if prop_type == "array":
                    items = prop_schema.get("items", {})
                    item_type = items.get("type", "any")
                    if item_type == "object" and "$ref" in items:
                        # Reference to another model
                        ref_name = items["$ref"].split("/")[-1]
                        ts_type = f"{ref_name}[]"
                    else:
                        ts_type = f"{type_mappings.get(item_type, 'any')}[]"
                elif "enum" in prop_schema:
                    # Enum type
                    ts_type = "SearchMode" if "semantic" in prop_schema["enum"] else "string"
                elif "$ref" in prop_schema:
                    # Reference to another model
                    ts_type = prop_schema["$ref"].split("/")[-1]
                
                # Optional vs required
                optional_marker = "" if prop_name in required else "?"
                
                typescript_lines.append(f"  {prop_name}{optional_marker}: {ts_type};")
            
            typescript_lines.append("}")
            typescript_lines.append("")
    
    return "\n".join(typescript_lines)

def main():
    """Main export function - generates both JSON schema and TypeScript types"""
    print("🔄 Exporting Pydantic schemas to JSON and TypeScript...")
    
    # Export JSON schemas
    schemas = export_model_schemas()
    
    # Create output directory
    output_dir = Path(__file__).parent.parent.parent / "types"
    output_dir.mkdir(exist_ok=True)
    
    # Write JSON schema file
    json_output_path = output_dir / "api-schemas.json"
    with open(json_output_path, "w") as f:
        json.dump(schemas, f, indent=2)
    print(f"📄 JSON schemas written to {json_output_path}")
    
    # Generate TypeScript types
    typescript_content = generate_typescript_types(schemas)
    
    # Write TypeScript file
    ts_output_path = output_dir / "api-types.ts"
    with open(ts_output_path, "w") as f:
        f.write(typescript_content)
    print(f"📝 TypeScript types written to {ts_output_path}")
    
    print(f"✅ Schema export complete! Exported {len(schemas)} models.")

if __name__ == "__main__":
    main()