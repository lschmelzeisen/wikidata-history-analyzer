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


from logging import getLogger
from pathlib import Path
from sys import argv
from typing import Counter, Sequence, cast

from jpype import shutdownJVM, startJVM  # type: ignore
from nasty_utils import Argument, ColoredBraceStyleAdapter, Program, ProgramConfig
from overrides import overrides
from pydantic import validator

import wikidata_history_analyzer
from wikidata_history_analyzer._paths import get_wikidata_dump_dir, get_wikidata_rdf_dir
from wikidata_history_analyzer.java_logging_bride import setup_java_logging_bridge
from wikidata_history_analyzer.settings_ import WikidataHistoryAnalyzerSettings
from wikidata_history_analyzer.wikidata_dump_manager import WikidataDumpManager
from wikidata_history_analyzer.wikidata_rdf_serializer import (
    WikidataRdfSerializationException,
    WikidataRdfSerializer,
)

_LOGGER = ColoredBraceStyleAdapter(getLogger(__name__))


class WikidataExtractRdf(Program):
    class Config(ProgramConfig):
        title = "wikidata-extract-rdf"
        version = wikidata_history_analyzer.__version__
        description = "Extract RDF statements about specific pages/revisions."

    settings: WikidataHistoryAnalyzerSettings = Argument(
        alias="config", description="Overwrite default config file path."
    )

    dump_file: Path = Argument(
        short_alias="f", alias="dump-file", description="The dump file to search."
    )

    title_: Sequence[str] = Argument(
        (),
        short_alias="t",
        alias="title",
        description="Target title (prefixed, separate multiple with commas).",
    )
    page_id: Sequence[str] = Argument(
        (),
        short_alias="p",
        alias="page-id",
        description="Target page ID (separate multiple with commas).",
    )
    revision_id: Sequence[str] = Argument(
        (),
        short_alias="r",
        alias="revision-id",
        description="Target revision ID (separate multiple with commas).",
    )

    @classmethod
    @validator("title_", "page_id", "revision_id", pre=True)
    def _split_at_comma(cls, value: object) -> Sequence[str]:
        return (
            value.split(",") if isinstance(value, str) else cast(Sequence[str], value)
        )

    @overrides
    def run(self) -> None:
        settings = self.settings.wikidata_history_analyzer

        dump_manager = WikidataDumpManager(
            settings.data_dir,
            settings.wikidata_dump_version,
            settings.wikidata_dump_mirror_base,
        )
        dump = None
        for meta_history_7z_dump in dump_manager.meta_history_7z_dumps():
            if meta_history_7z_dump.path.name == self.dump_file.name:
                dump = meta_history_7z_dump
                break
        assert dump is not None

        dump_dir = get_wikidata_dump_dir(settings.data_dir)
        rdf_dir = get_wikidata_rdf_dir(settings.data_dir)

        startJVM(classpath=[str(settings.wikidata_toolkit_jars_dir / "*")])
        setup_java_logging_bridge()

        rdf_serializer = WikidataRdfSerializer(
            dump_dir / f"wikidatawiki-{settings.wikidata_dump_version}-sites.sql.gz"
        )
        rdf_serializer_exception_counter = Counter[str]()

        for revision in dump.iter_revisions():
            if not (
                revision.prefixed_title in self.title_
                or revision.page_id in self.page_id
                or revision.revision_id in self.revision_id
            ):
                continue

            try:
                triples = rdf_serializer.process_revision(revision)
            except WikidataRdfSerializationException as exception:
                rdf_serializer_exception_counter[exception.reason] += 1
                continue

            revision_file = (
                rdf_dir
                / self.dump_file
                / revision.prefixed_title
                / (revision.revision_id + ".ttl")
            )
            revision_file.parent.mkdir(exist_ok=True, parents=True)
            with revision_file.open("w", encoding="UTF-8") as fout:
                for attr in dir(revision):
                    if attr.startswith("_") or attr == "text":
                        continue
                    fout.write(f"# {attr}: {getattr(revision, attr)}\n")
                fout.write("\n")
                for triple in triples:
                    fout.write(" ".join(triple) + " .\n")

        shutdownJVM()


def main(*args: str) -> None:
    if not args:
        args = tuple(argv[1:])
    WikidataExtractRdf.init(*args).run()


if __name__ == "__main__":
    main()