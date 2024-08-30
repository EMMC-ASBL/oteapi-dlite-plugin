"""Generic generate strategy using DLite storage plugin."""

# pylint: disable=unused-argument,invalid-name,too-many-branches,too-many-locals
import tempfile
from typing import TYPE_CHECKING, Annotated, Optional

from oteapi.datacache import DataCache
from oteapi.models import AttrDict, DataCacheConfig, FunctionConfig
from pydantic import Field
from pydantic.dataclasses import dataclass

from oteapi_dlite.models import DLiteSessionUpdate
from oteapi_dlite.utils import (
    get_collection,
    get_driver,
    get_settings,
    update_collection,
)

if TYPE_CHECKING:  # pragma: no cover
    from typing import Any


# Constants
hasInput = "https://w3id.org/emmo#EMMO_36e69413_8c59_4799_946c_10b05d266e22"


class KBError(ValueError):
    """Invalud data in knowledge base."""


class DLiteStorageConfig(AttrDict):
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
    store_collection: Annotated[
        bool,
        Field(
            description="Whether to store the entire collection in the session "
            "instead of a single instance.  Cannot be combined with `label` or "
            "`datamodel`.",
        ),
    ] = False
    store_collection_id: Annotated[
        Optional[str],
        Field(
            description="Used together with `store_collection` If given, store "
            "a copy of the collection with this id.",
        ),
    ] = None
    allow_incomplete: Annotated[
        Optional[bool],
        Field(
            description="Whether to allow incomplete property mappings.",
        ),
    ] = False
    collection_id: Annotated[
        Optional[str],
        Field(
            description=("ID of the collection to use."),
        ),
    ] = None
    datacache_config: Annotated[
        Optional[DataCacheConfig],
        Field(
            description="Configuration options for the local data cache.",
        ),
    ] = None
    kb_document_iri: Annotated[
        Optional[str],
        Field(
            description=(
                "If given, document the generated instance in the knowledge "
                "base using as an individual with this IRI."
                "\n\n"
                "Expects that a 'tripper.triplestore' settings has been "
                "added. This settings should be a dict that can be passed "
                "as keyword arguments to `tripper.Triplestore()`."
            ),
        ),
    ] = None
    kb_document_context: Annotated[
        Optional[dict],
        Field(
            description=(
                "If `kb_document_iri` is given, this configuration adds "
                "will add additional context to the documentation of the "
                "generated instance."
                "\n\n"
                "This configuration should be a dict mapping providing the "
                "additional documentation of the driver. It should map OWL "
                "properties to either tripper literals or IRIs."
            ),
        ),
    ] = None
    kb_document_computation: Annotated[
        Optional[str],
        Field(
            description=(
                "If `kb_document_iri` is given, this configuration adds "
                "will document what computation that created the current "
                "output instance and what input instances that went into the "
                "computation."
                "\n\n"
                "The value should be the IRI of a computation class."
                "\n\n"
                "Note: It is assumed that there exists only one instance of "
                "the data models for the input to the computation."
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

    generate_config: DLiteGenerateConfig

    def initialize(
        self,
        session: Optional[dict[str, "Any"]] = None,
    ) -> DLiteSessionUpdate:
        """Initialize."""
        return DLiteSessionUpdate(collection_id=get_collection(session).uuid)

    def get(
        self, session: Optional[dict[str, "Any"]] = None
    ) -> DLiteSessionUpdate:
        """Execute the strategy.

        This method will be called through the strategy-specific endpoint
        of the OTE-API Services.

        Parameters:
            session: A session-specific dictionary context.

        Returns:
            SessionUpdate instance.
        """
        config = self.generate_config.configuration
        cacheconfig = config.datacache_config

        driver = (
            config.driver
            if config.driver
            else get_driver(mediaType=config.mediaType)
        )

        coll = get_collection(session, config.collection_id)

        if config.label:
            inst = coll[config.label]
        elif config.datamodel:
            instances = coll.get_instances(
                metaid=config.datamodel,
                property_mappings=True,
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
                inst.save(driver, "{tmpdir}/data", config.options)
                with open(f"{tmpdir}/data", "rb") as f:
                    cache.add(f.read(), key=key)

        # Store documentation of this instance in the knowledge base
        if config.kb_document_iri:
            kb_settings = get_settings(session, "tripper.triplestore")
            if not kb_settings:
                raise KeyError(
                    "The `kb_document_iri` configuration requires that a "
                    "'tripper.triplestore' settings has been added using the "
                    "application/vnd.dlite-settings strategy."
                )

            # Import here to avoid hard dependencies on tripper.
            # pylint: disable=import-outside-toplevel
            from tripper import Triplestore
            from tripper.convert import save_container

            resource = {
                "dataresource": {
                    "downloadUrl": config.location,
                    "mediaType": (
                        config.mediaType
                        if config.mediaType
                        else "application/vnd.dlite-parse"
                    ),
                    "configuration": {
                        "metadata": (
                            config.datamodel
                            if config.datamodel
                            else inst.meta.uri
                        ),
                        "driver": config.driver,
                        "options": config.options,
                    },
                }
            }

            ts = Triplestore(**kb_settings)
            try:
                save_container(
                    ts,
                    resource,
                    config.kb_document_iri,
                    recognised_keys="basic",
                )

                if config.kb_document_context:
                    for prop, val in config.kb_document_context.items():
                        ts.add((config.kb_document_iri, prop, val))

                if config.kb_document_computation:
                    restrictions = ts.restrictions(
                        config.kb_document_computation, hasInput
                    )
                    for r in restrictions:
                        indv = inputs.append(r["value"])
                        d = load_container(ts, indv, recognised_keys="basic")
                        metaid = (
                            d.get("dataresource", {})
                            .get("configuration", {})
                            .get("metadata")
                        )
                        if not metaid:
                            raise KBError(
                                f"expected that individual '{indv}' is "
                                "documented as an OTEAPI dataresource with "
                                "of explicit metadata"
                            )

            finally:
                ts.close()

        # __TODO__
        # Can we safely assume that all strategies in a pipeline will be
        # executed in the same Python interpreter?  If not, we should write
        # the collection to a storage, such that it can be shared with the
        # other strategies.

        update_collection(coll)
        return DLiteSessionUpdate(collection_id=coll.uuid)
