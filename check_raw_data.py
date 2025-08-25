import gzip
import json

# Check FA25 CS data structure
with gzip.open("data/raw/FA25_CS.json.gz", 'rt') as f:
    data = json.load(f)

if 'data' in data and 'classes' in data['data']:
    classes = data['data']['classes']
    print(f"Total classes in FA25 CS: {len(classes)}")
    
    if classes:
        first_class = classes[0]
        print(f"\nFirst class fields:")
        for key in sorted(first_class.keys()):
            value = first_class[key]
            if isinstance(value, str):
                print(f"  {key}: '{value[:100]}{'...' if len(value) > 100 else ''}'")
            else:
                print(f"  {key}: {type(value).__name__}")
        
        # Look for prerequisite-related fields
        prereq_fields = [k for k in first_class.keys() if 'prereq' in k.lower() or 'pre' in k.lower()]
        print(f"\nPrerequisite-related fields: {prereq_fields}")
        
        # Check a few courses for prerequisite data
        print(f"\nSample prerequisite data:")
        for i, course in enumerate(classes[:5]):
            course_code = f"{course.get('subject', 'UNK')} {course.get('catalogNbr', 'UNK')}"
            prereq_text = course.get('catalogPrereqCoreq', '')
            print(f"  {course_code}: '{prereq_text}'")