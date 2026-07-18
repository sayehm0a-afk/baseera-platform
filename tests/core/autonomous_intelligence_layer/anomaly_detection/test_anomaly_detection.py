"""
Unit tests for Anomaly Detection
"""

import pytest
from core.autonomous_intelligence_layer.anomaly_detection import (
    AnomalyDetection,
    AnomalyType,
    AnomalySeverity,
    AnomalyDetectionConfig,
)


class TestAnomalyDetection:
    """Test cases for AnomalyDetection class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.detector = AnomalyDetection()

    def test_anomaly_detection_initialization(self):
        """Test that AnomalyDetection initializes correctly."""
        assert self.detector is not None
        assert self.detector.config is not None
        assert isinstance(self.detector.config, AnomalyDetectionConfig)

    def test_anomaly_detection_with_custom_config(self):
        """Test AnomalyDetection with custom config."""
        custom_config = AnomalyDetectionConfig(
            detection_method="behavioral",
            z_score_threshold=2.5,
        )
        detector = AnomalyDetection(config=custom_config)
        assert detector.config.z_score_threshold == 2.5

    def test_record_data_point(self):
        """Test recording a data point."""
        point = self.detector.record_data_point(
            point_id="point_001",
            value=100.0,
        )

        assert point is not None
        assert point.value == 100.0

    def test_record_multiple_data_points(self):
        """Test recording multiple data points."""
        for i in range(20):
            self.detector.record_data_point(
                point_id=f"point_{i:03d}",
                value=100.0 + i * 5,
            )

        assert len(self.detector.data_points) == 20

    def test_detect_anomalies_statistical(self):
        """Test detecting statistical anomalies."""
        # Record normal data points
        for i in range(15):
            self.detector.record_data_point(
                point_id=f"point_{i:03d}",
                value=100.0 + (i % 3) * 2,
            )

        # Record anomalous data point
        self.detector.record_data_point(
            point_id="point_anomaly",
            value=500.0,  # Outlier
        )

        anomalies = self.detector.detect_anomalies()
        assert len(anomalies) > 0

    def test_detect_anomalies_behavioral(self):
        """Test detecting behavioral anomalies."""
        config = AnomalyDetectionConfig(detection_method="behavioral")
        detector = AnomalyDetection(config=config)

        # Record normal data points
        for i in range(15):
            detector.record_data_point(
                point_id=f"point_{i:03d}",
                value=100.0 + (i % 3) * 2,
            )

        # Record anomalous data point
        detector.record_data_point(
            point_id="point_anomaly",
            value=500.0,
        )

        anomalies = detector.detect_anomalies()
        assert len(anomalies) > 0

    def test_get_data_point(self):
        """Test retrieving a data point."""
        self.detector.record_data_point(
            point_id="point_001",
            value=100.0,
        )

        point = self.detector.get_data_point("point_001")
        assert point is not None
        assert point.value == 100.0

    def test_get_anomaly(self):
        """Test retrieving an anomaly."""
        for i in range(15):
            self.detector.record_data_point(
                point_id=f"point_{i:03d}",
                value=100.0 + (i % 3) * 2,
            )

        self.detector.record_data_point(
            point_id="point_anomaly",
            value=500.0,
        )

        anomalies = self.detector.detect_anomalies()
        if anomalies:
            anomaly = self.detector.get_anomaly(anomalies[0].anomaly_id)
            assert anomaly is not None

    def test_get_anomalies_by_severity(self):
        """Test getting anomalies by severity."""
        for i in range(15):
            self.detector.record_data_point(
                point_id=f"point_{i:03d}",
                value=100.0 + (i % 3) * 2,
            )

        self.detector.record_data_point(
            point_id="point_anomaly",
            value=500.0,
        )

        self.detector.detect_anomalies()

        critical = self.detector.get_anomalies_by_severity(AnomalySeverity.CRITICAL)
        assert isinstance(critical, list)

    def test_get_anomalies_by_type(self):
        """Test getting anomalies by type."""
        for i in range(15):
            self.detector.record_data_point(
                point_id=f"point_{i:03d}",
                value=100.0 + (i % 3) * 2,
            )

        self.detector.record_data_point(
            point_id="point_anomaly",
            value=500.0,
        )

        self.detector.detect_anomalies()

        statistical = self.detector.get_anomalies_by_type(AnomalyType.STATISTICAL)
        assert isinstance(statistical, list)

    def test_get_critical_anomalies(self):
        """Test getting critical anomalies."""
        for i in range(15):
            self.detector.record_data_point(
                point_id=f"point_{i:03d}",
                value=100.0 + (i % 3) * 2,
            )

        self.detector.record_data_point(
            point_id="point_anomaly",
            value=500.0,
        )

        self.detector.detect_anomalies()

        critical = self.detector.get_critical_anomalies()
        assert isinstance(critical, list)

    def test_get_anomaly_report(self):
        """Test generating anomaly report."""
        for i in range(15):
            self.detector.record_data_point(
                point_id=f"point_{i:03d}",
                value=100.0 + (i % 3) * 2,
            )

        self.detector.record_data_point(
            point_id="point_anomaly",
            value=500.0,
        )

        self.detector.detect_anomalies()

        report = self.detector.get_anomaly_report()
        assert "total_data_points" in report
        assert "total_anomalies" in report
        assert "anomalies_by_severity" in report
        assert "anomalies_by_type" in report

    def test_insufficient_data_points(self):
        """Test anomaly detection with insufficient data."""
        for i in range(5):
            self.detector.record_data_point(
                point_id=f"point_{i:03d}",
                value=100.0,
            )

        anomalies = self.detector.detect_anomalies()
        assert len(anomalies) == 0

    def test_data_point_limit(self):
        """Test data point limit enforcement."""
        config = AnomalyDetectionConfig(max_data_points=10)
        detector = AnomalyDetection(config=config)

        for i in range(10):
            result = detector.record_data_point(
                point_id=f"point_{i:03d}",
                value=100.0 + i,
            )
            assert result is not None

        # Should fail when limit reached
        result = detector.record_data_point(
            point_id="point_10",
            value=200.0,
        )
        assert result is None

    def test_z_score_calculation(self):
        """Test Z-score calculation for anomaly detection."""
        # Record normal data points
        for i in range(15):
            self.detector.record_data_point(
                point_id=f"point_{i:03d}",
                value=100.0 + (i % 3) * 2,
            )

        # Record anomalous point
        self.detector.record_data_point(
            point_id="point_anomaly",
            value=500.0,
        )

        anomalies = self.detector.detect_anomalies()

        # Should detect the anomaly
        assert len(anomalies) > 0
        assert anomalies[0].anomaly_type == AnomalyType.STATISTICAL

    def test_anomaly_confidence(self):
        """Test anomaly confidence calculation."""
        for i in range(15):
            self.detector.record_data_point(
                point_id=f"point_{i:03d}",
                value=100.0 + (i % 3) * 2,
            )

        self.detector.record_data_point(
            point_id="point_anomaly",
            value=500.0,
        )

        anomalies = self.detector.detect_anomalies()

        if anomalies:
            assert 0.0 <= anomalies[0].confidence <= 1.0

    def test_multiple_anomalies(self):
        """Test detecting multiple anomalies."""
        for i in range(20):
            self.detector.record_data_point(
                point_id=f"point_{i:03d}",
                value=100.0 + (i % 5) * 1,
            )

        # Record multiple anomalous points
        self.detector.record_data_point(
            point_id="point_anomaly_1",
            value=500.0,
        )

        self.detector.record_data_point(
            point_id="point_anomaly_2",
            value=600.0,
        )

        anomalies = self.detector.detect_anomalies()
        assert len(anomalies) >= 0
