"""
Time-series forecasting utilities for pineapple growth stage and harvest timing.

This module builds lightweight trend models from sensor history to forecast
near-term environmental conditions, then estimates crop growth stage and
optimal harvest date.
"""

from __future__ import annotations

import json
import math
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import numpy as np


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

    def __init__(self, data_folder: str = "sensor_data"):
        self.data_folder = data_folder

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
            return datetime.fromisoformat(value)
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
            file_name = f"{sensor_prefix}_{day.strftime('%Y%m%d')}.json"
            file_path = os.path.join(self.data_folder, file_name)
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

    def _soil_row_to_percent(self, row: Dict) -> Optional[float]:
        """
        Normalize soil reading into 0 to 100 where higher means wetter soil.
        Supports both digital DO and analog ADC modes used by this project.
        """
        mode = str(row.get("sensor_mode", "digital_do")).strip().lower()

        if mode == "digital_do":
            raw = row.get("raw_value", row.get("value"))
            if not isinstance(raw, (int, float)):
                return None
            return 80.0 if int(raw) == 0 else 25.0

        # analog_adc: based on existing thresholds where higher ADC is drier
        raw = row.get("raw_value", row.get("value"))
        if not isinstance(raw, (int, float)):
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

    def _daily_environment_score(self, soil_pct: float, temp_c: float, humidity_pct: float) -> float:
        """Compute environment score (0 to 100) for pineapple growth quality."""
        soil_score = max(0.0, 100.0 - abs(soil_pct - 60.0) * 1.5)
        temp_score = max(0.0, 100.0 - abs(temp_c - 28.0) * 6.0)
        humidity_score = max(0.0, 100.0 - abs(humidity_pct - 70.0) * 2.0)

        return (soil_score * 0.4) + (temp_score * 0.35) + (humidity_score * 0.25)

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
            return "Vegetative Stage"
        if effective_day < profile_cfg["pre_flowering_end"]:
            return "Pre-Flowering Stage"
        if effective_day < profile_cfg["fruit_development_end"]:
            return "Fruit Development Stage"
        if effective_day < profile_cfg["ripening_end"]:
            return "Ripening Stage"
        return "Optimal Harvest Window"

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
    ) -> Dict:
        """
        Forecast growth stage and optimal harvest time from sensor time-series.

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

        # Collect daily sensor history
        soil_rows = self._load_daily_sensor_rows("soil_moisture", days=history_days)
        th_rows = self._load_daily_sensor_rows("temp_humidity", days=history_days)

        by_day: Dict[str, Dict[str, Optional[float]]] = {}
        for row in soil_rows:
            by_day.setdefault(row["date"], {"soil_pct": None, "temp_c": None, "humidity_pct": None})
            by_day[row["date"]]["soil_pct"] = row.get("soil_pct")

        for row in th_rows:
            by_day.setdefault(row["date"], {"soil_pct": None, "temp_c": None, "humidity_pct": None})
            by_day[row["date"]]["temp_c"] = row.get("temp_c")
            by_day[row["date"]]["humidity_pct"] = row.get("humidity_pct")

        if not by_day:
            raise ValueError("No sensor history found yet. Collect at least one day of readings first.")

        sorted_days = sorted(by_day.keys())
        soil_series = self._impute_series([by_day[d]["soil_pct"] for d in sorted_days], default_value=55.0)
        temp_series = self._impute_series([by_day[d]["temp_c"] for d in sorted_days], default_value=28.0)
        humid_series = self._impute_series([by_day[d]["humidity_pct"] for d in sorted_days], default_value=70.0)

        historical_scores = [
            self._daily_environment_score(soil_series[i], temp_series[i], humid_series[i])
            for i in range(len(sorted_days))
        ]

        # Fit linear trend models
        soil_slope, soil_intercept = self._fit_linear_trend(soil_series)
        temp_slope, temp_intercept = self._fit_linear_trend(temp_series)
        humid_slope, humid_intercept = self._fit_linear_trend(humid_series)

        # Build horizon forecast
        future = []
        n_hist = len(sorted_days)
        for i in range(1, horizon_days + 1):
            x = n_hist - 1 + i
            soil_pred = max(0.0, min(100.0, soil_slope * x + soil_intercept))
            temp_pred = max(10.0, min(45.0, temp_slope * x + temp_intercept))
            humid_pred = max(20.0, min(100.0, humid_slope * x + humid_intercept))

            score = self._daily_environment_score(soil_pred, temp_pred, humid_pred)
            forecast_date = (datetime.now() + timedelta(days=i)).strftime("%Y-%m-%d")
            future.append(
                {
                    "date": forecast_date,
                    "soil_moisture_percent": round(soil_pred, 2),
                    "temperature_c": round(temp_pred, 2),
                    "humidity_percent": round(humid_pred, 2),
                    "growth_score": round(score, 2),
                }
            )

        avg_future_score = float(sum(item["growth_score"] for item in future) / len(future)) if future else 70.0
        avg_historical_score = float(sum(historical_scores) / len(historical_scores)) if historical_scores else avg_future_score
        blended_env_score = (avg_historical_score * 0.6) + (avg_future_score * 0.4)

        # Convert elapsed calendar days into effective growth days using environment factor.
        days_since_planting = max(0, (datetime.now() - plant_dt).days)
        env_factor = max(0.72, min(1.18, blended_env_score / 75.0))
        effective_growth_days = days_since_planting * env_factor

        stage = self._stage_from_effective_day(effective_growth_days, profile_cfg)

        target_effective_days = float(profile_cfg["cycle_days"])
        days_to_optimal = max(0, int(round((target_effective_days - effective_growth_days) / max(0.75, env_factor))))
        optimal_harvest_date = (datetime.now() + timedelta(days=days_to_optimal)).strftime("%Y-%m-%d")

        confidence = min(0.95, 0.45 + 0.12 * math.log1p(len(sorted_days)))
        size_profile = self._estimate_size_profile(days_since_planting)

        possible_problem = False
        growth_status = 'on_track'
        growth_alert = None
        problem_signals = []

        if actual_height_cm is not None:
            actual_height_cm = float(actual_height_cm)
            if actual_height_cm < size_profile['expected_height_cm'] * 0.85:
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
            "model_type": "Linear time-series trend + agronomic stage model",
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

        return {
            "summary": summary,
            "forecast_window_days": horizon_days,
            "history_days_used": len(sorted_days),
            "future_environment_forecast": future,
            "trend_coefficients": {
                "soil_moisture": {"slope": round(soil_slope, 4), "intercept": round(soil_intercept, 4)},
                "temperature": {"slope": round(temp_slope, 4), "intercept": round(temp_intercept, 4)},
                "humidity": {"slope": round(humid_slope, 4), "intercept": round(humid_intercept, 4)},
            },
            "stage_boundaries_days": profile_cfg,
            "notes": [
                "Provide actual planting_date for best harvest-time accuracy.",
                "Model confidence improves with longer and cleaner sensor history.",
                "Digital soil sensor (DO) is converted into moisture proxy values for forecasting.",
                "Most farms replace a pineapple plant after about 2 good-quality fruiting cycles.",
            ],
        }


growth_forecaster = PineappleGrowthForecaster()
