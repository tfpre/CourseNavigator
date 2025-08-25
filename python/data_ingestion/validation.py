"""
Strict data validation with fail-fast patterns for Cornell course data.

Replaces "graceful degradation" with honest validation that exposes quality issues.
Following best practices: fail-fast, explicit error handling, comprehensive monitoring.
"""

from typing import List, Dict, Any, Optional, Tuple
from pydantic import BaseModel, ValidationError
import logging
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class ValidationSeverity(Enum):
    """Classification of validation issues by severity"""
    CRITICAL = "critical"    # Business rule violation - reject record
    WARNING = "warning"      # Quality issue - accept with flag
    INFO = "info"           # Minor issue - log for monitoring


@dataclass
class ValidationIssue:
    """Individual validation issue with context"""
    severity: ValidationSeverity
    field: str
    message: str
    raw_value: Any = None
    expected_format: Optional[str] = None


@dataclass
class ValidationResult:
    """Result of validation with all issues found"""
    is_valid: bool
    issues: List[ValidationIssue]
    course_code: str
    
    @property
    def critical_issues(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.severity == ValidationSeverity.CRITICAL]
    
    @property
    def warning_issues(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.severity == ValidationSeverity.WARNING]
    
    def log_issues(self):
        """Log all validation issues with appropriate levels"""
        for issue in self.issues:
            if issue.severity == ValidationSeverity.CRITICAL:
                logger.error(f"CRITICAL [{self.course_code}] {issue.field}: {issue.message}")
            elif issue.severity == ValidationSeverity.WARNING:
                logger.warning(f"WARNING [{self.course_code}] {issue.field}: {issue.message}")
            else:
                logger.info(f"INFO [{self.course_code}] {issue.field}: {issue.message}")


class BusinessRuleValidator:
    """
    Strict business rule validation for Cornell courses.
    
    Implements fail-fast patterns that expose data quality issues rather than hiding them.
    Each validation rule has clear business justification and error thresholds.
    """
    
    def __init__(self, strict_mode: bool = True):
        """
        Args:
            strict_mode: If True, critical issues cause validation failure
        """
        self.strict_mode = strict_mode
        
    def validate_course(self, raw_course: Any, roster: str) -> ValidationResult:
        """
        Comprehensive course validation with business rule enforcement.
        
        Returns ValidationResult with detailed issue tracking.
        """
        course_code = f"{raw_course.subject} {raw_course.catalogNbr}"
        issues = []
        
        # Core business rules
        issues.extend(self._validate_identifiers(raw_course))
        issues.extend(self._validate_credits(raw_course, course_code))
        issues.extend(self._validate_content(raw_course, course_code))
        issues.extend(self._validate_enrollment_groups(raw_course, course_code))
        
        # Determine if validation passes
        critical_issues = [i for i in issues if i.severity == ValidationSeverity.CRITICAL]
        is_valid = len(critical_issues) == 0 or not self.strict_mode
        
        return ValidationResult(is_valid, issues, course_code)
    
    def _validate_identifiers(self, raw_course: Any) -> List[ValidationIssue]:
        """Validate course identifier fields"""
        issues = []
        
        # Subject code validation
        if not hasattr(raw_course, 'subject') or not raw_course.subject:
            issues.append(ValidationIssue(
                ValidationSeverity.CRITICAL,
                "subject",
                "Missing subject code",
                getattr(raw_course, 'subject', None)
            ))
        elif not raw_course.subject.isalpha() or len(raw_course.subject) < 2:
            issues.append(ValidationIssue(
                ValidationSeverity.CRITICAL,
                "subject", 
                f"Invalid subject format: '{raw_course.subject}'",
                raw_course.subject,
                "2-5 letter code (e.g., 'CS', 'MATH')"
            ))
        
        # Catalog number validation  
        if not hasattr(raw_course, 'catalogNbr') or not raw_course.catalogNbr:
            issues.append(ValidationIssue(
                ValidationSeverity.CRITICAL,
                "catalogNbr",
                "Missing catalog number",
                getattr(raw_course, 'catalogNbr', None)
            ))
        elif not raw_course.catalogNbr.isdigit() or len(raw_course.catalogNbr) != 4:
            issues.append(ValidationIssue(
                ValidationSeverity.WARNING,
                "catalogNbr",
                f"Unusual catalog number format: '{raw_course.catalogNbr}'",
                raw_course.catalogNbr,
                "4-digit number (e.g., '2110')"
            ))
        
        # Course ID validation
        if not hasattr(raw_course, 'crseId') or not raw_course.crseId:
            issues.append(ValidationIssue(
                ValidationSeverity.CRITICAL,
                "crseId",
                "Missing course ID",
                getattr(raw_course, 'crseId', None)
            ))
        
        return issues
    
    def _validate_credits(self, raw_course: Any, course_code: str) -> List[ValidationIssue]:
        """Validate credit information with business rules"""
        issues = []
        
        if not hasattr(raw_course, 'enrollGroups') or not raw_course.enrollGroups:
            issues.append(ValidationIssue(
                ValidationSeverity.CRITICAL,
                "enrollGroups",
                "Missing enrollment groups",
                None
            ))
            return issues
        
        # Extract all credit values
        min_credits = []
        max_credits = []
        
        for group in raw_course.enrollGroups:
            if hasattr(group, 'unitsMinimum') and group.unitsMinimum is not None:
                min_credits.append(group.unitsMinimum)
            if hasattr(group, 'unitsMaximum') and group.unitsMaximum is not None:
                max_credits.append(group.unitsMaximum)
        
        # Business rule: courses must have credit information
        if not min_credits and not max_credits:
            issues.append(ValidationIssue(
                ValidationSeverity.CRITICAL,
                "credits",
                "No credit information found in any enrollment group",
                None
            ))
            return issues
        
        # Validate credit ranges
        if min_credits:
            min_credit = min(min_credits)
            max_credit = max(max_credits) if max_credits else min_credit
            
            # Business rule: credits must be reasonable
            if min_credit < 0 or min_credit > 10:
                issues.append(ValidationIssue(
                    ValidationSeverity.WARNING,
                    "credits",
                    f"Unusual minimum credits: {min_credit}",
                    min_credit,
                    "0-10 credits typical"
                ))
            
            if max_credit < min_credit:
                issues.append(ValidationIssue(
                    ValidationSeverity.CRITICAL,
                    "credits",
                    f"Maximum credits ({max_credit}) less than minimum ({min_credit})",
                    f"min={min_credit}, max={max_credit}"
                ))
        
        return issues
    
    def _validate_content(self, raw_course: Any, course_code: str) -> List[ValidationIssue]:
        """Validate course content fields"""
        issues = []
        
        # Title validation
        if not hasattr(raw_course, 'titleLong') or not raw_course.titleLong:
            issues.append(ValidationIssue(
                ValidationSeverity.CRITICAL,
                "title",
                "Missing course title",
                getattr(raw_course, 'titleLong', None)
            ))
        elif len(raw_course.titleLong.strip()) < 5:
            issues.append(ValidationIssue(
                ValidationSeverity.WARNING,
                "title",
                f"Very short title: '{raw_course.titleLong}'",
                raw_course.titleLong
            ))
        
        # Description validation (not critical - some courses legitimately have no description)
        if hasattr(raw_course, 'description') and raw_course.description:
            if len(raw_course.description.strip()) < 20:
                issues.append(ValidationIssue(
                    ValidationSeverity.INFO,
                    "description",
                    "Very short description",
                    len(raw_course.description.strip())
                ))
        
        return issues
    
    def _validate_enrollment_groups(self, raw_course: Any, course_code: str) -> List[ValidationIssue]:
        """Validate enrollment group structure"""
        issues = []
        
        if not hasattr(raw_course, 'enrollGroups') or not raw_course.enrollGroups:
            issues.append(ValidationIssue(
                ValidationSeverity.CRITICAL,
                "enrollGroups",
                "Missing enrollment groups",
                None
            ))
            return issues
        
        # Validate each enrollment group
        for i, group in enumerate(raw_course.enrollGroups):
            if not hasattr(group, 'classSections') or not group.classSections:
                issues.append(ValidationIssue(
                    ValidationSeverity.WARNING,
                    f"enrollGroups[{i}].classSections",
                    f"Enrollment group {i} has no class sections",
                    None
                ))
        
        return issues


