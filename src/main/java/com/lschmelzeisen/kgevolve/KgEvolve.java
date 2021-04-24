/*
 * Copyright 2021 Lukas Schmelzeisen
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *    http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

package com.lschmelzeisen.kgevolve;

import examples.ExampleHelpers;
import java.io.IOException;
import java.nio.file.Path;
import java.nio.file.Paths;
import org.wikidata.wdtk.datamodel.helpers.Datamodel;
import org.wikidata.wdtk.datamodel.interfaces.EntityDocumentProcessorBroker;
import org.wikidata.wdtk.datamodel.interfaces.Sites;
import org.wikidata.wdtk.dumpfiles.EntityTimerProcessor;
import org.wikidata.wdtk.dumpfiles.MwLocalDumpFile;
import org.wikidata.wdtk.dumpfiles.MwSitesDumpFileProcessor;
import org.wikidata.wdtk.rdf.PropertyRegister;

public class KgEvolve {
    public static void main(String[] args) throws IOException, InterruptedException {
        ExampleHelpers.configureLogging();

        Path fullDumpFilesDirectory = Paths.get("dumpfiles/wikidatawiki/full-20210401");
        Path dumpFile =
                fullDumpFilesDirectory.resolve(
                        // "wikidatawiki-20210401-pages-meta-history1.xml-p1p192.7z");
                        "wikidatawiki-20210401-pages-meta-history25.xml-p67174382p67502430.7z");

        MwLocalDumpFile sitesTableDump =
                new MwLocalDumpFile(
                        "dumpfiles/wikidatawiki/sites-20210401/wikidatawiki-20210401-sites.sql.gz");
        MwSitesDumpFileProcessor sitesDumpFileProcessor = new MwSitesDumpFileProcessor();
        sitesDumpFileProcessor.processDumpFileContents(
                sitesTableDump.getDumpFileStream(), sitesTableDump);
        Sites sites = sitesDumpFileProcessor.getSites();

        var entityTimerProcessor = new EntityTimerProcessor(0);

        var rdfSerializer =
                new MyRdfSerializer(
                        Paths.get("triples-ALL_ENTITIES_ALL_EXACT_DATA.ttl"),
                        sites,
                        PropertyRegister.getWikidataPropertyRegister(),
                        Datamodel.SITE_WIKIDATA);

        var entityDocumentProcessor = new EntityDocumentProcessorBroker();
        entityDocumentProcessor.registerEntityDocumentProcessor(entityTimerProcessor);
        //        entityDocumentProcessor.registerEntityDocumentProcessor(rdfSerializer);

        var dumpProcessor = new FastRevisionDumpFileProcessor(rdfSerializer);
        //                        entityTimerProcessor);
        //                                new WikibaseRevisionProcessor(
        //                                entityDocumentProcessor, "http://www.wikidata.org/"));

        entityTimerProcessor.open();
        dumpProcessor.processDumpFile(dumpFile);
        entityTimerProcessor.close();
    }
}
