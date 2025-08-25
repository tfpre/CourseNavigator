"""
Comprehensive data quality monitoring and error reporting system.

Provides production-grade tracking of validation metrics, trend analysis,
and alerting for data quality degradation.
"""

import json
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, asdict
from enum import Enum
import statistics

from python.data_ingestion.validation import DataQualityTracker, ValidationResult, ValidationSeverity

logger = logging.getLogger(__name__)


class QualityMetricType(Enum):
    """Types of quality metrics we track"""
    VALIDATION_SUCCESS_RATE = "validation_success_rate"
    PREREQUISITE_CONFIDENCE = "prerequisite_confidence" 
    CROSS_LISTING_COVERAGE = "cross_listing_coverage"
    PARSING_ERROR_RATE = "parsing_error_rate"
    DATA_COMPLETENESS = "data_completeness"


@dataclass
class QualityMetricSnapshot:
    """Single snapshot of a quality metric"""
    timestamp: datetime
    metric_type: QualityMetricType
    value: float
    context: Dict[str, Any]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'timestamp': self.timestamp.isoformat(),
            'metric_type': self.metric_type.value,
            'value': self.value,
            'context': self.context
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'QualityMetricSnapshot':
        return cls(
            timestamp=datetime.fromisoformat(data['timestamp']),
            metric_type=QualityMetricType(data['metric_type']),
            value=data['value'],
            context=data['context']
        )


@dataclass
class QualityAlert:
    """Alert for quality degradation"""
    timestamp: datetime
    metric_type: QualityMetricType
    current_value: float
    threshold: float
    severity: str  # "warning", "critical"
    description: str
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'timestamp': self.timestamp.isoformat(),
            'metric_type': self.metric_type.value,
            'current_value': self.current_value,
            'threshold': self.threshold,
            'severity': self.severity,
            'description': self.description
        }


