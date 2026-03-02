# php

Multi-arch Alpine-based PHP images

![build](https://github.com/rafalmasiarek/php-images/actions/workflows/build.yml/badge.svg?branch=main)
![release](https://img.shields.io/github/v/release/rafalmasiarek/php-images?display_name=tag)
![license](https://img.shields.io/github/license/rafalmasiarek/php-images)

![trivy-total](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/rafalmasiarek/php-images/badges/badges/trivy-total.json)
![php](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/rafalmasiarek/php-images/badges/badges/php.json)
![built](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/rafalmasiarek/php-images/badges/badges/built.json)
![images](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/rafalmasiarek/php-images/badges/badges/images.json)

---

## Supported images

| PHP | Tags | Alpine | PECL modules (declared) | Trivy |
| - | - | - | - | - |
| `8.2` | **cli**: `8.2-cli`<br>**fpm**: `8.2-fpm` | **cli**: `3.22`<br>**fpm**: `3.22` | **cli**: redis, apcu, mongodb, msgpack, mailparse, xdebug, imagick, memcached, amqp, ssh2, ast, ds, pcov<br>**fpm**: redis, apcu, mongodb, msgpack, mailparse, xdebug, imagick, memcached, amqp, ssh2, ast, ds, pcov | **cli**: ![trivy](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/rafalmasiarek/php-images/badges/badges/trivy-8.2-cli.json)<br>**fpm**: ![trivy](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/rafalmasiarek/php-images/badges/badges/trivy-8.2-fpm.json) |
| `8.3` | **cli**: `8.3-cli`<br>**fpm**: `8.3-fpm` | **cli**: `3.22`<br>**fpm**: `3.22` | **cli**: redis, apcu, mongodb, msgpack, mailparse, xdebug, imagick, memcached, amqp, ssh2, ast, ds, pcov<br>**fpm**: redis, apcu, mongodb, msgpack, mailparse, xdebug, imagick, memcached, amqp, ssh2, ast, ds, pcov | **cli**: ![trivy](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/rafalmasiarek/php-images/badges/badges/trivy-8.3-cli.json)<br>**fpm**: ![trivy](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/rafalmasiarek/php-images/badges/badges/trivy-8.3-fpm.json) |

---

## Install one more extension on top of an image

Images ship with `/usr/local/bin/php-ext-install` for PECL modules:

```sh
php-ext-install pecl igbinary
php-ext-install pecl imagick --runtime imagemagick --apk imagemagick-dev
```

## License
MIT
