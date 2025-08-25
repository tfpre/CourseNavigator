# Grades Service v1 - Real Cornell Data with Provenance Tracking
# Implements Friend 1's recommendation: CSV → Redis TagCache → API with provenance
# Ground Truth: Information Consolidation + Information Reliability

import csv
import hashlib
import logging
import os
import statistics
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timezone, timedelta
from pathlib import Path

from .tag_cache import TagCache
from .provenance_service import ProvenanceService, ProvenanceTag, compute_data_version
from ..models import CourseGradesStats, GradeHistogram, GradesProvenance, CourseCode, ProvenanceTagModel

logger = logging.getLogger(__name__)

class GradesService:
    """
    Real grades data service with versioned caching and provenance tracking.
    
    Key Features:
    - Loads Cornell grade distributions from CSV
    - TagCache integration for performance (24h TTL)
    - Full provenance tracking (file hash, version, timestamps)
    - Difficulty scoring and pass rate calculation
    - Thread-safe and production-ready
    
    Implements Friend's architecture: Single source of truth for all difficulty metrics.
    """
    
    def __init__(
        self, 
        redis_client, 
        csv_path: str = "data/cornell_grades.csv",
        tag: str = "grades",
        ttl_seconds: int = 24 * 3600  # 24 hour cache
    ):
        self.redis = redis_client
        self.tag = tag
        self.ttl_seconds = ttl_seconds
        self.csv_path = Path(csv_path)
        self.cache = TagCache(redis_client, ttl_s=ttl_seconds)
        
        # Initialize ProvenanceService for comprehensive tracking
        self.provenance = ProvenanceService(redis_client)
        
        # TTL configuration from environment or defaults
        self.GRADES_TTL_SECONDS = int(os.getenv("GRADES_TTL_DAYS", "30")) * 24 * 3600
        self.GRADES_SOFT_TTL_SECONDS = int(os.getenv("GRADES_SOFT_TTL_DAYS", "7")) * 24 * 3600
        
        # Verify CSV exists
        if not self.csv_path.exists():
            logger.warning(f"Grades CSV not found at {csv_path}, service will return empty results")
        
    def _sha256_file(self, path: Path) -> str:
        """Compute SHA256 hash of file for provenance tracking"""
        if not path.exists():
            return "missing_file"
        
        hash_sha256 = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                hash_sha256.update(chunk)
        return hash_sha256.hexdigest()
    
    def _normalize_course_code(self, course_id: str) -> CourseCode:
        """
        Normalize course codes to standard format: 'SUBJ ####'
        Example: 'CS 4820', 'MATH 1920'
        """
        return course_id.strip().upper()
    
    def _parse_csv_row(self, row: Dict[str, str]) -> Tuple[CourseCode, str, Dict[str, float]]:
        """
        Parse a single CSV row into structured data.
        Expected CSV columns: course_id, term, mean_gpa, grade_a_pct, grade_b_pct, 
                             grade_c_pct, grade_d_pct, grade_f_pct, enrollment_count, 
                             difficulty_percentile, updated_at
        """
        course_code = self._normalize_course_code(row["course_id"])
        term = row["term"].strip()
        
        # Parse grade statistics with error handling
        stats = {}
        try:
            stats["mean_gpa"] = float(row["mean_gpa"])
            stats["grade_a_pct"] = float(row["grade_a_pct"])
            stats["grade_b_pct"] = float(row["grade_b_pct"])
            stats["grade_c_pct"] = float(row["grade_c_pct"])
            stats["grade_d_pct"] = float(row["grade_d_pct"])
            stats["grade_f_pct"] = float(row["grade_f_pct"])
            stats["enrollment_count"] = int(row["enrollment_count"])
            stats["difficulty_percentile"] = int(row.get("difficulty_percentile", 50))
        except (ValueError, KeyError) as e:
            logger.warning(f"Failed to parse row for {course_code} {term}: {e}")
            return course_code, term, {}
            
        return course_code, term, stats
    
    def _calculate_pass_rate(self, grade_percentages: Dict[str, float]) -> float:
        """Calculate pass rate (D or better) from grade percentages"""
        passing_grades = ["grade_a_pct", "grade_b_pct", "grade_c_pct", "grade_d_pct"]
        pass_rate = sum(grade_percentages.get(grade, 0.0) for grade in passing_grades)
        return min(pass_rate / 100.0, 1.0)  # Convert to decimal and cap at 1.0
    
    async def _load_grades_data(self) -> Dict[CourseCode, Dict]:
        """
        Load and aggregate grades data from CSV with caching.
        Returns aggregated statistics per course across all terms.
        """
        if not self.csv_path.exists():
            logger.warning(f"Grades CSV missing: {self.csv_path}")
            return {}
        
        async def compute_grades_data():
            """Asynchronous function to load and process CSV data"""
            course_data = {}
            record_count = 0
            
            try:
                with open(self.csv_path, 'r', newline='', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    
                    for row in reader:
                        record_count += 1
                        course_code, term, stats = self._parse_csv_row(row)
                        
                        if not stats:  # Skip malformed rows
                            continue
                            
                        if course_code not in course_data:
                            course_data[course_code] = {
                                "terms": [],
                                "gpas": [],
                                "enrollments": [],
                                "grade_distributions": [],
                                "difficulty_percentiles": []
                            }
                        
                        # Aggregate data for multi-term courses
                        course_data[course_code]["terms"].append(term)
                        course_data[course_code]["gpas"].append(stats["mean_gpa"])
                        course_data[course_code]["enrollments"].append(stats["enrollment_count"])
                        course_data[course_code]["grade_distributions"].append({
                            "grade_a_pct": stats["grade_a_pct"],
                            "grade_b_pct": stats["grade_b_pct"],
                            "grade_c_pct": stats["grade_c_pct"],
                            "grade_d_pct": stats["grade_d_pct"],
                            "grade_f_pct": stats["grade_f_pct"]
                        })
                        course_data[course_code]["difficulty_percentiles"].append(
                            stats["difficulty_percentile"]
                        )
                        
            except Exception as e:
                logger.exception(f"Failed to load grades CSV: {e}")
                return {"courses": {}, "record_count": 0}
            
            logger.info(f"Loaded {len(course_data)} courses from {record_count} records")
            return {"courses": course_data, "record_count": record_count}
        
        # Use TagCache for versioned caching
        file_hash = self._sha256_file(self.csv_path)
        cache_key = {"file_hash": file_hash}
        
        data = await self.cache.get_or_set(
            tag=self.tag,
            key_fields=cache_key,
            loader=compute_grades_data,
            custom_ttl=self.ttl_seconds
        )
        
        return data
    
    async def get_course_stats(self, course_code: str) -> Optional[CourseGradesStats]:
        """
        Get comprehensive grade statistics for a specific course.
        Returns None if course not found.
        """
        # Normalize course code for consistent lookup
        normalized_code = self._normalize_course_code(course_code)
        
        # Load data from cache or CSV
        grades_data = await self._load_grades_data()
        courses = grades_data.get("courses", {})
        record_count = grades_data.get("record_count", 0)
        
        if normalized_code not in courses:
            logger.debug(f"Course {normalized_code} not found in grades data")
            return None
        
        course_info = courses[normalized_code]
        
        # Calculate aggregate statistics
        try:
            # GPA statistics
            gpas = course_info["gpas"]
            mean_gpa = statistics.mean(gpas)
            stdev_gpa = statistics.pstdev(gpas) if len(gpas) > 1 else 0.0
            
            # Grade distribution (average across terms)
            grade_dists = course_info["grade_distributions"]
            avg_grades = {
                "grade_a_pct": statistics.mean(d["grade_a_pct"] for d in grade_dists),
                "grade_b_pct": statistics.mean(d["grade_b_pct"] for d in grade_dists),
                "grade_c_pct": statistics.mean(d["grade_c_pct"] for d in grade_dists),
                "grade_d_pct": statistics.mean(d["grade_d_pct"] for d in grade_dists),
                "grade_f_pct": statistics.mean(d["grade_f_pct"] for d in grade_dists)
            }
            
            # Pass rate and enrollment
            pass_rate = self._calculate_pass_rate(avg_grades)
            total_enrollment = sum(course_info["enrollments"])
            avg_difficulty = statistics.mean(course_info["difficulty_percentiles"])
            
            # Enhanced provenance tracking with ProvenanceService
            dataset_version = os.getenv("GRADES_DATA_VERSION") or f"csv_{self._sha256_file(self.csv_path)[:8]}"
            course_stats_payload = {
                "mean_gpa": mean_gpa,
                "histogram": avg_grades,
                "pass_rate": pass_rate,
                "enrollment_count": total_enrollment,
                "difficulty_percentile": avg_difficulty,
                "terms": sorted(set(course_info["terms"]))
            }
            data_hash = compute_data_version(course_stats_payload)
            
            # Create comprehensive provenance tag with term-scoped entity_id to prevent collisions
            default_term = os.getenv("DEFAULT_TERM", "UNKNOWN")
            entity_id = f"{default_term}:{normalized_code}" if default_term and default_term != "UNKNOWN" else normalized_code
            expires_at = (datetime.now(timezone.utc) + timedelta(seconds=self.GRADES_TTL_SECONDS)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
            provenance_tag = ProvenanceTag(
                source="grades",
                entity_id=entity_id,
                version=dataset_version,
                data_version=data_hash,
                term=default_term,
                observed_at=None,  # CSV doesn't have original observation time
                expires_at=expires_at,
                ttl_seconds=self.GRADES_TTL_SECONDS,
                soft_ttl_seconds=self.GRADES_SOFT_TTL_SECONDS,
                meta={
                    "provider": "cornell_grade_distributions",
                    "file_path": str(self.csv_path),
                    "record_count": record_count
                }
            )
            
            # Record provenance tag
            await self.provenance.record(provenance_tag)
            
            # Check for version changes and invalidate if needed
            async def drop_downstream_cache():
                if hasattr(self, 'cache'):
                    await self.cache.redis.delete(f"grades:{normalized_code}")
            
            await self.provenance.invalidate_on_version_change(
                source="grades",
                entity_id=entity_id,
                current_version=dataset_version,
                current_data_version=data_hash,
                drop_cache_fn=drop_downstream_cache
            )
            
            # Legacy provenance for backward compatibility
            tag_version = await self.cache._get_tag_version(self.tag)
            legacy_provenance = GradesProvenance(
                tag=self.tag,
                version=tag_version,
                file_hash=self._sha256_file(self.csv_path),
                refreshed_at=datetime.utcnow(),
                record_count=record_count
            )
            
            # Build response
            histogram = GradeHistogram(**avg_grades)
            
            # Convert dataclass to Pydantic model for API serialization
            provenance_tag_model = ProvenanceTagModel(
                source=provenance_tag.source,
                entity_id=provenance_tag.entity_id,
                tenant=provenance_tag.tenant,
                source_id=provenance_tag.source_id,
                url=provenance_tag.url,
                term=provenance_tag.term,
                version=provenance_tag.version,
                data_version=provenance_tag.data_version,
                observed_at=provenance_tag.observed_at,
                fetched_at=provenance_tag.fetched_at,
                expires_at=provenance_tag.expires_at,
                ttl_seconds=provenance_tag.ttl_seconds,
                soft_ttl_seconds=provenance_tag.soft_ttl_seconds,
                serialization_version=provenance_tag.serialization_version,
                meta=provenance_tag.meta
            )
            
            stats = CourseGradesStats(
                course_code=normalized_code,
                terms=sorted(set(course_info["terms"])),
                mean_gpa=round(mean_gpa, 2),
                stdev_gpa=round(stdev_gpa, 2),
                pass_rate=round(pass_rate, 3),
                histogram=histogram,
                enrollment_count=total_enrollment,
                difficulty_percentile=round(avg_difficulty),
                provenance=legacy_provenance,
                provenance_tag=provenance_tag_model
            )
                    
            return stats
            
        except Exception as e:
            logger.exception(f"Failed to compute stats for {normalized_code}: {e}")
            return None
    
    async def get_difficulty_ranking(self, course_codes: List[str]) -> Dict[str, float]:
        """
        Get relative difficulty ranking for a list of courses.
        Returns difficulty scores (0.0 = easiest, 1.0 = hardest) based on percentiles.
        """
        difficulty_map = {}
        
        for course_code in course_codes:
            stats = await self.get_course_stats(course_code)
            if stats and stats.difficulty_percentile is not None:
                # Convert percentile to 0.0-1.0 scale
                difficulty_map[course_code] = stats.difficulty_percentile / 100.0
        
        return difficulty_map
    
    async def health_check(self) -> bool:
        """Health check for grades service"""
        try:
            if not self.csv_path.exists():
                return False
            
            # Test cache connectivity
            test_key = f"health_check_{datetime.utcnow().timestamp()}"
            await self.redis.set(test_key, "ok", ex=1)
            result = await self.redis.get(test_key)
            await self.redis.delete(test_key)
            
            return result == "ok"
        except Exception:
            return False