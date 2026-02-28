# php-base-images

Multi-arch (amd64+arm64) PHP base images.

---

## Supported images

| PHP | Base tag | Flavor | Image tag prefix | PECL modules (declared) |
| - | - | - | - | - |
| 8.2 | cli-alpine | base | `8.2-cli-alpine-base` | redis, apcu, mongodb, msgpack, mailparse, xdebug |
| 8.2 | cli-alpine | fat | `8.2-cli-alpine-fat` | redis, apcu, mongodb, msgpack, mailparse, xdebug, imagick, memcached, amqp, ssh2, ast, ds, pcov |
| 8.2 | fpm-alpine | base | `8.2-fpm-alpine-base` | redis, apcu, mongodb, msgpack, mailparse, xdebug |
| 8.2 | fpm-alpine | fat | `8.2-fpm-alpine-fat` | redis, apcu, mongodb, msgpack, mailparse, xdebug, imagick, memcached, amqp, ssh2, ast, ds, pcov |
| 8.3 | cli-alpine | base | `8.3-cli-alpine-base` | redis, apcu, mongodb, msgpack, mailparse, xdebug |
| 8.3 | cli-alpine | fat | `8.3-cli-alpine-fat` | redis, apcu, mongodb, msgpack, mailparse, xdebug, imagick, memcached, amqp, ssh2, ast, ds, pcov |
| 8.3 | fpm-alpine | base | `8.3-fpm-alpine-base` | redis, apcu, mongodb, msgpack, mailparse, xdebug |
| 8.3 | fpm-alpine | fat | `8.3-fpm-alpine-fat` | redis, apcu, mongodb, msgpack, mailparse, xdebug, imagick, memcached, amqp, ssh2, ast, ds, pcov |

---

## Install one more extension on top of a base image

Images ship with `/usr/local/bin/php-ext-install` for PECL modules:

```sh
php-ext-install pecl igbinary
php-ext-install pecl imagick --runtime imagemagick --apk imagemagick-dev
```

---

## License
MIT
