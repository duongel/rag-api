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
