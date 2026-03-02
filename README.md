# php-base-images

Multi-arch (amd64+arm64) PHP images.

---

## Supported images

| PHP | Variant | Image tag prefix | PECL modules (declared) |
| - | - | - | - |
| 8.2 | cli | `8.2-cli` | redis, apcu, mongodb, msgpack, mailparse, xdebug, imagick, memcached, amqp, ssh2, ast, ds, pcov |
| 8.2 | fpm | `8.2-fpm` | redis, apcu, mongodb, msgpack, mailparse, xdebug, imagick, memcached, amqp, ssh2, ast, ds, pcov |
| 8.3 | cli | `8.3-cli` | redis, apcu, mongodb, msgpack, mailparse, xdebug, imagick, memcached, amqp, ssh2, ast, ds, pcov |
| 8.3 | fpm | `8.3-fpm` | redis, apcu, mongodb, msgpack, mailparse, xdebug, imagick, memcached, amqp, ssh2, ast, ds, pcov |

---

## Install one more extension on top of an image

Images ship with `/usr/local/bin/php-ext-install` for PECL modules:

```sh
php-ext-install pecl igbinary
php-ext-install pecl imagick --runtime imagemagick --apk imagemagick-dev
```

## License
MIT
