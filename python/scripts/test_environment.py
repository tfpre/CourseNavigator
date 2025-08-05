"""
Test script to verify Python environment setup
Checks key dependencies and GPU availability
"""

import sys
import subprocess
from typing import Dict, Any


def check_python_version() -> Dict[str, Any]:
    """Check Python version compatibility"""
    version = sys.version_info
    return {
        "python_version": f"{version.major}.{version.minor}.{version.micro}",
        "compatible": version >= (3, 11),
        "status": "✅" if version >= (3, 11) else "❌",
    }


def check_dependencies() -> Dict[str, Any]:
    """Check if critical dependencies are importable"""
    deps = {
        "torch": "PyTorch for GPU acceleration",
        "transformers": "Hugging Face Transformers",
        "langchain": "LangChain for RAG",
        "neo4j": "Neo4j driver for graph database",
        "qdrant_client": "Qdrant client for vector database",
        "networkx": "NetworkX for graph algorithms",
        "pandas": "Pandas for data processing",
        "numpy": "NumPy for numerical computing",
    }
    
    results = {}
    for dep, description in deps.items():
        try:
            __import__(dep)
            results[dep] = {"status": "✅", "description": description}
        except ImportError:
            results[dep] = {"status": "❌", "description": description}
    
    return results


def check_gpu_availability() -> Dict[str, Any]:
    """Check CUDA/GPU availability"""
    try:
        import torch
        cuda_available = torch.cuda.is_available()
        device_count = torch.cuda.device_count() if cuda_available else 0
        
        result = {
            "cuda_available": cuda_available,
            "device_count": device_count,
            "status": "✅" if cuda_available else "❌",
        }
        
        if cuda_available:
            result["device_name"] = torch.cuda.get_device_name(0)
            result["cuda_version"] = torch.version.cuda
        
        return result
    except ImportError:
        return {"status": "❌", "error": "PyTorch not available"}


def main():
    """Main test function"""
    print("🔍 Cornell Course Navigator - Environment Check")
    print("=" * 50)
    
    # Check Python version
    python_check = check_python_version()
    print(f"\n📍 Python Version: {python_check['status']} {python_check['python_version']}")
    
    # Check dependencies
    print("\n📦 Dependencies:")
    deps = check_dependencies()
    for dep, info in deps.items():
        print(f"  {info['status']} {dep}: {info['description']}")
    
    # Check GPU
    print("\n🎮 GPU Status:")
    gpu_check = check_gpu_availability()
    print(f"  {gpu_check['status']} CUDA Available: {gpu_check.get('cuda_available', False)}")
    if gpu_check.get('cuda_available'):
        print(f"  📊 Device: {gpu_check.get('device_name', 'Unknown')}")
        print(f"  🔧 CUDA Version: {gpu_check.get('cuda_version', 'Unknown')}")
    
    # Summary
    print(f"\n{'='*50}")
    total_deps = len(deps)
    working_deps = sum(1 for info in deps.values() if info['status'] == '✅')
    
    print(f"📊 Summary:")
    print(f"  Python: {python_check['status']}")
    print(f"  Dependencies: {working_deps}/{total_deps} working")
    print(f"  GPU: {gpu_check['status']}")
    
    if python_check['compatible'] and working_deps == total_deps and gpu_check.get('cuda_available'):
        print("\n🎉 Environment ready for development!")
        return 0
    else:
        print("\n⚠️  Environment needs attention before development")
        return 1


if __name__ == "__main__":
    sys.exit(main())