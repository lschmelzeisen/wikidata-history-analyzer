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

from pathlib import Path

from nasty_utils import LoggingSettings, Settings, SettingsConfig


class WikidataHistoryAnalyzerInternalSettings(Settings):
    num_workers: int
    data_dir: Path
    wikidata_toolkit_jars_dir: Path
    wikidata_dump_version: str
    wikidata_dump_mirror_base: str


class WikidataHistoryAnalyzerSettings(LoggingSettings):
    class Config(SettingsConfig):
        search_path = Path("wikidata-history-analyzer.toml")

    wikidata_history_analyzer: WikidataHistoryAnalyzerInternalSettings
