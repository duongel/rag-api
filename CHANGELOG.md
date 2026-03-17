# [1.9.0](https://github.com/duongel/rag-api/compare/v1.8.2...v1.9.0) (2026-03-17)


### Bug Fixes

* correct version to match latest release v1.8.2 ([7757a16](https://github.com/duongel/rag-api/commit/7757a16b65e25da6c603505c1a5ff2f5c41981f8))
* record cleanup paths after document detail resolution ([de8d9f8](https://github.com/duongel/rag-api/commit/de8d9f82cb5dc941fe8658898b4aaa95f0f5d3fc))
* thread-safety bugs in concurrent Paperless indexing ([4b70723](https://github.com/duongel/rag-api/commit/4b707231ba01d8262a51bfae73bb6688a1dacc43))
* version fallback in start.sh when pyproject.toml is missing ([0aff0b3](https://github.com/duongel/rag-api/commit/0aff0b36810c7129ff20b1e46ed586a5bc8b7ae5))


### Features

* display current version in start.sh banner ([dc5e6f5](https://github.com/duongel/rag-api/commit/dc5e6f550cd70c3f28731305ce478481837c3e62))


### Performance Improvements

* concurrent Paperless indexing with ThreadPoolExecutor ([1018958](https://github.com/duongel/rag-api/commit/10189582dcb31a852cc3f51d01849938e0e3c1e4))

## [1.8.2](https://github.com/duongel/rag-api/compare/v1.8.1...v1.8.2) (2026-03-17)


### Bug Fixes

* install into current directory instead of fixed ~/rag-api ([3b3b8f6](https://github.com/duongel/rag-api/commit/3b3b8f6110fef966ff94f98ca9073a94658718e9))

## [1.8.1](https://github.com/duongel/rag-api/compare/v1.8.0...v1.8.1) (2026-03-17)


### Performance Improvements

* prefetch all tags and correspondents before Paperless reindex ([feee539](https://github.com/duongel/rag-api/commit/feee53935555fdb7b27d7d2ee721c7f568f2ce02))

# [1.8.0](https://github.com/duongel/rag-api/compare/v1.7.2...v1.8.0) (2026-03-17)


### Bug Fixes

* address PR review comments - dead code, type hints, tag cache TTL ([33e04b7](https://github.com/duongel/rag-api/commit/33e04b7cfc29a7b01c2f8c2f9b2dc8efeb1924cf))
* address PR review comments (fail-closed, pagination, filter enforcement, cache refresh) ([8b1eaf6](https://github.com/duongel/rag-api/commit/8b1eaf6badd0dc7ab4039e39e5d8a6676b7bfe6f))
* include tag_names in Paperless change detection hash ([ffe0c47](https://github.com/duongel/rag-api/commit/ffe0c474104154ecef8e821ae01c6c0b722aa158))
* **indexing:** avoid permanent cache on failed tag lookups ([67c9def](https://github.com/duongel/rag-api/commit/67c9defc14703e6618df47872f400393944ebde8))
* **indexing:** enrich paperless API chunks with metadata text ([86ed214](https://github.com/duongel/rag-api/commit/86ed214c12984f7bcf001c9d2a1606066427a498))
* **indexing:** reindex paperless docs on metadata-only updates ([fcc07ad](https://github.com/duongel/rag-api/commit/fcc07ad803c2c18429fd02488bef3e7fc4e372cb))
* keyword_search respects Paperless filter, handle multi-tag intersection ([a3cca3e](https://github.com/duongel/rag-api/commit/a3cca3e884be197dde24a0891dc98fb37864c737))
* resolve Paperless tag IDs to names in index_paperless_doc ([50c49a1](https://github.com/duongel/rag-api/commit/50c49a159d4fbdb7eb243d40b013796b2cf6940c))
* resolve test isolation failures (env-var ordering, status name shadowing, sys.modules stubs) ([1bdabf0](https://github.com/duongel/rag-api/commit/1bdabf0993ca2a51e585e2e1f321b64cd822638b))
* revert config.py PUBLIC_URL default to localhost, handle both in api.py ([681f0a3](https://github.com/duongel/rag-api/commit/681f0a379187c8092a03567d3cfdaff14beb99ef))
* **search:** preserve filename matches and substring paperless filters ([f20d0a5](https://github.com/duongel/rag-api/commit/f20d0a58f9fd100be6a9ac9552d3a2071f213291))
* separate correspondent display name from filter field, remove dead code, add filter tests ([a9105c1](https://github.com/duongel/rag-api/commit/a9105c1423ff31c6fa02b0daf7e6074b0c6d2dc9))


### Features

* boost tag weight in Paperless chunk embeddings ([8553a1a](https://github.com/duongel/rag-api/commit/8553a1aaf0d74191f62727f3c31bcecd755eb7c4))
* increase tag repetition to 5x for stronger embedding weight ([1ea99e5](https://github.com/duongel/rag-api/commit/1ea99e55ee4b8a4db28ddd7d96947b1912a8f788))
* **indexing:** include Paperless tags in indexed document content ([2624c09](https://github.com/duongel/rag-api/commit/2624c097a9d0eef1eb098a9083870ea08674b742))
* new api to filter, improved search results ([36b091a](https://github.com/duongel/rag-api/commit/36b091a516d30e527de7c20e40790aa769e70ddf))
* Paperless pre-filter for search (tags, correspondent, year) ([830fa92](https://github.com/duongel/rag-api/commit/830fa92cba312822112158501aa16574f96a0068))


### Performance Improvements

* batch-fetch Paperless tag names to avoid N+1 API calls ([61c7e52](https://github.com/duongel/rag-api/commit/61c7e521bb77c121ce133f94f893aa7b97cff497))

## [1.7.2](https://github.com/duongel/rag-api/compare/v1.7.1...v1.7.2) (2026-03-16)


### Bug Fixes

* get_note returns Paperless docs from ChromaDB index ([4bd2218](https://github.com/duongel/rag-api/commit/4bd2218d7367ad40fb218919e2e7efed9c5dae7e))

## [1.7.1](https://github.com/duongel/rag-api/compare/v1.7.0...v1.7.1) (2026-03-16)


### Bug Fixes

* prompt for routable PUBLIC_URL in network mode ([e70663c](https://github.com/duongel/rag-api/commit/e70663c72812b462d0d4d59be448f71c97dfb594))
* show domain example in PUBLIC_URL prompt ([021f314](https://github.com/duongel/rag-api/commit/021f314163d2de447dd940320f17f6b088f7f6a6))

# [1.7.0](https://github.com/duongel/rag-api/compare/v1.6.1...v1.7.0) (2026-03-16)


### Bug Fixes

* address 2 unresolved PR review comments ([f2f05f4](https://github.com/duongel/rag-api/commit/f2f05f41d7ae86ddff7d9a7523754c18ff8b4561))
* address 2 unresolved PR review comments ([5f0b234](https://github.com/duongel/rag-api/commit/5f0b2349d19cec3ddf4300fe3ddd12e0f33bd840))
* address 3 unresolved PR review comments ([d73b9df](https://github.com/duongel/rag-api/commit/d73b9df5c34676b8098886a17a06fbf243b8c6d7))
* address unresolved PR review comments ([ad26cb5](https://github.com/duongel/rag-api/commit/ad26cb5f5c55c452cdb75a9c52098661e62b4087))
* always use Docker service name for webhook callback URL ([1ebf99d](https://github.com/duongel/rag-api/commit/1ebf99dc87f6ccaca66664b05f0655e5a195246d))
* check PAPERLESS_TOKEN in .env reuse, clear stale index on empty content ([7989283](https://github.com/duongel/rag-api/commit/79892837f20124394eb5ff691f47c143062c811d))
* ensure full reindex gets content and handle path changes ([48293d7](https://github.com/duongel/rag-api/commit/48293d7d45a0654adb17390c1b3a66085969cb9a))
* guard cleanup on partial fetch and require auth for webhook ([95c1e2f](https://github.com/duongel/rag-api/commit/95c1e2f02b393de557dc767d490d3c176fb22e8c))
* guard empty-content removal and skip disabled workflows ([681a400](https://github.com/duongel/rag-api/commit/681a4003c1fefc4a62b837b10b340e249d4d7b67))
* handle empty Paperless instance cleanup and paginate workflow lookup ([0dbefe7](https://github.com/duongel/rag-api/commit/0dbefe70e79ff5bd357dfd15de7b5a871311f640))
* include bearer token in Paperless webhook registration ([a937edb](https://github.com/duongel/rag-api/commit/a937edbcd05f101b84668876b1032509764623ec))
* **main:** remove non-existent document_removed webhook trigger ([1f846bb](https://github.com/duongel/rag-api/commit/1f846bb11b85a7546b7bfb6ec3839cb0ec6fbe55))
* make webhook auth conditional on AUTH_REQUIRED ([f906fb2](https://github.com/duongel/rag-api/commit/f906fb2c99d73a391099e616312046f5e9dd3be1))
* propagate webhook failures and fix header update race ([14241e6](https://github.com/duongel/rag-api/commit/14241e645ab9513a1495619eecf3cb51d3d15f56))
* reconcile webhook headers on token change, clarify action semantics ([3512479](https://github.com/duongel/rag-api/commit/3512479274aedbf37e71aa06281fe841ab07342f))
* register removal webhook and clean all doc paths on empty content ([8ceaade](https://github.com/duongel/rag-api/commit/8ceaadebe9572d8eb7803a772b8d4180abebbb9a))
* robust webhook URL handling for network access mode ([ed04f40](https://github.com/duongel/rag-api/commit/ed04f40c7bee26830008b98a80e262173b82a7eb))
* **start:** write RAG_API_INTERNAL_URL to .env during setup ([3665ee5](https://github.com/duongel/rag-api/commit/3665ee59d8907935bd046db156c30361d9352f00))
* use relative path for logo ([ad4e3b9](https://github.com/duongel/rag-api/commit/ad4e3b9bd98c2c2f2d7804cb44919d9b461f17fa))


### Features

* add network access mode for cross-machine deployments ([8daf276](https://github.com/duongel/rag-api/commit/8daf2765662a9f464ba4004f1b0d1781e1b6d160))
* API-driven Paperless indexing with webhook support ([b36a0a4](https://github.com/duongel/rag-api/commit/b36a0a435396ec29774cf8147c83e8dd9545144c))


### Reverts

* remove auth from webhook endpoint ([c569237](https://github.com/duongel/rag-api/commit/c56923721809caf9920cbd35416fb70eb521cec2))

## [1.6.1](https://github.com/duongel/rag-api/compare/v1.6.0...v1.6.1) (2026-03-16)


### Bug Fixes

* compare full archive_filename path to avoid subdirectory collisions ([a564143](https://github.com/duongel/rag-api/commit/a564143596974d41e87b1ce91e94fced41fdcf02))
* only use basename fallback when unambiguous (single match) ([d909ac1](https://github.com/duongel/rag-api/commit/d909ac147fc47c3095d3f572f6fc4c1b0da766e1))
* paginate Paperless lookup and restrict basename fallback ([092cd0e](https://github.com/duongel/rag-api/commit/092cd0e00b81dfc585b7dbb84f97dddc87305404))
* pass paperless_doc_id through search results ([ec21bf9](https://github.com/duongel/rag-api/commit/ec21bf9ad6c636b9e6391c08181193933ea2ab9a))
* remove _MAX_PAGES cap, paginate until no next page ([8fddfd2](https://github.com/duongel/rag-api/commit/8fddfd2350e38135b6350ede6ba917d0ab3f7ee0))
* resolve Paperless doc ID for non-numeric filenames ([2e45aab](https://github.com/duongel/rag-api/commit/2e45aab6f0e083baf09067f7ea01e146df676a63))
* use paperless_doc_id from metadata in _enrich_source_url ([04733da](https://github.com/duongel/rag-api/commit/04733daee3ec3982a951b310c4fcf165884e7679))
* verify exact archive_filename match in Paperless lookup ([12a73d9](https://github.com/duongel/rag-api/commit/12a73d9754c351b71ff8963842c4311a33d2f121))

# [1.6.0](https://github.com/duongel/rag-api/compare/v1.5.0...v1.6.0) (2026-03-16)


### Features

* add POST /note endpoint for n8n compatibility ([4de0676](https://github.com/duongel/rag-api/commit/4de0676ca5cfd194853fa22112b3c3bccca1243f))

# [1.5.0](https://github.com/duongel/rag-api/compare/v1.4.3...v1.5.0) (2026-03-16)


### Features

* improve keyword search with relevance-based scoring ([cea6b9c](https://github.com/duongel/rag-api/commit/cea6b9c7f75688c3f2ae12dc7eda6c501d462b7b))

## [1.4.3](https://github.com/duongel/rag-api/compare/v1.4.2...v1.4.3) (2026-03-16)


### Bug Fixes

* remove POST /note references (belongs to separate PR) ([51a5a0b](https://github.com/duongel/rag-api/commit/51a5a0baef6e69185e1f2fcab91b8e025ae2d7b1))

## [1.4.2](https://github.com/duongel/rag-api/compare/v1.4.1...v1.4.2) (2026-03-16)


### Bug Fixes

* allow install into existing directory with pre-placed .env ([1d376f1](https://github.com/duongel/rag-api/commit/1d376f121c6ae3ec536b03eae88dd858e7d8d70f))

## [1.4.1](https://github.com/duongel/rag-api/compare/v1.4.0...v1.4.1) (2026-03-16)


### Bug Fixes

* clean up api_content_hashes entry when removing a file ([59bf99d](https://github.com/duongel/rag-api/commit/59bf99d8ded6439c7c9714e4110f579fd88a8902))

# [1.4.0](https://github.com/duongel/rag-api/compare/v1.3.0...v1.4.0) (2026-03-16)


### Bug Fixes

* chunking bug when chunks is None ([46652ba](https://github.com/duongel/rag-api/commit/46652baea8ac7423033ec08953b307f52b6f2d10))
* document reindexing if ocr text changes, even if pdf file did not change ([2ca0507](https://github.com/duongel/rag-api/commit/2ca0507c483938ce576165a6971b6e99802324c9))
* progressbar cursor position now aligned correctly ([315e29a](https://github.com/duongel/rag-api/commit/315e29a56d88bddd1bc7b63014c1beb5d2fadf5f))
* track raw file hash and API content hash separately ([8ea0059](https://github.com/duongel/rag-api/commit/8ea0059c993b2cace931502031922f4d31914de4))


### Features

* improved indexing speed, fix: missing tty for one-liner install via ssh, fix: ghcr.io auto publish ([1c2dc62](https://github.com/duongel/rag-api/commit/1c2dc62d83f240aed12e30fed5fb8dcf54a36a95))

# [1.3.0](https://github.com/duongel/rag-api/compare/v1.2.0...v1.3.0) (2026-03-16)


### Bug Fixes

* handle missing TTY during installer setup ([f292ca5](https://github.com/duongel/rag-api/commit/f292ca5ccc39c8422577adf66071e90c2e97d77c))


### Features

* improve CI workflows and install script TTY handling ([b4e1ea3](https://github.com/duongel/rag-api/commit/b4e1ea36044740fc57146c1b3e932881560880a9))

# [1.2.0](https://github.com/duongel/rag-api/compare/v1.1.0...v1.2.0) (2026-03-15)


### Bug Fixes

* chunking strategy switched to RecursiveCharacterTextSplitter with Markdown-Awareness, preventing huge chucks getting rejected ([d53ff28](https://github.com/duongel/rag-api/commit/d53ff28e188476e0518c312b12b29c2ad3892124))
* CLI flag (incl. default 'all') always overrides stored DATA_SOURCES in .env ([8df7240](https://github.com/duongel/rag-api/commit/8df72400cd0b292a01bd2b82e6544f4eb25f90c3))
* fixed docker build when updating ([c9d5ec1](https://github.com/duongel/rag-api/commit/c9d5ec1f5866a141a9312045978548a405c5c994))
* guard installer updates and persist missing env keys ([d513f0b](https://github.com/duongel/rag-api/commit/d513f0b7ea58b53551492409021c71abea8d0527))
* guard paperless indexing when archive path is missing ([aa6406f](https://github.com/duongel/rag-api/commit/aa6406fdd76cee6144db7d5744c31ab537d7c001))
* indexing algorithm, fixed update mechanism rebuilds container ([80fad0b](https://github.com/duongel/rag-api/commit/80fad0b890f3473afba7a17436cf4f6b9fbff7cb))
* prompt for missing vault/paperless paths on Y-reuse when DATA_SOURCES expands ([cbf60d1](https://github.com/duongel/rag-api/commit/cbf60d17f0d6225eebe9a39eb4980b0cf3ef4ef9))
* regression ([#3](https://github.com/duongel/rag-api/issues/3)) ([2cdea4c](https://github.com/duongel/rag-api/commit/2cdea4cfbac2ff5aaf49b61e8fa7bafedb1d70d7))
* removed testfile, fixed color use ([1f51635](https://github.com/duongel/rag-api/commit/1f516357e29338a72a86c54c6c21f94761df8735))
* restructured project, implemented tests for chunking ([9c4e908](https://github.com/duongel/rag-api/commit/9c4e908ee70d86aa5ee4923922fef9b239843b0e))
* revert to curl-based installer, add exec </dev/tty for piped stdin, safe re-run ([f62c1dc](https://github.com/duongel/rag-api/commit/f62c1dc380dd7a92eaf778e644966cb3a7f1a56f))
* **start:** harden env updates and status counter fallback ([26b8be7](https://github.com/duongel/rag-api/commit/26b8be7e1805f9bf827670013ee4035dd3f0737d))


### Features

* distribution optimization ([#2](https://github.com/duongel/rag-api/issues/2)) ([d00648c](https://github.com/duongel/rag-api/commit/d00648cb16741a01257d21fd0cd2986329608927))

# [1.1.0](https://github.com/duongel/rag-api/compare/v1.0.0...v1.1.0) (2026-03-15)


### Features

* distribution optimization ([#4](https://github.com/duongel/rag-api/issues/4)) ([7b99b92](https://github.com/duongel/rag-api/commit/7b99b9247c7459b9f6af6fb1116e35e940421846))

# 1.0.0 (2026-03-15)


### Bug Fixes

* replace bash arrays with if/else to fix runtime syntax error on macOS bash 3.2 ([809a461](https://github.com/duongel/rag-api/commit/809a4611f5178167f3977e13e6392964b84b1ea3))
* suppress docker network create output ([692fc67](https://github.com/duongel/rag-api/commit/692fc6711075c3191459f58270bc6f0e8bcf4800))


### Features

* --obsidian-only / --paperless-only flags and DATA_SOURCES config ([240b7ea](https://github.com/duongel/rag-api/commit/240b7ea29ae16d52049b0240809389707c2602eb))
* **start.sh:** prompt for DOCKER_NETWORK during setup ([c6d1c12](https://github.com/duongel/rag-api/commit/c6d1c122d861684e30bc0714ddc3661db8fd8db1))
