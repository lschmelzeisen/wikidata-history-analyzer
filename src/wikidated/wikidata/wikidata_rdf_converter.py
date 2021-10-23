#
# Copyright 2021 Lukas Schmelzeisen
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

from typing import NamedTuple, Optional, Sequence

from jpype import JClass, JException, JObject  # type: ignore
from marisa_trie import Trie

from wikidated._utils import JvmManager
from wikidated.wikidata.wikidata_dump_pages_meta_history import WikidataRawRevision
from wikidated.wikidata.wikidata_dump_sites_table import WikidataDumpSitesTable
from wikidated.wikidata.wikidata_revision_base import WikidataRevisionBase

# Prefixes taken from
# https://www.mediawiki.org/w/index.php?title=Wikibase/Indexing/RDF_Dump_Format&oldid=4471307#Full_list_of_prefixes
# but sorted so that the longer URLs come first to enable one-pass prefixing.
WIKIDATA_RDF_PREFIXES = {
    "http://creativecommons.org/ns#": "cc",
    "http://purl.org/dc/terms/": "dct",
    "http://schema.org/": "schema",
    "http://wikiba.se/ontology#": "wikibase",
    "http://www.bigdata.com/queryHints#": "hint",
    "http://www.bigdata.com/rdf#": "bd",
    "http://www.opengis.net/ont/geosparql#": "geo",
    "http://www.w3.org/1999/02/22-rdf-syntax-ns#": "rdf",
    "http://www.w3.org/2000/01/rdf-schema#": "rdfs",
    "http://www.w3.org/2001/XMLSchema#": "xsd",
    "http://www.w3.org/2002/07/owl#": "owl",
    "http://www.w3.org/2004/02/skos/core#": "skos",
    "http://www.w3.org/ns/lemon/ontolex#": "ontolex",
    "http://www.w3.org/ns/prov#": "prov",
    "http://www.wikidata.org/entity/": "wd",
    "http://www.wikidata.org/entity/statement/": "wds",
    "http://www.wikidata.org/prop/": "p",
    "http://www.wikidata.org/prop/direct-normalized/": "wdtn",
    "http://www.wikidata.org/prop/direct/": "wdt",
    "http://www.wikidata.org/prop/novalue/": "wdno",
    "http://www.wikidata.org/prop/qualifier/": "pq",
    "http://www.wikidata.org/prop/qualifier/value-normalized/": "pqn",
    "http://www.wikidata.org/prop/qualifier/value/": "pqv",
    "http://www.wikidata.org/prop/reference/": "pr",
    "http://www.wikidata.org/prop/reference/value-normalized/": "prn",
    "http://www.wikidata.org/prop/reference/value/": "prv",
    "http://www.wikidata.org/prop/statement/": "ps",
    "http://www.wikidata.org/prop/statement/value-normalized/": "psn",
    "http://www.wikidata.org/prop/statement/value/": "psv",
    "http://www.wikidata.org/reference/": "wdref",
    "http://www.wikidata.org/value/": "wdv",
    "http://www.wikidata.org/wiki/Special:EntityData/": "wdata",
}
WIKIDATA_RDF_PREFIXES_TRIE = Trie(WIKIDATA_RDF_PREFIXES.keys())


class WikidataRdfTriple(NamedTuple):
    subject: str
    predicate: str
    object_: str

    def __str__(self) -> str:
        return f"{self.subject} {self.predicate} {self.object_} ."

    # We need to reimplement equivalence and hash generation, since WDTK generates blank
    # nodes as something like "_:node1f8mm5pv5x4125", i.e., it gives them an
    # auto-generated ID. There is no way to ensure that the blank node ID for the same
    # triple will be the same if the RDF is regenerated. Luckily, for WDTK's RDF
    # generation, blank nodes only occur in the object position and are never reused.
    # This allows us to treat two triples as equal, if a blank nodes occurs in the
    # object position of both and if subject and predicate are equal to each other.

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, WikidataRdfTriple):
            return False
        if self.object_[:2] == "_:" and other.object_[:2] == "_:":
            return self.subject == other.subject and self.predicate == other.predicate
        else:
            return (
                self.subject == other.subject
                and self.predicate == other.predicate
                and self.object_ == other.object_
            )

    def __hash__(self) -> int:
        if self.object_[:2] == "_:":
            return hash((self.subject, self.predicate, "_:"))
        else:
            return hash((self.subject, self.predicate, self.object_))


class WikidataRdfRevision(WikidataRevisionBase):
    triples: Sequence[WikidataRdfTriple]


