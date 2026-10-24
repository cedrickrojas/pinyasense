"""
Plant monitoring records and problem recommendations for the Forecast module.

Pineapple plots, status (measurement) logs, problem reports and monthly growth
prediction snapshots are stored in Firestore next to the app's other
collections. Recommendations for reported problems reuse the disease
detector's image model and recommendation knowledge base.
"""

from __future__ import annotations

import math
import re
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple

from core.time_series_forecaster import GROWTH_STAGES, PineappleGrowthForecaster

PLANT_CONDITIONS = ["Healthy", "Needs Attention", "Critical"]
PROBLEM_TYPES = [
    "Leaf discoloration",
    "Leaf spots",
    "Wilting",
    "Pest damage",
    "Root problem",
    "Fruit abnormality",
    "Slow growth",
    "Disease symptoms",
    "Other",
]
SEVERITIES = ["Low", "Moderate", "Severe"]
PROBLEM_STATUSES = ["Open", "Monitoring", "Resolved"]
FARM_PROFILES = list(PineappleGrowthForecaster.FARM_PROFILES.keys())
PROFILE_VARIETIES = {"standard": "Standard", "smooth_cayenne": "Smooth Cayenne", "md2": "MD2"}

PLANTS_COLLECTION = "pineapple_plants"
STATUS_COLLECTION = "plant_status_logs"
PROBLEMS_COLLECTION = "plant_problem_logs"
PREDICTIONS_COLLECTION = "growth_predictions"

STORE_UNAVAILABLE_MESSAGE = "Firebase is not connected, so monitoring records cannot be saved or loaded right now."
READ_TIMEOUT_SECONDS = 8

PLANT_CODE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _.\-]{0,39}$")
MAX_PLANT_AGE_DAYS = 1500
FUTURE_TOLERANCE = timedelta(minutes=10)

# (field, label, maximum, unit, whole number)
MEASUREMENT_FIELDS = [
    ("height_cm", "Plant height", 300, "cm", False),
    ("leaf_length_cm", "Leaf length", 200, "cm", False),
    ("leaf_count", "Number of leaves", 300, "", True),
    ("fruit_diameter_cm", "Fruit diameter", 40, "cm", False),
    ("fruit_length_cm", "Fruit length", 60, "cm", False),
    ("estimated_weight_kg", "Estimated fruit weight", 10, "kg", False),
    ("soil_moisture", "Soil moisture", 100, "%", False),
]


def monitoring_options() -> Dict[str, List[str]]:
    """Choice lists shared with the Forecast page so both sides validate the same values."""
    return {
        "growth_stages": list(GROWTH_STAGES),
        "plant_conditions": list(PLANT_CONDITIONS),
        "problem_types": list(PROBLEM_TYPES),
        "severities": list(SEVERITIES),
        "problem_statuses": list(PROBLEM_STATUSES),
    }


# ============================================
# VALIDATION
# ============================================

class ValidationError(ValueError):
    """Invalid monitoring input; `errors` maps each field to a readable message."""

    def __init__(self, errors: Dict[str, str]):
        self.errors = errors
        super().__init__(next(iter(errors.values()), "Invalid input."))


