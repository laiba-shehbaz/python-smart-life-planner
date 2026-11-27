"""All file I/O lives here, separate from application logic."""
import copy
import json
import os
from collections import namedtuple
from datetime import datetime
from pathlib import Path

from models.destination import Destination
from utils.constants import DEFAULT_SETTINGS
from utils.validators import ValidationError, validate_email

DestinationData = namedtuple("DestinationData", "destinations settings errors")
PROJECT_ROOT = Path(__file__).resolve().parent.parent
PLACEHOLDER = "Not provided"


class DataError(Exception):
    """Raised when data cannot be written."""


def build_settings(raw):
    """Merge settings from JSON over the defaults, ignoring invalid entries."""
    settings, errors = copy.deepcopy(DEFAULT_SETTINGS), []
    if not isinstance(raw, dict):
        return settings, errors
    for key, default in DEFAULT_SETTINGS.items():
        if key not in raw:
            continue
        value = raw[key]
        if isinstance(default, dict) and key != "category_defaults":
            if isinstance(value, dict) and all(isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0 for v in value.values()):
                settings[key].update(value)
            else:
                errors.append(f"Invalid setting '{key}'; defaults used.")
        elif key == "category_defaults":
            if isinstance(value, dict):
                for cat, prefs in value.items():
                    if isinstance(prefs, dict) and {"transport", "accommodation"} <= set(prefs):
                        settings[key][cat] = prefs
            else:
                errors.append(f"Invalid setting '{key}'; defaults used.")
        elif isinstance(value, (int, float)) and not isinstance(value, bool) and 0 <= value <= (50 if key == "emergency_percentage" else 1):
            settings[key] = value
        else:
            errors.append(f"Invalid setting '{key}'; default used.")
    return settings, errors


class DataManager:
    def __init__(self, base_dir=None):
        self.base_dir = Path(base_dir) if base_dir else PROJECT_ROOT
        self.data_dir = self.base_dir / "data"
        self.config_dir = self.base_dir / "config"
        self.reports_dir = self.base_dir / "reports"
        self.warnings = []

    # ---- low-level JSON ----
    def read_json(self, path, default):
        path = Path(path)
        try:
            text = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return copy.deepcopy(default)
        except (OSError, UnicodeDecodeError) as exc:
            self.warnings.append(f"Could not read {path.name}: {exc}")
            return copy.deepcopy(default)
        if not text.strip():
            self.warnings.append(f"{path.name} is empty; starting with empty data.")
            return copy.deepcopy(default)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            self.warnings.append(f"{path.name} is corrupted; it was ignored.")
            return copy.deepcopy(default)

    def write_json(self, path, data):
        path = Path(path)
        tmp = path.with_suffix(path.suffix + ".tmp")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
            os.replace(tmp, path)
        except (OSError, TypeError, ValueError) as exc:
            raise DataError(f"Could not save {path.name}: {exc}") from exc

    def _records(self, filename, key):
        raw = self.read_json(self.data_dir / filename, {key: []})
        items = raw.get(key, []) if isinstance(raw, dict) else raw
        if not isinstance(items, list):
            self.warnings.append(f"{filename} has an unexpected format; ignored.")
            return []
        return [item for item in items if isinstance(item, dict)]

    # ---- destinations ----
    def load_destination_data(self):
        raw = self.read_json(self.data_dir / "destinations.json", {})
        errors = []
        records = raw.get("destinations", []) if isinstance(raw, dict) else []
        settings, setting_errors = build_settings(raw.get("settings") if isinstance(raw, dict) else None)
        errors.extend(setting_errors)
        destinations, seen = [], set()
        for record in records if isinstance(records, list) else []:
            try:
                dest = Destination.from_dict(record)
            except ValidationError as exc:
                errors.append(str(exc))
                continue
            if dest.name.lower() in seen:
                errors.append(f"Duplicate destination '{dest.name}' ignored.")
                continue
            seen.add(dest.name.lower())
            destinations.append(dest)
        if not destinations:
            errors.append("No valid destinations were loaded.")
        return DestinationData(destinations, settings, errors)

    # ---- trips ----
    @staticmethod
    def is_valid_trip_record(record):
        return (isinstance(record, dict) and isinstance(record.get("trip"), dict)
                and isinstance(record.get("breakdown"), dict) and "plan_id" in record
                and isinstance(record["breakdown"].get("total"), (int, float)))

    def load_trips(self):
        valid = [r for r in self._records("trips.json", "trips") if self.is_valid_trip_record(r)]
        return valid

    def save_trip(self, plan_dict):
        record = dict(plan_dict)
        record.setdefault("plan_id", "TRIP-" + datetime.now().strftime("%Y%m%d%H%M%S%f"))
        record["saved_at"] = datetime.now().isoformat(timespec="seconds")
        trips = [t for t in self.load_trips() if t["plan_id"] != record["plan_id"]]
        trips.append(record)
        self.write_json(self.data_dir / "trips.json", {"trips": trips})
        return record

    # ---- budgets ----
    def load_budget_records(self):
        return self._records("budgets.json", "budgets")

    def save_budget_records(self, records):
        self.write_json(self.data_dir / "budgets.json", {"budgets": list(records)})

    # ---- report references ----
    def load_reports(self):
        return self._records("reports_index.json", "reports")

    def add_report(self, reference):
        reports = self.load_reports()
        reports.append(dict(reference))
        self.write_json(self.data_dir / "reports_index.json", {"reports": reports})

    def ensure_reports_dir(self):
        try:
            self.reports_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise DataError(f"Could not create reports folder: {exc}") from exc
        return self.reports_dir

    # ---- developer configuration ----
    @staticmethod
    def developer_problems(config):
        if not isinstance(config, dict):
            return ["Developer configuration must be a JSON object."]
        problems = []
        for key in ("developer_name", "github_username", "email"):
            if not str(config.get(key, "")).strip():
                problems.append(f"Missing '{key}'.")
        if str(config.get("email", "")).strip():
            try:
                validate_email(config["email"])
            except ValidationError:
                problems.append("Email address is invalid.")
        return problems

    def load_developer(self):
        raw = self.read_json(self.config_dir / "developer.json", {})
        if not isinstance(raw, dict):
            raw = {}
        info = {k: str(raw.get(k, "")).strip() or PLACEHOLDER
                for k in ("developer_name", "github_username", "email")}
        for problem in self.developer_problems(raw):
            self.warnings.append(f"Developer config: {problem}")
        if info["email"] != PLACEHOLDER:
            try:
                validate_email(info["email"])
            except ValidationError:
                info["email"] = PLACEHOLDER
        return info
