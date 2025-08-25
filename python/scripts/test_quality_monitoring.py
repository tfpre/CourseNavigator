#!/usr/bin/env python3
"""
Test comprehensive data quality monitoring with real FA25 data.

Demonstrates production-grade quality tracking, alerting, and reporting.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import gzip
import logging
from pathlib import Path
from python.data_ingestion.models import RawCourse, CleanCourse
from python.data_ingestion.validation import BusinessRuleValidator, DataQualityTracker
from python.data_ingestion.quality_monitor import QualityMonitor, QualityMetricType

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


def run_pipeline_with_monitoring():
    """Run data pipeline with comprehensive quality monitoring"""
    
    # Initialize quality monitor
    monitor_dir = Path("/tmp/course_navigator_quality")
    quality_monitor = QualityMonitor(storage_dir=monitor_dir)
    
    logger.info("Starting data pipeline with quality monitoring")
    
    # Load FA25 data
    raw_data_dir = Path("/mnt/c/dev/CourseNavigator/data/raw")
    fa25_files = list(raw_data_dir.glob("FA25_*.json.gz"))
    
    all_validation_results = []
    prerequisite_confidences = []
    cross_listing_stats = {'courses_with_cross_listings': 0, 'total_courses': 0}
    parsing_errors = 0
    
    for file_path in fa25_files[:3]:  # Test with first 3 files
        logger.info(f"Processing {file_path.name}")
        
        try:
            with gzip.open(file_path, 'rt') as f:
                data = json.load(f)
                
            classes_data = data.get('data', {}).get('classes', [])
            validator = BusinessRuleValidator(strict_mode=False)
            
            for class_data in classes_data:
                try:
                    # Validate raw course
                    raw_course = RawCourse(**class_data)
                    validation_result = validator.validate_course(raw_course, "FA25")
                    all_validation_results.append(validation_result)
                    
                    # Process course and extract quality metrics
                    clean_course = CleanCourse.from_raw(raw_course, "FA25", strict_mode=False)
                    
                    # Track prerequisite confidence if available
                    if clean_course.prereq_confidence is not None:
                        prerequisite_confidences.append(clean_course.prereq_confidence)
                    
                    # Track cross-listing coverage
                    cross_listing_stats['total_courses'] += 1
                    if clean_course.cross_listings:
                        cross_listing_stats['courses_with_cross_listings'] += 1
                    
                except Exception as e:
                    parsing_errors += 1
                    logger.debug(f"Parsing error for course {class_data.get('crseId')}: {e}")
                    
        except Exception as e:
            logger.error(f"Error processing {file_path}: {e}")
    
    # Calculate additional stats
    total_courses = len(all_validation_results)
    cross_listing_stats['coverage_rate'] = (
        cross_listing_stats['courses_with_cross_listings'] / 
        cross_listing_stats['total_courses'] 
        if cross_listing_stats['total_courses'] > 0 else 0
    )
    
    parsing_stats = {
        'prerequisite_confidences': prerequisite_confidences,
        'cross_listing_stats': cross_listing_stats,
        'parsing_error_rate': parsing_errors / total_courses if total_courses > 0 else 0,
        'total_parsing_errors': parsing_errors
    }
    
    # Record pipeline run in quality monitor
    monitoring_result = quality_monitor.record_pipeline_run(
        validation_results=all_validation_results,
        parsing_stats=parsing_stats
    )
    
    logger.info(f"Quality monitoring results:")
    logger.info(f"  Metrics recorded: {monitoring_result['metrics_recorded']}")
    logger.info(f"  Alerts generated: {monitoring_result['alerts_generated']}")
    logger.info(f"  Overall quality score: {monitoring_result['quality_score']:.1f}/100")
    
    # Show any alerts
    for alert in monitoring_result['alerts']:
        severity_emoji = {'warning': '⚠️', 'critical': '❌'}.get(alert['severity'], '❓')
        logger.info(f"  {severity_emoji} ALERT: {alert['description']}")
    
    return quality_monitor, monitoring_result


def demonstrate_dashboard_and_reporting(quality_monitor: QualityMonitor):
    """Demonstrate dashboard data and quality reporting"""
    
    logger.info("\n=== QUALITY DASHBOARD DATA ===")
    
    # Get dashboard data
    dashboard_data = quality_monitor.get_dashboard_data(hours_back=24)
    
    logger.info(f"Overall Quality Score: {dashboard_data['overall_quality_score']:.1f}/100")
    logger.info(f"Time Range: Last {dashboard_data['time_range_hours']} hours")
    
    # Show current metrics
    for metric_name, metric_data in dashboard_data['metrics'].items():
        status_emoji = {'good': '✅', 'warning': '⚠️', 'critical': '❌'}.get(metric_data['status'], '❓')
        trend_emoji = {'improving': '📈', 'stable': '➡️', 'degrading': '📉'}.get(metric_data['trend'], '❓')
        
        logger.info(f"{status_emoji} {metric_name}: {metric_data['current_value']:.3f} {trend_emoji}")
        logger.info(f"   Warning: {metric_data['threshold_warning']:.3f}, Critical: {metric_data['threshold_critical']:.3f}")
    
    # Show recent alerts
    if dashboard_data['alerts']:
        logger.info(f"\nRecent Alerts ({len(dashboard_data['alerts'])}):")
        for alert in dashboard_data['alerts'][-3:]:  # Last 3 alerts
            alert_emoji = {'warning': '⚠️', 'critical': '❌'}.get(alert['severity'], '❓')
            logger.info(f"  {alert_emoji} {alert['timestamp']}: {alert['description']}")
    
    logger.info("\n=== QUALITY REPORT ===")
    
    # Generate and display quality report
    quality_report = quality_monitor.generate_quality_report(hours_back=24)
    for line in quality_report.split('\n'):
        logger.info(line)


def simulate_quality_degradation(quality_monitor: QualityMonitor):
    """Simulate quality degradation to test alerting"""
    
    logger.info("\n=== SIMULATING QUALITY DEGRADATION ===")
    
    from python.data_ingestion.quality_monitor import QualityMetricSnapshot
    from datetime import datetime
    
    # Simulate degrading prerequisite confidence
    bad_confidence_metric = QualityMetricSnapshot(
        timestamp=datetime.utcnow(),
        metric_type=QualityMetricType.PREREQUISITE_CONFIDENCE,
        value=0.55,  # Below critical threshold of 0.60
        context={'simulated': True, 'avg_confidence': 0.55}
    )
    
    # Record the bad metric
    quality_monitor._record_metric(bad_confidence_metric)
    
    # Check for alerts
    alert = quality_monitor._check_threshold(bad_confidence_metric)
    if alert:
        quality_monitor._record_alert(alert)
        logger.info(f"❌ CRITICAL ALERT GENERATED: {alert.description}")
    
    # Simulate low validation success rate
    bad_validation_metric = QualityMetricSnapshot(
        timestamp=datetime.utcnow(),
        metric_type=QualityMetricType.VALIDATION_SUCCESS_RATE,
        value=0.85,  # Below critical threshold of 0.90
        context={'simulated': True, 'success_rate': 0.85}
    )
    
    quality_monitor._record_metric(bad_validation_metric)
    alert = quality_monitor._check_threshold(bad_validation_metric)
    if alert:
        quality_monitor._record_alert(alert)
        logger.info(f"❌ CRITICAL ALERT GENERATED: {alert.description}")
    
    # Show updated dashboard
    logger.info("\nUpdated dashboard after quality degradation:")
    dashboard_data = quality_monitor.get_dashboard_data(hours_back=1)
    logger.info(f"Overall Quality Score: {dashboard_data['overall_quality_score']:.1f}/100")
    
    for metric_name, metric_data in dashboard_data['metrics'].items():
        status_emoji = {'good': '✅', 'warning': '⚠️', 'critical': '❌'}.get(metric_data['status'], '❓')
        logger.info(f"{status_emoji} {metric_name}: {metric_data['current_value']:.3f}")


def show_integration_example():
    """Show how to integrate quality monitoring with existing pipeline"""
    
    logger.info("\n=== INTEGRATION EXAMPLE ===")
    
    integration_code = '''
# In your data pipeline script:

from python.data_ingestion.quality_monitor import QualityMonitor

def process_cornell_data():
    # Initialize quality monitor
    quality_monitor = QualityMonitor()
    
    # Your existing pipeline code...
    validation_results = []
    prerequisite_confidences = []
    
    for course in courses:
        # Validate course
        result = validator.validate_course(course)
        validation_results.append(result)
        
        # Process course
        clean_course = CleanCourse.from_raw(course)
        if clean_course.prereq_confidence:
            prerequisite_confidences.append(clean_course.prereq_confidence)
    
    # Record quality metrics
    parsing_stats = {'prerequisite_confidences': prerequisite_confidences}
    monitoring_result = quality_monitor.record_pipeline_run(
        validation_results, parsing_stats
    )
    
    # Check for critical alerts
    if monitoring_result['alerts_generated'] > 0:
        logger.error("Quality alerts detected!")
        # Send notifications, halt pipeline, etc.
    
    return monitoring_result

# For monitoring dashboard:
dashboard_data = quality_monitor.get_dashboard_data()
quality_report = quality_monitor.generate_quality_report()
'''
    
    for line in integration_code.split('\n'):
        logger.info(f"    {line}")


if __name__ == "__main__":
    logger.info("Testing comprehensive data quality monitoring")
    
    # Run pipeline with monitoring
    quality_monitor, monitoring_result = run_pipeline_with_monitoring()
    
    # Demonstrate dashboard and reporting
    demonstrate_dashboard_and_reporting(quality_monitor)
    
    # Simulate quality issues to test alerting
    simulate_quality_degradation(quality_monitor)
    
    # Show integration guidance
    show_integration_example()
    
    logger.info("Quality monitoring test complete")