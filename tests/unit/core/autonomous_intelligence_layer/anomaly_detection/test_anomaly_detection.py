import pytest
from datetime import datetime
from src.core.autonomous_intelligence_layer.anomaly_detection.anomaly_detection import (
    AnomalyDetection,
    AnomalyDetectionConfig,
    AnomalyType,
    AnomalySeverity,
    DataPoint,
    Anomaly
)

@pytest.fixture
def anomaly_detector():
    config = AnomalyDetectionConfig(min_data_points=3)
    return AnomalyDetection(config)

def test_record_data_point(anomaly_detector):
    point = anomaly_detector.record_data_point("p1", 10.5)
    assert point is not None
    assert point.point_id == "p1"
    assert point.value == 10.5
    assert len(anomaly_detector.data_points) == 1
    assert len(anomaly_detector.data_history) == 1

def test_record_data_point_max_limit():
    config = AnomalyDetectionConfig(max_data_points=2)
    detector = AnomalyDetection(config)
    detector.record_data_point("p1", 10.0)
    detector.record_data_point("p2", 20.0)
    point = detector.record_data_point("p3", 30.0)
    assert point is None
    assert len(detector.data_points) == 2

def test_detect_statistical_anomalies(anomaly_detector):
    anomaly_detector.config.detection_method = "statistical"
    anomaly_detector.config.z_score_threshold = 1.0
    
    # Normal points
    anomaly_detector.record_data_point("p1", 10.0)
    anomaly_detector.record_data_point("p2", 10.0)
    anomaly_detector.record_data_point("p3", 10.0)
    
    # Anomaly point
    anomaly_detector.record_data_point("p4", 100.0)
    
    anomalies = anomaly_detector.detect_anomalies()
    assert len(anomalies) > 0
    assert anomalies[0].anomaly_type == AnomalyType.STATISTICAL
    assert anomalies[0].data_point_id == "p4"

def test_detect_behavioral_anomalies(anomaly_detector):
    anomaly_detector.config.detection_method = "behavioral"
    anomaly_detector.config.iqr_multiplier = 1.0
    
    # Normal points
    for i in range(10):
        anomaly_detector.record_data_point(f"p{i}", 10.0)
        
    # Anomaly point
    anomaly_detector.record_data_point("p_anom", 100.0)
    
    anomalies = anomaly_detector.detect_anomalies()
    assert len(anomalies) > 0
    assert anomalies[0].anomaly_type == AnomalyType.BEHAVIORAL
    assert anomalies[0].data_point_id == "p_anom"

def test_detect_contextual_anomalies(anomaly_detector):
    anomaly_detector.config.detection_method = "contextual"
    for i in range(5):
        anomaly_detector.record_data_point(f"p{i}", 10.0)
    
    anomalies = anomaly_detector.detect_anomalies()
    assert len(anomalies) == 0

def test_insufficient_data_points(anomaly_detector):
    anomaly_detector.record_data_point("p1", 10.0)
    anomalies = anomaly_detector.detect_anomalies()
    assert len(anomalies) == 0

def test_calculate_severity(anomaly_detector):
    assert anomaly_detector._calculate_severity(3.0) == AnomalySeverity.LOW
    assert anomaly_detector._calculate_severity(4.5) == AnomalySeverity.MEDIUM
    assert anomaly_detector._calculate_severity(5.5) == AnomalySeverity.HIGH
    assert anomaly_detector._calculate_severity(6.5) == AnomalySeverity.CRITICAL

def test_getters(anomaly_detector):
    anomaly_detector.config.detection_method = "statistical"
    anomaly_detector.config.z_score_threshold = 1.0
    
    anomaly_detector.record_data_point("p1", 10.0)
    anomaly_detector.record_data_point("p2", 10.0)
    anomaly_detector.record_data_point("p3", 10.0)
    anomaly_detector.record_data_point("p4", 100.0)
    
    anomalies = anomaly_detector.detect_anomalies()
    
    assert anomaly_detector.get_data_point("p1") is not None
    assert anomaly_detector.get_data_point("nonexistent") is None
    
    anomaly_id = anomalies[0].anomaly_id
    assert anomaly_detector.get_anomaly(anomaly_id) is not None
    assert anomaly_detector.get_anomaly("nonexistent") is None
    
    severity = anomalies[0].severity
    assert len(anomaly_detector.get_anomalies_by_severity(severity)) > 0
    
    assert len(anomaly_detector.get_anomalies_by_type(AnomalyType.STATISTICAL)) > 0
    
    report = anomaly_detector.get_anomaly_report()
    assert report["total_data_points"] == 4
    assert report["total_anomalies"] > 0
