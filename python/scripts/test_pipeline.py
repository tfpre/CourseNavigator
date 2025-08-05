"""
Test runner for the complete data pipeline: scraping → processing → embedding → search.
This script validates the entire system end-to-end.
"""

import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

def test_data_models():
    """Test the data models work correctly."""
    print("🧪 Testing data models...")
    
    from python.data_ingestion.models import RawCourse, CleanCourse, RawEnrollGroup, parse_meetings
    
    # Test RawCourse creation
    sample_raw = {
        "crseId": 12345,
        "crseOfferNbr": 1,
        "subject": "CS",
        "catalogNbr": "2110",
        "titleLong": "Object-Oriented Programming and Data Structures",
        "description": "Introduction to object-oriented programming...",
        "catalogPrereq": "CS 1110 or CS 1112",
        "enrollGroups": [
            {
                "classSections": [{"ssrComponent": "LEC"}],
                "unitsMinimum": 4,
                "unitsMaximum": 4
            }
        ]
    }
    
    raw_course = RawCourse(**sample_raw)
    clean_course = CleanCourse.from_raw(raw_course, "FA25")
    
    print(f"   ✓ Raw course: {raw_course.subject} {raw_course.catalogNbr}")
    print(f"   ✓ Clean course: {clean_course.id} - {clean_course.title}")
    
    # Test ARR pattern handling
    arr_raw = {
        "crseId": 12346,
        "crseOfferNbr": 1,
        "subject": "CS",
        "catalogNbr": "4999",
        "titleLong": "Independent Study",
        "enrollGroups": [
            {
                "classSections": [
                    {
                        "ssrComponent": "IND",
                        "meetings": [
                            {
                                "pattern": "ARR",
                                "timeStart": None,
                                "timeEnd": None,
                                "facilityDescr": "TBA"
                            }
                        ]
                    }
                ],
                "unitsMinimum": 1,
                "unitsMaximum": 4
            }
        ]
    }
    
    arr_course = RawCourse(**arr_raw)
    arr_meetings = parse_meetings(arr_course)
    
    # Verify ARR pattern produces empty days list
    assert len(arr_meetings) == 1, "Should have one meeting"
    assert arr_meetings[0].days == [], f"ARR pattern should have empty days, got {arr_meetings[0].days}"
    print(f"   ✓ ARR pattern test: {arr_meetings[0].type} with {len(arr_meetings[0].days)} days")
    
    print("   ✅ Data models test passed!")
    return True

def test_scraper_import():
    """Test that the scraper can be imported and configured."""
    print("🕷️  Testing scraper import...")
    
    try:
        from python.data_ingestion.scraper import make_request, save_state, load_state
        print("   ✓ Scraper imports successful")
        
        # Test state management
        test_state = {"last_completed_roster": "FA25", "last_completed_subject_index": 5, "roster_hash": "dummy_hash"}
        save_state(test_state["last_completed_roster"], test_state["last_completed_subject_index"], test_state["roster_hash"])
        loaded_state = load_state()
        assert loaded_state == test_state
        print("   ✓ State management working")
        
        print("   ✅ Scraper test passed!")
        return True
    except ImportError as e:
        print(f"   ❌ Scraper import failed: {e}")
        return False

def test_processor_import():
    """Test that the processor can be imported."""
    print("🔄 Testing processor import...")
    
    try:
        from python.data_ingestion.processor import process_raw_file, load_clean_courses
        print("   ✓ Processor imports successful")
        print("   ✅ Processor test passed!")
        return True
    except ImportError as e:
        print(f"   ❌ Processor import failed: {e}")
        return False

def test_embedding_dependencies():
    """Test that embedding dependencies are available."""
    print("🤖 Testing embedding dependencies...")
    
    try:
        from sentence_transformers import SentenceTransformer
        from qdrant_client import QdrantClient
        print("   ✓ SentenceTransformers available")
        print("   ✓ Qdrant client available")
        
        # Test model loading
        model = SentenceTransformer('all-MiniLM-L6-v2')
        test_embedding = model.encode("Test sentence")
        print(f"   ✓ Embedding created, dimension: {len(test_embedding)}")
        
        print("   ✅ Embedding dependencies test passed!")
        return True
    except Exception as e:
        print(f"   ❌ Embedding dependencies failed: {e}")
        return False

def run_integration_test():
    """Run the full Qdrant integration test."""
    print("🔗 Running integration test...")
    
    try:
        from python.scripts.test_qdrant_integration import test_qdrant_integration
        test_qdrant_integration()
        return True
    except Exception as e:
        print(f"   ❌ Integration test failed: {e}")
        return False

def main():
    """Run all tests."""
    print("🧪 Cornell Course Navigator - Pipeline Test Suite")
    print("=" * 50)
    
    tests = [
        ("Data Models", test_data_models),
        ("Scraper Import", test_scraper_import),
        ("Processor Import", test_processor_import),
        ("Embedding Dependencies", test_embedding_dependencies),
        ("Integration Test", run_integration_test),
    ]
    
    results = []
    for test_name, test_func in tests:
        print(f"\n📋 Running {test_name}...")
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"   ❌ {test_name} failed with exception: {e}")
            results.append((test_name, False))
    
    print("\n" + "=" * 50)
    print("📊 Test Results Summary:")
    print("=" * 50)
    
    passed = 0
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {test_name}")
        if result:
            passed += 1
    
    print(f"\n🎯 {passed}/{len(tests)} tests passed")
    
    if passed == len(tests):
        print("🎉 All tests passed! Pipeline is ready for production.")
        return True
    else:
        print("⚠️  Some tests failed. Check the output above for details.")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)