"""Generic function strategy that converts zero or more input instances
to zero or more new output instances.

"""

from __future__ import annotations

import importlib
from collections.abc import Sequence
from typing import Annotated, Optional

import dlite
from oteapi.models import AttrDict, FunctionConfig
from pydantic import Field
from pydantic.dataclasses import dataclass

from oteapi_dlite.models import DLiteResult
from oteapi_dlite.utils import get_collection, update_collection


class DLiteConvertInputConfig(AttrDict):
    """Configuration for input instance to generic DLite converter.

    At least one of `label` or `datamodel` should be given.
    """

    label: Annotated[
        Optional[str],
        Field(
            description="Label of the instance.",
        ),
    ] = None
    datamodel: Annotated[
        Optional[str],
        Field(
            description="URI of data model.",
        ),
    ] = None
    property_mappings: Annotated[
        bool,
        Field(
            description="Whether to infer instance from property mappings.",
        ),
    ] = False


class DLiteConvertOutputConfig(AttrDict):
    """Configuration for output instance to generic DLite converter."""

    label: Annotated[
        Optional[str],
        Field(
            description="Label to use when storing the instance.",
        ),
    ] = None
    datamodel: Annotated[
        Optional[str],
        Field(
            description="URI of data model.  Used for documentation.",
        ),
    ] = None


class DLiteConvertStrategyConfig(DLiteResult):
    """Configuration for generic DLite converter."""

    function_name: Annotated[
        str,
        Field(
            description="Name of convert function.  It will be pased the input "
            "instances as arguments and should return a sequence of output "
            "instances.",
        ),
    ]
    module_name: Annotated[
        str,
        Field(
            description=(
                "Name of Python module containing the convertion function."
            ),
        ),
    ]
    package: Annotated[
        Optional[str],
        Field(
            description=(
                "Used when performing a relative import of the converter "
                "function.  It specifies the package to use as the anchor "
                "point from which to resolve the relative import to an absolute"
                " import."
            ),
        ),
    ] = None
    pypi_package: Annotated[
        Optional[str],
        Field(
            description=(
                "Package name on PyPI.  This field is currently only "
                "informative, but might be used in the future for automatic "
                "package installation."
            ),
        ),
    ] = None
    inputs: Annotated[
        Sequence[DLiteConvertInputConfig],
        Field(
            description="Input instances.",
        ),
    ] = []
    outputs: Annotated[
        Sequence[DLiteConvertOutputConfig],
        Field(
            description="Output instances.",
        ),
    ] = []
    kwargs: Annotated[
        Optional[dict],
        Field(
            description="Additional keyword arguments passed "
            "to the convert function.",
        ),
    ] = {}  # noqa: RUF012


class DLiteConvertConfig(FunctionConfig):
    """DLite convert strategy resource config."""

    configuration: Annotated[
        DLiteConvertStrategyConfig,
        Field(description="DLite convert strategy-specific configuration."),
    ]


@dataclass
class DLiteConvertStrategy:
    """Generic DLite convert strategy for converting zero or more input
    instances to zero or more output instances.

    **Registers strategies**:

    - `("functionType", "application/vnd.dlite-convert")`

    """

    function_config: DLiteConvertConfig

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
        module = importlib.import_module(config.module_name, config.package)
        function = getattr(module, config.function_name)
        kwargs = config.kwargs

        coll = get_collection(config.collection_id)

        instances = []
        for i, input_config in enumerate(config.inputs):
            if input_config.label:
                instances.append(
                    coll.get(input_config.label, input_config.datamodel)
                )
            elif input_config.datamodel:
                inst = coll.get_instances(
                    metaid=input_config.datamodel,
                    property_mappings=input_config.property_mappings,
                    # More to do: add more arguments...
                )
                instances.append(inst)
            else:
                raise ValueError(
                    "either `label` or `datamodel` must be specified in "
                    f"inputs[{i}]"
                )
        outputs = function(*instances, **kwargs)
        if isinstance(outputs, dlite.Instance):
            outputs = [outputs]

        for inst, output_config in zip(outputs, config.outputs):
            coll.add(output_config.label, inst)
            inst._incref()

        update_collection(coll)
        return DLiteResult(collection_id=coll.uuid)
