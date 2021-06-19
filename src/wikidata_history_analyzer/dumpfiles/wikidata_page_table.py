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

import gzip
import re
from datetime import datetime
from typing import Iterator, Mapping

from wikidata_history_analyzer.datamodel.wikidata_page_meta import WikidataPageMeta
from wikidata_history_analyzer.dumpfiles.wikidata_dump import WikidataDump

_PATTERN = re.compile(
    r"""
        \(
            (?P<page_id>\d+),
            (?P<namespace>\d+),
            '(?P<title>[^']+)',
            '(?P<restrictions>[^']*)',
            (?P<is_redirect>\d+),
            (?P<is_new>\d+),
            (?P<random>\d.\d+),
            '(?P<touched>\d+)',
            '(?P<links_updated>\d+)',
            (?P<latest_revision_id>\d+),
            (?P<len>\d+),
            '(?P<content_model>[^']*)',
            '?(?P<lang>[^')]*)'?
        \)
    """,
    re.VERBOSE,
)


class WikidataPageTable(WikidataDump):
    def iter_pages(
        self, namespace_titles: Mapping[int, str]
    ) -> Iterator[WikidataPageMeta]:
        assert self.path.exists()

        insert_line_start = "INSERT INTO `page` VALUES "
        insert_line_end = ";\n"

        with gzip.open(self.path, "rt", encoding="UTF-8") as fin:
            for line in fin:
                if not (
                    line.startswith(insert_line_start)
                    and line.endswith(insert_line_end)
                ):
                    continue

                line = line[len(insert_line_start) : -len(insert_line_end)]
                for match in _PATTERN.finditer(line):
                    namespace = int(match["namespace"])
                    title = match["title"]

                    yield WikidataPageMeta.construct(
                        namespace=namespace,
                        title=title,
                        prefixed_title=(
                            namespace_titles[namespace] + ":" + title
                            if namespace_titles[namespace]
                            else title
                        ),
                        page_id=match["page_id"],
                        restrictions=match["restrictions"],
                        is_redirect=int(match["is_redirect"]),
                        is_new=int(match["is_new"]),
                        random=float(match["random"]),
                        touched=datetime.strptime(match["touched"], "%Y%m%d%H%M%S"),
                        links_updated=datetime.strptime(
                            match["links_updated"], "%Y%m%d%H%M%S"
                        ),
                        latest_revision_id=match["latest_revision_id"],
                        len=int(match["len"]),
                        content_model=match["content_model"],
                        lang=match["lang"],
                    )