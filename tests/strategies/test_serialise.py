"""Tests serialise strategy."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from oteapi.interfaces import IFilterStrategy


def test_serialise(tmp_path: "Path") -> None:
    """Test the serialise filter."""
    import dlite

    from oteapi_dlite.strategies.serialise import (
        SerialiseFilterConfig,
        SerialiseStrategy,
    )
    from oteapi_dlite.utils import get_meta

    coll = dlite.Collection()
    config = SerialiseFilterConfig(
        filterType="dlite_serialise",
        configuration={
            "driver": "json",
            "location": str(tmp_path / "coll.json"),
            "options": "mode=w",
            "collection_id": coll.uuid,
        },
    )

    serialiser: "IFilterStrategy" = SerialiseStrategy(config)
    serialiser.initialize()

    # Imitate other filters adding stuff to the collection
    coll.add_relation("subject", "predicate", "object")
    Image = get_meta(  # pylint: disable=invalid-name
        "http://onto-ns.com/meta/1.0/Image"
    )
    image = Image([2, 2, 1])
    image.data = [[[1], [2]], [[3], [4]]]
    coll.add("image", image)

    serialiser: "IFilterStrategy" = SerialiseStrategy(config)
    serialiser.get()

    assert (tmp_path / "coll.json").exists()