def parse_datetime(value) -> Optional[datetime]:
    """Parse an ISO date/time into a naive local datetime (the app's convention)."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone().replace(tzinfo=None)
    return parsed


def _parse_date(value) -> Optional[date]:
    try:
        return datetime.strptime(str(value).strip(), "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def _text(data: Dict, field: str, label: str, errors: Dict, max_length: int,
          required: bool = False, min_length: int = 0) -> Optional[str]:
    value = str(data.get(field) or "").strip()
    if not value:
        if required:
            errors[field] = f"{label} is required."
        return None
    if len(value) < min_length:
        errors[field] = f"{label} must be at least {min_length} characters."
    elif len(value) > max_length:
        errors[field] = f"{label} must be at most {max_length} characters."
    return value


def _choice(data: Dict, field: str, label: str, options: List[str], errors: Dict) -> Optional[str]:
    raw = str(data.get(field) or "").strip()
    if not raw:
        errors[field] = f"{label} is required."
        return None
    for option in options:
        if option.lower() == raw.lower():
            return option
    errors[field] = f"{label} must be one of: {', '.join(options)}."
    return None


def _number(data: Dict, field: str, label: str, errors: Dict, maximum: float,
            unit: str, integer: bool) -> Optional[float]:
    raw = data.get(field)
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        errors[field] = f"{label} must be a number."
        return None
    if not math.isfinite(value):
        errors[field] = f"{label} must be a number."
        return None
    if field == "soil_moisture" and not 0 <= value <= 100:
        errors[field] = "Soil moisture must be between 0 and 100%."
        return None
    if value < 0:
        errors[field] = f"{label} cannot be negative."
        return None
    if value > maximum:
        errors[field] = f"{label} must be at most {maximum:g}{' ' + unit if unit else ''}."
        return None
    if integer:
        if not value.is_integer():
            errors[field] = f"{label} must be a whole number."
            return None
        return int(value)
    return round(value, 2)


def _plant_fields(data: Dict, errors: Dict, now: datetime) -> Tuple[Dict, Optional[date]]:
    code = re.sub(r"\s+", " ", str(data.get("plant_code") or "").strip())
    if not code:
        errors["plant_code"] = "Plant/Plot ID is required."
    elif not PLANT_CODE_PATTERN.match(code):
        errors["plant_code"] = "Plant/Plot ID may only use letters, numbers, spaces, '-', '_' or '.' (max 40 characters)."

    planting = None
    raw_planting = str(data.get("planting_date") or "").strip()
    if not raw_planting:
        errors["planting_date"] = "Planting date is required."
    else:
        planting = _parse_date(raw_planting)
        if planting is None:
            errors["planting_date"] = "Planting date must be a valid date (YYYY-MM-DD)."
        elif planting > now.date():
            errors["planting_date"] = "Planting date cannot be in the future."
            planting = None
        elif (now.date() - planting).days > MAX_PLANT_AGE_DAYS:
            errors["planting_date"] = "Planting date is more than 4 years ago. Please check the date."
            planting = None

    profile = str(data.get("profile") or data.get("farm_profile") or "standard").strip().lower()
    if profile not in FARM_PROFILES:
        errors["profile"] = "Farm profile is not recognized."

    cycle_days = None
    raw_cycle = data.get("cycle_days")
    if raw_cycle not in (None, ""):
        try:
            cycle_value = float(raw_cycle)
            if not cycle_value.is_integer():
                raise ValueError
            cycle_days = int(cycle_value)
        except (TypeError, ValueError):
            errors["cycle_days"] = "Cycle days must be a whole number."
        else:
            if not 120 <= cycle_days <= 700:
                errors["cycle_days"] = "Cycle days must be between 120 and 700."

    plant = {
        "plant_code": code,
        "planting_date": planting.isoformat() if planting else None,
        "farm_profile": profile,
        "variety": PROFILE_VARIETIES.get(profile, profile),
        "cycle_days": cycle_days,
    }
    return plant, planting


def _logged_at(data: Dict, errors: Dict, planting: Optional[date], now: datetime, label: str) -> Optional[datetime]:
    raw = data.get("logged_at")
    if raw in (None, ""):
        errors["logged_at"] = f"{label} is required."
        return None
    parsed = parse_datetime(raw)
    if parsed is None:
        errors["logged_at"] = f"{label} is not a valid date/time."
        return None
    if parsed > now + FUTURE_TOLERANCE:
        errors["logged_at"] = f"{label} cannot be in the future."
        return None
    if planting and parsed.date() < planting:
        errors["logged_at"] = f"{label} cannot be before the planting date."
        return None
    return parsed


def validate_status_submission(data: Dict, now: Optional[datetime] = None) -> Tuple[Dict, Dict]:
    """Validate a Save Current Status request. Returns (plant fields, status fields)."""
    now = now or datetime.now()
    errors: Dict[str, str] = {}
    plant, planting = _plant_fields(data, errors, now)

    logged_at = _logged_at(data, errors, planting, now, "Status date/time")
    stage = _choice(data, "growth_stage", "Current growth stage", GROWTH_STAGES, errors)
    condition = _choice(data, "plant_condition", "Plant condition", PLANT_CONDITIONS, errors)

    measurements = {}
    for field, label, maximum, unit, integer in MEASUREMENT_FIELDS:
        measurements[field] = _number(data, field, label, errors, maximum, unit, integer)

    measurement_errors = any(field in errors for field, *_ in MEASUREMENT_FIELDS)
    if not measurement_errors and all(value is None for value in measurements.values()):
        errors["measurements"] = "Enter at least one measurement (for example plant height or soil moisture)."

    notes = _text(data, "notes", "Additional notes", errors, 1000)

    if errors:
        raise ValidationError(errors)

    status = {
        "logged_at": logged_at.isoformat(timespec="seconds"),
        "days_after_planting": (logged_at.date() - planting).days,
        "growth_stage": stage,
        "plant_condition": condition,
        "notes": notes,
        **measurements,
    }
    return plant, status


def validate_problem_submission(data: Dict, now: Optional[datetime] = None) -> Tuple[Dict, Dict]:
    """Validate a Log Plant Problem request. Returns (plant fields, problem fields)."""
    now = now or datetime.now()
    errors: Dict[str, str] = {}
    plant, planting = _plant_fields(data, errors, now)

    logged_at = _logged_at(data, errors, planting, now, "Problem date/time")
    problem_type = _choice(data, "problem_type", "Problem type", PROBLEM_TYPES, errors)
    severity = _choice(data, "severity", "Severity", SEVERITIES, errors)
    description = _text(data, "description", "Description / observation", errors, 2000,
                        required=True, min_length=5)
    notes = _text(data, "notes", "Additional notes", errors, 1000)

    if errors:
        raise ValidationError(errors)

    problem = {
        "logged_at": logged_at.isoformat(timespec="seconds"),
        "days_after_planting": (logged_at.date() - planting).days,
        "problem_type": problem_type,
        "severity": severity,
        "description": description,
        "notes": notes,
    }
    return plant, problem


def validate_problem_status(data: Dict) -> str:
    errors: Dict[str, str] = {}
    status = _choice(data, "status", "Status", PROBLEM_STATUSES, errors)
    if errors:
        raise ValidationError(errors)
    return status


# ============================================
# FIRESTORE STORE
# ============================================

class MonitoringStoreUnavailable(RuntimeError):
    """Firestore is not connected, so monitoring records cannot be read or written."""


class PlantMonitoringStore:
    """Firestore persistence for plots, status logs, problem reports and growth predictions.

    Queries use equality filters only and sort in Python, matching the rest of
    the app, so no composite Firestore indexes are required.
    """

    def __init__(self, firestore_client):
        self.db = firestore_client

    @property
    def available(self) -> bool:
        return self.db is not None

    def _client(self):
        if self.db is None:
            raise MonitoringStoreUnavailable(STORE_UNAVAILABLE_MESSAGE)
        return self.db

    @staticmethod
    def _now() -> str:
        # Microsecond precision so records written in the same second still sort predictably.
        return datetime.now().isoformat()

    @staticmethod
    def _to_dict(doc) -> Dict:
        item = doc.to_dict() or {}
        item["id"] = doc.id
        return item

    @staticmethod
    def plant_doc_id(owner_id: str, plant_code: str) -> str:
        # '~' is not allowed in plot IDs, so owner + code maps to exactly one document.
        return f"{owner_id or 'anonymous'}~{plant_code.strip().lower()}"

    # ---- Plants ----

    def get_plant(self, owner_id: str, plant_code: Optional[str]) -> Optional[Dict]:
        if not plant_code or not plant_code.strip():
            return None
        doc = self._client().collection(PLANTS_COLLECTION).document(
            self.plant_doc_id(owner_id, plant_code)
        ).get(retry=None, timeout=READ_TIMEOUT_SECONDS)
        return self._to_dict(doc) if doc.exists else None

    def upsert_plant(self, owner_id: str, plant: Dict) -> Tuple[Dict, bool]:
        """Create the plot, or update its planting settings. Returns (plant, created)."""
        ref = self._client().collection(PLANTS_COLLECTION).document(
            self.plant_doc_id(owner_id, plant["plant_code"])
        )
        snapshot = ref.get()
        now = self._now()
        settings = {key: plant.get(key) for key in ("planting_date", "variety", "farm_profile", "cycle_days")}

        if snapshot.exists:
            existing = snapshot.to_dict() or {}
            changes = {key: value for key, value in settings.items() if existing.get(key) != value}
            if changes:
                changes["updated_at"] = now
                ref.set(changes, merge=True)
                existing.update(changes)
            existing["id"] = ref.id
            return existing, False

        data = {
            **settings,
            "plant_code": plant["plant_code"],
            "user_id": owner_id,
            "created_at": now,
            "updated_at": now,
        }
        ref.set(data)
        return {**data, "id": ref.id}, True

    def list_plants(self, owner_id: str) -> List[Dict]:
        docs = self._client().collection(PLANTS_COLLECTION).where("user_id", "==", owner_id).stream(
            retry=None, timeout=READ_TIMEOUT_SECONDS
        )
        plants = [self._to_dict(doc) for doc in docs]
        plants.sort(key=lambda p: p.get("last_activity_at") or p.get("updated_at") or "", reverse=True)
        return plants

    def _touch_plant(self, plant: Dict, **fields) -> None:
        self._client().collection(PLANTS_COLLECTION).document(plant["id"]).set(
            {"last_activity_at": self._now(), **fields}, merge=True
        )

    # ---- Status logs ----

    def add_status_log(self, plant: Dict, status: Dict) -> Dict:
        """Append a status record; earlier records are never modified."""
        ref = self._client().collection(STATUS_COLLECTION).document()
        data = {
            **status,
            "plant_id": plant["id"],
            "plant_code": plant["plant_code"],
            "user_id": plant.get("user_id"),
            "created_at": self._now(),
        }
        ref.set(data)
        self._touch_plant(plant)
        return {**data, "id": ref.id}

    def list_status_logs(self, plant_id: str) -> List[Dict]:
        """All status records for a plot, oldest first."""
        docs = self._client().collection(STATUS_COLLECTION).where("plant_id", "==", plant_id).stream(
            retry=None, timeout=READ_TIMEOUT_SECONDS
        )
        logs = [self._to_dict(doc) for doc in docs]
        logs.sort(key=lambda log: (log.get("logged_at") or "", log.get("created_at") or ""))
        return logs

    # ---- Problem logs ----

    def add_problem_log(self, plant: Dict, problem: Dict, image_path: Optional[str], recommendation: Dict) -> Dict:
        now = self._now()
        ref = self._client().collection(PROBLEMS_COLLECTION).document()
        data = {
            **problem,
            "plant_id": plant["id"],
            "plant_code": plant["plant_code"],
            "user_id": plant.get("user_id"),
            "image_path": image_path,
            "recommendation": recommendation.get("summary"),
            "recommendation_source": recommendation.get("source"),
            "detected_condition": recommendation.get("matched_condition"),
            "recommendation_details": recommendation,
            "status": "Open",
            "status_history": [{"status": "Open", "changed_at": now}],
            "created_at": now,
            "updated_at": now,
        }
        ref.set(data)
        self._touch_plant(plant)
        return {**data, "id": ref.id}

    def list_problem_logs(self, owner_id: str, plant_id: Optional[str] = None, limit: int = 200) -> List[Dict]:
        query = self._client().collection(PROBLEMS_COLLECTION).where("user_id", "==", owner_id)
        if plant_id:
            query = query.where("plant_id", "==", plant_id)
        problems = [self._to_dict(doc) for doc in query.stream(retry=None, timeout=READ_TIMEOUT_SECONDS)]
        problems.sort(key=lambda p: (p.get("logged_at") or "", p.get("created_at") or ""), reverse=True)
        return problems[:limit]

    def get_problem_log(self, owner_id: str, problem_id: str) -> Optional[Dict]:
        if not problem_id or "/" in problem_id:
            return None
        doc = self._client().collection(PROBLEMS_COLLECTION).document(problem_id).get(
            retry=None, timeout=READ_TIMEOUT_SECONDS
        )
        if not doc.exists:
            return None
        problem = self._to_dict(doc)
        return problem if problem.get("user_id") == owner_id else None

    def update_problem_status(self, owner_id: str, problem_id: str, status: str) -> Optional[Dict]:
        problem = self.get_problem_log(owner_id, problem_id)
        if problem is None:
            return None
        if problem.get("status") == status:
            return problem
        now = self._now()
        history = list(problem.get("status_history") or [])
        history.append({"status": status, "changed_at": now})
        changes = {"status": status, "status_history": history, "updated_at": now}
        self._client().collection(PROBLEMS_COLLECTION).document(problem_id).set(changes, merge=True)
        problem.update(changes)
        return problem

    # ---- Growth predictions ----

    def save_prediction_snapshot(self, plant: Dict, prediction_date: str, months: List[Dict],
                                 max_months: int = PineappleGrowthForecaster.MAX_PREDICTION_MONTHS) -> int:
        """Store one prediction snapshot per plot per day (re-running the same day replaces it)."""
        db = self._client()
        collection = db.collection(PREDICTIONS_COLLECTION)
        batch = db.batch()
        now = self._now()
        for row in months:
            doc_id = f"{plant['id']}~{prediction_date}~{int(row['month']):02d}"
            batch.set(collection.document(doc_id), {
                "plant_id": plant["id"],
                "plant_code": plant["plant_code"],
                "user_id": plant.get("user_id"),
                "prediction_date": prediction_date,
                "target_month": int(row["month"]),
                "target_date": row.get("date"),
                "days_after_planting": int(row["days_after_planting"]),
                "predicted_height_cm": row.get("height_cm"),
                "predicted_fruit_diameter_cm": row.get("fruit_diameter_cm"),
                "predicted_fruit_length_cm": row.get("fruit_length_cm"),
                "predicted_weight_kg": row.get("weight_kg"),
                "growth_stage": row.get("growth_stage"),
                "confidence": row.get("confidence"),
                "created_at": now,
            })
        # Drop months left over from an earlier, longer snapshot on the same day.
        for month in range(len(months) + 1, max_months + 1):
            batch.delete(collection.document(f"{plant['id']}~{prediction_date}~{month:02d}"))
        batch.commit()
        return len(months)


# ============================================
# PROBLEM RECOMMENDATIONS
# ============================================

_STOPWORDS = {
    "the", "and", "for", "with", "from", "after", "not", "its", "has", "have", "are", "was",
    "were", "been", "this", "that", "there", "very", "some", "also", "inside", "affected",
    "formation", "appearance", "area", "reduced", "rapid", "normal", "development", "quality",
    "pineapple", "plant", "disease", "symptom", "appearing", "appear", "part", "lower", "upper",
    "seen", "observed", "showing", "show",
}
_SYNONYMS = {
    "leaves": "leaf", "spots": "spot", "spotted": "spot", "yellowish": "yellow", "yellowed": "yellow",
    "yellowing": "yellow", "blackened": "black", "blackish": "black", "rotten": "rot", "rotting": "rot",
    "rots": "rot", "decaying": "decay", "smell": "odor", "smelly": "odor", "odour": "odor", "stink": "odor",
    "mushy": "soft", "droop": "wilt", "drooping": "wilt", "wilted": "wilt", "wilting": "wilt",
    "pinkish": "pink", "discolored": "discoloration", "discoloured": "discoloration",
    "discolouration": "discoloration",
}
_CANONICAL = set(_SYNONYMS.values())
# Where a symptom appears, not what it looks like; these alone must not identify a disease.
LOCATION_TERMS = {"leaf", "fruit", "root", "core", "skin", "tissue", "flower", "heart", "base", "stem", "crown"}

# Nudges toward knowledge-base entries when the problem type points at a disease group.
PROBLEM_TYPE_PRIORS = {
    "Root problem": {"Heart Rot": 0.75},  # Phytophthora causes both heart rot and root rot
    "Leaf spots": {"Yellow Spot": 0.25},  # the only leaf-spot disease in the knowledge base
    "Leaf discoloration": {"Yellow Spot": 0.25},
}

SEVERITY_FIRST_STEPS = {
    "Low": "Mark the plant and keep monitoring the affected area to see whether the symptoms change or spread.",
    "Moderate": "Inspect the affected parts closely and check whether the symptoms are spreading to nearby plants.",
    "Severe": "Isolate the plant if possible and remove severely affected parts to limit spread.",
}
SEVERITY_URGENCY = {"Low": "Monitor closely", "Moderate": "Within 1-2 days", "Severe": "Immediate"}
URGENCY_RANK = {"Maintain": 0, "Monitor closely": 1, "Within 1-2 days": 2, "Consult expert": 2, "Immediate": 3}

SOURCE_LABELS = {
    "image_detection": "Image detection model",
    "symptom_match": "Symptom match (disease knowledge base)",
    "general_guidance": "General guidance",
}


def _stem(word: str) -> str:
    if word in _CANONICAL:
        return word
    for suffix in ("ing", "ed", "s"):
        if word.endswith(suffix) and not word.endswith("ss") and len(word) - len(suffix) >= 3:
            word = word[: -len(suffix)]
            if len(word) > 3 and word[-1] == word[-2]:
                word = word[:-1]
            break
    return word


def _tokens(text: str) -> set:
    tokens = set()
    for word in re.findall(r"[a-z]+", (text or "").lower()):
        word = _SYNONYMS.get(word, word)
        if len(word) < 3 or word in _STOPWORDS:
            continue
        tokens.add(_stem(word))
    return tokens


class ProblemRecommender:
    """Build recommendations for reported plant problems from the existing detection logic.

    Order of evidence: the image detection model (when a photo is attached), then a
    match of the written symptoms against the disease library, then the detector's
    generic guidance. Recorded measurements and soil readings add field context.
    """

    def __init__(self, detector, disease_library: List[Dict], growth_forecaster: PineappleGrowthForecaster):
        self.detector = detector
        self.growth_forecaster = growth_forecaster
        self.disease_keywords: Dict[str, set] = {}
        for disease in disease_library:
            name = disease.get("name")
            if not name or name == "Healthy":
                continue
            text = " ".join([name] + list(disease.get("symptoms") or []))
            self.disease_keywords[name] = _tokens(text)

        document_frequency: Dict[str, int] = {}
        for keywords in self.disease_keywords.values():
            for token in keywords:
                document_frequency[token] = document_frequency.get(token, 0) + 1
        self.token_weights = {
            token: min(1.0 / count, 0.3) if token in LOCATION_TERMS else 1.0 / count
            for token, count in document_frequency.items()
        }

    def match_symptoms(self, problem_type: str, text: str) -> Dict:
        """Score each library disease by weighted keyword overlap with the written observation.

        The problem type only nudges scores through PROBLEM_TYPE_PRIORS, and symptoms seen on a
        different part of the plant than the disease affects count for half.
        """
        report_tokens = _tokens(text)
        report_locations = report_tokens & LOCATION_TERMS
        priors = PROBLEM_TYPE_PRIORS.get(problem_type, {})
        scored = []
        for name, keywords in self.disease_keywords.items():
            matched = sorted(report_tokens & keywords)
            score = sum(self.token_weights[token] for token in matched)
            if report_locations and not report_locations & keywords:
                score *= 0.5
            if name.lower() in (text or "").lower():  # the farmer named the disease
                score += 1.0
                matched.append(name)
            score += priors.get(name, 0.0)
            if score > 0:
                scored.append({"disease": name, "score": round(score, 3), "matched_terms": matched})
        scored.sort(key=lambda item: item["score"], reverse=True)

        best = scored[0] if scored else None
        runner_up = scored[1]["score"] if len(scored) > 1 else 0.0
        confident = bool(best and best["score"] >= 1.0 and best["score"] - runner_up >= 0.25)
        total = sum(item["score"] for item in scored) or 1.0
        return {
            "match": best if confident else None,
            "strength": round(best["score"] / total, 2) if confident else None,
            "candidates": scored[:3],
        }

    def _knowledge_base(self, condition: str) -> Dict:
        if self.detector is None:
            return {"severity": "Unknown", "action": "Consult expert", "treatments": [], "recommendations": []}
        recommendation = self.detector.get_recommendations(condition) or {}
        recommendation.pop("fertilization", None)
        return recommendation

    def _run_image_detection(self, image_path: str) -> Tuple[Optional[Dict], List[str]]:
        notes = []
        try:
            result = self.detector.detect(image_path)
        except Exception as exc:  # detector failures must not block logging the problem
            return None, [f"Image analysis could not run ({exc}); the recommendation is based on the reported symptoms."]

        detection = {
            "disease": result.get("disease"),
            "confidence": round(float(result.get("confidence") or 0.0), 3),
            "method": result.get("method"),
        }
        if result.get("not_pineapple"):
            detection["not_pineapple"] = True
            notes.append("The uploaded photo was not recognized as a pineapple plant, so the recommendation is based on the reported symptoms.")
        elif result.get("error"):
            detection["error"] = result.get("error")
            notes.append("Image analysis failed; the recommendation is based on the reported symptoms.")
        elif detection["disease"] == "Healthy":
            notes.append(
                f"The image model found no visible disease signs (Healthy, {detection['confidence']:.0%} confidence). "
                "The recommendation is based on the reported symptoms."
            )
        return detection, notes

    def _feeding_for_month(self, month: int) -> Optional[str]:
        """Stage-appropriate feeding from the detector's 'Healthy' fertilization schedule."""
        if self.detector is None:
            return None
        schedule = (self.detector.get_recommendations("Healthy") or {}).get("fertilization", {}).get("schedule", [])
        ranged = []
        for entry in schedule:
            found = re.search(r"Month (\d+)-(\d+)", entry.get("timing", ""))
            if found:
                ranged.append((int(found.group(1)), int(found.group(2)), entry))
        if not ranged:
            return None
        entry = next((e for lo, hi, e in ranged if lo <= month <= hi), ranged[-1][2])
        return (
            f"Stage-appropriate feeding for month {month}: {entry.get('type')}, {entry.get('amount')}, "
            f"{str(entry.get('method', '')).lower()}, {str(entry.get('frequency', '')).lower()}."
        )

    def recommend(self, problem: Dict, latest_status: Optional[Dict] = None, image_path: Optional[str] = None,
                  sensor_reading: Optional[Dict] = None, planting_date: Optional[str] = None) -> Dict:
        problem_type = problem.get("problem_type") or "Other"
        severity = problem.get("severity") or "Moderate"
        report_text = " ".join(filter(None, [problem.get("description"), problem.get("notes")]))

        context_notes: List[str] = []
        context_actions: List[str] = []
        detection = None
        source = "general_guidance"
        condition = None
        confidence = None

        if image_path and self.detector is not None:
            detection, detection_notes = self._run_image_detection(image_path)
            context_notes.extend(detection_notes)
            if detection and not detection.get("not_pineapple") and not detection.get("error") \
                    and detection.get("disease") not in (None, "Healthy", "Unknown"):
                condition = detection["disease"]
                confidence = detection["confidence"]
                source = "image_detection"

        symptom_match = self.match_symptoms(problem_type, report_text)
        if condition is None and symptom_match["match"]:
            condition = symptom_match["match"]["disease"]
            confidence = symptom_match["strength"]
            source = "symptom_match"

        if condition:
            knowledge = self._knowledge_base(condition)
        elif problem_type == "Slow growth":
            knowledge = self._knowledge_base("Healthy")
        else:
            knowledge = self._knowledge_base("Diseased" if severity == "Severe" else "Possibly Diseased")

        # Field context from saved measurements and the soil sensor.
        soil = (latest_status or {}).get("soil_moisture")
        if soil is not None:
            if soil < 30:
                context_actions.append(
                    f"Latest recorded soil moisture is {soil:.0f}% (very dry). Irrigate and re-check the soil before applying any treatment or fertilizer."
                )
            elif soil > 85:
                context_actions.append(
                    f"Latest recorded soil moisture is {soil:.0f}% (waterlogged). Improve drainage and reduce watering; excess water favors rot diseases."
                )
            else:
                context_notes.append(f"Latest recorded soil moisture is {soil:.0f}%, within the normal range.")

        sensor_state = str((sensor_reading or {}).get("state") or "").upper()
        if sensor_state == "DRY":
            context_actions.append("The soil moisture sensor currently reads DRY. Water the plot before applying treatments.")
        elif sensor_state == "WET":
            if condition == "Heart Rot" or problem_type in ("Root problem", "Wilting"):
                context_actions.append("The soil moisture sensor reads WET. Avoid extra irrigation until the soil drains.")
            else:
                context_notes.append("The soil moisture sensor currently reads WET.")

        height = (latest_status or {}).get("height_cm")
        dap = (latest_status or {}).get("days_after_planting")
        if height is not None and dap is not None and self.growth_forecaster is not None:
            expected = self.growth_forecaster._estimate_size_profile(int(dap))["expected_height_cm"]
            if height < expected * 0.85:
                context_actions.append(
                    f"Latest measured height ({height:g} cm) is below the expected ~{expected:g} cm for {int(dap)} days after planting. "
                    "Check nutrition, watering and root health."
                )
            elif problem_type == "Slow growth":
                context_notes.append(
                    f"Latest measured height ({height:g} cm) is within the expected range for {int(dap)} days after planting."
                )

        if problem_type == "Slow growth" and planting_date:
            planted = _parse_date(planting_date)
            if planted:
                month = max(1, math.ceil(max(1, (date.today() - planted).days) / 30))
                feeding = self._feeding_for_month(month)
                if feeding:
                    context_actions.append(feeding)

        if (latest_status or {}).get("plant_condition") == "Critical":
            context_actions.append("The latest status record marks this plant as Critical. Prioritize it during field inspection.")

        if source != "image_detection" and severity in ("Moderate", "Severe"):
            context_actions.append(
                "Attach a clear photo of the affected part (or scan it on the Diseases page) so the image detection model can confirm the cause."
            )

        first_step = SEVERITY_FIRST_STEPS.get(severity, SEVERITY_FIRST_STEPS["Moderate"])
        treatments = list(knowledge.get("treatments") or [])
        actions = [first_step] + treatments + context_actions
        # The more urgent of the reported severity and the matched disease's own action.
        severity_urgency = SEVERITY_URGENCY.get(severity, "Within 1-2 days")
        knowledge_urgency = knowledge.get("action") or severity_urgency
        urgency = max((severity_urgency, knowledge_urgency), key=lambda value: URGENCY_RANK.get(value, 2))

        if source == "image_detection":
            cause = f"the image detection model identified {condition} ({confidence:.0%} confidence)"
        elif source == "symptom_match":
            cause = f"the reported symptoms most closely match {condition}"
        else:
            cause = "no specific disease could be matched from the report, so general guidance applies"
        summary_steps = " ".join(step.rstrip(".") + "." for step in [first_step] + treatments[:2])
        summary = f"{severity} {problem_type.lower()}: {cause}. Priority: {urgency}. {summary_steps}"

        alternatives = [
            {"disease": item["disease"], "score": item["score"]}
            for item in symptom_match["candidates"]
            if item["disease"] != condition
        ]

        return {
            "summary": summary,
            "source": source,
            "source_label": SOURCE_LABELS[source],
            "matched_condition": condition,
            "match_confidence": confidence,
            "urgency": urgency,
            "disease_severity": knowledge.get("severity"),
            "actions": actions,
            "follow_up": list(knowledge.get("recommendations") or []),
            "context_notes": context_notes,
            "image_detection": detection,
            "symptom_terms": symptom_match["match"]["matched_terms"] if symptom_match["match"] else [],
            "alternative_matches": alternatives,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "disclaimer": (
                "Recommendations are decision support based on the reported symptoms, the image model and recorded "
                "field conditions. Confirm serious cases with an agricultural technician."
            ),
        }