class QualityMonitor:
    """
    Production-grade data quality monitoring system.
    
    Features:
    - Real-time metric tracking
    - Trend analysis and alerting
    - Historical data storage
    - Dashboard data generation
    - Integration with validation pipeline
    """
    
    def __init__(self, storage_dir: Path = None):
        self.storage_dir = storage_dir or Path("/tmp/quality_monitor")
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        
        # Metric storage
        self.metrics_file = self.storage_dir / "quality_metrics.jsonl"
        self.alerts_file = self.storage_dir / "quality_alerts.jsonl"
        
        # Quality thresholds for alerting
        self.thresholds = {
            QualityMetricType.VALIDATION_SUCCESS_RATE: {'warning': 0.95, 'critical': 0.90},
            QualityMetricType.PREREQUISITE_CONFIDENCE: {'warning': 0.70, 'critical': 0.60},
            QualityMetricType.CROSS_LISTING_COVERAGE: {'warning': 0.30, 'critical': 0.20},
            QualityMetricType.PARSING_ERROR_RATE: {'warning': 0.05, 'critical': 0.10},
            QualityMetricType.DATA_COMPLETENESS: {'warning': 0.95, 'critical': 0.90}
        }
        
        # Recent metrics cache for trend analysis
        self.recent_metrics: Dict[QualityMetricType, List[QualityMetricSnapshot]] = {}
        self._load_recent_metrics()
    
    def record_pipeline_run(self, validation_results: List[ValidationResult], 
                          parsing_stats: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Record quality metrics from a complete pipeline run.
        
        Args:
            validation_results: List of validation results from all courses
            parsing_stats: Additional parsing statistics
            
        Returns:
            Dict with recorded metrics and any alerts generated
        """
        timestamp = datetime.utcnow()
        metrics_recorded = []
        alerts_generated = []
        
        # Calculate validation success rate
        total_courses = len(validation_results)
        successful_validations = sum(1 for r in validation_results if r.is_valid)
        success_rate = successful_validations / total_courses if total_courses > 0 else 0
        
        success_metric = QualityMetricSnapshot(
            timestamp=timestamp,
            metric_type=QualityMetricType.VALIDATION_SUCCESS_RATE,
            value=success_rate,
            context={
                'total_courses': total_courses,
                'successful_validations': successful_validations,
                'critical_failures': sum(1 for r in validation_results if not r.is_valid)
            }
        )
        metrics_recorded.append(success_metric)
        
        # Calculate prerequisite confidence metrics
        prereq_confidences = []
        courses_with_prereqs = 0
        low_confidence_count = 0
        
        for result in validation_results:
            # This would need integration with prerequisite parser results
            # For now, simulate based on known statistics
            pass
        
        # If we have parsing stats, extract prerequisite confidence
        if parsing_stats and 'prerequisite_confidences' in parsing_stats:
            prereq_confidences = parsing_stats['prerequisite_confidences']
            courses_with_prereqs = len(prereq_confidences)
            avg_confidence = statistics.mean(prereq_confidences) if prereq_confidences else 0
            low_confidence_count = sum(1 for c in prereq_confidences if c < 0.8)
            
            confidence_metric = QualityMetricSnapshot(
                timestamp=timestamp,
                metric_type=QualityMetricType.PREREQUISITE_CONFIDENCE,
                value=avg_confidence,
                context={
                    'courses_with_prereqs': courses_with_prereqs,
                    'avg_confidence': avg_confidence,
                    'low_confidence_count': low_confidence_count,
                    'low_confidence_rate': low_confidence_count / courses_with_prereqs if courses_with_prereqs > 0 else 0
                }
            )
            metrics_recorded.append(confidence_metric)
        
        # Calculate cross-listing coverage
        if parsing_stats and 'cross_listing_stats' in parsing_stats:
            cross_listing_stats = parsing_stats['cross_listing_stats']
            coverage_rate = cross_listing_stats.get('coverage_rate', 0)
            
            coverage_metric = QualityMetricSnapshot(
                timestamp=timestamp,
                metric_type=QualityMetricType.CROSS_LISTING_COVERAGE,
                value=coverage_rate,
                context=cross_listing_stats
            )
            metrics_recorded.append(coverage_metric)
        
        # Record metrics and check for alerts
        for metric in metrics_recorded:
            self._record_metric(metric)
            alert = self._check_threshold(metric)
            if alert:
                alerts_generated.append(alert)
                self._record_alert(alert)
        
        return {
            'metrics_recorded': len(metrics_recorded),
            'alerts_generated': len(alerts_generated),
            'alerts': [alert.to_dict() for alert in alerts_generated],
            'quality_score': self._calculate_overall_quality_score()
        }
    
    def get_dashboard_data(self, hours_back: int = 24) -> Dict[str, Any]:
        """Generate data for quality monitoring dashboard"""
        cutoff_time = datetime.utcnow() - timedelta(hours=hours_back)
        
        dashboard_data = {
            'timestamp': datetime.utcnow().isoformat(),
            'time_range_hours': hours_back,
            'metrics': {},
            'trends': {},
            'alerts': self._get_recent_alerts(hours_back),
            'overall_quality_score': self._calculate_overall_quality_score()
        }
        
        # Get latest values and trends for each metric type
        for metric_type in QualityMetricType:
            recent_values = self._get_recent_values(metric_type, cutoff_time)
            
            if recent_values:
                latest_value = recent_values[-1].value
                trend = self._calculate_trend(recent_values)
                
                dashboard_data['metrics'][metric_type.value] = {
                    'current_value': latest_value,
                    'trend': trend,
                    'threshold_warning': self.thresholds[metric_type]['warning'],
                    'threshold_critical': self.thresholds[metric_type]['critical'],
                    'status': self._get_metric_status(latest_value, metric_type),
                    'data_points': len(recent_values)
                }
                
                # Historical data for charts
                dashboard_data['trends'][metric_type.value] = [
                    {'timestamp': m.timestamp.isoformat(), 'value': m.value}
                    for m in recent_values
                ]
        
        return dashboard_data
    
    def generate_quality_report(self, hours_back: int = 24) -> str:
        """Generate human-readable quality report"""
        dashboard_data = self.get_dashboard_data(hours_back)
        
        report_lines = [
            f"# Data Quality Report",
            f"Generated: {dashboard_data['timestamp']}",
            f"Time Range: Last {hours_back} hours",
            f"Overall Quality Score: {dashboard_data['overall_quality_score']:.1f}/100",
            f"",
            f"## Metrics Summary"
        ]
        
        for metric_name, metric_data in dashboard_data['metrics'].items():
            status_emoji = {'good': '✅', 'warning': '⚠️', 'critical': '❌'}.get(metric_data['status'], '❓')
            trend_emoji = {'improving': '📈', 'stable': '➡️', 'degrading': '📉'}.get(metric_data['trend'], '❓')
            
            report_lines.extend([
                f"",
                f"### {metric_name.replace('_', ' ').title()} {status_emoji}",
                f"Current Value: {metric_data['current_value']:.3f}",
                f"Trend: {metric_data['trend'].title()} {trend_emoji}",
                f"Warning Threshold: {metric_data['threshold_warning']:.3f}",
                f"Critical Threshold: {metric_data['threshold_critical']:.3f}"
            ])
        
        # Recent alerts
        if dashboard_data['alerts']:
            report_lines.extend([
                f"",
                f"## Recent Alerts ({len(dashboard_data['alerts'])})"
            ])
            
            for alert in dashboard_data['alerts'][-5:]:  # Last 5 alerts
                alert_emoji = {'warning': '⚠️', 'critical': '❌'}.get(alert['severity'], '❓')
                report_lines.append(
                    f"- {alert_emoji} {alert['timestamp']}: {alert['description']}"
                )
        
        return '\n'.join(report_lines)
    
    def _record_metric(self, metric: QualityMetricSnapshot):
        """Record a quality metric to persistent storage"""
        # Write to JSONL file
        with open(self.metrics_file, 'a') as f:
            f.write(json.dumps(metric.to_dict()) + '\n')
        
        # Update in-memory cache
        if metric.metric_type not in self.recent_metrics:
            self.recent_metrics[metric.metric_type] = []
        
        self.recent_metrics[metric.metric_type].append(metric)
        
        # Keep only last 100 metrics per type in memory
        if len(self.recent_metrics[metric.metric_type]) > 100:
            self.recent_metrics[metric.metric_type] = self.recent_metrics[metric.metric_type][-100:]
    
    def _record_alert(self, alert: QualityAlert):
        """Record a quality alert"""
        with open(self.alerts_file, 'a') as f:
            f.write(json.dumps(alert.to_dict()) + '\n')
        
        # Log alert
        if alert.severity == 'critical':
            logger.error(f"CRITICAL QUALITY ALERT: {alert.description}")
        else:
            logger.warning(f"QUALITY WARNING: {alert.description}")
    
    def _check_threshold(self, metric: QualityMetricSnapshot) -> Optional[QualityAlert]:
        """Check if metric violates quality thresholds"""
        thresholds = self.thresholds.get(metric.metric_type)
        if not thresholds:
            return None
        
        current_value = metric.value
        
        # For metrics where higher is better
        if metric.metric_type in [QualityMetricType.VALIDATION_SUCCESS_RATE, 
                                QualityMetricType.PREREQUISITE_CONFIDENCE,
                                QualityMetricType.CROSS_LISTING_COVERAGE,
                                QualityMetricType.DATA_COMPLETENESS]:
            if current_value < thresholds['critical']:
                severity = 'critical'
                threshold = thresholds['critical']
            elif current_value < thresholds['warning']:
                severity = 'warning'
                threshold = thresholds['warning']
            else:
                return None
        
        # For metrics where lower is better (error rates)
        elif metric.metric_type in [QualityMetricType.PARSING_ERROR_RATE]:
            if current_value > thresholds['critical']:
                severity = 'critical'
                threshold = thresholds['critical']
            elif current_value > thresholds['warning']:
                severity = 'warning'
                threshold = thresholds['warning']
            else:
                return None
        else:
            return None
        
        return QualityAlert(
            timestamp=metric.timestamp,
            metric_type=metric.metric_type,
            current_value=current_value,
            threshold=threshold,
            severity=severity,
            description=f"{metric.metric_type.value} is {current_value:.3f}, below {severity} threshold of {threshold:.3f}"
        )
    
    def _load_recent_metrics(self):
        """Load recent metrics from storage"""
        if not self.metrics_file.exists():
            return
        
        cutoff_time = datetime.utcnow() - timedelta(hours=24)
        
        try:
            with open(self.metrics_file, 'r') as f:
                for line in f:
                    if line.strip():
                        metric_data = json.loads(line)
                        metric = QualityMetricSnapshot.from_dict(metric_data)
                        
                        if metric.timestamp > cutoff_time:
                            if metric.metric_type not in self.recent_metrics:
                                self.recent_metrics[metric.metric_type] = []
                            self.recent_metrics[metric.metric_type].append(metric)
        
        except Exception as e:
            logger.warning(f"Failed to load recent metrics: {e}")
    
    def _get_recent_values(self, metric_type: QualityMetricType, 
                          cutoff_time: datetime) -> List[QualityMetricSnapshot]:
        """Get recent values for a metric type"""
        if metric_type not in self.recent_metrics:
            return []
        
        return [m for m in self.recent_metrics[metric_type] if m.timestamp > cutoff_time]
    
    def _calculate_trend(self, recent_values: List[QualityMetricSnapshot]) -> str:
        """Calculate trend direction for recent values"""
        if len(recent_values) < 2:
            return 'stable'
        
        values = [m.value for m in recent_values]
        
        # Simple trend calculation based on first vs last values
        first_half = values[:len(values)//2]
        second_half = values[len(values)//2:]
        
        if not first_half or not second_half:
            return 'stable'
        
        first_avg = statistics.mean(first_half)
        second_avg = statistics.mean(second_half)
        
        change_threshold = 0.01  # 1% change threshold
        
        if second_avg > first_avg + change_threshold:
            return 'improving'
        elif second_avg < first_avg - change_threshold:
            return 'degrading'
        else:
            return 'stable'
    
    def _get_metric_status(self, value: float, metric_type: QualityMetricType) -> str:
        """Get status (good/warning/critical) for a metric value"""
        thresholds = self.thresholds.get(metric_type, {})
        
        # For metrics where higher is better
        if metric_type in [QualityMetricType.VALIDATION_SUCCESS_RATE, 
                          QualityMetricType.PREREQUISITE_CONFIDENCE,
                          QualityMetricType.CROSS_LISTING_COVERAGE,
                          QualityMetricType.DATA_COMPLETENESS]:
            if value < thresholds.get('critical', 0):
                return 'critical'
            elif value < thresholds.get('warning', 0):
                return 'warning'
            else:
                return 'good'
        
        # For metrics where lower is better
        elif metric_type in [QualityMetricType.PARSING_ERROR_RATE]:
            if value > thresholds.get('critical', 1):
                return 'critical'
            elif value > thresholds.get('warning', 1):
                return 'warning'
            else:
                return 'good'
        
        return 'good'
    
    def _get_recent_alerts(self, hours_back: int) -> List[Dict[str, Any]]:
        """Get recent alerts for dashboard"""
        if not self.alerts_file.exists():
            return []
        
        cutoff_time = datetime.utcnow() - timedelta(hours=hours_back)
        alerts = []
        
        try:
            with open(self.alerts_file, 'r') as f:
                for line in f:
                    if line.strip():
                        alert_data = json.loads(line)
                        alert_time = datetime.fromisoformat(alert_data['timestamp'])
                        
                        if alert_time > cutoff_time:
                            alerts.append(alert_data)
        
        except Exception as e:
            logger.warning(f"Failed to load recent alerts: {e}")
        
        return sorted(alerts, key=lambda x: x['timestamp'], reverse=True)
    
    def _calculate_overall_quality_score(self) -> float:
        """Calculate overall quality score (0-100)"""
        scores = []
        
        for metric_type in QualityMetricType:
            if metric_type in self.recent_metrics and self.recent_metrics[metric_type]:
                latest_metric = self.recent_metrics[metric_type][-1]
                
                # Normalize to 0-100 scale based on thresholds
                thresholds = self.thresholds.get(metric_type, {})
                warning_threshold = thresholds.get('warning', 0.5)
                
                if metric_type in [QualityMetricType.VALIDATION_SUCCESS_RATE,
                                  QualityMetricType.PREREQUISITE_CONFIDENCE,
                                  QualityMetricType.CROSS_LISTING_COVERAGE,
                                  QualityMetricType.DATA_COMPLETENESS]:
                    # Higher is better - normalize where warning threshold = 80 points
                    score = min(100, (latest_metric.value / warning_threshold) * 80)
                else:
                    # Lower is better (error rates)
                    score = max(0, 100 - (latest_metric.value / warning_threshold) * 80)
                
                scores.append(score)
        
        return statistics.mean(scores) if scores else 50.0  # Default neutral score