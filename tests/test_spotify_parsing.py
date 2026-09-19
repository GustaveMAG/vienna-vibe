"""Tests de la transformation Spotify."""

from __future__ import annotations

from vienna_vibe.sources import spotify


def _item(track_id: str, played_at: str, artist_id: str = "art1") -> dict:
    return {
        "played_at": played_at,
        "context": {"type": "playlist"},
        "track": {
            "id": track_id,
            "name": f"Titre {track_id}",
            "duration_ms": 214000,
            "explicit": False,
            "popularity": 57,
            "album": {"name": "Album X", "release_date": "2024-03-01"},
            "artists": [{"id": artist_id, "name": "Artiste A"}],
        },
    }


def test_parse_reads_events() -> None:
    payload = {"items": [_item("t1", "2026-09-19T18:03:11.000Z")]}

    events = spotify.parse(payload)

    assert len(events) == 1
    event = events[0]
    assert event.track.track_id == "t1"
    assert event.track.primary_artist is not None
    assert event.track.primary_artist.artist_name == "Artiste A"
    assert event.context_type == "playlist"
    assert event.played_at.tzinfo is not None


def test_parse_deduplicates_within_payload() -> None:
    """Deux pages qui se recouvrent renvoient la même écoute deux fois.

    On la dédoublonne avant la base : la clé naturelle nous protégerait de
    toute façon, mais autant ne pas envoyer de bruit jusque-là.
    """
    payload = {
        "items": [
            _item("t1", "2026-09-19T18:03:11.000Z"),
            _item("t1", "2026-09-19T18:03:11.000Z"),
            _item("t2", "2026-09-19T18:07:44.000Z"),
        ]
    }

    events = spotify.parse(payload)

    assert len(events) == 2
    assert {e.track.track_id for e in events} == {"t1", "t2"}


def test_same_track_at_different_times_is_two_events() -> None:
    """Réécouter un titre est un fait distinct, pas un doublon."""
    payload = {
        "items": [
            _item("t1", "2026-09-19T18:03:11.000Z"),
            _item("t1", "2026-09-19T19:41:02.000Z"),
        ]
    }

    events = spotify.parse(payload)

    assert len(events) == 2


def test_parse_sorts_chronologically() -> None:
    payload = {
        "items": [
            _item("t2", "2026-09-19T19:00:00.000Z"),
            _item("t1", "2026-09-19T18:00:00.000Z"),
        ]
    }

    events = spotify.parse(payload)

    assert [e.track.track_id for e in events] == ["t1", "t2"]


def test_parse_skips_malformed_items_without_failing() -> None:
    """Une écoute cassée ne doit pas faire perdre les autres."""
    payload = {
        "items": [
            {"played_at": "2026-09-19T18:00:00.000Z", "track": {}},  # sans id
            {"track": {"id": "t2", "name": "X"}},  # sans played_at
            _item("t3", "2026-09-19T18:30:00.000Z"),
        ]
    }

    events = spotify.parse(payload)

    assert [e.track.track_id for e in events] == ["t3"]


def test_parse_handles_track_without_artist() -> None:
    item = _item("t1", "2026-09-19T18:00:00.000Z")
    item["track"]["artists"] = []

    events = spotify.parse({"items": [item]})

    assert len(events) == 1
    assert events[0].track.primary_artist is None


def test_parse_handles_missing_context() -> None:
    item = _item("t1", "2026-09-19T18:00:00.000Z")
    item["context"] = None

    events = spotify.parse({"items": [item]})

    assert events[0].context_type is None


def test_parse_handles_empty_payload() -> None:
    assert spotify.parse({}) == []
    assert spotify.parse({"items": []}) == []
