# php

Multi-arch Alpine-based PHP images

![build](https://github.com/rafalmasiarek/php-images/actions/workflows/build.yml/badge.svg?branch=main)
![license](https://img.shields.io/github/license/rafalmasiarek/php-images)
![trivy-total](https://img.shields.io/endpoint?url=https%3A%2F%2Fphp-images.masiarek.dev%2Fbadges%2Ftrivy-total.json&cacheSeconds=300&v=24020147085)
![built](https://img.shields.io/endpoint?url=https%3A%2F%2Fphp-images.masiarek.dev%2Fbadges%2Fbuilt.json&cacheSeconds=300&v=24020147085)

---

## Supported images

| PHP | Version | EOL | Tags | OS | Trivy |
| - | - | - | - | - | - |
| [`8.2`](https://github.com/rafalmasiarek/php-images/releases/tag/php-8.2) | `8.2.30` | `2026-12-31` | **cli**: `8.2-cli`<br>**fpm**: `8.2-fpm` | **cli**: [![alpine](https://img.shields.io/static/v1?label=alpine&message=v3.22&color=blue&cacheSeconds=300&v=24020147085)](https://hub.docker.com/layers/library/alpine/3.22)<br>**fpm**: [![alpine](https://img.shields.io/static/v1?label=alpine&message=v3.22&color=blue&cacheSeconds=300&v=24020147085)](https://hub.docker.com/layers/library/alpine/3.22) | **cli**: ![trivy](https://img.shields.io/endpoint?url=https%3A%2F%2Fphp-images.masiarek.dev%2Fbadges%2Ftrivy-8.2-cli.json&cacheSeconds=300&v=24020147085)<br>**fpm**: ![trivy](https://img.shields.io/endpoint?url=https%3A%2F%2Fphp-images.masiarek.dev%2Fbadges%2Ftrivy-8.2-fpm.json&cacheSeconds=300&v=24020147085) |
| [`8.3`](https://github.com/rafalmasiarek/php-images/releases/tag/php-8.3) | `8.3.30` | `2027-12-31` | **cli**: `8.3-cli`<br>**fpm**: `8.3-fpm` | **cli**: [![alpine](https://img.shields.io/static/v1?label=alpine&message=v3.22&color=blue&cacheSeconds=300&v=24020147085)](https://hub.docker.com/layers/library/alpine/3.22)<br>**fpm**: [![alpine](https://img.shields.io/static/v1?label=alpine&message=v3.22&color=blue&cacheSeconds=300&v=24020147085)](https://hub.docker.com/layers/library/alpine/3.22) | **cli**: ![trivy](https://img.shields.io/endpoint?url=https%3A%2F%2Fphp-images.masiarek.dev%2Fbadges%2Ftrivy-8.3-cli.json&cacheSeconds=300&v=24020147085)<br>**fpm**: ![trivy](https://img.shields.io/endpoint?url=https%3A%2F%2Fphp-images.masiarek.dev%2Fbadges%2Ftrivy-8.3-fpm.json&cacheSeconds=300&v=24020147085) |
| [`8.4`](https://github.com/rafalmasiarek/php-images/releases/tag/php-8.4) | `8.4.19` | `2028-12-31` | **cli**: `8.4-cli`<br>**fpm**: `8.4-fpm` | **cli**: [![alpine](https://img.shields.io/static/v1?label=alpine&message=v3.23&color=blue&cacheSeconds=300&v=24020147085)](https://hub.docker.com/layers/library/alpine/3.23)<br>**fpm**: [![alpine](https://img.shields.io/static/v1?label=alpine&message=v3.23&color=blue&cacheSeconds=300&v=24020147085)](https://hub.docker.com/layers/library/alpine/3.23) | **cli**: ![trivy](https://img.shields.io/endpoint?url=https%3A%2F%2Fphp-images.masiarek.dev%2Fbadges%2Ftrivy-8.4-cli.json&cacheSeconds=300&v=24020147085)<br>**fpm**: ![trivy](https://img.shields.io/endpoint?url=https%3A%2F%2Fphp-images.masiarek.dev%2Fbadges%2Ftrivy-8.4-fpm.json&cacheSeconds=300&v=24020147085) |
| [`8.5`](https://github.com/rafalmasiarek/php-images/releases/tag/php-8.5) | `8.5.4` | `2029-12-31` | **cli**: `8.5-cli`<br>**fpm**: `8.5-fpm` | **cli**: [![alpine](https://img.shields.io/static/v1?label=alpine&message=v3.23&color=blue&cacheSeconds=300&v=24020147085)](https://hub.docker.com/layers/library/alpine/3.23)<br>**fpm**: [![alpine](https://img.shields.io/static/v1?label=alpine&message=v3.23&color=blue&cacheSeconds=300&v=24020147085)](https://hub.docker.com/layers/library/alpine/3.23) | **cli**: ![trivy](https://img.shields.io/endpoint?url=https%3A%2F%2Fphp-images.masiarek.dev%2Fbadges%2Ftrivy-8.5-cli.json&cacheSeconds=300&v=24020147085)<br>**fpm**: ![trivy](https://img.shields.io/endpoint?url=https%3A%2F%2Fphp-images.masiarek.dev%2Fbadges%2Ftrivy-8.5-fpm.json&cacheSeconds=300&v=24020147085) |

---

## Pulling images

All images are published to `ghcr.io/rafalmasiarek/php`.

Tag scheme:

- `<php>-<variant>` — moving tag
- `<php>-<variant>-YYYY-MM-DD` — date tag
- `<php>-<variant>-sha-<gitsha7>` — immutable tag

---

## Trivy reports

HTML reports are published under `/reports/` on the project site.

If `SITE_BASE_URL` is configured during generation, badges and report links will point to the published site output.

---

## Installing additional extensions

Images ship with `phpctl`, which can install, enable, disable and inspect PHP extensions.

### Install a PECL extension

```sh
phpctl ext install redis --type pecl
```

### Install and enable immediately

```sh
phpctl ext install redis --type pecl --enable
```

### Install a PECL extension with additional build and runtime packages

```sh
phpctl ext install imagick \
  --type pecl \
  --apk imagemagick-dev \
  --runtime imagemagick
```

### Install a core extension

```sh
phpctl ext install xsl --type core
```

### Enable or disable an already installed extension

```sh
phpctl ext enable redis
phpctl ext disable redis
```

### Inspect extension state

```sh
phpctl ext list
phpctl ext status redis
phpctl ext versions
```

Available extension configuration files are stored in:

```text
/usr/local/etc/php/conf.d/available
```

Active extension configuration files are stored in:

```text
/usr/local/etc/php/conf.d
```

This means installation and activation are separate operations:

- installation creates the module and an ini file in `available`
- enabling creates an active ini entry in `conf.d`
- disabling removes the active ini entry without uninstalling the module

---

## phpctl

`phpctl` is the control utility shipped with these images. It is designed to make PHP image operations predictable and scriptable, especially around extension management, PHP-FPM pool management, runtime diagnostics and health checks.

The tool uses a simple filesystem model:

- available PHP extension configuration: `/usr/local/etc/php/conf.d/available`
- active PHP extension configuration: `/usr/local/etc/php/conf.d`
- available PHP-FPM pools: `/usr/local/etc/php-fpm.d/available`
- active PHP-FPM pools: `/usr/local/etc/php-fpm.d`

The defaults can be overridden with environment variables, but the images are built around those standard locations.

---

## Main goals

`phpctl` is intended to solve the most common operational tasks in a PHP container:

- inspect PHP runtime configuration
- install core and PECL extensions
- enable or disable extensions
- inspect available and active extension state
- manage PHP-FPM pools
- expose health, status and metrics endpoints
- provide machine-friendly CLI output formats

---

## Output formats

By default `phpctl` prints human-readable text output.

You can change the format globally with:

```sh
phpctl --output text ...
phpctl --output json ...
phpctl --output tsv ...
```

Examples:

```sh
phpctl --output json info
phpctl --output tsv ext list
phpctl --output json health
```

You can also set the default output format through an environment variable:

```sh
PHPCTL_OUTPUT_FORMAT=json phpctl info
```

Supported values:

- `text`
- `json`
- `tsv`

---

## Basic commands

### Show version

```sh
phpctl version
```

### Show runtime information

```sh
phpctl info
```

Information includes:

- PHP binary path
- PHP version
- PHP SAPI
- loaded php.ini
- additional ini scan directory
- extension directory
- PHP-FPM binary path

### Show important paths

```sh
phpctl paths
```

This displays the directories used internally by the image.

### Run diagnostics

```sh
phpctl doctor
phpctl self-test
```

`doctor` checks for required tools and directories.

`self-test` runs runtime checks such as:

- `php -v`
- `php -m`
- `php --ini`
- `php-fpm -t` (if available)

---

## PHP extension management

The `ext` command group manages PHP extensions.

### List extensions

```sh
phpctl ext list
```

Shows:

- available extensions
- active extensions
- loaded extensions

### List only loaded extensions

```sh
phpctl ext list-loaded
```

### Show extension versions

```sh
phpctl ext versions
```

### Show extension status

```sh
phpctl ext status redis
```

Output includes:

- availability
- active state
- loaded state
- extension version
- extension type
- ini paths

### Detect extension type

```sh
phpctl ext detect redis
phpctl ext detect xsl
```

Possible types:

- `core`
- `pecl`
- `core-known-but-source-not-extracted`
- `core-known-but-source-missing`
- `unknown`

---

## Installing extensions

### Install a core extension

```sh
phpctl ext install xsl --type core
```

### Install a PECL extension

```sh
phpctl ext install redis --type pecl
```

### Install and enable

```sh
phpctl ext install redis --type pecl --enable
```

By default installation creates an entry in the `available` directory but does not activate it.

### Install specific version

```sh
phpctl ext install xdebug --type pecl --version 3.4.0
```

### Add build dependencies

Example:

```sh
phpctl ext install imagick \
  --type pecl \
  --apk imagemagick-dev \
  --runtime imagemagick
```

### Configure core extensions

```sh
phpctl ext install gd \
  --type core \
  --configure --with-freetype \
  --configure --with-jpeg
```

### Control parallel jobs

```sh
phpctl ext install intl --type core --jobs 4
```

### Disable cleanup for debugging

```sh
phpctl ext install redis --type pecl --no-cleanup
```

### Force reinstall

```sh
phpctl ext install redis --type pecl --force
```

---

## Enabling extensions

Extensions are enabled by linking the ini file into the active directory.

### Enable extension

```sh
phpctl ext enable redis
```

### Disable extension

```sh
phpctl ext disable redis
```

### Enable all available extensions

```sh
phpctl ext enable-all
```

### Disable all active extensions

```sh
phpctl ext disable-all
```

This only removes active configuration files.

Installed `.so` modules remain in the extension directory.

---

## PHP-FPM management

When PHP-FPM is present, `phpctl` can inspect and manage pool configurations.

### Show FPM status

```sh
phpctl fpm status
```

### Validate FPM configuration

```sh
phpctl fpm test
phpctl fpm configtest
```

### Reload PHP-FPM

```sh
phpctl fpm reload
```

### List pools

```sh
phpctl fpm pool list
```

### Show one pool

```sh
phpctl fpm pool show www
```

### Enable or disable a pool

```sh
phpctl fpm pool enable www
phpctl fpm pool disable www
```

### Create a pool

```sh
phpctl fpm pool create api --enable
```

### Render pool config without saving

```sh
phpctl fpm pool render api
```

### Generate a pool config for manual editing

```sh
phpctl fpm pool generate api --output-file /tmp/api.conf
```

### Import an existing pool file

```sh
phpctl fpm pool import api --from /tmp/api.conf --enable
```

### Validate a specific pool

```sh
phpctl fpm pool validate api
```

### Delete a pool

```sh
phpctl fpm pool delete api
```

### Import multiple pools from JSON

```sh
phpctl fpm pool bundle import --json-file /tmp/pools.json --reload
```

---

## Health checks

`phpctl` provides container-friendly health commands.

### Basic health

```sh
phpctl health
```

### Status summary

```sh
phpctl status
```

The health and status commands expose information such as:

- PHP runtime availability
- PHP-FPM availability
- PHP-FPM configuration validity
- loaded extension count
- active and available pool count

---

## Metrics

Basic runtime metrics can be retrieved with:

```sh
phpctl metrics
```

In text mode this exposes Prometheus-style metrics, including:

- PHP availability
- PHP-FPM availability
- PHP-FPM config validity
- number of loaded extensions
- number of available FPM pools
- number of enabled FPM pools

Example:

```sh
phpctl metrics
```

---

## HTTP serving mode

`phpctl` can expose lightweight HTTP endpoints.

### Serve health and metrics endpoints

```sh
phpctl serve --listen 0.0.0.0:8080
```

Exposed endpoints:

- `/healthz`
- `/readyz`
- `/status`
- `/metrics`

### Run remote-control server

```sh
phpctl server --listen 0.0.0.0:8080
```

This mode exposes:

- `/healthz`
- `/readyz`
- `/status`
- `/metrics`
- `POST /run`

### Use remote client mode

```sh
phpctl client --host 127.0.0.1:8080 info
phpctl --client --host 127.0.0.1:8080 ext list
```

You can also use a client configuration file.

Default path:

```text
~/.phpctl/client.conf
```

Supported keys:

```text
host=
user=
password=
```

---

## Example workflows

### Install and enable Redis

```sh
phpctl ext install redis --type pecl
phpctl ext enable redis
```

### Install Imagick with dependencies

```sh
phpctl ext install imagick \
  --type pecl \
  --apk imagemagick-dev \
  --runtime imagemagick
```

### Inspect extension state

```sh
phpctl ext list
phpctl ext status redis
```

### Show runtime diagnostics

```sh
phpctl doctor
phpctl info
phpctl health
```

### Create and enable a custom FPM pool

```sh
phpctl fpm pool create api \
  -p USER=www-data \
  -p GROUP=www-data \
  -p LISTEN=/var/run/php-fpm-api.sock \
  -p PM_MAX_CHILDREN=16 \
  --enable
```

---

## Environment variables

`phpctl` supports overriding many internal paths and tool locations through environment variables.

### Output and client/server configuration

#### `PHPCTL_OUTPUT_FORMAT`

Default output format.

Default:

```text
text
```

Supported values:

- `text`
- `json`
- `tsv`

Example:

```sh
PHPCTL_OUTPUT_FORMAT=json phpctl info
```

#### `PHPCTL_SERVE_LISTEN`

Default listen address for `phpctl serve`.

Default:

```text
0.0.0.0:8080
```

#### `PHPCTL_SERVER_LISTEN`

Default listen address for `phpctl server`.

If not set, it falls back to `PHPCTL_SERVE_LISTEN`.

#### `PHPCTL_CLIENT_CONF`

Path to the client configuration file used by `phpctl client`.

Default:

```text
$HOME/.phpctl/client.conf
```

### Binary overrides

These variables let you replace the command used internally.

#### `PHPCTL_PHP_BIN`

PHP CLI binary.

Default resolution:

- `PHPCTL_PHP_BIN`
- `PHP_BIN`
- `php`

#### `PHPCTL_PHP_FPM_BIN`

PHP-FPM binary.

Default resolution:

- `PHPCTL_PHP_FPM_BIN`
- `PHP_FPM_BIN`
- `php-fpm`

#### `PHPCTL_PECL_BIN`

PECL binary.

Default resolution:

- `PHPCTL_PECL_BIN`
- `PECL_BIN`
- `pecl`

#### `PHPCTL_PHPIZE_BIN`

`phpize` binary.

Default resolution:

- `PHPCTL_PHPIZE_BIN`
- `PHPIZE_BIN`
- `phpize`

#### `PHPCTL_MAKE_BIN`

`make` binary.

Default resolution:

- `PHPCTL_MAKE_BIN`
- `MAKE_BIN`
- `make`

#### `PHPCTL_READ_ELF_BIN`

`readelf` binary used to detect Zend extensions.

Default resolution:

- `PHPCTL_READ_ELF_BIN`
- `READ_ELF_BIN`
- `readelf`

#### `PHPCTL_NC_BIN`

`nc` binary used for HTTP serve/server modes.

Default resolution:

- `PHPCTL_NC_BIN`
- `NC_BIN`
- `nc`

#### `PHPCTL_STRIP_BIN`

`strip` binary used to shrink compiled modules.

Default resolution:

- `PHPCTL_STRIP_BIN`
- `STRIP_BIN`
- `strip`

### PHP configuration paths

#### `PHPCTL_PHP_INI_DIR`

Base PHP configuration directory.

Default resolution:

- `PHPCTL_PHP_INI_DIR`
- `PHP_INI_DIR`
- `/usr/local/etc/php`

#### `PHPCTL_PHP_EXT_AVAILABLE_DIR`

Directory where available extension ini files are stored.

Default resolution:

- `PHPCTL_PHP_EXT_AVAILABLE_DIR`
- `PHP_EXT_AVAILABLE_DIR`
- `${PHP_INI_DIR}/conf.d/available`

Default effective value in these images:

```text
/usr/local/etc/php/conf.d/available
```

#### `PHPCTL_PHP_EXT_ACTIVE_DIR`

Directory where active extension ini files are stored.

Default resolution:

- `PHPCTL_PHP_EXT_ACTIVE_DIR`
- `PHP_EXT_ACTIVE_DIR`
- `${PHP_INI_DIR}/conf.d`

Default effective value in these images:

```text
/usr/local/etc/php/conf.d
```

### PHP-FPM configuration paths

#### `PHPCTL_PHP_FPM_CONF_DIR`

Base PHP-FPM configuration directory.

Default resolution:

- `PHPCTL_PHP_FPM_CONF_DIR`
- `PHP_FPM_CONF_DIR`
- `/usr/local/etc`

#### `PHPCTL_PHP_FPM_POOL_AVAILABLE_DIR`

Directory where available FPM pool configs are stored.

Default resolution:

- `PHPCTL_PHP_FPM_POOL_AVAILABLE_DIR`
- `PHP_FPM_POOL_AVAILABLE_DIR`
- `${PHP_FPM_CONF_DIR}/php-fpm.d/available`

Default effective value:

```text
/usr/local/etc/php-fpm.d/available
```

#### `PHPCTL_PHP_FPM_POOL_ACTIVE_DIR`

Directory where active FPM pool configs are stored.

Default resolution:

- `PHPCTL_PHP_FPM_POOL_ACTIVE_DIR`
- `PHP_FPM_POOL_ACTIVE_DIR`
- `${PHP_FPM_CONF_DIR}/php-fpm.d`

Default effective value:

```text
/usr/local/etc/php-fpm.d
```

#### `PHPCTL_PHP_FPM_POOL_TEMPLATE`

Path to a custom default FPM pool template file.

Default:

empty

If this is set, `phpctl fpm pool create`, `render` and `generate` can use it as the default template source.

#### `PHPCTL_PHP_FPM_RELOAD_SIGNAL`

Signal used by `phpctl fpm reload`.

Default:

```text
HUP
```

### PHP source and build settings

#### `PHPCTL_PHP_SRC_DIR`

Location of the PHP source tree used when building core extensions.

Default resolution:

- `PHPCTL_PHP_SRC_DIR`
- `PHP_SRC_DIR`
- `/usr/src/php`

#### `PHPCTL_PHP_BUILD_DEPS_VIRTUAL`

Name of the Alpine virtual package used for temporary build dependencies.

Default:

```text
.phpctl-php-ext-build
```

#### `PHPCTL_PHP_BUILD_DEPS`

List of build dependencies installed when needed.

Default resolution:

- `PHPCTL_PHP_BUILD_DEPS`
- `PHP_BUILD_DEPS`
- `${PHPIZE_DEPS:-autoconf dpkg-dev dpkg file g++ gcc libc-dev make pkgconf re2c} linux-headers pkgconfig re2c git binutils`

This is mainly useful when you need to customize build tooling in a derived image.

### Remote operation internals

#### `PHPCTL_SELF_PATH`

Path used when `phpctl` needs to re-exec itself, for example in server/client or bundle-import flows.

Default:

```text
$0
```

Usually there is no need to override this unless you are wrapping `phpctl` inside another launcher script.

---

## Full list of supported environment variables

```text
PHPCTL_OUTPUT_FORMAT
PHPCTL_PHP_BIN
PHPCTL_PHP_FPM_BIN
PHPCTL_PECL_BIN
PHPCTL_PHPIZE_BIN
PHPCTL_MAKE_BIN
PHPCTL_READ_ELF_BIN
PHPCTL_NC_BIN
PHPCTL_STRIP_BIN
PHPCTL_PHP_INI_DIR
PHPCTL_PHP_EXT_AVAILABLE_DIR
PHPCTL_PHP_EXT_ACTIVE_DIR
PHPCTL_PHP_FPM_CONF_DIR
PHPCTL_PHP_FPM_POOL_AVAILABLE_DIR
PHPCTL_PHP_FPM_POOL_ACTIVE_DIR
PHPCTL_PHP_FPM_POOL_TEMPLATE
PHPCTL_PHP_FPM_RELOAD_SIGNAL
PHPCTL_PHP_SRC_DIR
PHPCTL_PHP_BUILD_DEPS_VIRTUAL
PHPCTL_PHP_BUILD_DEPS
PHPCTL_SERVE_LISTEN
PHPCTL_SERVER_LISTEN
PHPCTL_CLIENT_CONF
PHPCTL_SELF_PATH
```

---

## License

MIT
