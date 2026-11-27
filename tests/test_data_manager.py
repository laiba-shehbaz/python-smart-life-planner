import json

import pytest

from models.destination import Destination
from utils.data_manager import DataError, DataManager, PLACEHOLDER, build_settings
from utils.validators import ValidationError


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.fixture
def dest_record():
    return {"name": "Alpha", "region": "R", "category": "Mountains", "transport_cost_pp": 1000,
            "accommodation_per_room_night": 4000, "food_pp_day": 500, "activities_pp_day": 200,
            "misc_pp_day": 100, "room_capacity": 2, "travel_categories": ["Standard"],
            "transport_modes": ["Car"], "accommodation_types": ["Hotel"]}


def test_real_destination_file_is_valid_and_complete():
    data = DataManager().load_destination_data()
    names = {d.name for d in data.destinations}
    assert {"Murree", "Nathiagali", "Swat", "Kalam", "Hunza", "Skardu", "Naran", "Lahore", "Islamabad"} <= names
    assert data.errors == []


@pytest.mark.parametrize("content", [None, "", "   \n", "{not json", "[1, 2, 3]", '{"destinations": "oops"}'])
def test_missing_empty_or_corrupt_destination_file_gives_empty_list(tmp_path, content):
    dm = DataManager(tmp_path)
    if content is not None:
        write(tmp_path / "data" / "destinations.json", content)
    data = dm.load_destination_data()
    assert data.destinations == [] and data.errors  # error message, no crash


def test_invalid_destination_records_are_skipped_with_errors(tmp_path, dest_record):
    bad_cost = {**dest_record, "name": "Bad", "food_pp_day": "free"}
    missing = {k: v for k, v in dest_record.items() if k != "transport_cost_pp"} | {"name": "Missing"}
    negative = {**dest_record, "name": "Neg", "accommodation_per_room_night": -5}
    zero_cap = {**dest_record, "name": "Zero", "room_capacity": 0}
    write(tmp_path / "data" / "destinations.json",
          json.dumps({"destinations": [dest_record, bad_cost, missing, negative, zero_cap, dest_record, "junk"]}))
    data = DataManager(tmp_path).load_destination_data()
    assert [d.name for d in data.destinations] == ["Alpha"]
    assert len(data.errors) >= 5


def test_destination_from_dict_validates():
    with pytest.raises(ValidationError):
        Destination.from_dict({"name": "X"})
    with pytest.raises(ValidationError):
        Destination.from_dict("not a dict")


def test_build_settings_ignores_invalid_values():
    settings, errors = build_settings({"emergency_percentage": -5, "transport_multipliers": {"Bus": -1}})
    assert settings["emergency_percentage"] == 10 and settings["transport_multipliers"]["Bus"] == 0.6
    assert len(errors) == 2


def test_build_settings_accepts_valid_override():
    settings, _ = build_settings({"emergency_percentage": 15})
    assert settings["emergency_percentage"] == 15


def test_read_json_missing_returns_default_copy(tmp_path):
    dm = DataManager(tmp_path)
    default = {"a": []}
    result = dm.read_json(tmp_path / "nope.json", default)
    result["a"].append(1)
    assert default == {"a": []}


def test_corrupt_json_adds_warning(tmp_path):
    dm = DataManager(tmp_path)
    write(tmp_path / "x.json", "{{{")
    assert dm.read_json(tmp_path / "x.json", {}) == {}
    assert any("corrupted" in w for w in dm.warnings)


def test_write_json_creates_folders_and_round_trips(tmp_path):
    dm = DataManager(tmp_path)
    target = tmp_path / "deep" / "nested" / "f.json"
    dm.write_json(target, {"k": [1, 2]})
    assert dm.read_json(target, {}) == {"k": [1, 2]}
    assert not list(target.parent.glob("*.tmp"))


def test_write_json_unserialisable_raises_data_error(tmp_path):
    with pytest.raises(DataError):
        DataManager(tmp_path).write_json(tmp_path / "f.json", {"bad": object()})


def test_save_and_load_trip_records(tmp_dm):
    record = {"trip": {"destination": "Alpha"}, "breakdown": {"total": 100}, "plan_id": "T1"}
    tmp_dm.save_trip(record)
    tmp_dm.save_trip({**record, "breakdown": {"total": 250}})  # same id replaces
    trips = tmp_dm.load_trips()
    assert len(trips) == 1 and trips[0]["breakdown"]["total"] == 250 and "saved_at" in trips[0]


def test_corrupted_saved_trips_are_handled_safely(tmp_dm, tmp_path):
    good = {"trip": {}, "breakdown": {"total": 5}, "plan_id": "OK"}
    write(tmp_path / "data" / "trips.json", json.dumps({"trips": [good, {"trip": 1}, "x", {"plan_id": "N"}]}))
    assert [t["plan_id"] for t in tmp_dm.load_trips()] == ["OK"]
    write(tmp_path / "data" / "trips.json", "garbage")
    assert tmp_dm.load_trips() == []
    write(tmp_path / "data" / "trips.json", json.dumps({"trips": "not a list"}))
    assert tmp_dm.load_trips() == []


def test_budget_records_round_trip_and_missing_file(tmp_dm):
    assert tmp_dm.load_budget_records() == []
    tmp_dm.save_budget_records([{"month": "2026-11"}])
    assert tmp_dm.load_budget_records() == [{"month": "2026-11"}]


def test_report_references_accumulate(tmp_dm):
    tmp_dm.add_report({"report_id": "A"})
    tmp_dm.add_report({"report_id": "B"})
    assert [r["report_id"] for r in tmp_dm.load_reports()] == ["A", "B"]


def test_missing_reports_directory_is_created(tmp_path):
    dm = DataManager(tmp_path / "fresh")
    assert not dm.reports_dir.exists()
    assert dm.ensure_reports_dir().is_dir()


def test_developer_config_valid(tmp_path):
    write(tmp_path / "config" / "developer.json", json.dumps(
        {"developer_name": "A", "github_username": "a-gh", "email": "a@b.com"}))
    dm = DataManager(tmp_path)
    assert dm.load_developer() == {"developer_name": "A", "github_username": "a-gh", "email": "a@b.com"}
    assert dm.warnings == []


@pytest.mark.parametrize("content", [None, "", "{bad", "[]", '{"developer_name": "A"}'])
def test_developer_config_missing_or_incomplete_uses_placeholders(tmp_path, content):
    if content is not None:
        write(tmp_path / "config" / "developer.json", content)
    info = DataManager(tmp_path).load_developer()
    assert set(info) == {"developer_name", "github_username", "email"}
    assert PLACEHOLDER in info.values()


def test_developer_invalid_email_is_replaced_and_reported(tmp_path):
    write(tmp_path / "config" / "developer.json", json.dumps(
        {"developer_name": "A", "github_username": "g", "email": "not-an-email"}))
    dm = DataManager(tmp_path)
    assert dm.load_developer()["email"] == PLACEHOLDER
    assert any("invalid" in w.lower() for w in dm.warnings)


@pytest.mark.parametrize("config,count", [({"developer_name": "A", "github_username": "g", "email": "a@b.com"}, 0),
                                          ({}, 3), ({"developer_name": "A", "github_username": "g", "email": "bad"}, 1), ("x", 1)])
def test_developer_problems(config, count):
    assert len(DataManager.developer_problems(config)) == count
