"""Generic generate strategy using DLite storage plugin."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Optional

from oteapi.datacache import DataCache
from oteapi.models import DataCacheConfig, FunctionConfig
from pydantic import Field
from pydantic.dataclasses import dataclass

from oteapi_dlite.models import DLiteConfiguration, DLiteResult
from oteapi_dlite.utils import (
    get_collection,
    get_driver,
    get_triplestore,
    update_collection,
    update_dict,
)

# Constants
hasInput = "https://w3id.org/emmo#EMMO_36e69413_8c59_4799_946c_10b05d266e22"
hasOutput = "https://w3id.org/emmo#EMMO_c4bace1d_4db0_4cd3_87e9_18122bae2840"


class KBError(ValueError):
    """Invalid data in knowledge base."""


class DLiteStorageConfig(DLiteConfiguration):
    """Configuration for a generic DLite storage filter.

    The DLite storage driver to can be specified using either the `driver`
    or `mediaType` field.

    Where the output should be written, is specified using either the
    `location` or `datacache_config.accessKey` field.

    Either `label` or `datamodel` should be provided.
    """

    driver: Annotated[
        Optional[str],
        Field(
            description='Name of DLite driver (ex: "json").',
        ),
    ] = None
    mediaType: Annotated[
        Optional[str],
        Field(
            description='Media type for DLite driver (ex: "application/json").',
        ),
    ] = None
    options: Annotated[
        Optional[str],
        Field(
            description=(
                "Comma-separated list of options passed to the DLite "
                "storage plugin."
            ),
        ),
    ] = None
    location: Annotated[
        Optional[str],
        Field(
            description=(
                "Location of storage to write to.  If unset to store in data "
                "cache using the key provided with "
                "`datacache_config.accessKey` (defaults to 'generate_data')."
            ),
        ),
    ] = None
    label: Annotated[
        Optional[str],
        Field(
            description=(
                "Label of DLite instance in the collection to serialise."
            ),
        ),
    ] = None
    datamodel: Annotated[
        Optional[str],
        Field(
            description=(
                "URI to the datamodel of the new instance.  Needed when "
                "generating the instance from mappings.  Cannot be combined "
                "with `label`"
            ),
        ),
    ] = None
    property_mappings: Annotated[
        bool,
        Field(
            description="Whether property mappings should be performed.",
        ),
    ] = True
    store_collection: Annotated[
        bool,
        Field(
            description=(
                "Whether to store the entire collection in the session "
                "instead of a single instance.  Cannot be combined with "
                "`label` or `datamodel`."
            ),
        ),
    ] = False
    store_collection_id: Annotated[
        Optional[str],
        Field(
            description=(
                "Used together with `store_collection` If given, store "
                "a copy of the collection with this id."
            ),
        ),
    ] = None
    allow_incomplete: Annotated[
        Optional[bool],
        Field(
            description="Whether to allow incomplete property mappings.",
        ),
    ] = False
    datacache_config: Annotated[
        Optional[DataCacheConfig],
        Field(
            description="Configuration options for the local data cache.",
        ),
    ] = None
    kb_document_class: Annotated[
        Optional[str],
        Field(
            description=(
                "IRI of a class in the ontology."
                "\n\n"
                "If given, the generated DLite instance is documented in the "
                "knowledge base as an instance of this class."
                "\n\n"
                "Expects that the 'tripper.triplestore' setting has been "
                "set using the SettingsStrategy (vnd.dlite-settings). "
                "This settings should be a dict that can be passed "
                "as keyword arguments to `tripper.Triplestore()`."
                "\n\n"
                "Example of adding expected settings using OTELib:\n"
                "\n\n"
                ">>> kb_settings = client.create_filter(\n"
                "...     filterType='application/vnd.dlite-settings',\n"
                "...     configuration={\n"
                "...         'label': 'tripper.triplestore',\n"
                "...         'settings': {\n"
                "...             'backend': 'rdflib',\n"
                "...             'triplestore_url': '/path/to/local/kb.ttl',\n"
                "...         },\n"
                "...     },\n"
                "... )\n"
                ">>> generate = client.create_function(\n"
                "...     functionType='application/vnd.dlite-generate'\n"
                "...     configuration={\n"
                "...         kb_document_class='http://example.com#MyClass'\n"
                "...         ...\n"
                "...     },\n"
                "... )\n"
                ">>> pipeline = ... >> generate >> kb_settings\n"
                ">>> pipeline.get()\n"
            ),
        ),
    ] = None
    kb_document_update: Annotated[
        Optional[dict],
        Field(
            description=(
                "Dict updating the documentation (partial pipeline) created "
                "with `kb_document_class`."
                "\n\n"
                "This dict should be structured as follows: "
                "\n\n"
                "    {\n"
                '      "dataresource": {...},\n'
                '      "parse": {...}\n'
                '      "mapping": {...}\n'
                "    }\n"
                "\n"
                "where the provided items will override the the default "
                "configurations in respective partial pipeline created by "
                '`kb_document_class`.  Any of the items "dataresource", '
                '"parse" and "mapping" are optional.',
            ),
        ),
    ] = None
    kb_document_base_iri: Annotated[
        str, Field(description="Base IRI or prefix for created individuals.")
    ] = ":"
    kb_document_context: Annotated[
        Optional[dict],
        Field(
            description=(
                "If `kb_document_class` is given, this configuration will add "
                "additional context to the documentation of the generated "
                "individual."
                "\n\n"
                "This might be useful to make it easy to later access the "
                "generated individual."
                "\n\n"
                "This configuration should be a dict mapping providing the "
                "additional documentation of the driver. It should map OWL "
                "properties to either tripper literals or IRIs."
                "\n\n"
                "Example: `{RDF.type: ONTO.MyDataSet, "
                "EMMO.isDescriptionFor: ONTO.MyMaterial}`"
            ),
        ),
    ] = None
    kb_document_computation: Annotated[
        Optional[str],
        Field(
            description=(
                "IRI of a computation subclass."
                "\n\n"
                "Requires `kb_document_class`, and is used to "
                "document the computation (model) that the "
                "individual (of `kb_document_class`) to be documented "
                "is output of."
                "When `kb_document_computation` is given a new individual of "
                "the computation subclass is created. Input and "
                "output datasets are documented using the relation "
                " `emmo:hasInput` and `emmo:hasOutput`, "
                "respectively.  The individual of `kb_document_class` is "
                "one of the output individuals."
                "\n\n"
                "Note: This configuration relies on several assumptions:\n"
                "  - The `kb_document_computation` class exists in the "
                "knowledge base and is related to its input and output "
                "dataset classes via `emmo:hasInput` and `emmo:hasOutput` "
                "restrictions, respectively.\n"
                "  - There exists only one individual of each input dataset "
                "class.\n"
                "  - There exists at most one individual of each output "
                "dataset class.\n"
            ),
        ),
    ] = None


class DLiteGenerateConfig(FunctionConfig):
    """DLite generate strategy config."""

    configuration: Annotated[
        DLiteStorageConfig,
        Field(description="DLite generate strategy-specific configuration."),
    ]


@dataclass
class DLiteGenerateStrategy:
    """Generic DLite generate strategy utilising DLite storage plugins.

    **Registers strategies**:

    - `("mediaType", "application/vnd.dlite-generate")`

    """

    function_config: DLiteGenerateConfig

    def initialize(self) -> DLiteResult:
        """Initialize."""
        return DLiteResult(
            collection_id=get_collection(
                self.function_config.configuration.collection_id
            ).uuid
        )

    def get(self) -> DLiteResult:
        """Execute the strategy.

        This method will be called through the strategy-specific endpoint
        of the OTE-API Services.

        Returns:
            SessionUpdate instance.
        """
        config = self.function_config.configuration
        cacheconfig = config.datacache_config

        driver = (
            config.driver
            if config.driver
            else get_driver(mediaType=config.mediaType)
        )

        coll = get_collection(config.collection_id)

        if config.label:
            inst = coll[config.label]
        elif config.datamodel:
            instances = coll.get_instances(
                metaid=config.datamodel,
                property_mappings=config.property_mappings,
                allow_incomplete=config.allow_incomplete,
            )
            inst = next(instances)
        elif config.store_collection:
            if config.store_collection_id:
                inst = coll.copy(newid=config.store_collection_id)
            else:
                inst = coll
        else:  # fail if there are more instances
            raise ValueError(
                "One of `label` or `datamodel` configurations should be given."
            )

        # Save instance
        if config.location:
            inst.save(driver, config.location, config.options)
        else:  # missing test
            if cacheconfig and cacheconfig.accessKey:
                key = cacheconfig.accessKey
            else:  # missing test
                key = "generate_data"
            cache = DataCache()
            with tempfile.TemporaryDirectory() as tmpdir:
                inst.save(driver, f"{tmpdir}/data", config.options)
                with Path(f"{tmpdir}/data").open("rb") as f:
                    cache.add(f.read(), key=key)

        # Store documentation of this instance in the knowledge base
        if config.kb_document_class:

            # Import here to avoid hard dependencies on tripper.
            from tripper import RDF
            from tripper.convert import save_container

            kb_settings = config.dlite_settings.get("tripper.triplestore")
            if isinstance(kb_settings, str):
                kb_settings = json.loads(kb_settings)
            if kb_settings and not isinstance(kb_settings, dict):
                raise ValueError(
                    "The `kb_document_class` configuration expects a dict "
                    "with settings for the tripper.triplestore."
                )

            if TYPE_CHECKING:  # pragma: no cover
                # This block will only be run by mypy when checking typing
                assert (
                    isinstance(kb_settings, dict) or kb_settings is None
                )  # nosec

            # IRI of new individual
            iri = individual_iri(
                class_iri=config.kb_document_class,
                base_iri=config.kb_document_base_iri,
            )

            triples = [(iri, RDF.type, config.kb_document_class)]
            if config.kb_document_context:
                for prop, val in config.kb_document_context.items():
                    triples.append((iri, prop, val))

            ts = get_triplestore(
                kb_settings=kb_settings,
                collection_id=config.collection_id,
            )
            try:
                if config.kb_document_computation:
                    comput = individual_iri(
                        class_iri=config.kb_document_computation,
                        base_iri=config.kb_document_base_iri,
                    )
                    triples.extend(
                        [
                            (comput, RDF.type, config.kb_document_computation),
                            (comput, hasOutput, iri),
                        ]
                    )

                    # Relate computation individual `comput` to its
                    # input individuals.
                    #
                    # This simple implementation works against KB.  It
                    # assumes that the input of
                    # `kb_document_computation` is documented in the
                    # KB and that there only exists one individual of each
                    # input class.
                    #
                    # In the case of multiple individuals of the input
                    # classes, the workflow executer must be involded
                    # in the documentation.  It can either do the
                    # documentation itself or provide a callback
                    # providing the needed info, which can be called
                    # from this strategy.

                    # Relate to input dataset individuals
                    restrictions = ts.restrictions(
                        config.kb_document_computation, hasInput
                    )
                    for r in restrictions:
                        input_class = r["value"]
                        indv = ts.value(predicate=RDF.type, object=input_class)
                        triples.append((comput, r["property"], indv))

                    # Add output dataset individuals
                    restrictions = ts.restrictions(
                        config.kb_document_computation, hasOutput
                    )
                    for r in restrictions:
                        output_class = r["value"]
                        indv = ts.value(
                            predicate=RDF.type,
                            object=output_class,
                            default=None,
                        )
                        if indv and indv != iri:
                            triples.append((comput, r["property"], indv))

                # Document data source
                resource = {
                    "dataresource": {
                        "type": config.kb_document_class,
                        "downloadUrl": config.location,
                        "mediaType": (
                            config.mediaType
                            if config.mediaType
                            else "application/vnd.dlite-parse"
                        ),
                        "configuration": {
                            "datamodel": (
                                config.datamodel
                                if config.datamodel
                                else inst.meta.uri
                            ),
                            "driver": config.driver,
                            "options": (  # Trying to be clever here...
                                config.options.replace("mode=w", "mode=r")
                                if config.options
                                else config.options
                            ),
                        },
                    },
                    # "parse": {},  # No supported by OTEAPI yet...
                    "mapping": {
                        "mappingType": "mappings",
                        # __TODO__
                        # Populate prefixes and triples from mapping
                        # strategy in current partial pipeline
                        # "prefixes": {},
                        # "triples": [],
                    },
                }
                update_dict(resource, config.kb_document_update)

                save_container(
                    ts,
                    resource,
                    iri,
                    recognised_keys="basic",
                )
                ts.add_triples(triples)

            finally:
                ts.close()

        # __TODO__
        # Can we safely assume that all strategies in a pipeline will be
        # executed in the same Python interpreter?  If not, we should write
        # the collection to a storage, such that it can be shared with the
        # other strategies.

        update_collection(coll)
        return DLiteResult(collection_id=coll.uuid)


def individual_iri(
    class_iri: str, base_iri: str = ":", randbytes: int = 6
) -> str:
    """Return an IRI for an individual of a class.

    Arguments:
        class_iri: IRI of the class to create an individual of.
        base_iri: Base IRI of the created individual.
        randbytes: Number of random bytes to include in the returned IRI.

    Returns:
        IRI of a new individual.

    """
    basename = (
        class_iri.split(":", 1)[-1]
        .rsplit("/", 1)[-1]
        .rsplit("#", 1)[-1]
        .lower()
    )
    return f"{base_iri}{basename}-{os.urandom(randbytes).hex()}"
