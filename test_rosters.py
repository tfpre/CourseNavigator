import requests
import json

response = requests.get("https://classes.cornell.edu/api/2.0/config/rosters.json")
data = response.json()

print("Available rosters (first 10):")
for i, roster in enumerate(data['data']['rosters'][:10]):
    print(f"{i}: {roster['slug']} - {roster.get('description', 'No description')}")
    
print(f"\nFirst roster (oldest): {data['data']['rosters'][0]['slug']}")
print(f"Last roster (newest): {data['data']['rosters'][-1]['slug']}")
print(f"Total rosters: {len(data['data']['rosters'])}")

print("\nLast 5 rosters:")
for roster in data['data']['rosters'][-5:]:
    print(f"  {roster['slug']}")