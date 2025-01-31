"""Tests storing documentation of instance with the generate strategy."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..conftest import PathsTuple


def test_generate_kb(paths: PathsTuple) -> None:
    """Test generate with kb documentation enabled."""
    import ssl

    import dlite
    from otelib import OTEClient
    from tripper import OWL, RDF, RDFS, Namespace, Triplestore
    from tripper.convert import load_container, save_container

    from oteapi_dlite.utils import get_meta

    # Disable SSL certificate verification
    ssl._create_default_https_context = ssl._create_unverified_context
    # For some reason creating the Namespace below causes this failure
    # but only in this repository...

    EMMO = Namespace(
        iri="https://w3id.org/emmo#",
        label_annotations=True,
        check=True,
    )

    # Prepare the knowledge base
    kb = paths.outputdir / "kb.ttl"
    ts = Triplestore(backend="rdflib")
    ts.bind("", "http://myproj.org/kb#")
    ts.add_triples(
        [
            (":Sim", RDF.type, OWL.Class),
            (":Sim", RDFS.subClassOf, EMMO.Computation),
            (":input1", RDF.type, ":Input1"),
            (":input2", RDF.type, ":Input2"),
        ]
    )
    ts.add_restriction(":Sim", EMMO.hasInput, ":Input1", "exactly", 1)
    ts.add_restriction(":Sim", EMMO.hasInput, ":Input2", "exactly", 1)
    ts.add_restriction(":Sim", EMMO.hasOutput, ":Output", "exactly", 1)
    input1 = {
        "dataresource": {
            "type": ":Input1",
            "downloadUrl": "file1.json",
            "mediaType": "application/vnd.dlite-parse",
            "configuration": {
                "metadata": "http://onto-ns.com/meta/ex/0.1/Input1",
                "driver": "json",
            },
        },
    }
    input2 = {
        "dataresource": {
            "type": ":Input2",
            "downloadUrl": "file2.yaml",
            "mediaType": "application/vnd.dlite-parse",
            "configuration": {
                "metadata": "http://onto-ns.com/meta/ex/0.1/Input2",
                "driver": "yaml",
            },
        },
    }
    save_container(ts, input1, ":input1", recognised_keys="basic")
    save_container(ts, input2, ":input2", recognised_keys="basic")
    ts.serialize(kb)
    ts.close()

    # Prepare data
    Image = get_meta("http://onto-ns.com/meta/1.0/Image")
    image = Image([2, 2, 1])
    image.data = [[[1], [2]], [[3], [4]]]
    image.save("yaml", paths.outputdir / "image.yaml", "mode=w")

    # Prepare pipeline
    kb_kwargs = {"backend": "rdflib", "triplestore_url": str(kb)}

    client = OTEClient("python")

    resource = client.create_dataresource(
        resourceType="resource/url",
        downloadUrl=(paths.outputdir / "image.yaml").as_uri(),
        mediaType="application/yaml",
    )
    parse = client.create_parser(
        parserType="application/vnd.dlite-parse",
        entity="http://example.org",
        configuration={
            "driver": "yaml",
            "options": "mode=r",
        },
    )
    generate = client.create_function(
        functionType="application/vnd.dlite-generate",
        configuration={
            "datamodel": Image.uri,
            "driver": "json",
            "location": str(paths.outputdir / "image.json"),
            "options": "mode=w",
            "kb_document_class": ":MyData",
            "kb_document_update": {"dataresource": {"license": "MIT"}},
            "kb_document_base_iri": "http://ex.com#",
            # EMMO.isDescriptionFor is part of the release candate 3 in EMMO,
            # and is therefore not yet resolvable.
            # "kb_document_context": {EMMO.isDescriptionFor: ":MyMaterial"},
            "kb_document_computation": ":Sim",
        },
    )
    settings = client.create_filter(
        filterType="application/vnd.dlite-settings",
        configuration={
            "label": "tripper.triplestore",
            "settings": kb_kwargs,
        },
    )

    # Execute pipeline...
    pipeline = resource >> parse >> generate >> settings
    pipeline.get()

    # Check that the data in the newly created generated json file matches our
    # image instance.
    # Fefore loading the generated file, we delete the original image instance
    # to ensure that we are not just fetching it from the dlite cache...
    image_dict = image.asdict()
    del image
    image2 = dlite.Instance.from_location(
        "json", paths.outputdir / "image.json", "mode=r"
    )
    assert image2.asdict() == image_dict

    # Check data documentation in KB
    ts = Triplestore(**kb_kwargs)

    # Get IRI of the created data individual
    iri = ts.value(predicate=RDF.type, object=":MyData")
    assert iri.startswith("http://ex.com#mydata-")

    doc = load_container(
        ts, iri, recognised_keys="basic", ignore_unrecognised=True
    )
    assert doc == {
        "dataresource": {
            "type": ":MyData",
            "downloadUrl": str(paths.outputdir / "image.json"),
            "mediaType": "application/yaml",
            "license": "MIT",
            "configuration": {
                "driver": "json",
                "options": "mode=r",
                "datamodel": "http://onto-ns.com/meta/1.0/Image",
            },
        },
        # "parse": {}
        "mapping": {
            "mappingType": "mappings",
            # "prefixes": {},
            # "triples": [],
        },
    }

    # Check kb_document_class
    assert ts.has(iri, RDF.type, ":MyData")

    # EMMO.isDescriptionFor is part of the release candate 3 in EMMO,
    # and is therefore not yet resolvable.
    # # Check kb_document_context
    # assert ts.has(iri, EMMO.isDescriptionFor, ":MyMaterial")

    # Check: kb_document_computation
    sim = ts.value(predicate=RDF.type, object=":Sim")
    assert sim.startswith("http://ex.com#sim-")
    assert ts.has(sim, EMMO.hasInput, ":input1")
    assert ts.has(sim, EMMO.hasInput, ":input2")
    assert ts.has(sim, EMMO.hasOutput, iri)
