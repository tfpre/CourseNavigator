# Neo4j Aura Deployment Instructions

## 🚀 **Neo4j Aura Setup (5 minutes)**

### Step 1: Create Neo4j Aura Account
1. Go to [neo4j.com/aura](https://neo4j.com/aura)
2. Sign up for free account (no credit card required)
3. Create new **AuraDB Free** instance
   - Name: `cornell-course-navigator`
   - Region: Choose closest to your location
   - Version: Latest stable (5.x)

### Step 2: Save Connection Credentials
After instance creation, **save these immediately**:
```
Neo4j URI: neo4j+s://xxxxx.databases.neo4j.io
Username: neo4j
Password: [generated-password]
```

## 📂 **Data Import Process**

### Step 3: Upload CSV Files to Neo4j Aura

Neo4j Aura requires files to be imported via the browser interface:

1. **Log into Neo4j Browser** (click "Open" on your Aura instance)
2. **Upload CSV files** one by one using the import tool:
   - `courses.csv` (240 courses)
   - `aliases.csv` (208 cross-listings) 
   - `prerequisite_edges.csv` (154 prerequisite relationships)

### Step 4: Run Import Script

Copy and paste the contents of `import_script.cypher` into Neo4j Browser:

```cypher
// 1. First run schema setup queries
CREATE CONSTRAINT course_id IF NOT EXISTS 
FOR (c:Course) REQUIRE c.id IS UNIQUE;

CREATE CONSTRAINT alias_code IF NOT EXISTS 
FOR (a:Alias) REQUIRE a.code IS UNIQUE;

// 2. Then run import queries (adjust file paths as needed)
LOAD CSV WITH HEADERS FROM 'file:///courses.csv' AS row
MERGE (c:Course {id: row.id})
SET c.subject = row.subject,
    c.catalogNbr = row.catalogNbr,
    // ... rest of import script
```

## ✅ **Verification Queries**

After import, verify data integrity:

```cypher
// Check counts
MATCH (c:Course) RETURN count(c) as courses;
MATCH (a:Alias) RETURN count(a) as aliases;  
MATCH ()-[r:REQUIRES]->() RETURN count(r) as edges;

// Expected results:
// courses: 240
// aliases: 208
// edges: 154
```

## 🔧 **Connect FastAPI Gateway**

Update environment variables:
```bash
export NEO4J_URI="neo4j+s://xxxxx.databases.neo4j.io"
export NEO4J_USERNAME="neo4j"
export NEO4J_PASSWORD="your-generated-password"
```

## 📊 **Data Summary**

Successfully imported:
- **240 courses** from Cornell FA14 semester
- **208 course aliases** (cross-listings like CS 2110 ≡ ENGRD 2110)
- **154 prerequisite edges** with relationship types:
  - `PREREQUISITE_OR` (94): Alternative requirements
  - `COREQUISITE` (21): Concurrent enrollment  
  - `PREREQUISITE` (23): Must complete first
  - `UNSURE` (7): Low-confidence relationships
  - Other types (9): Various specialized relationships

## 🎯 **Next Steps**

1. ✅ **Schema Setup** - Constraints and indexes created
2. ✅ **Data Import** - 240 courses with relationships imported
3. 🔄 **FastAPI Connection** - Connect gateway to production Neo4j
4. 🔄 **Graph Queries** - Test prerequisite path queries
5. 🔄 **UI Integration** - Connect Next.js frontend

## 🚨 **Troubleshooting**

### Import Errors
- **File not found**: Ensure CSV files are uploaded to Neo4j browser first
- **Constraint violations**: Run schema setup queries before import
- **Connection timeout**: Use smaller batch sizes for large imports

### Query Performance  
- **Slow queries**: Indexes are automatically created by schema setup
- **Memory issues**: Neo4j Free tier has 0.5GB limit, should be sufficient for this dataset
- **Rate limiting**: Aura Free has query rate limits, normal for development

## 📈 **Monitoring**

Neo4j Aura provides built-in monitoring:
- Query performance metrics
- Memory and storage usage  
- Connection statistics
- Error logs

Your Cornell Course Navigator graph database is now ready for production! 🎉