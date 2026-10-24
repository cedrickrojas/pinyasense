"""
Time-series forecasting utilities for pineapple growth stage and harvest timing.

This module builds lightweight trend models from sensor history to forecast
near-term environmental conditions, then estimates crop growth stage and
optimal harvest date. Saved field status records (measurements, observed
growth stage, manual soil moisture) calibrate the forecast and the monthly
plant/fruit size predictions.
"""

from __future__ import annotations

import glob
import json
import math
import os
import random
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import numpy as np

GROWTH_STAGES = [
    "Vegetative Stage",
    "Pre-Flowering Stage",
    "Fruit Development Stage",
    "Ripening Stage",
    "Optimal Harvest Window",
]

# Shape of the logistic fruit growth curve (progress 0..1 from fruit onset to harvest).
_FRUIT_STEEPNESS = 7.0
_FRUIT_MIDPOINT = 0.45


class PineappleGrowthForecaster:
    """Forecast pineapple growth stage and optimal harvest window."""

    # Profile values are in effective growth days and map to local farm cycles.
    FARM_PROFILES = {
        "standard": {
            "cycle_days": 540,
            "vegetative_end": 240,
            "pre_flowering_end": 330,
            "fruit_development_end": 480,
            "ripening_end": 540,
        },
        "smooth_cayenne": {
            "cycle_days": 560,
            "vegetative_end": 250,
            "pre_flowering_end": 350,
            "fruit_development_end": 505,
            "ripening_end": 560,
        },
        "md2": {
            "cycle_days": 500,
            "vegetative_end": 220,
            "pre_flowering_end": 315,
            "fruit_development_end": 450,
            "ripening_end": 500,
        },
    }

    # Typical mature fruit size per profile; the reference the fruit curve grows toward.
    FRUIT_REFERENCE = {
        "standard": {"diameter_cm": 12.5, "length_cm": 17.0},
        "smooth_cayenne": {"diameter_cm": 13.5, "length_cm": 19.0},
        "md2": {"diameter_cm": 12.5, "length_cm": 16.5},
    }
    # kg per cm^3 of diameter^2 x length: barrel-shaped fruit (shape factor ~0.75) at ~0.98 g/cm^3.
    FRUIT_WEIGHT_FACTOR = 0.000577
    MAX_PREDICTION_MONTHS = 30
    PREDICTION_METRICS = ("height_cm", "fruit_diameter_cm", "fruit_length_cm", "weight_kg")
    # Allowed measured/reference ratios. Fruit size is bounded by variety, so its range is tighter.
    CALIBRATION_BOUNDS = {
        "height_cm": (0.5, 1.8),
        "fruit_diameter_cm": (0.75, 1.3),
        "fruit_length_cm": (0.75, 1.3),
        "weight_kg": (0.6, 1.6),
    }

    def __init__(self, data_folder: str = "sensor_data"):
        if os.path.isabs(data_folder):
            self.data_folder = data_folder
        else:
            project_folder = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            self.data_folder = os.path.join(project_folder, data_folder)

    def _date_range(self, start: datetime, end: datetime) -> List[datetime]:
        days = []
        current = datetime(start.year, start.month, start.day)
        final = datetime(end.year, end.month, end.day)
        while current <= final:
            days.append(current)
            current += timedelta(days=1)
        return days

    def _safe_iso_to_datetime(self, value: str) -> Optional[datetime]:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is not None:
                parsed = parsed.astimezone().replace(tzinfo=None)
            return parsed
        except Exception:
            return None

    def _load_daily_sensor_rows(self, sensor_prefix: str, days: int = 90) -> List[Dict]:
        """Load and aggregate sensor rows from daily JSON files."""
        end_dt = datetime.now()
        start_dt = end_dt - timedelta(days=max(1, days))

        aggregated: Dict[str, Dict[str, List[float]]] = {}

        if not os.path.exists(self.data_folder):
            return []

        for day in self._date_range(start_dt, end_dt):
            date_key = day.strftime('%Y%m%d')
            file_paths = [os.path.join(self.data_folder, f"{sensor_prefix}_{date_key}.json")]
            if sensor_prefix == "soil_moisture":
                file_paths.extend(glob.glob(os.path.join(self.data_folder, f"{sensor_prefix}_zone*_{date_key}.json")))

            for file_path in file_paths:
                if not os.path.exists(file_path):
                    continue

                try:
                    with open(file_path, "r") as f:
                        rows = json.load(f)
                except Exception:
                    continue

                if not isinstance(rows, list):
                    continue

                for row in rows:
                    if str(row.get("data_source", "")).lower().startswith("simulated"):
                        continue

                    timestamp = self._safe_iso_to_datetime(str(row.get("timestamp", "")))
                    if not timestamp:
                        continue
                    if timestamp < start_dt or timestamp > end_dt:
                        continue

                    key = timestamp.strftime("%Y-%m-%d")
                    if key not in aggregated:
                        aggregated[key] = {
                            "soil_pct": [],
                            "temp_c": [],
                            "humidity_pct": [],
                        }

                    if sensor_prefix == "soil_moisture":
                        soil_pct = self._soil_row_to_percent(row)
                        if soil_pct is not None:
                            aggregated[key]["soil_pct"].append(soil_pct)

                    if sensor_prefix == "temp_humidity":
                        temp = row.get("temperature")
                        humid = row.get("humidity")
                        if isinstance(temp, (int, float)):
                            aggregated[key]["temp_c"].append(float(temp))
                        if isinstance(humid, (int, float)):
                            aggregated[key]["humidity_pct"].append(float(humid))

        merged_rows = []
        for key, values in sorted(aggregated.items()):
            merged_rows.append(
                {
                    "date": key,
                    "soil_pct": self._mean_or_none(values["soil_pct"]),
                    "temp_c": self._mean_or_none(values["temp_c"]),
                    "humidity_pct": self._mean_or_none(values["humidity_pct"]),
                }
            )

        return merged_rows

    def _aggregate_sensor_rows(
        self,
        rows: List[Dict],
        sensor_prefix: str,
        start_dt: datetime,
        end_dt: datetime,
    ) -> List[Dict]:
        """Aggregate normalized Firestore sensor readings by calendar day."""
        aggregated: Dict[str, Dict[str, List[float]]] = {}

        for row in rows:
            if str(row.get("data_source", "")).strip().lower() == "simulated_daily":
                continue

            sensor_type = str(row.get("sensor_type", "")).strip().lower()
            if sensor_prefix == "soil_moisture":
                if not sensor_type.startswith("soil_moisture"):
                    continue
                if str(row.get("sensor_mode", "")).strip().lower() != "digital_do":
                    continue
            elif not sensor_type.startswith(("temp_humidity", "temperature_humidity")):
                continue

            timestamp = self._safe_iso_to_datetime(str(row.get("timestamp", "")))
            if timestamp is None or timestamp < start_dt or timestamp > end_dt:
                continue

            key = timestamp.strftime("%Y-%m-%d")
            values = aggregated.setdefault(
                key,
                {"soil_pct": [], "temp_c": [], "humidity_pct": []},
            )
            if sensor_prefix == "soil_moisture":
                soil_pct = self._soil_row_to_percent(row)
                if soil_pct is not None:
                    values["soil_pct"].append(soil_pct)
            else:
                temp = row.get("temperature")
                humidity = row.get("humidity")
                if isinstance(temp, (int, float)):
                    values["temp_c"].append(float(temp))
                if isinstance(humidity, (int, float)):
                    values["humidity_pct"].append(float(humidity))

        return [
            {
                "date": day,
                "soil_pct": self._mean_or_none(values["soil_pct"]),
                "temp_c": self._mean_or_none(values["temp_c"]),
                "humidity_pct": self._mean_or_none(values["humidity_pct"]),
            }
            for day, values in sorted(aggregated.items())
        ]

    def _soil_row_to_percent(self, row: Dict) -> Optional[float]:
        """
        Normalize soil reading into 0 to 100 where higher means wetter soil.
        Supports both digital DO and analog ADC modes used by this project.
        """
        mode = str(row.get("sensor_mode", "digital_do")).strip().lower()

        if mode in {'arduino_analog', 'estimated_percent'}:
            value = row.get('value')
            if (isinstance(value, (int, float)) and not isinstance(value, bool)
                    and math.isfinite(value) and 0 <= value <= 100):
                return float(value)
            return None

        if mode == "digital_do":
            raw = row.get("raw_value", row.get("value"))
            if (not isinstance(raw, (int, float)) or isinstance(raw, bool)
                    or not math.isfinite(raw) or raw not in (0, 1)):
                return None
            return 80.0 if int(raw) == 0 else 25.0

        # analog_adc: based on existing thresholds where higher ADC is drier
        raw = row.get("raw_value", row.get("value"))
        if not isinstance(raw, (int, float)) or isinstance(raw, bool) or not math.isfinite(raw):
            return None

        adc = max(0.0, min(1023.0, float(raw)))
        pct = 100.0 * (1.0 - adc / 1023.0)
        return max(0.0, min(100.0, pct))

    def _mean_or_none(self, values: List[float]) -> Optional[float]:
        if not values:
            return None
        return float(sum(values) / len(values))

    def _fit_linear_trend(self, values: List[float]) -> Tuple[float, float]:
        """Return slope and intercept for y = slope*x + intercept."""
        if not values:
            return 0.0, 0.0
        if len(values) == 1:
            return 0.0, float(values[0])

        x = np.arange(len(values), dtype=float)
        y = np.array(values, dtype=float)
        slope, intercept = np.polyfit(x, y, 1)
        return float(slope), float(intercept)

    def _impute_series(self, values: List[Optional[float]], default_value: float) -> List[float]:
        """Forward-fill and back-fill missing values with a conservative default."""
        if not values:
            return []

        output: List[float] = [default_value if v is None else float(v) for v in values]

        # Forward fill
        for i in range(1, len(output)):
            if values[i] is None:
                output[i] = output[i - 1]

        # Back fill for leading gaps
        for i in range(len(output) - 2, -1, -1):
            if values[i] is None:
                output[i] = output[i + 1]

        return output

    def _daily_environment_score(
        self,
        soil_pct: Optional[float],
        temp_c: Optional[float],
        humidity_pct: Optional[float],
    ) -> Optional[float]:
        """Score only available sensor metrics, scaling their weights to 100%."""
        score_parts = []
        if soil_pct is not None:
            score_parts.append((max(0.0, 100.0 - abs(soil_pct - 60.0) * 1.5), 0.4))
        if temp_c is not None:
            score_parts.append((max(0.0, 100.0 - abs(temp_c - 28.0) * 6.0), 0.35))
        if humidity_pct is not None:
            score_parts.append((max(0.0, 100.0 - abs(humidity_pct - 70.0) * 2.0), 0.25))
        if not score_parts:
            return None
        total_weight = sum(weight for _, weight in score_parts)
        return sum(score * weight for score, weight in score_parts) / total_weight

    def _simulate_soil_moisture(
        self, future: List[Dict], initial_soil: Optional[float], start: datetime
    ) -> Dict:
        """Illustrative proxy water balance for the chart, never measured history.

        Losses and water inputs are demo assumptions in proxy percentage points,
        not calibrated volumetric water content or a weather forecast. Date-based
        seeds keep refreshes and overlapping forecast horizons consistent.
        """
        moisture = 55.0 if initial_soil is None else max(0.0, min(100.0, initial_soil))
        initial = moisture
        daily = []
        for item in future:
            rng = random.Random(f"pinyasense-soil-scenario-v1:{item['date']}")
            rain_gain = rng.uniform(10.0, 24.0) if rng.random() < 0.22 else 0.0
            temp = item["temperature_c"] if item["temperature_c"] is not None else 28.0
            humidity = item["humidity_percent"] if item["humidity_percent"] is not None else 70.0
            drying = rng.uniform(2.8, 4.8) * max(0.6, min(1.5, temp / 28.0))
            drying *= max(0.65, min(1.4, (110.0 - humidity) / 40.0))
            if rain_gain:
                drying *= 0.65
            drainage = max(0.0, moisture - 65.0) * 0.16
            moisture -= drying + drainage
            irrigation_gain = 0.0
            if moisture + rain_gain < 35.0:
                irrigation_gain = rng.uniform(58.0, 66.0) - (moisture + rain_gain)
            moisture = max(8.0, min(95.0, moisture + rain_gain + irrigation_gain))
            event = "Simulated irrigation" if irrigation_gain else (
                "Simulated rain" if rain_gain else "Simulated drying / drainage"
            )
            daily.append({
                "date": item["date"],
                "soil_moisture_percent": round(moisture, 2),
                "event": event,
                "data_source": "simulated",
            })
        return {
            "data_source": "simulated",
            "initial_soil_moisture_percent": round(initial, 2),
            "initial_source": "latest_soil_proxy" if initial_soil is not None else "demo_default",
            "start_date": start.strftime("%Y-%m-%d"),
            "daily": daily,
        }

    def _model_growth_scores(self, future: List[Dict], soil_scenario: Dict) -> Dict:
        """Score the soil scenario without changing sensor forecasts or harvest dates.

        Reuse the existing suitability rule, rather than adding random score noise.
        Missing temperature/humidity stay absent instead of contributing ideal scores.
        These are illustrative conditions, not measured growth or model accuracy.
        """
        environment_by_date = {item["date"]: item for item in future}
        daily = []
        for soil_day in soil_scenario["daily"]:
            environment = environment_by_date[soil_day["date"]]
            score = self._daily_environment_score(
                soil_day["soil_moisture_percent"],
                environment["temperature_c"],
                environment["humidity_percent"],
            )
            daily.append({
                **soil_day,
                "temperature_c": environment["temperature_c"],
                "humidity_percent": environment["humidity_percent"],
                "growth_score": round(score, 2),
            })
        return {
            "data_source": "simulated",
            "score_type": "environmental_suitability",
            "initial_source": soil_scenario["initial_source"],
            "daily": daily,
        }

    def _estimate_size_profile(self, days_since_planting: int) -> Dict[str, float]:
        """Estimate pineapple plant size from crop age."""
        capped_days = max(0, min(int(days_since_planting), 540))
        early_days = min(capped_days, 90)
        late_days = max(0, capped_days - 90)

        expected_height_cm = 12.0 + (early_days * 0.26) + (late_days * 0.10)
        expected_canopy_cm = 18.0 + (early_days * 0.36) + (late_days * 0.14)

        target_90_day_height_cm = 12.0 + (90 * 0.26)
        target_90_day_canopy_cm = 18.0 + (90 * 0.36)

        return {
            "expected_height_cm": round(expected_height_cm, 1),
            "expected_canopy_cm": round(expected_canopy_cm, 1),
            "target_90_day_height_cm": round(target_90_day_height_cm, 1),
            "target_90_day_height_range_cm": [round(target_90_day_height_cm * 0.85, 1), round(target_90_day_height_cm * 1.15, 1)],
            "target_90_day_canopy_cm": round(target_90_day_canopy_cm, 1),
            "target_90_day_canopy_range_cm": [round(target_90_day_canopy_cm * 0.85, 1), round(target_90_day_canopy_cm * 1.15, 1)],
        }

    def _resolve_profile(
        self,
        profile: str,
        cycle_days: Optional[int],
        stage_vegetative_end: Optional[int],
        stage_pre_flowering_end: Optional[int],
        stage_fruit_development_end: Optional[int],
        stage_ripening_end: Optional[int],
    ) -> Dict[str, int]:
        selected = self.FARM_PROFILES.get(profile, self.FARM_PROFILES["standard"]).copy()

        if cycle_days is not None:
            selected["cycle_days"] = int(cycle_days)
        if stage_vegetative_end is not None:
            selected["vegetative_end"] = int(stage_vegetative_end)
        if stage_pre_flowering_end is not None:
            selected["pre_flowering_end"] = int(stage_pre_flowering_end)
        if stage_fruit_development_end is not None:
            selected["fruit_development_end"] = int(stage_fruit_development_end)
        if stage_ripening_end is not None:
            selected["ripening_end"] = int(stage_ripening_end)

        v = selected["vegetative_end"]
        p = selected["pre_flowering_end"]
        f = selected["fruit_development_end"]
        r = selected["ripening_end"]
        c = selected["cycle_days"]
        if not (120 <= v < p < f < r <= c <= 700):
            raise ValueError(
                "Invalid stage boundaries. Ensure vegetative < pre_flowering < fruit_development < ripening <= cycle_days."
            )

        return selected

    def _stage_from_effective_day(self, effective_day: float, profile_cfg: Dict[str, int]) -> str:
        if effective_day < profile_cfg["vegetative_end"]:
            return GROWTH_STAGES[0]
        if effective_day < profile_cfg["pre_flowering_end"]:
            return GROWTH_STAGES[1]
        if effective_day < profile_cfg["fruit_development_end"]:
            return GROWTH_STAGES[2]
        if effective_day < profile_cfg["ripening_end"]:
            return GROWTH_STAGES[3]
        return GROWTH_STAGES[4]

    def _stage_bounds(self, stage: str, profile_cfg: Dict[str, int]) -> Tuple[float, float]:
        """Effective-day range [start, end) of a growth stage."""
        edges = [
            0.0,
            float(profile_cfg["vegetative_end"]),
            float(profile_cfg["pre_flowering_end"]),
            float(profile_cfg["fruit_development_end"]),
            float(profile_cfg["ripening_end"]),
            math.inf,
        ]
        index = GROWTH_STAGES.index(stage)
        return edges[index], edges[index + 1]

    def _prepare_status_logs(self, status_logs: Optional[List[Dict]], plant_dt: datetime, now: datetime) -> List[Dict]:
        """Keep status records dated between planting and now, oldest first, with day offsets."""
        prepared = []
        for log in status_logs or []:
            logged_at = self._safe_iso_to_datetime(str(log.get("logged_at", "")))
            if logged_at is None or logged_at < plant_dt or logged_at > now + timedelta(minutes=10):
                continue
            item = dict(log)
            item["_dt"] = logged_at
            item["_dap"] = max(0, (logged_at - plant_dt).days)
            prepared.append(item)
        prepared.sort(key=lambda item: item["_dt"])
        return prepared

    def _collect_daily_environment(
        self,
        history_days: int,
        logs: List[Dict],
        now: datetime,
        sensor_rows: Optional[List[Dict]] = None,
    ) -> Tuple[Dict[str, Dict], int, int]:
        """Merge sensor history by day; manual soil readings from status records fill days without sensor soil data.

        Returns (by_day, sensor_days, status_soil_days).
        """
        if sensor_rows is None:
            soil_rows = self._load_daily_sensor_rows("soil_moisture", days=history_days)
            th_rows = self._load_daily_sensor_rows("temp_humidity", days=history_days)
        else:
            start_dt = now - timedelta(days=max(1, history_days))
            soil_rows = self._aggregate_sensor_rows(sensor_rows, "soil_moisture", start_dt, now)
            th_rows = self._aggregate_sensor_rows(sensor_rows, "temp_humidity", start_dt, now)

        by_day: Dict[str, Dict[str, Optional[float]]] = {}
        for row in soil_rows:
            by_day.setdefault(row["date"], {"soil_pct": None, "temp_c": None, "humidity_pct": None})
            by_day[row["date"]]["soil_pct"] = row.get("soil_pct")

        for row in th_rows:
            by_day.setdefault(row["date"], {"soil_pct": None, "temp_c": None, "humidity_pct": None})
            by_day[row["date"]]["temp_c"] = row.get("temp_c")
            by_day[row["date"]]["humidity_pct"] = row.get("humidity_pct")

        sensor_days = len(by_day)

        cutoff = now - timedelta(days=max(1, history_days))
        manual: Dict[str, List[float]] = {}
        for log in logs if sensor_rows is None else []:
            soil = log.get("soil_moisture")
            if soil is None or log["_dt"] < cutoff:
                continue
            manual.setdefault(log["_dt"].strftime("%Y-%m-%d"), []).append(float(soil))

        status_soil_days = 0
        for day, values in manual.items():
            row = by_day.setdefault(day, {"soil_pct": None, "temp_c": None, "humidity_pct": None})
            if row["soil_pct"] is None:
                row["soil_pct"] = sum(values) / len(values)
                status_soil_days += 1

        return by_day, sensor_days, status_soil_days

    def _measured_growth_rate(self, logs: List[Dict]) -> Optional[Dict]:
        """Compare the measured height growth rate with the reference curve over the same period."""
        by_day: Dict[int, float] = {}
        for log in logs:
            if log.get("height_cm") is not None and float(log["height_cm"]) > 0:
                by_day[log["_dap"]] = float(log["height_cm"])
        points = sorted(by_day.items())[-4:]
        if len(points) < 2 or points[-1][0] - points[0][0] < 14:
            return None

        days = np.array([p[0] for p in points], dtype=float)
        heights = np.array([p[1] for p in points], dtype=float)
        observed = float(np.polyfit(days, heights, 1)[0])
        span = points[-1][0] - points[0][0]
        expected = (
            self._estimate_size_profile(points[-1][0])["expected_height_cm"]
            - self._estimate_size_profile(points[0][0])["expected_height_cm"]
        ) / span
        if expected <= 0.01:
            return None

        raw_ratio = observed / expected
        return {
            "observed_cm_per_day": round(observed, 3),
            "expected_cm_per_day": round(expected, 3),
            "ratio": round(max(0.85, min(1.15, raw_ratio)), 3),
            "raw_ratio": round(raw_ratio, 3),
            "measurements": len(points),
        }

    def forecast_growth_and_harvest(
        self,
        planting_date: Optional[str] = None,
        horizon_days: int = 30,
        history_days: int = 90,
        profile: str = "standard",
        cycle_days: Optional[int] = None,
        stage_vegetative_end: Optional[int] = None,
        stage_pre_flowering_end: Optional[int] = None,
        stage_fruit_development_end: Optional[int] = None,
        stage_ripening_end: Optional[int] = None,
        actual_height_cm: Optional[float] = None,
        actual_canopy_cm: Optional[float] = None,
        status_logs: Optional[List[Dict]] = None,
        sensor_rows: Optional[List[Dict]] = None,
    ) -> Dict:
        """
        Forecast growth stage and optimal harvest time from sensor time-series,
        calibrated with saved field status records when provided.

        planting_date format: YYYY-MM-DD
        """
        horizon_days = max(7, min(90, int(horizon_days)))
        history_days = max(14, min(365, int(history_days)))
        profile = (profile or "standard").strip().lower()

        profile_cfg = self._resolve_profile(
            profile=profile,
            cycle_days=cycle_days,
            stage_vegetative_end=stage_vegetative_end,
            stage_pre_flowering_end=stage_pre_flowering_end,
            stage_fruit_development_end=stage_fruit_development_end,
            stage_ripening_end=stage_ripening_end,
        )

        if planting_date:
            try:
                plant_dt = datetime.strptime(planting_date, "%Y-%m-%d")
            except ValueError:
                raise ValueError("planting_date must be in YYYY-MM-DD format")
        else:
            # Fallback assumption when no date is provided.
            plant_dt = datetime.now() - timedelta(days=120)

        now = datetime.now()
        logs = self._prepare_status_logs(status_logs, plant_dt, now)
        latest_log = logs[-1] if logs else None
        warnings: List[str] = []

        # Collect daily sensor history (plus manual soil readings from status records)
        by_day, sensor_days, status_soil_days = self._collect_daily_environment(
            history_days, logs, now, sensor_rows=sensor_rows
        )
        observed_days = len(by_day)
        soil_sensor_days = sum(1 for row in by_day.values() if row["soil_pct"] is not None)

        if not by_day:
            warnings.append("No actual sensor history found. The charts show a modeled scenario; sensor-based growth scores need recorded sensor readings.")
        elif soil_sensor_days == 0 and sensor_rows is not None:
            warnings.append("No digital DO soil readings were found in Firebase for this history window.")

        sorted_days = sorted(by_day.keys())
        soil_series = self._impute_series([by_day[d]["soil_pct"] for d in sorted_days], default_value=55.0)
        temp_series = self._impute_series([by_day[d]["temp_c"] for d in sorted_days], default_value=28.0)
        humid_series = self._impute_series([by_day[d]["humidity_pct"] for d in sorted_days], default_value=70.0)
        has_soil_data = any(by_day[day]["soil_pct"] is not None for day in sorted_days)
        has_temp_data = any(by_day[day]["temp_c"] is not None for day in sorted_days)
        has_humidity_data = any(by_day[day]["humidity_pct"] is not None for day in sorted_days)

        historical_scores = []
        for day in sorted_days:
            score = self._daily_environment_score(
                by_day[day]["soil_pct"], by_day[day]["temp_c"], by_day[day]["humidity_pct"]
            )
            if score is not None:
                historical_scores.append(score)

        # Fit linear trend models
        soil_slope, soil_intercept = self._fit_linear_trend(soil_series)
        temp_slope, temp_intercept = self._fit_linear_trend(temp_series)
        humid_slope, humid_intercept = self._fit_linear_trend(humid_series)

        # Build horizon forecast
        future = []
        n_hist = len(sorted_days)
        first_day = datetime.strptime(sorted_days[0], "%Y-%m-%d") if sorted_days else now
        last_day = datetime.strptime(sorted_days[-1], "%Y-%m-%d") if sorted_days else now
        # Trend rows are positions in the series, not calendar days. With sparse history
        # (a few manual readings weeks apart) one row spans many days, so the trend has to
        # advance more slowly; with daily sensor data this is exactly one row per day.
        rows_per_day = min(1.0, n_hist / max(1, (last_day - first_day).days + 1))
        for i in range(1, horizon_days + 1):
            x = n_hist - 1 + i * rows_per_day
            soil_pred = max(0.0, min(100.0, soil_slope * x + soil_intercept)) if has_soil_data else None
            temp_pred = max(10.0, min(45.0, temp_slope * x + temp_intercept)) if has_temp_data else None
            humid_pred = max(20.0, min(100.0, humid_slope * x + humid_intercept)) if has_humidity_data else None

            score = self._daily_environment_score(soil_pred, temp_pred, humid_pred)
            forecast_date = (now + timedelta(days=i)).strftime("%Y-%m-%d")
            future.append(
                {
                    "date": forecast_date,
                    "soil_moisture_percent": None if soil_pred is None else round(soil_pred, 2),
                    "temperature_c": None if temp_pred is None else round(temp_pred, 2),
                    "humidity_percent": None if humid_pred is None else round(humid_pred, 2),
                    "growth_score": None if score is None else round(score, 2),
                }
            )

        valid_future_scores = [item["growth_score"] for item in future if item["growth_score"] is not None]
        avg_future_score = float(sum(valid_future_scores) / len(valid_future_scores)) if valid_future_scores else 70.0
        avg_historical_score = float(sum(historical_scores) / len(historical_scores)) if historical_scores else avg_future_score
        blended_env_score = (avg_historical_score * 0.6) + (avg_future_score * 0.4)

        # Convert elapsed calendar days into effective growth days using environment factor.
        days_since_planting = max(0, (now - plant_dt).days)
        env_factor = max(0.72, min(1.18, blended_env_score / 75.0))

        # Measured height growth speeds up or slows down development (half weight, bounded).
        growth_rate = self._measured_growth_rate(logs)
        if growth_rate:
            env_factor = max(0.72, min(1.18, env_factor * (1.0 + 0.5 * (growth_rate["ratio"] - 1.0))))

        effective_growth_days = days_since_planting * env_factor

        # The latest observed growth stage is ground truth: keep the model inside that stage.
        stage_adjustment = None
        if latest_log and latest_log.get("growth_stage") in GROWTH_STAGES:
            stage_start, stage_end = self._stage_bounds(latest_log["growth_stage"], profile_cfg)
            model_at_log = latest_log["_dap"] * env_factor
            observed_at_log = min(max(model_at_log, stage_start), stage_end - 1)
            if abs(observed_at_log - model_at_log) >= 1:
                stage_adjustment = observed_at_log - model_at_log
                effective_growth_days = max(0.0, effective_growth_days + stage_adjustment)

        stage = self._stage_from_effective_day(effective_growth_days, profile_cfg)

        target_effective_days = float(profile_cfg["cycle_days"])
        days_to_optimal = max(0, int(round((target_effective_days - effective_growth_days) / max(0.75, env_factor))))
        optimal_harvest_date = (now + timedelta(days=days_to_optimal)).strftime("%Y-%m-%d")

        if observed_days:
            confidence = 0.45 + 0.12 * math.log1p(observed_days)
        else:
            confidence = 0.30
        confidence += min(0.12, 0.04 * len(logs))
        if latest_log and (now - latest_log["_dt"]).days <= 30:
            confidence += 0.03
        if latest_log and latest_log.get("plant_condition") == "Critical":
            confidence -= 0.08
        confidence = max(0.2, min(0.95, confidence))
        size_profile = self._estimate_size_profile(days_since_planting)

        # Use the latest saved height when no explicit height was passed, compared at its own age.
        height_reference = size_profile
        if actual_height_cm is None and latest_log and latest_log.get("height_cm") is not None:
            actual_height_cm = latest_log["height_cm"]
            height_reference = self._estimate_size_profile(latest_log["_dap"])

        possible_problem = False
        growth_status = 'on_track'
        growth_alert = None
        problem_signals = []

        if actual_height_cm is not None:
            actual_height_cm = float(actual_height_cm)
            if actual_height_cm < height_reference['expected_height_cm'] * 0.85:
                possible_problem = True
                growth_status = 'below_expected'
                growth_alert = 'Measured plant height is below the expected range for its age.'
                problem_signals.append('Height is below the expected growth range.')

        if actual_canopy_cm is not None:
            actual_canopy_cm = float(actual_canopy_cm)
            if actual_canopy_cm < size_profile['expected_canopy_cm'] * 0.85:
                possible_problem = True
                growth_status = 'below_expected'
                if growth_alert is None:
                    growth_alert = 'Measured canopy spread is below the expected range for its age.'
                problem_signals.append('Canopy spread is below the expected growth range.')

        if growth_alert is None and (blended_env_score < 62 or effective_growth_days < days_since_planting * 0.9):
            possible_problem = True
            growth_status = 'slow_growth_risk'
            growth_alert = 'Environment trends suggest slower-than-expected growth. Check watering, nutrition, and pests.'
            problem_signals.append('Environmental trend suggests slow growth.')

        notes = [
            "Provide actual planting_date for best harvest-time accuracy.",
            "Model confidence improves with longer and cleaner sensor history.",
            "Digital soil sensor (DO) is converted into moisture proxy values for forecasting.",
            "The daily score chart estimates environmental suitability from the soil scenario; it is not measured plant growth or prediction accuracy.",
            "Most farms replace a pineapple plant after about 2 good-quality fruiting cycles.",
        ]
        if logs:
            notes.append(
                f"Forecast calibrated with {len(logs)} saved status record(s); latest on {latest_log['_dt'].strftime('%Y-%m-%d')}."
            )
            days_since_log = (now - latest_log["_dt"]).days
            if days_since_log > 30:
                warnings.append(
                    f"The latest status record is {days_since_log} days old. Save a new status to keep the forecast current."
                )
            condition = latest_log.get("plant_condition")
            if condition == "Critical":
                warnings.append("The latest status marks this plant as Critical. The harvest forecast may be unreliable until the issue is resolved.")
        if stage_adjustment is not None:
            shift_days = int(round(abs(stage_adjustment) / max(0.75, env_factor)))
            direction = "earlier" if stage_adjustment > 0 else "later"
            notes.append(
                f"Growth stage aligned with your latest observation ({latest_log['growth_stage']}); "
                f"harvest estimate moved about {shift_days} days {direction}."
            )
        if growth_rate:
            notes.append(
                f"Measured height growth is {growth_rate['raw_ratio']:.0%} of the reference rate "
                f"({growth_rate['observed_cm_per_day']:.2f} vs {growth_rate['expected_cm_per_day']:.2f} cm/day)."
            )
        if status_soil_days:
            notes.append(f"{status_soil_days} day(s) of soil moisture came from saved status records.")

        model_type = "Linear time-series trend + agronomic stage model"
        if logs:
            model_type += " + field measurement calibration"

        summary = {
            "planting_date": plant_dt.strftime("%Y-%m-%d"),
            "days_since_planting": days_since_planting,
            "effective_growth_days": round(effective_growth_days, 1),
            "predicted_growth_stage": stage,
            "optimal_harvest_date": optimal_harvest_date,
            "days_until_optimal_harvest": days_to_optimal,
            "profile_used": profile,
            "average_forecast_growth_score": round(avg_future_score, 2),
            "average_historical_growth_score": round(avg_historical_score, 2),
            "forecast_confidence": round(confidence, 3),
            "model_type": model_type,
            "environment_factor": round(env_factor, 4),
            "status_logs_used": len(logs),
            "latest_status_at": latest_log["logged_at"] if latest_log else None,
            "observed_growth_stage": latest_log.get("growth_stage") if latest_log else None,
            "latest_plant_condition": latest_log.get("plant_condition") if latest_log else None,
            "stage_adjustment_days": round(stage_adjustment, 1) if stage_adjustment is not None else None,
            "growth_rate": growth_rate,
            "sensor_days_used": sensor_days,
            "soil_sensor_days_used": soil_sensor_days,
            "status_soil_days_used": status_soil_days,
            "size_prediction": {
                "current_expected_height_cm": size_profile["expected_height_cm"],
                "current_expected_canopy_cm": size_profile["expected_canopy_cm"],
                "target_90_day_height_cm": size_profile["target_90_day_height_cm"],
                "target_90_day_height_range_cm": size_profile["target_90_day_height_range_cm"],
                "target_90_day_canopy_cm": size_profile["target_90_day_canopy_cm"],
                "target_90_day_canopy_range_cm": size_profile["target_90_day_canopy_range_cm"],
                "actual_height_cm": None if actual_height_cm is None else round(float(actual_height_cm), 1),
                "actual_canopy_cm": None if actual_canopy_cm is None else round(float(actual_canopy_cm), 1),
                "growth_status": growth_status,
                "possible_problem": possible_problem,
                "growth_alert": growth_alert,
                "problem_signals": problem_signals,
            },
            "productive_harvest_cycles": {
                "good_quality_cycles": 2,
                "replacement_recommended_after_cycles": 2,
                "note": "A pineapple plant usually gives one main fruit and may produce one strong ratoon crop. After about 2 good-quality harvests, fruit size and yield usually decline and replacement becomes practical.",
            },
        }

        soil_scenario = self._simulate_soil_moisture(
            future, soil_series[-1] if has_soil_data else None, now
        )
        return {
            "summary": summary,
            "forecast_window_days": horizon_days,
            "history_days_used": observed_days,
            "future_environment_forecast": future,
            "soil_moisture_simulation": soil_scenario,
            "growth_score_scenario": self._model_growth_scores(future, soil_scenario),
            "trend_coefficients": {
                "soil_moisture": {"slope": round(soil_slope, 4), "intercept": round(soil_intercept, 4)},
                "temperature": {"slope": round(temp_slope, 4), "intercept": round(temp_intercept, 4)},
                "humidity": {"slope": round(humid_slope, 4), "intercept": round(humid_intercept, 4)},
            },
            "stage_boundaries_days": profile_cfg,
            "notes": notes,
            "warnings": warnings,
        }

    # ============================================
    # MONTHLY PLANT / FRUIT SIZE PREDICTION
    # ============================================

    def _reference_height(self, effective_day: float) -> float:
        return self._estimate_size_profile(int(round(effective_day)))["expected_height_cm"]

    @staticmethod
    def _fruit_curve_bounds() -> Tuple[float, float]:
        low = 1.0 / (1.0 + math.exp(_FRUIT_STEEPNESS * _FRUIT_MIDPOINT))
        high = 1.0 / (1.0 + math.exp(-_FRUIT_STEEPNESS * (1.0 - _FRUIT_MIDPOINT)))
        return low, high

    @classmethod
    def _fruit_fraction(cls, effective_day: float, onset: float, harvest: float) -> Optional[float]:
        """Share of final fruit size (0..1) on a logistic curve from fruit onset to harvest; None before onset."""
        if effective_day < onset:
            return None
        t = min(1.0, (effective_day - onset) / max(1.0, harvest - onset))
        low, high = cls._fruit_curve_bounds()
        value = 1.0 / (1.0 + math.exp(-_FRUIT_STEEPNESS * (t - _FRUIT_MIDPOINT)))
        return (value - low) / (high - low)

    @classmethod
    def _fruit_progress(cls, fraction: float) -> float:
        """Inverse of `_fruit_fraction`: curve progress (0..1) at which fruit reaches `fraction` of final size."""
        low, high = cls._fruit_curve_bounds()
        value = low + min(max(fraction, 0.0), 0.999) * (high - low)
        return max(0.0, min(1.0, _FRUIT_MIDPOINT + math.log(value / (1.0 - value)) / _FRUIT_STEEPNESS))

    @staticmethod
    def _calibrate(points: List[Tuple[int, float, float]], bounds: Tuple[float, float] = (0.5, 1.8)) -> Optional[Dict]:
        """Summarize measured/reference ratios; recent measurements weigh more."""
        if not points:
            return None
        points = sorted(points)
        latest_dap = points[-1][0]
        low, high = bounds
        ratios = [max(low, min(high, value / reference)) for _, value, reference in points]
        weights = [math.exp(-(latest_dap - dap) / 60.0) for dap, _, _ in points]
        historical = sum(w * r for w, r in zip(weights, ratios)) / sum(weights)
        return {
            "n": len(points),
            "latest_dap": latest_dap,
            "latest_value": points[-1][1],
            "latest_ratio": ratios[-1],
            "historical_ratio": historical,
            "ratio_spread": float(np.std(ratios)) if len(ratios) > 1 else 0.0,
        }

    @staticmethod
    def _calibration_factor(calibration: Optional[Dict], dap: int) -> float:
        """Past months use the historical ratio; future months start at the latest ratio and relax toward it."""
        if not calibration:
            return 1.0
        if dap <= calibration["latest_dap"]:
            return calibration["historical_ratio"]
        relax = 1.0 - math.exp(-(dap - calibration["latest_dap"]) / 90.0)
        return calibration["latest_ratio"] + (calibration["historical_ratio"] - calibration["latest_ratio"]) * relax

    @staticmethod
    def _relative_uncertainty(calibration: Optional[Dict], dap: int, dap_now: int, sensor_days: int) -> float:
        if calibration:
            base = max(0.06, 0.18 - 0.03 * calibration["n"]) + min(0.1, calibration["ratio_spread"])
            anchor = calibration["latest_dap"]
        else:
            base = 0.25
            anchor = dap_now
        relative = base + 0.025 * abs(dap - anchor) / 30.0
        if sensor_days >= 14:
            relative -= 0.02
        return max(0.05, min(0.6, relative))

    def predict_monthly_growth(self, forecast: Dict, status_logs: Optional[List[Dict]] = None,
                               now: Optional[datetime] = None) -> Dict:
        """
        Predict plant height and fruit size for every month from planting to harvest.

        Reference curves (plant height from `_estimate_size_profile`, a logistic fruit
        curve from fruit onset to harvest) are driven by effective growth days from
        `forecast_growth_and_harvest`, then calibrated with the plant's own measurements.
        """
        now = now or datetime.now()
        summary = forecast["summary"]
        cfg = forecast["stage_boundaries_days"]
        profile = summary.get("profile_used", "standard")
        plant_dt = datetime.strptime(summary["planting_date"], "%Y-%m-%d")
        dap_now = int(summary["days_since_planting"])
        eff_now = float(summary["effective_growth_days"])
        env_factor = float(summary.get("environment_factor") or 1.0)
        sensor_days = int(forecast.get("history_days_used") or 0)
        logs = self._prepare_status_logs(status_logs, plant_dt, now)

        harvest_dap = dap_now + int(summary["days_until_optimal_harvest"])
        total_months = int(min(self.MAX_PREDICTION_MONTHS, max(1, math.ceil(max(harvest_dap, dap_now + 30) / 30.0))))
        current_month = max(1, math.ceil(dap_now / 30.0))

        def effective_at(dap: int) -> float:
            return max(0.0, eff_now + (dap - dap_now) * env_factor)

        notes = [
            "Predictions are estimates from agronomic reference growth curves for the selected farm profile, "
            "not exact measurements."
        ]

        fruit_ref = self.FRUIT_REFERENCE.get(profile, self.FRUIT_REFERENCE["standard"])
        profile_onset = float(cfg["pre_flowering_end"])
        fruit_span = float(cfg["cycle_days"]) - profile_onset
        fruit_onset = profile_onset

        # A fruit measurement shows how far along the fruit curve the plant is, so it
        # re-times fruit onset (e.g. after forced flowering) rather than inflating size.
        implied_onsets = []
        earliest_fruit_eff = None
        for log in logs:
            for field, final_size, start_size in (
                ("fruit_diameter_cm", fruit_ref["diameter_cm"], 2.5),
                ("fruit_length_cm", fruit_ref["length_cm"], 3.0),
            ):
                value = log.get(field)
                if value is None or float(value) <= 0:
                    continue
                eff = effective_at(log["_dap"])
                earliest_fruit_eff = eff if earliest_fruit_eff is None else min(earliest_fruit_eff, eff)
                fraction = (float(value) - start_size) / (final_size - start_size)
                if 0.02 <= fraction <= 0.95:
                    implied_onsets.append((log["_dap"], eff - self._fruit_progress(fraction) * fruit_span))
                break
        if implied_onsets:
            latest_fruit_dap = max(dap for dap, _ in implied_onsets)
            weights = [math.exp(-(latest_fruit_dap - dap) / 60.0) for dap, _ in implied_onsets]
            data_onset = sum(w * onset for w, (_, onset) in zip(weights, implied_onsets)) / sum(weights)
            fruit_onset = max(0.0, data_onset)
        if earliest_fruit_eff is not None and earliest_fruit_eff < fruit_onset:
            fruit_onset = earliest_fruit_eff
        fruit_harvest = fruit_onset + fruit_span

        onset_shift = fruit_onset - profile_onset
        if abs(onset_shift) >= 10:
            notes.append(
                "Fruit growth timing was adjusted from your fruit measurements (about "
                f"{abs(onset_shift) / max(0.75, env_factor):.0f} days {'earlier' if onset_shift < 0 else 'later'} "
                "than the profile expects)."
            )

        def reference(dap: int) -> Dict[str, Optional[float]]:
            eff = effective_at(dap)
            fraction = self._fruit_fraction(eff, fruit_onset, fruit_harvest)
            values: Dict[str, Optional[float]] = {"height_cm": self._reference_height(eff)}
            if fraction is None:
                values["fruit_diameter_cm"] = None
                values["fruit_length_cm"] = None
            else:
                values["fruit_diameter_cm"] = 2.5 + (fruit_ref["diameter_cm"] - 2.5) * fraction
                values["fruit_length_cm"] = 3.0 + (fruit_ref["length_cm"] - 3.0) * fraction
            return values

        def fruit_grown_enough(dap: int) -> bool:
            # Early fruit measurements only set timing (above); half-grown or larger fruit
            # also say something about final size.
            fraction = self._fruit_fraction(effective_at(dap), fruit_onset, fruit_harvest)
            return fraction is not None and fraction >= 0.5

        calibrations: Dict[str, Optional[Dict]] = {}
        for metric in ("height_cm", "fruit_diameter_cm", "fruit_length_cm"):
            points = []
            for log in logs:
                value = log.get(metric)
                ref_value = reference(log["_dap"])[metric]
                if metric != "height_cm" and not fruit_grown_enough(log["_dap"]):
                    continue
                if value is not None and float(value) > 0 and ref_value:
                    points.append((log["_dap"], float(value), ref_value))
            calibrations[metric] = self._calibrate(points, self.CALIBRATION_BOUNDS[metric])

        def dimension(metric: str, dap: int) -> Optional[float]:
            ref_value = reference(dap)[metric]
            if ref_value is None:
                return None
            return ref_value * self._calibration_factor(calibrations[metric], dap)

        def base_weight(dap: int) -> Optional[float]:
            diameter = dimension("fruit_diameter_cm", dap)
            length = dimension("fruit_length_cm", dap)
            if diameter is None or length is None:
                return None
            return self.FRUIT_WEIGHT_FACTOR * diameter * diameter * length

        weight_points = []
        for log in logs:
            weight = log.get("estimated_weight_kg")
            base = base_weight(log["_dap"])
            if weight is not None and float(weight) > 0 and base and fruit_grown_enough(log["_dap"]):
                weight_points.append((log["_dap"], float(weight), base))
        calibrations["weight_kg"] = self._calibrate(weight_points, self.CALIBRATION_BOUNDS["weight_kg"])

        def predicted(metric: str, dap: int) -> Optional[float]:
            if metric == "weight_kg":
                base = base_weight(dap)
                return None if base is None else base * self._calibration_factor(calibrations["weight_kg"], dap)
            return dimension(metric, dap)

        field_for_metric = {
            "height_cm": "height_cm",
            "fruit_diameter_cm": "fruit_diameter_cm",
            "fruit_length_cm": "fruit_length_cm",
            "weight_kg": "estimated_weight_kg",
        }
        actual_series: Dict[str, List[Dict]] = {metric: [] for metric in self.PREDICTION_METRICS}
        for log in logs:
            for metric, field in field_for_metric.items():
                value = log.get(field)
                if value is None or float(value) <= 0:
                    continue
                actual_series[metric].append({
                    "x": round(log["_dap"] / 30.0, 2),
                    "days_after_planting": log["_dap"],
                    "value": round(float(value), 2),
                    "logged_at": log.get("logged_at"),
                })

        months = []
        previous: Dict[str, float] = {}
        for month in range(1, total_months + 1):
            dap = month * 30
            if month < current_month:
                phase = "past"
            elif month == current_month:
                phase = "current"
            else:
                phase = "future"

            row: Dict = {
                "month": month,
                "days_after_planting": dap,
                "date": (plant_dt + timedelta(days=dap)).strftime("%Y-%m-%d"),
                "phase": phase,
                "growth_stage": self._stage_from_effective_day(effective_at(dap), cfg),
            }

            uncertainties = {}
            for metric in self.PREDICTION_METRICS:
                value = predicted(metric, dap)
                if value is None:
                    row[metric] = None
                    row[f"{metric}_range"] = None
                    continue

                calibration = calibrations[metric]
                if phase != "past":
                    # Plants and fruit do not shrink: never predict below the last measurement or previous month.
                    floors = [previous.get(metric)]
                    if calibration and dap >= calibration["latest_dap"]:
                        floors.append(calibration["latest_value"])
                    value = max([value] + [f for f in floors if f is not None])
                previous[metric] = value

                if metric == "weight_kg" and not calibration:
                    relative = min(0.7, math.hypot(2 * uncertainties.get("fruit_diameter_cm", 0.25),
                                                   uncertainties.get("fruit_length_cm", 0.25)))
                else:
                    relative = self._relative_uncertainty(calibration, dap, dap_now, sensor_days)
                uncertainties[metric] = relative

                digits = 2 if metric == "weight_kg" else 1
                row[metric] = round(value, digits)
                row[f"{metric}_range"] = [round(value * (1 - relative), digits), round(value * (1 + relative), digits)]

            row["confidence"] = round(max(0.3, min(0.95, 1.0 - sum(uncertainties.values()) / len(uncertainties))), 2)

            in_month = [log for log in logs if 30 * (month - 1) < log["_dap"] <= dap or (month == 1 and log["_dap"] == 0)]
            actual = {}
            for metric, field in field_for_metric.items():
                values = [log[field] for log in in_month if log.get(field) is not None and float(log[field]) > 0]
                if values:
                    actual[metric] = round(float(values[-1]), 2)
            row["actual"] = actual or None
            months.append(row)

        if logs:
            notes.append(f"Calibrated with {len(logs)} saved status record(s) for this plot.")
            height_cal = calibrations["height_cm"]
            if height_cal:
                notes.append(f"Measured plant height is running at {height_cal['latest_ratio']:.0%} of the reference curve.")
        else:
            notes.append(
                "No measurements saved yet, so predictions use reference curves only. "
                "Save Current Status records to calibrate them to this plant."
            )

        fruit_month = next((row for row in months if row["fruit_diameter_cm"] is not None), None)
        if fruit_month:
            notes.append(
                f"Fruit size predictions start around month {fruit_month['month']} ({fruit_month['growth_stage']}), "
                "when fruit development begins; earlier months show '--'."
            )
        else:
            notes.append("Fruit development is not expected within this prediction window.")
        if sensor_days == 0:
            notes.append("No sensor history was available, so environment effects use default values.")

        return {
            "planting_date": summary["planting_date"],
            "profile_used": profile,
            "generated_at": now.isoformat(timespec="seconds"),
            "prediction_date": now.strftime("%Y-%m-%d"),
            "days_after_planting": dap_now,
            "current_month": current_month,
            "today_x": round(dap_now / 30.0, 2),
            "harvest_month": max(1, math.ceil(harvest_dap / 30.0)),
            "months": months,
            "actual_series": actual_series,
            "model": {
                "type": "Agronomic reference growth curves calibrated with field measurements",
                "environment_factor": round(env_factor, 4),
                "fruit_onset_month": fruit_month["month"] if fruit_month else None,
                "calibration": {
                    metric: None if not cal else {
                        "measurements": cal["n"],
                        "latest_ratio": round(cal["latest_ratio"], 3),
                        "historical_ratio": round(cal["historical_ratio"], 3),
                    }
                    for metric, cal in calibrations.items()
                },
            },
            "notes": notes,
            "is_estimate": True,
            "disclaimer": "Predicted values are estimates. Accuracy improves as more status measurements are saved.",
        }


growth_forecaster = PineappleGrowthForecaster()
