# php

Multi-arch Alpine-based PHP images

![build](https://github.com/rafalmasiarek/php-images/actions/workflows/build.yml/badge.svg?branch=main)
![license](https://img.shields.io/github/license/rafalmasiarek/php-images)

![trivy-total](https://img.shields.io/endpoint?url=https%3A%2F%2Fphp-images.masiarek.dev%2Fbadges%2Ftrivy-total.json)
![built](https://img.shields.io/endpoint?url=https%3A%2F%2Fphp-images.masiarek.dev%2Fbadges%2Fbuilt.json)

---

## Supported images

| PHP | Tags | OS | Trivy |
| - | - | - | - |
| `8.2` | **cli**: `8.2-cli`<br>**fpm**: `8.2-fpm` | **cli**: [![alpine](https://img.shields.io/badge/alpine-v3.22)](https://hub.docker.com/layers/library/alpine/3.22)<br>**fpm**: [![alpine](https://img.shields.io/badge/alpine-v3.22)](https://hub.docker.com/layers/library/alpine/3.22) | **cli**: ![trivy](https://img.shields.io/endpoint?url=https%3A%2F%2Fphp-images.masiarek.dev%2Fbadges%2Ftrivy-8.2-cli.json)<br>**fpm**: ![trivy](https://img.shields.io/endpoint?url=https%3A%2F%2Fphp-images.masiarek.dev%2Fbadges%2Ftrivy-8.2-fpm.json) |
| `8.3` | **cli**: `8.3-cli`<br>**fpm**: `8.3-fpm` | **cli**: [![alpine](https://img.shields.io/badge/alpine-v3.22)](https://hub.docker.com/layers/library/alpine/3.22)<br>**fpm**: [![alpine](https://img.shields.io/badge/alpine-v3.22)](https://hub.docker.com/layers/library/alpine/3.22) | **cli**: ![trivy](https://img.shields.io/endpoint?url=https%3A%2F%2Fphp-images.masiarek.dev%2Fbadges%2Ftrivy-8.3-cli.json)<br>**fpm**: ![trivy](https://img.shields.io/endpoint?url=https%3A%2F%2Fphp-images.masiarek.dev%2Fbadges%2Ftrivy-8.3-fpm.json) |

---

## Pulling images

All images are published to `ghcr.io/rafalmasiarek/php`.

Tag scheme:

- `<php>-<variant>` (moving)
- `<php>-<variant>-YYYY-MM-DD` (date)
- `<php>-<variant>-sha-<gitsha7>` (immutable)

## Trivy reports

- HTML reports: https://php-images.masiarek.dev/reports/

## Install one more extension on top of an image

Images ship with `/usr/local/bin/php-ext-install` for PECL modules:

```sh
php-ext-install pecl igbinary
php-ext-install pecl imagick --runtime imagemagick --apk imagemagick-dev
```

## License
MIT
