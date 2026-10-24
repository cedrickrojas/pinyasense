import json
from copy import deepcopy
from datetime import datetime, timedelta

from core.time_series_forecaster import PineappleGrowthForecaster


def test_loads_real_zone_readings_and_ignores_simulated_rows(tmp_path):
    now = datetime.now()
    date_key = now.strftime("%Y%m%d")
    timestamp = now.isoformat()
    rows = [
        {"timestamp": timestamp, "sensor_mode": "digital_do", "raw_value": 0},
        {"timestamp": timestamp, "sensor_mode": "digital_do", "raw_value": 1},
        {
            "timestamp": timestamp,
            "sensor_mode": "digital_do",
            "raw_value": 1,
            "data_source": "simulated_daily",
        },
    ]
    (tmp_path / f"soil_moisture_zone1_{date_key}.json").write_text(json.dumps(rows))

    result = PineappleGrowthForecaster(str(tmp_path))._load_daily_sensor_rows("soil_moisture", days=1)

    assert result == [{"date": now.strftime("%Y-%m-%d"), "soil_pct": 52.5, "temp_c": None, "humidity_pct": None}]


def test_forecast_does_not_show_default_environment_as_sensor_data(tmp_path):
    result = PineappleGrowthForecaster(str(tmp_path)).forecast_growth_and_harvest(
        planting_date="2026-04-01", horizon_days=7, history_days=14
    )

    assert result["history_days_used"] == 0
    assert result["future_environment_forecast"][0]["soil_moisture_percent"] is None
    assert result["future_environment_forecast"][0]["growth_score"] is None
    assert any("No actual sensor history" in warning for warning in result["warnings"])


def test_single_digital_do_day_does_not_add_flat_forecast_warning(tmp_path):
    now = datetime.now().isoformat()
    rows = [
        {
            "sensor_type": "soil_moisture_zone1",
            "sensor_mode": "digital_do",
            "raw_value": 0,
            "timestamp": now,
        }
    ]

    result = PineappleGrowthForecaster(str(tmp_path)).forecast_growth_and_harvest(
        planting_date="2026-04-01", horizon_days=7, history_days=14, sensor_rows=rows
    )

    assert result["summary"]["soil_sensor_days_used"] == 1
    assert result["future_environment_forecast"][0]["soil_moisture_percent"] == 80.0
    assert not any("Only one day of digital DO" in warning for warning in result["warnings"])

    # Demo variation is separate from the evidence-based forecast and history.
    simulation = result["soil_moisture_simulation"]
    assert simulation["initial_source"] == "latest_soil_proxy"
    assert simulation["initial_soil_moisture_percent"] == 80.0
    assert len({day["soil_moisture_percent"] for day in simulation["daily"]}) > 1
    assert all(day["soil_moisture_percent"] == 80.0 for day in result["future_environment_forecast"])
    assert all(day["growth_score"] == 70.0 for day in result["future_environment_forecast"])
    assert result["summary"]["average_forecast_growth_score"] == 70.0
    scores = result["growth_score_scenario"]
    assert scores["data_source"] == "simulated"
    assert scores["initial_source"] == "latest_soil_proxy"
    assert len({day["growth_score"] for day in scores["daily"]}) > 1
    assert [day["date"] for day in scores["daily"]] == [day["date"] for day in simulation["daily"]]


def _scenario_days(count):
    start = datetime(2026, 10, 23)
    return start, [
        {"date": (start + timedelta(days=i)).strftime("%Y-%m-%d"),
         "temperature_c": None, "humidity_percent": None}
        for i in range(1, count + 1)
    ]


def test_soil_simulation_is_stable_across_refreshes_and_horizons(tmp_path):
    forecaster = PineappleGrowthForecaster(str(tmp_path))
    start, future = _scenario_days(90)
    long = forecaster._simulate_soil_moisture(future, 80.0, start)
    assert long == forecaster._simulate_soil_moisture(future, 80.0, start)
    short = forecaster._simulate_soil_moisture(future[:7], 80.0, start)
    assert long["daily"][:7] == short["daily"]


