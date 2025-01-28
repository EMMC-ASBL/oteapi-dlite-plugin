"""Tests mapping strategy."""

from __future__ import annotations


def test_mapping_without_prefixes() -> None:
    """Test without prefixes."""
    from oteapi.utils.config_updater import populate_config_from_session
    from tripper import EMMO, MAP, Namespace

    from oteapi_dlite.strategies.mapping import (
        DLiteMappingConfig,
        DLiteMappingStrategy,
    )
    from oteapi_dlite.utils import get_collection

    FORCES = Namespace("http://onto-ns.com/meta/0.1/Forces#")
    ENERGY = Namespace("http://onto-ns.com/meta/0.1/Energy#")

    config = DLiteMappingConfig(
        mappingType="mappings",
        triples=[
            (FORCES.forces, MAP.mapsTo, EMMO.Force),
            (ENERGY.energy, MAP.mapsTo, EMMO.PotentialEnergy),
        ],
    )

    session = DLiteMappingStrategy(config).initialize()

    # Remove the line immediately below once EMMC-ASBL/oteapi#545 is fixed
    config.configuration.collection_id = session.collection_id
    populate_config_from_session(session, config)

    DLiteMappingStrategy(config).get()

    coll = get_collection(session.collection_id)

    relations = set(coll.get_relations())
    assert len(list(coll.get_relations())) == len(relations)
    assert (FORCES.forces, MAP.mapsTo, EMMO.Force) in relations
    assert (ENERGY.energy, MAP.mapsTo, EMMO.PotentialEnergy) in relations


def test_mapping_with_prefixes() -> None:
    """Test with prefixes."""
    from oteapi.utils.config_updater import populate_config_from_session
    from tripper import EMMO, MAP, Namespace

    from oteapi_dlite.strategies.mapping import (
        DLiteMappingConfig,
        DLiteMappingStrategy,
    )
    from oteapi_dlite.utils import get_collection

    FORCES = Namespace("http://onto-ns.com/meta/0.1/Forces#")
    ENERGY = Namespace("http://onto-ns.com/meta/0.1/Energy#")

    config = DLiteMappingConfig(
        mappingType="mappings",
        prefixes={
            "f": "http://onto-ns.com/meta/0.1/Forces#",
            "e": "http://onto-ns.com/meta/0.1/Energy#",
            "map": str(MAP),  # __FIXME__: prefixes should accept a Namespace
            "emmo": str(EMMO),
        },
        triples=[
            # From tripper 0.3.5 importing EMMO as namespace resolves correctly
            (
                "f:forces",
                "map:mapsTo",
                "https://w3id.org/emmo#EMMO_1f087811_06cb_42d5_90fb_25d0e7e068ef",
            ),
            (
                "e:energy",
                "map:mapsTo",
                "https://w3id.org/emmo#EMMO_4c151909_6f26_4ef9_b43d_7c9e9514883a",
            ),
        ],
    )
    session = DLiteMappingStrategy(config).initialize()

    # Remove the line immediately below once EMMC-ASBL/oteapi#545 is fixed
    config.configuration.collection_id = session.collection_id
    populate_config_from_session(session, config)

    DLiteMappingStrategy(config).get()

    coll = get_collection(session.collection_id)

    relations = set(coll.get_relations())
    assert len(list(coll.get_relations())) == len(relations)
    assert (FORCES.forces, MAP.mapsTo, EMMO.Force) in relations
    assert (ENERGY.energy, MAP.mapsTo, EMMO.PotentialEnergy) in relations
