# Changelog

## [1.5.1](https://github.com/andrewtryder/abs-media-importer/compare/v1.5.0...v1.5.1) (2026-07-02)


### Bug Fixes

* **extension:** harden popup and optional auth websocket flow ([41a4542](https://github.com/andrewtryder/abs-media-importer/commit/41a454215f3037b5f8eb42a7793a10d218bac933))
* **extension:** harden popup flow and align optional auth websocket behavior ([8ed0097](https://github.com/andrewtryder/abs-media-importer/commit/8ed009701b72223c0393199e478493eff880713f))

## [1.5.0](https://github.com/andrewtryder/abs-media-importer/compare/v1.4.1...v1.5.0) (2026-07-02)


### Features

* **app:** add dedup ledger, output filesize, and extension UX updates ([664cf27](https://github.com/andrewtryder/abs-media-importer/commit/664cf276316a41d313026bab1eaef97539b884a8))
* **app:** ship jobs dedup, output metadata, and extension updates ([5b58813](https://github.com/andrewtryder/abs-media-importer/commit/5b5881305f491731ccff14fb9564f422574c2b07))
* **branding:** replace app and extension icons ([a32f026](https://github.com/andrewtryder/abs-media-importer/commit/a32f02601bffe82f1f1b5fe5598487eb775ada5c))
* **branding:** replace app and extension icons ([26cf385](https://github.com/andrewtryder/abs-media-importer/commit/26cf38507872046537451c6d05e471cd426bdaca))
* **browser-extension:** add extension integration and UI updates ([0b97341](https://github.com/andrewtryder/abs-media-importer/commit/0b97341f1fc785bccae56a2cf73d22d2c9cfc26b))
* **browser-extension:** add extension integration and UI updates ([1da5904](https://github.com/andrewtryder/abs-media-importer/commit/1da59042c94165cd3a9afd6a87da7a7f397caff1))


### Bug Fixes

* **api:** register routes during app startup ([6f93169](https://github.com/andrewtryder/abs-media-importer/commit/6f93169e0fc0baffcae2a79f75e406797d6f5a12))
* **api:** register routes synchronously at startup ([ab56418](https://github.com/andrewtryder/abs-media-importer/commit/ab5641832166a89db4d44381b889ebb2d9c27419))
* **api:** remove duplicated extension auth logic ([2a69408](https://github.com/andrewtryder/abs-media-importer/commit/2a69408de8d1cec63038ecdca99239b3cfcabe00))
* **api:** replace websocket timeout call for mypy ([ae5b4b2](https://github.com/andrewtryder/abs-media-importer/commit/ae5b4b244a7fd8d54106f5f0d27f65a0b26a4c6e))
* **api:** resolve Ruff failures in extension websocket path ([6caeec6](https://github.com/andrewtryder/abs-media-importer/commit/6caeec636f1c6e1c7fbe679cf5a0bde039089714))
* **tests:** align mocked and on-disk output filesize ([6e48fe6](https://github.com/andrewtryder/abs-media-importer/commit/6e48fe6bb62c64e34162bc32d50132ba0609e408))
* **tests:** initialize extension API DB via lifespan ([3f03b65](https://github.com/andrewtryder/abs-media-importer/commit/3f03b65ef02ac32560a5e81d16749ed38e7de043))

## [1.4.1](https://github.com/andrewtryder/abs-media-importer/compare/v1.4.0...v1.4.1) (2026-06-30)


### Bug Fixes

* **frontend:** self-host fonts and fix Material Icons rendering ([f9d94b0](https://github.com/andrewtryder/abs-media-importer/commit/f9d94b0bba46b98eebdcd62b858fabec64973922))
* **frontend:** self-host fonts and fix Material Icons rendering ([4154dcf](https://github.com/andrewtryder/abs-media-importer/commit/4154dcfcb53bcd377938a949e91146ea4e3fd0f4))

## [1.4.0](https://github.com/andrewtryder/abs-media-importer/compare/v1.3.0...v1.4.0) (2026-06-30)


### Features

* **frontend:** integrate Google Stitch redesign and sidebar layout ([06b7f87](https://github.com/andrewtryder/abs-media-importer/commit/06b7f874cefba5110241c0a86dc3e34319365a35))
* **frontend:** integrate Google Stitch redesign and sidebar layout ([eb0a838](https://github.com/andrewtryder/abs-media-importer/commit/eb0a838564abc79941c3c7cd34a5b927d233598e))
* **worker:** import pipeline refactor and real-time progress tracking ([dfd511d](https://github.com/andrewtryder/abs-media-importer/commit/dfd511d8735e6ab4d167c4c7c75fd36f1910189a))
* **worker:** import pipeline refactor and real-time progress tracking ([c2bc4f0](https://github.com/andrewtryder/abs-media-importer/commit/c2bc4f02c9ce84816ffa8a69e33f1595e671f0cf))


### Bug Fixes

* **db:** resolve mypy typecheck issues ([2df20b4](https://github.com/andrewtryder/abs-media-importer/commit/2df20b414605f96bc14be8531e628ce71af9ee35))

## [1.3.0](https://github.com/andrewtryder/abs-media-importer/compare/v1.2.0...v1.3.0) (2026-06-30)


### Features

* **ui:** polish web interface look and feel for release ([2e974d3](https://github.com/andrewtryder/abs-media-importer/commit/2e974d3d87dd700cdf2437a24f48add1357030b6))
* **ui:** polish web interface look and feel for release ([fd4cca2](https://github.com/andrewtryder/abs-media-importer/commit/fd4cca22b7bf813f35aec9550f6415a33b3e5831))

## [1.2.0](https://github.com/andrewtryder/abs-media-importer/compare/v1.1.0...v1.2.0) (2026-06-30)


### Features

* **docker:** make podcasts directory configurable via .env ([ac8860f](https://github.com/andrewtryder/abs-media-importer/commit/ac8860f7bbe2a42a660cc1d053a67509bfe58bb4))
* **docker:** make podcasts directory configurable via .env ([d2a5f0c](https://github.com/andrewtryder/abs-media-importer/commit/d2a5f0cf66bb582637aa0f5aaadf4ef3b6baf1e8))

## [1.1.0](https://github.com/andrewtryder/abs-media-importer/compare/v1.0.1...v1.1.0) (2026-06-30)


### Features

* **web:** allow output root directory configuration from settings page ([3f23fe4](https://github.com/andrewtryder/abs-media-importer/commit/3f23fe4a19ae2a4b456c3b0d3fc26fa8aeaf9062))
* **web:** allow output root directory configuration from settings page ([d52daac](https://github.com/andrewtryder/abs-media-importer/commit/d52daacea5a2ef131fef3b3e1c0e835050b3bd60))

## [1.0.1](https://github.com/andrewtryder/abs-media-importer/compare/v1.0.0...v1.0.1) (2026-06-30)


### Bug Fixes

* **deps:** resolve pytest-asyncio and pytest 9 dependency conflict ([d74c995](https://github.com/andrewtryder/abs-media-importer/commit/d74c995edb9f145cc41651a1d86406dacf893be4))

## 1.0.0 (2026-06-30)


### Bug Fixes

* **ci:** format tests and correct cloud-init validation flags ([cf9ea08](https://github.com/andrewtryder/abs-media-importer/commit/cf9ea08859406b1869f3e5fa5b95bcd4e86f70d7))
* **ci:** remove Proxmox dry-run check from validate-proxmox workflow ([6b9313e](https://github.com/andrewtryder/abs-media-importer/commit/6b9313ebf288744a8951a3d2e308c3c5f402be9f))

## [Unreleased]
