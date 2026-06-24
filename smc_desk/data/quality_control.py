from typing import List
from datetime import datetime, timedelta, timezone
import uuid

from smc_desk.data.schemas import Candle, DataQualityIncident, IncidentType, Severity

class DataQualityReport:
    def __init__(self, instrument: str, timeframe: str):
        self.instrument = instrument
        self.timeframe = timeframe
        self.incidents: List[DataQualityIncident] = []
        self.generated_at = datetime.now(timezone.utc)

    @property
    def is_clean(self) -> bool:
        return len(self.incidents) == 0

def detect_gaps(candles: List[Candle], expected_step: timedelta) -> List[DataQualityIncident]:
    incidents = []
    if len(candles) < 2:
        return incidents
    
    for i in range(1, len(candles)):
        prev_candle = candles[i-1]
        curr_candle = candles[i]
        diff = curr_candle.open_time - prev_candle.close_time
        
        # Open time is usually equal to prev close_time in Binance data or exactly expected_step later depending on convention.
        # Assuming open_time = previous close_time
        if curr_candle.open_time != prev_candle.close_time:
            # We have a gap
            incidents.append(DataQualityIncident(
                incident_id=str(uuid.uuid4()),
                instrument=curr_candle.instrument,
                timeframe=curr_candle.timeframe,
                incident_type=IncidentType.GAP,
                severity=Severity.HIGH,
                details=f"Gap detected between {prev_candle.close_time} and {curr_candle.open_time}",
                detected_at=datetime.now(timezone.utc)
            ))
    return incidents

def detect_duplicates(candles: List[Candle]) -> List[DataQualityIncident]:
    incidents = []
    seen_times = set()
    for candle in candles:
        if candle.open_time in seen_times:
            incidents.append(DataQualityIncident(
                incident_id=str(uuid.uuid4()),
                instrument=candle.instrument,
                timeframe=candle.timeframe,
                incident_type=IncidentType.DUPLICATE,
                severity=Severity.HIGH,
                details=f"Duplicate candle found at {candle.open_time}",
                detected_at=datetime.now(timezone.utc)
            ))
        seen_times.add(candle.open_time)
    return incidents

def validate_ohlc_integrity(candles: List[Candle]) -> List[DataQualityIncident]:
    incidents = []
    for candle in candles:
        if not (candle.low <= candle.open <= candle.high and candle.low <= candle.close <= candle.high):
            incidents.append(DataQualityIncident(
                incident_id=str(uuid.uuid4()),
                instrument=candle.instrument,
                timeframe=candle.timeframe,
                incident_type=IncidentType.MISMATCH,
                severity=Severity.CRITICAL,
                details=f"OHLC integrity violation at {candle.open_time}: O={candle.open}, H={candle.high}, L={candle.low}, C={candle.close}",
                detected_at=datetime.now(timezone.utc)
            ))
    return incidents

def generate_quality_report(candles: List[Candle], expected_step: timedelta) -> DataQualityReport:
    if not candles:
        raise ValueError("Cannot generate report for empty candle list.")
    
    report = DataQualityReport(
        instrument=candles[0].instrument,
        timeframe=candles[0].timeframe
    )
    
    report.incidents.extend(detect_duplicates(candles))
    report.incidents.extend(detect_gaps(candles, expected_step))
    report.incidents.extend(validate_ohlc_integrity(candles))
    
    return report