class WikidataRdfConversionError(Exception):
    def __init__(
        self,
        reason: str,
        revision: WikidataRawRevision,
        exception: Optional[Exception] = None,
    ):
        self.reason = reason
        self.revision = revision
        self.exception = exception

    def __str__(self) -> str:
        return (
            f"{self.reason} ({self.revision.entity.entity_id}, "
            f"page ID: {self.revision.entity.page_id}, "
            f"revision ID: {self.revision.revision.revision_id})"
        )


class WikidataRdfConverter:
    def __init__(
        self, sites_table: WikidataDumpSitesTable, jvm_manager: JvmManager
    ) -> None:
        self._wdtk_output_stream = JClass("java.io.ByteArrayOutputStream")()
        self._wdtk_rdf_writer = JClass("org.wikidata.wdtk.rdf.RdfWriter")(
            JClass("org.eclipse.rdf4j.rio.RDFFormat").NTRIPLES, self._wdtk_output_stream
        )
        self._wdtk_rdf_writer.start()
        self._wdtk_rdf_converter = JClass("org.wikidata.wdtk.rdf.RdfConverter")(
            self._wdtk_rdf_writer,
            self._load_wdtk_sites(sites_table),
            JClass(
                "org.wikidata.wdtk.rdf.PropertyRegister"
            ).getWikidataPropertyRegister(),
        )
        # Largest Java Integer, i.e., just ones in the binary representation. Used here
        # as the aggregation of all possible flags.
        self._wdtk_rdf_converter.setTasks(2 ** 31 - 1)

        self._wdtk_json_deserializer = JClass(
            "org.wikidata.wdtk.datamodel.helpers.JsonDeserializer"
        )(JClass("org.wikidata.wdtk.datamodel.helpers.Datamodel").SITE_WIKIDATA)
        self._wdtk_item_ri = self._wdtk_rdf_writer.WB_ITEM
        self._wdtk_property_iri = self._wdtk_rdf_writer.WB_PROPERTY
        self._wdtk_same_as_iri = self._wdtk_rdf_writer.getUri(
            "http://www.w3.org/2002/07/owl#sameAs"
        )

    @classmethod
    def _load_wdtk_sites(cls, sites_table: WikidataDumpSitesTable) -> JObject:
        dump = JClass("org.wikidata.wdtk.dumpfiles.MwLocalDumpFile")(
            str(sites_table.path)
        )
        processor = JClass("org.wikidata.wdtk.dumpfiles.MwSitesDumpFileProcessor")()
        processor.processDumpFileContents(dump.getDumpFileStream(), dump)
        return processor.getSites()

    def __call__(
        self, revision: WikidataRawRevision, *, include_schema_triples: bool = False
    ) -> WikidataRdfRevision:
        return self.convert(
            revision=revision, include_schema_triples=include_schema_triples
        )

    def convert(
        self, revision: WikidataRawRevision, *, include_schema_triples: bool = False
    ) -> WikidataRdfRevision:
        # TODO: document that this is basically a mix of RdfSerializer, RdfWriter,
        #  RdfConverter and AbstractRdfConverter.
        # TODO: document that RdfConverter basically only adds the "TASK filtering" on
        #  top of AbstractRdfConverter.

        wdtk_rdf_writer = self._wdtk_rdf_writer
        wdtk_rdf_converter = self._wdtk_rdf_converter

        self._wdtk_output_stream.reset()

        if include_schema_triples:
            wdtk_rdf_converter.writeNamespaceDeclarations()
            wdtk_rdf_converter.writeBasicDeclarations()

        wdtk_document = self._load_wdtk_document(revision)
        wdtk_document_class = str(wdtk_document.getClass().getSimpleName())
        wdtk_resource = wdtk_rdf_writer.getUri(wdtk_document.getEntityId().getIri())

        if wdtk_document_class not in (
            "ItemDocumentImpl",
            "PropertyDocumentImpl",
            "EntityRedirectDocumentImpl",
        ):
            raise WikidataRdfConversionError(
                f"RDF serialization of {wdtk_document_class} not implemented.", revision
            )

        try:
            if wdtk_document_class == "ItemDocumentImpl":
                wdtk_rdf_converter.writeDocumentType(wdtk_resource, self._wdtk_item_ri)
                wdtk_rdf_converter.writeDocumentTerms(wdtk_document)
                wdtk_rdf_converter.writeStatements(wdtk_document)
                wdtk_rdf_converter.writeSiteLinks(
                    wdtk_resource, wdtk_document.getSiteLinks()
                )

            elif wdtk_document_class == "PropertyDocumentImpl":
                wdtk_rdf_converter.writeDocumentType(
                    wdtk_resource, self._wdtk_property_iri
                )
                wdtk_rdf_converter.writePropertyDatatype(wdtk_document)
                wdtk_rdf_converter.writeDocumentTerms(wdtk_document)
                wdtk_rdf_converter.writeStatements(wdtk_document)
                wdtk_rdf_converter.writeInterPropertyLinks(wdtk_document)

            elif wdtk_document_class == "EntityRedirectDocumentImpl":
                # TODO: document that revisions that contain the "redirect" field in
                #  their JSON indicate that the respective entity is being redirected to
                #  the target entity starting from that point in time. Additionally, if
                #  an entity is ever the source of a redirect all revisions of it will
                #  also carry the revision.redirect attribute indicating the target of
                #  the redirect, even if at that time the entity is not yet being
                #  redirect.
                # The following representation of redirects as owl:sameAs triples is not
                # done by WDTK. In fact, WDTK does not represent redirects in RDF at
                # all. We choose to use owl:sameAs here on the basis that the Wikidata
                # Query Service also uses it to represent redirects.
                wdtk_rdf_writer.writeTripleUriObject(
                    wdtk_document.getEntityId().getIri(),
                    self._wdtk_same_as_iri,
                    wdtk_document.getTargetId().getIri(),
                )

        except JException as e:
            raise WikidataRdfConversionError(
                "RDF serialization by Wikidata Toolkit failed.", revision, e
            )

        if include_schema_triples:
            # The RdfConverter.finishDocument() method in Wikidata Toolkit is called
            # from both RdfConverter.writeItemDocument and
            # RdfConverter.writePropertyDocument and exports RDF triples like "this
            # property used above is a complement of this other property". However, this
            # information is not actually stored in the revisions themselves, but rather
            # queried from the internet. Because of this it is also does not change
            # between revisions.
            wdtk_rdf_converter.finishDocument()

        self._wdtk_rdf_writer.finish()

        return WikidataRdfRevision(
            entity=revision.entity,
            revision=revision.revision,
            triples=self._parse_ntriples(str(self._wdtk_output_stream)),
        )

    def _load_wdtk_document(self, revision: WikidataRawRevision) -> JObject:
        if revision.text is None:
            raise WikidataRdfConversionError("Entity has not text.", revision)

        # The following is based on WDTK's WikibaseRevisionProcessor.
        try:
            if '"redirect":' in revision.text:
                return self._wdtk_json_deserializer.deserializeEntityRedirectDocument(
                    revision.text
                )
            elif revision.revision.wikibase_model == "wikibase-item":
                return self._wdtk_json_deserializer.deserializeItemDocument(
                    revision.text
                )
            elif revision.revision.wikibase_model == "wikibase-property":
                return self._wdtk_json_deserializer.deserializePropertyDocument(
                    revision.text
                )
            else:
                raise WikidataRdfConversionError(
                    f"JSON deserialization of {revision.revision.wikibase_model} not "
                    "implemented by Wikidata Toolkit.",
                    revision,
                )
        except JException as e:
            raise WikidataRdfConversionError(
                "JSON deserialization by Wikidata Toolkit failed.", revision, e
            )

    @classmethod
    def _parse_ntriples(cls, ntriples: str) -> Sequence[WikidataRdfTriple]:
        # In rare cases, WDTK will output triples spanning multiple lines. For example,
        # this happens for the item https://www.wikidata.org/w/index.php?oldid=199561928
        # which contains the triple wd:Q34299 wdt:P1705 "Ð¡Ð°Ñ\nÐ° ÑÑÐ»Ð°"@sah .
        return [
            WikidataRdfTriple(
                # .split(" ", 2) split into subject, predicate, and object and ensures
                # spaces in literals are not split.
                *map(cls._prefix_ntriples_uri, triple.split(" ", 2))
            )
            for triple in ntriples.split(" .\n")
            if triple
        ]

    @classmethod
    def _prefix_ntriples_uri(cls, uri: str) -> str:
        if not uri[0] == "<":  # if uri starts with a "<" it also ends with a ">".
            return uri  # Argument is not an URI.

        # uri[1:-1] is the uri without the angel brackets.
        prefix_urls = WIKIDATA_RDF_PREFIXES_TRIE.prefixes(uri[1:-1])
        if prefix_urls:
            prefix_uri = prefix_urls[-1]  # Longest prefix is always at the end.
            prefix = WIKIDATA_RDF_PREFIXES[prefix_uri]
            return prefix + ":" + uri[len(prefix_uri) + 1 : -1]  # [+1:-1] like before.
        return uri
