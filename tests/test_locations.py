import json
import tempfile
import unittest
from pathlib import Path

from app.config import DEFAULT_NOTIFICATION_FIELDS, DEFAULT_NOTIFICATION_INTERVAL
from app.locations import SCHEMA_VERSION, LocationStore, SavedLocation
from app.weather import Place


def _place(**overrides):
    values = {
        "name": "Santos",
        "latitude": -23.96,
        "longitude": -46.33,
        "country": "Brasil",
        "admin1": "São Paulo",
        "timezone": "America/Sao_Paulo",
        "place_id": 3449433,
    }
    values.update(overrides)
    return Place(**values)


def _store(directory, name="locations.json"):
    return LocationStore(Path(directory) / name)


class SavedLocationTests(unittest.TestCase):
    def test_display_name_prefers_the_alias(self):
        location = SavedLocation(place=_place(), alias="Casa")
        self.assertEqual(location.display_name, "Casa")

    def test_display_name_falls_back_to_the_place_name(self):
        self.assertEqual(SavedLocation(place=_place()).display_name, "Santos")

    def test_a_blank_alias_does_not_hide_the_place_name(self):
        self.assertEqual(SavedLocation(place=_place(), alias="   ").display_name, "Santos")

    def test_full_label_shows_the_alias_and_the_place(self):
        location = SavedLocation(place=_place(), alias="Casa")
        self.assertEqual(location.full_label, "Casa (Santos, São Paulo, Brasil)")

    def test_full_label_without_an_alias_is_the_place_label(self):
        self.assertEqual(
            SavedLocation(place=_place()).full_label, _place().label
        )

    def test_key_comes_from_the_place(self):
        self.assertEqual(SavedLocation(place=_place()).key, _place().key)

    def test_defaults_are_notifiable_and_not_favorite(self):
        location = SavedLocation(place=_place())
        self.assertTrue(location.notify)
        self.assertFalse(location.favorite)
        self.assertEqual(location.alerts, ())

    def test_round_trips_through_dict(self):
        location = SavedLocation(
            place=_place(), alias="Casa", favorite=True, notify=False,
            alerts=({"kind": "rain"},),
        )
        self.assertEqual(SavedLocation.from_dict(location.to_dict()), location)

    def test_reads_the_legacy_inline_place_format(self):
        payload = _place().to_dict()
        payload["alias"] = "Casa"
        location = SavedLocation.from_dict(payload)
        self.assertEqual(location.alias, "Casa")
        self.assertEqual(location.place.name, "Santos")

    def test_rejects_a_non_dict(self):
        with self.assertRaises(Exception):
            SavedLocation.from_dict("Santos")

    def test_rejects_a_missing_place(self):
        with self.assertRaises(Exception):
            SavedLocation.from_dict({"alias": "Casa", "place": "Santos"})


