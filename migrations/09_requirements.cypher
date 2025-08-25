// Idempotent loader for majors & requirements
// Expects a parameter $majorsJson (stringified JSON). We unwind in Cypher for simplicity.

WITH apoc.convert.fromJsonMap($majorsJson) AS root
UNWIND root.majors AS m
MERGE (maj:Major {id: m.id})
SET maj.name = m.name, maj.catalog_year = m.catalog_year

WITH m, maj
UNWIND m.requirements AS r
MERGE (req:Requirement {id: r.id})
SET req.summary = r.summary,
    req.type = coalesce(r.type, 'COUNT_AT_LEAST'),
    req.min_count = coalesce(r.min_count, 0),
    req.min_credits = coalesce(r.min_credits, 0)

MERGE (maj)-[:REQUIRES]->(req)

WITH req, r
FOREACH (c IN coalesce(r.courses, []) |
  MERGE (course:Course {code: c.code})
  SET course.credits = coalesce(c.credits, 3)
  MERGE (req)-[:SATISFIED_BY]->(course)
)