class DataQualityTracker:
    """
    Tracks data quality metrics across the validation process.
    
    Provides comprehensive monitoring of validation issues and trends.
    """
    
    def __init__(self):
        self.total_courses = 0
        self.validation_failures = 0
        self.issue_counts = {severity: 0 for severity in ValidationSeverity}
        self.field_issues = {}  # field -> count mapping
        self.course_issues = []  # detailed issue tracking
        
    def record_validation(self, result: ValidationResult):
        """Record a validation result for tracking"""
        self.total_courses += 1
        
        if not result.is_valid:
            self.validation_failures += 1
        
        # Track issue counts by severity
        for issue in result.issues:
            self.issue_counts[issue.severity] += 1
            
            # Track field-specific issues
            if issue.field not in self.field_issues:
                self.field_issues[issue.field] = 0
            self.field_issues[issue.field] += 1
        
        # Store detailed course issues for analysis
        if result.issues:
            self.course_issues.append({
                'course_code': result.course_code,
                'is_valid': result.is_valid,
                'critical_count': len(result.critical_issues),
                'warning_count': len(result.warning_issues),
                'issues': result.issues
            })
    
    def get_quality_report(self) -> Dict[str, Any]:
        """Generate comprehensive data quality report"""
        success_rate = ((self.total_courses - self.validation_failures) / self.total_courses * 100) if self.total_courses > 0 else 0
        
        # Find most problematic fields
        top_problematic_fields = sorted(
            self.field_issues.items(), 
            key=lambda x: x[1], 
            reverse=True
        )[:10]
        
        # Find courses with most issues
        problematic_courses = sorted(
            [c for c in self.course_issues if not c['is_valid']], 
            key=lambda x: x['critical_count'] + x['warning_count'],
            reverse=True
        )[:10]
        
        return {
            'summary': {
                'total_courses': self.total_courses,
                'validation_failures': self.validation_failures,
                'success_rate_pct': round(success_rate, 2),
                'critical_issues': self.issue_counts[ValidationSeverity.CRITICAL],
                'warning_issues': self.issue_counts[ValidationSeverity.WARNING],
                'info_issues': self.issue_counts[ValidationSeverity.INFO]
            },
            'top_problematic_fields': top_problematic_fields,
            'problematic_courses': problematic_courses,
            'quality_score': round(success_rate, 1)  # Simple quality score based on success rate
        }
    
    def log_quality_summary(self):
        """Log a summary of data quality findings"""
        report = self.get_quality_report()
        summary = report['summary']
        
        logger.info(f"DATA QUALITY SUMMARY:")
        logger.info(f"  Total courses processed: {summary['total_courses']}")
        logger.info(f"  Validation success rate: {summary['success_rate_pct']}%")
        logger.info(f"  Critical issues: {summary['critical_issues']}")
        logger.info(f"  Warning issues: {summary['warning_issues']}")
        logger.info(f"  Quality score: {report['quality_score']}/100")
        
        if report['top_problematic_fields']:
            logger.info(f"  Most problematic fields:")
            for field, count in report['top_problematic_fields'][:5]:
                logger.info(f"    {field}: {count} issues")