class LocationStoreBasicsTests(unittest.TestCase):
    def test_a_new_store_is_empty(self):
        with tempfile.TemporaryDirectory() as directory:
            store = _store(directory)
            self.assertEqual(len(store), 0)
            self.assertIsNone(store.default)
            self.assertEqual(store.keys(), [])
            self.assertIsNone(store.cycle(""))

    def test_default_path_is_under_data(self):
        store = LocationStore()
        self.assertEqual(store.path.parent.name, "data")
        self.assertEqual(store.path.name, "locations.json")

    def test_add_appends_and_becomes_default(self):
        with tempfile.TemporaryDirectory() as directory:
            store = _store(directory)
            location = store.add(_place())
            self.assertEqual(len(store), 1)
            self.assertIs(store.default, location)
            self.assertEqual(store.default_key, location.key)

    def test_adding_a_second_location_keeps_the_first_as_default(self):
        with tempfile.TemporaryDirectory() as directory:
            store = _store(directory)
            first = store.add(_place())
            store.add(_place(name="Campinas", place_id=2, latitude=-22.9))
            self.assertEqual(store.default_key, first.key)
            self.assertEqual(len(store), 2)

    def test_adding_the_same_place_does_not_duplicate(self):
        with tempfile.TemporaryDirectory() as directory:
            store = _store(directory)
            store.add(_place())
            store.add(_place(name="Santos"))
            self.assertEqual(len(store), 1)

    def test_adding_the_same_place_refreshes_its_data(self):
        with tempfile.TemporaryDirectory() as directory:
            store = _store(directory)
            store.add(_place())
            refreshed = store.add(_place(name="Santos", timezone="America/Bahia"))
            self.assertEqual(refreshed.place.timezone, "America/Bahia")

    def test_the_same_place_id_with_other_coordinates_deduplicates(self):
        with tempfile.TemporaryDirectory() as directory:
            store = _store(directory)
            store.add(_place())
            store.add(_place(latitude=-23.95, longitude=-46.34))
            self.assertEqual(len(store), 1)

    def test_distinct_places_without_an_id_are_kept(self):
        with tempfile.TemporaryDirectory() as directory:
            store = _store(directory)
            store.add(_place(place_id=0))
            store.add(_place(place_id=0, name="Outra", latitude=-1.0, longitude=-2.0))
            self.assertEqual(len(store), 2)

    def test_adding_with_an_alias_sets_it(self):
        with tempfile.TemporaryDirectory() as directory:
            store = _store(directory)
            self.assertEqual(store.add(_place(), alias="  Casa ").alias, "Casa")

    def test_adding_an_existing_place_without_an_alias_keeps_the_alias(self):
        with tempfile.TemporaryDirectory() as directory:
            store = _store(directory)
            store.add(_place(), alias="Casa")
            self.assertEqual(store.add(_place()).alias, "Casa")

    def test_contains_uses_the_key(self):
        with tempfile.TemporaryDirectory() as directory:
            store = _store(directory)
            location = store.add(_place())
            self.assertIn(location.key, store)
            self.assertNotIn("chave-inexistente", store)

    def test_find_returns_none_for_an_unknown_key(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertIsNone(_store(directory).find("nada"))

    def test_find_place_deduplicates_by_id(self):
        with tempfile.TemporaryDirectory() as directory:
            store = _store(directory)
            location = store.add(_place())
            self.assertIs(
                store.find_place(_place(latitude=-23.0, longitude=-46.0)), location
            )


class LocationStoreMutationTests(unittest.TestCase):
    def _populated(self, directory, count=3):
        store = _store(directory)
        store.add(_place(name="A", place_id=1, latitude=-1.0, longitude=-1.0))
        if count >= 2:
            store.add(_place(name="B", place_id=2, latitude=-2.0, longitude=-2.0))
        if count >= 3:
            store.add(_place(name="C", place_id=3, latitude=-3.0, longitude=-3.0))
        return store

    def test_remove_deletes_and_reports_success(self):
        with tempfile.TemporaryDirectory() as directory:
            store = self._populated(directory)
            key = store.locations[1].key
            self.assertTrue(store.remove(key))
            self.assertEqual([loc.place.name for loc in store], ["A", "C"])
            self.assertFalse(store.remove(key))

    def test_removing_the_default_promotes_the_first(self):
        with tempfile.TemporaryDirectory() as directory:
            store = self._populated(directory)
            store.set_default(store.locations[1].key)
            store.remove(store.locations[0].key)
            self.assertEqual(store.default.place.name, "B")

    def test_removing_everything_clears_the_default(self):
        with tempfile.TemporaryDirectory() as directory:
            store = self._populated(directory, count=1)
            store.remove(store.locations[0].key)
            self.assertEqual(store.default_key, "")
            self.assertIsNone(store.default)

    def test_move_shifts_a_location_down(self):
        with tempfile.TemporaryDirectory() as directory:
            store = self._populated(directory)
            self.assertTrue(store.move(store.locations[0].key, 1))
            self.assertEqual([loc.place.name for loc in store], ["B", "A", "C"])

    def test_move_clamps_at_the_edges(self):
        with tempfile.TemporaryDirectory() as directory:
            store = self._populated(directory)
            self.assertFalse(store.move(store.locations[0].key, -1))
            self.assertFalse(store.move(store.locations[-1].key, 1))

    def test_move_to_places_the_location_at_an_index(self):
        with tempfile.TemporaryDirectory() as directory:
            store = self._populated(directory)
            store.move_to(store.locations[0].key, 2)
            self.assertEqual([loc.place.name for loc in store], ["B", "C", "A"])

    def test_move_rejects_an_unknown_key(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertFalse(self._populated(directory).move("nada", 1))

    def test_reorder_accepts_a_full_permutation(self):
        with tempfile.TemporaryDirectory() as directory:
            store = self._populated(directory)
            keys = [store.locations[2].key, store.locations[0].key, store.locations[1].key]
            self.assertTrue(store.reorder(keys))
            self.assertEqual([loc.place.name for loc in store], ["C", "A", "B"])

    def test_reorder_rejects_an_incomplete_list(self):
        with tempfile.TemporaryDirectory() as directory:
            store = self._populated(directory)
            before = store.keys()
            self.assertFalse(store.reorder(before[:1]))
            self.assertEqual(store.keys(), before)

    def test_reorder_rejects_unknown_keys(self):
        with tempfile.TemporaryDirectory() as directory:
            store = self._populated(directory)
            before = store.keys()
            self.assertFalse(store.reorder([store.locations[0].key, "nada"]))
            self.assertEqual(store.keys(), before)

    def test_clear_empties_the_list(self):
        with tempfile.TemporaryDirectory() as directory:
            store = self._populated(directory)
            store.clear()
            self.assertEqual(len(store), 0)
            self.assertEqual(store.default_key, "")


class LocationStoreOptionTests(unittest.TestCase):
    def _one(self, directory):
        store = _store(directory)
        return store, store.add(_place())

    def test_set_alias_strips_whitespace(self):
        with tempfile.TemporaryDirectory() as directory:
            store, location = self._one(directory)
            self.assertTrue(store.set_alias(location.key, "  Trabalho "))
            self.assertEqual(location.alias, "Trabalho")

    def test_set_alias_with_none_clears_it(self):
        with tempfile.TemporaryDirectory() as directory:
            store, location = self._one(directory)
            store.set_alias(location.key, "Casa")
            store.set_alias(location.key, None)
            self.assertEqual(location.alias, "")

    def test_toggle_favorite_flips_and_returns_the_new_value(self):
        with tempfile.TemporaryDirectory() as directory:
            store, location = self._one(directory)
            self.assertTrue(store.toggle_favorite(location.key))
            self.assertTrue(location.favorite)
            self.assertFalse(store.toggle_favorite(location.key))

    def test_favorites_only_lists_the_marked_locations(self):
        with tempfile.TemporaryDirectory() as directory:
            store = _store(directory)
            first = store.add(_place(name="A", place_id=1))
            store.add(_place(name="B", place_id=2, latitude=-2.0))
            store.set_favorite(first.key, True)
            self.assertEqual([loc.place.name for loc in store.favorites], ["A"])

    def test_set_notify_is_stored(self):
        with tempfile.TemporaryDirectory() as directory:
            store, location = self._one(directory)
            store.set_notify(location.key, False)
            self.assertFalse(location.notify)

    def test_set_alerts_stores_the_rules(self):
        with tempfile.TemporaryDirectory() as directory:
            store, location = self._one(directory)
            rules = [{"kind": "rain", "threshold": 60}]
            store.set_alerts(location.key, rules)
            self.assertEqual(location.alerts, ({"kind": "rain", "threshold": 60},))

    def test_set_alerts_with_none_clears_them(self):
        with tempfile.TemporaryDirectory() as directory:
            store, location = self._one(directory)
            store.set_alerts(location.key, [{"kind": "rain"}])
            store.set_alerts(location.key, None)
            self.assertEqual(location.alerts, ())

    def test_option_setters_report_an_unknown_key(self):
        with tempfile.TemporaryDirectory() as directory:
            store, _ = self._one(directory)
            self.assertFalse(store.set_alias("nada", "x"))
            self.assertFalse(store.set_favorite("nada", True))
            self.assertFalse(store.set_notify("nada", True))
            self.assertFalse(store.set_alerts("nada", []))
            self.assertFalse(store.toggle_favorite("nada"))


class LocationStoreDefaultTests(unittest.TestCase):
    def _populated(self, directory):
        store = _store(directory)
        store.add(_place(name="A", place_id=1))
        store.add(_place(name="B", place_id=2, latitude=-2.0))
        store.add(_place(name="C", place_id=3, latitude=-3.0))
        return store

    def test_set_default_accepts_a_known_key(self):
        with tempfile.TemporaryDirectory() as directory:
            store = self._populated(directory)
            key = store.locations[2].key
            self.assertTrue(store.set_default(key))
            self.assertEqual(store.default_key, key)
            self.assertEqual(store.default.place.name, "C")

    def test_set_default_rejects_an_unknown_key(self):
        with tempfile.TemporaryDirectory() as directory:
            store = self._populated(directory)
            before = store.default_key
            self.assertFalse(store.set_default("nada"))
            self.assertEqual(store.default_key, before)

    def test_default_falls_back_to_the_first_location(self):
        with tempfile.TemporaryDirectory() as directory:
            store = self._populated(directory)
            store.default_key = "chave-antiga"
            self.assertEqual(store.default.place.name, "A")


class LocationStoreCycleTests(unittest.TestCase):
    def _populated(self, directory):
        store = _store(directory)
        store.add(_place(name="A", place_id=1))
        store.add(_place(name="B", place_id=2, latitude=-2.0))
        store.add(_place(name="C", place_id=3, latitude=-3.0))
        return store

    def test_cycle_advances(self):
        with tempfile.TemporaryDirectory() as directory:
            store = self._populated(directory)
            self.assertEqual(store.cycle(store.locations[0].key).place.name, "B")

    def test_cycle_wraps_around(self):
        with tempfile.TemporaryDirectory() as directory:
            store = self._populated(directory)
            self.assertEqual(store.cycle(store.locations[2].key).place.name, "A")

    def test_cycle_goes_backwards(self):
        with tempfile.TemporaryDirectory() as directory:
            store = self._populated(directory)
            self.assertEqual(store.cycle(store.locations[0].key, -1).place.name, "C")

    def test_cycle_from_an_unknown_key_starts_at_the_top(self):
        with tempfile.TemporaryDirectory() as directory:
            store = self._populated(directory)
            self.assertEqual(store.cycle("nada").place.name, "A")


class LocationStorePersistenceTests(unittest.TestCase):
    def test_round_trips_every_field(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "locations.json"
            store = LocationStore(path)
            first = store.add(_place(), alias="Casa")
            store.set_favorite(first.key, True)
            store.set_notify(first.key, False)
            store.set_alerts(first.key, [{"kind": "heat", "threshold": 35}])
            second = store.add(_place(name="B", place_id=2, latitude=-2.0))
            store.set_default(second.key)
            store.save()

            reloaded = LocationStore(path)
            self.assertEqual(reloaded.keys(), store.keys())
            self.assertEqual(reloaded.default_key, second.key)
            restored = reloaded.find(first.key)
            self.assertEqual(restored.alias, "Casa")
            self.assertTrue(restored.favorite)
            self.assertFalse(restored.notify)
            self.assertEqual(restored.alerts, ({"kind": "heat", "threshold": 35},))

    def test_saved_file_is_versioned_and_utf8(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "locations.json"
            store = LocationStore(path)
            store.add(_place(admin1="São Paulo"), alias="Casa")
            store.save()
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["version"], SCHEMA_VERSION)
            self.assertEqual(payload["locations"][0]["alias"], "Casa")

    def test_order_survives_a_reload(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "locations.json"
            store = LocationStore(path)
            store.add(_place(name="A", place_id=1))
            store.add(_place(name="B", place_id=2, latitude=-2.0))
            store.add(_place(name="C", place_id=3, latitude=-3.0))
            store.move_to(store.locations[0].key, 2)
            store.save()
            self.assertEqual(
                [loc.place.name for loc in LocationStore(path)], ["B", "C", "A"]
            )

    def test_a_corrupted_file_is_ignored(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "locations.json"
            path.write_text("{ não é json", encoding="utf-8")
            store = LocationStore(path)
            self.assertEqual(len(store), 0)
            self.assertIsNone(store.default)

    def test_invalid_entries_are_skipped(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "locations.json"
            payload = {
                "version": 1,
                "default": "",
                "locations": [
                    {"alias": "sem place"},
                    SavedLocation(place=_place()).to_dict(),
                ],
            }
            path.write_text(json.dumps(payload), encoding="utf-8")
            store = LocationStore(path)
            self.assertEqual(len(store), 1)
            self.assertEqual(store.locations[0].place.name, "Santos")

    def test_duplicate_keys_are_collapsed_on_load(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "locations.json"
            entry = SavedLocation(place=_place()).to_dict()
            payload = {"version": 1, "default": "", "locations": [entry, dict(entry)]}
            path.write_text(json.dumps(payload), encoding="utf-8")
            self.assertEqual(len(LocationStore(path)), 1)

    def test_a_stale_default_is_repaired_on_load(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "locations.json"
            payload = {
                "version": 1,
                "default": "chave-que-nao-existe",
                "locations": [SavedLocation(place=_place()).to_dict()],
            }
            path.write_text(json.dumps(payload), encoding="utf-8")
            store = LocationStore(path)
            self.assertEqual(store.default_key, store.locations[0].key)

    def test_an_empty_list_loads_without_a_default(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "locations.json"
            path.write_text('{"version": 1, "default": "", "locations": []}', encoding="utf-8")
            store = LocationStore(path)
            self.assertIsNone(store.default)

    def test_a_non_dict_file_is_ignored(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "locations.json"
            path.write_text("[1, 2, 3]", encoding="utf-8")
            self.assertEqual(len(LocationStore(path)), 0)


class NotificationTests(unittest.TestCase):
    def test_defaults_are_disabled_with_default_fields(self):
        location = SavedLocation(place=_place())
        self.assertFalse(location.notify_hourly)
        self.assertEqual(
            location.notification_fields, DEFAULT_NOTIFICATION_FIELDS
        )
        self.assertEqual(location.notify_interval, DEFAULT_NOTIFICATION_INTERVAL)

    def test_notification_survives_a_round_trip(self):
        location = SavedLocation(
            place=_place(),
            notify_hourly=True,
            notify_fields=("temperature", "humidity"),
            notify_interval=15,
        )
        restored = SavedLocation.from_dict(location.to_dict())
        self.assertTrue(restored.notify_hourly)
        self.assertEqual(restored.notify_fields, ("temperature", "humidity"))
        self.assertEqual(restored.notify_interval, 15)

    def test_interval_is_clamped_when_loading(self):
        payload = SavedLocation(place=_place()).to_dict()
        payload["notify_interval"] = 9999
        self.assertEqual(SavedLocation.from_dict(payload).notify_interval, 360)
        payload["notify_interval"] = 0
        self.assertEqual(SavedLocation.from_dict(payload).notify_interval, 1)
        payload["notify_interval"] = "nao e numero"
        self.assertEqual(
            SavedLocation.from_dict(payload).notify_interval,
            DEFAULT_NOTIFICATION_INTERVAL,
        )

    def test_unknown_fields_are_dropped_on_load(self):
        payload = SavedLocation(place=_place()).to_dict()
        payload["notify_fields"] = ["temperature", "inventado"]
        restored = SavedLocation.from_dict(payload)
        self.assertEqual(restored.notify_fields, ("temperature",))

    def test_store_updates_the_notification(self):
        with tempfile.TemporaryDirectory() as directory:
            store = _store(directory)
            location = store.add(_place())
            self.assertTrue(
                store.set_notification(
                    location.key, True, ("temperature", "wind_speed"), 30
                )
            )
            self.assertTrue(store.locations[0].notify_hourly)
            self.assertEqual(
                store.locations[0].notify_fields, ("temperature", "wind_speed")
            )
            self.assertEqual(store.locations[0].notify_interval, 30)

    def test_store_clamps_the_notification_interval(self):
        with tempfile.TemporaryDirectory() as directory:
            store = _store(directory)
            location = store.add(_place())
            store.set_notification(location.key, True, (), 100000)
            self.assertEqual(store.locations[0].notify_interval, 360)
            store.set_notification(location.key, True, (), None)
            self.assertEqual(store.locations[0].notify_interval, 360)

    def test_store_ignores_unknown_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            store = _store(directory)
            location = store.add(_place())
            store.set_notification(location.key, True, ("temperature", "nope"))
            self.assertEqual(store.locations[0].notify_fields, ("temperature",))

    def test_set_notification_on_a_missing_key_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            store = _store(directory)
            self.assertFalse(store.set_notification("nem-existe", True, ()))

    def test_notification_persists_to_disk(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "locations.json"
            store = LocationStore(path)
            location = store.add(_place())
            store.set_notification(location.key, True, ("condition",))
            store.save()
            reloaded = LocationStore(path)
            self.assertTrue(reloaded.locations[0].notify_hourly)
            self.assertEqual(reloaded.locations[0].notify_fields, ("condition",))


if __name__ == "__main__":
    unittest.main()