def test_soil_simulation_has_bounded_drying_and_water_input_cycles(tmp_path):
    start, future = _scenario_days(90)
    scenario = PineappleGrowthForecaster(str(tmp_path))._simulate_soil_moisture(future, 80.0, start)
    previous = 80.0
    events = set()
    for day in scenario["daily"]:
        value = day["soil_moisture_percent"]
        assert 8 <= value <= 95
        assert day["data_source"] == "simulated"
        if day["event"] == "Simulated drying / drainage":
            assert value < previous
        elif day["event"] == "Simulated irrigation":
            assert value > previous
        events.add(day["event"])
        previous = value
    assert events == {"Simulated rain", "Simulated irrigation", "Simulated drying / drainage"}


def test_simulation_without_readings_keeps_real_history_empty(tmp_path):
    result = PineappleGrowthForecaster(str(tmp_path)).forecast_growth_and_harvest(sensor_rows=[])
    assert result["soil_moisture_simulation"]["initial_source"] == "demo_default"
    assert result["soil_moisture_simulation"]["initial_soil_moisture_percent"] == 55.0
    assert result["soil_moisture_simulation"]["daily"]
    assert result["history_days_used"] == 0
    assert result["summary"]["soil_sensor_days_used"] == 0
    assert all(day["soil_moisture_percent"] is None for day in result["future_environment_forecast"])
    assert all(day["growth_score"] is None for day in result["future_environment_forecast"])
    assert result["growth_score_scenario"]["initial_source"] == "demo_default"


def test_modeled_scores_follow_soil_conditions_without_fabricating_other_sensors(tmp_path):
    forecaster = PineappleGrowthForecaster(str(tmp_path))
    _, future = _scenario_days(3)
    soil = {"initial_source": "latest_soil_proxy", "daily": [
        {"date": item["date"], "soil_moisture_percent": value,
         "data_source": "simulated", "event": "Simulated drying / drainage"}
        for item, value in zip(future, [30.0, 60.0, 85.0])
    ]}
    original = deepcopy((future, soil))
    scenario = forecaster._model_growth_scores(future, soil)
    assert [day["growth_score"] for day in scenario["daily"]] == [55.0, 100.0, 62.5]
    assert all(day["temperature_c"] is None and day["humidity_percent"] is None
               for day in scenario["daily"])
    assert (future, soil) == original


def test_modeled_scores_use_available_environment_trends_on_the_matching_date(tmp_path):
    forecaster = PineappleGrowthForecaster(str(tmp_path))
    _, future = _scenario_days(2)
    future[0].update(temperature_c=38.0, humidity_percent=90.0)
    future[1].update(temperature_c=28.0, humidity_percent=70.0)
    soil = {"initial_source": "demo_default", "daily": [
        {"date": day["date"], "soil_moisture_percent": 60.0, "data_source": "simulated"}
        for day in future
    ]}
    scenario = forecaster._model_growth_scores(list(reversed(future)), soil)
    assert [day["growth_score"] for day in scenario["daily"]] == [69.0, 100.0]
    assert scenario["daily"][0]["temperature_c"] == 38.0


def test_modeled_scores_are_bounded_and_stable_across_refreshes_and_horizons(tmp_path):
    forecaster = PineappleGrowthForecaster(str(tmp_path))
    start, future = _scenario_days(90)
    soil = forecaster._simulate_soil_moisture(future, 80.0, start)
    long = forecaster._model_growth_scores(future, soil)
    assert long == forecaster._model_growth_scores(future, soil)
    short_soil = forecaster._simulate_soil_moisture(future[:7], 80.0, start)
    short = forecaster._model_growth_scores(future[:7], short_soil)
    assert long["daily"][:7] == short["daily"]
    assert all(0 <= day["growth_score"] <= 100 for day in long["daily"])
    assert len({day["growth_score"] for day in long["daily"]}) > 30
