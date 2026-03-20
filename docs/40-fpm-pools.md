## PHP-FPM pool templates

`phpctl` can create, render, generate, import and enable PHP-FPM pool configurations.

This is useful when you want to:

- create a new pool from the built-in default template
- override selected parameters without writing a full config by hand
- use your own custom template
- import an existing pool config into the managed `available` / `active` layout

---

## Default pool template

If you do not provide a custom template, `phpctl` uses the built-in default template:

```ini
[{{POOL_NAME}}]
user = {{USER}}
group = {{GROUP}}
listen = {{LISTEN}}
listen.owner = {{LISTEN_OWNER}}
listen.group = {{LISTEN_GROUP}}
pm = {{PM}}
pm.max_children = {{PM_MAX_CHILDREN}}
pm.start_servers = {{PM_START_SERVERS}}
pm.min_spare_servers = {{PM_MIN_SPARE_SERVERS}}
pm.max_spare_servers = {{PM_MAX_SPARE_SERVERS}}
catch_workers_output = {{CATCH_WORKERS_OUTPUT}}
clear_env = {{CLEAR_ENV}}
{{ if ENABLE_PING }}
ping.path = {{ PING_PATH | default("/fpm-ping") }}
ping.response = {{ PING_RESPONSE | default("pong") }}
{{ endif }}
{{ if ENABLE_METRICS }}
pm.status_path = {{ STATUS_PATH | default("/fpm-status") }}
{{ endif }}
```

---

## Default parameter values

When a new pool is created, `phpctl` starts with these defaults:

```text
POOL_NAME=<pool name>
USER=www-data
GROUP=www-data
LISTEN=/var/run/php-fpm-<pool name>.sock
LISTEN_OWNER=www-data
LISTEN_GROUP=www-data
PM=dynamic
PM_MAX_CHILDREN=8
PM_START_SERVERS=2
PM_MIN_SPARE_SERVERS=1
PM_MAX_SPARE_SERVERS=3
CATCH_WORKERS_OUTPUT=yes
CLEAR_ENV=no
ENABLE_METRICS=false
STATUS_PATH=
ENABLE_PING=false
PING_PATH=
PING_RESPONSE=
```

So for example:

```sh
phpctl fpm pool create api
```

will generate:

```ini
[api]
user = www-data
group = www-data
listen = /var/run/php-fpm-api.sock
listen.owner = www-data
listen.group = www-data
pm = dynamic
pm.max_children = 8
pm.start_servers = 2
pm.min_spare_servers = 1
pm.max_spare_servers = 3
catch_workers_output = yes
clear_env = no
```

---

## Render a pool without saving it

To preview the generated config without writing any file:

```sh
phpctl fpm pool render api
```

You can also override parameters inline:

```sh
phpctl fpm pool render api \
  -p PM_MAX_CHILDREN=16 \
  -p ENABLE_PING=true \
  -p ENABLE_METRICS=true
```

---

## Create a pool from the default template

Create a pool in the `available` directory:

```sh
phpctl fpm pool create api
```

Create and enable immediately:

```sh
phpctl fpm pool create api --enable
```

By default this writes the pool config into:

```text
/usr/local/etc/php-fpm.d/available
```

If enabled, `phpctl` links it into:

```text
/usr/local/etc/php-fpm.d
```

---

## Override template parameters inline

You can override any parameter supported by the template using `-p` or `--param`:

```sh
phpctl fpm pool create api \
  -p USER=www-data \
  -p GROUP=www-data \
  -p LISTEN=/var/run/php-fpm-api.sock \
  -p PM_MAX_CHILDREN=16 \
  -p PM_START_SERVERS=4 \
  -p PM_MIN_SPARE_SERVERS=2 \
  -p PM_MAX_SPARE_SERVERS=6 \
  --enable
```

Enable ping and metrics endpoints:

```sh
phpctl fpm pool create api \
  -p ENABLE_PING=true \
  -p ENABLE_METRICS=true \
  --enable
```

This adds:

```ini
ping.path = /fpm-ping
ping.response = pong
pm.status_path = /fpm-status
```

You can also override the defaults for those values:

```sh
phpctl fpm pool create api \
  -p ENABLE_PING=true \
  -p PING_PATH=/ping \
  -p PING_RESPONSE=ok \
  -p ENABLE_METRICS=true \
  -p STATUS_PATH=/status \
  --enable
```

---

## Use a params file

Instead of passing many `-p KEY=VALUE` flags, you can keep parameters in a file.

Example `pool.params`:

```text
USER=www-data
GROUP=www-data
LISTEN=/var/run/php-fpm-api.sock
PM_MAX_CHILDREN=16
PM_START_SERVERS=4
PM_MIN_SPARE_SERVERS=2
PM_MAX_SPARE_SERVERS=6
ENABLE_PING=true
ENABLE_METRICS=true
```

Use it like this:

```sh
phpctl fpm pool create api --params-file pool.params --enable
```

Or preview the config first:

```sh
phpctl fpm pool render api --params-file pool.params
```

---

## Generate a config file for manual editing

If you want `phpctl` to render the config but save it somewhere for later review:

```sh
phpctl fpm pool generate api --output-file /tmp/api.conf
```

With overrides:

```sh
phpctl fpm pool generate api \
  -p PM_MAX_CHILDREN=32 \
  -p ENABLE_PING=true \
  --output-file /tmp/api.conf
```

This is useful when you want to generate a starting point and then edit the resulting file manually.

---

## Use a custom template file

If the built-in template is too small for your use case, provide your own template:

```sh
phpctl fpm pool create api --template /path/to/custom.pool.tpl --enable
```

You can still combine this with inline parameters:

```sh
phpctl fpm pool create api \
  --template /path/to/custom.pool.tpl \
  -p PM_MAX_CHILDREN=32 \
  -p REQUEST_TERMINATE_TIMEOUT=60s \
  --enable
```

### Example custom template

```ini
[{{POOL_NAME}}]
user = {{USER}}
group = {{GROUP}}
listen = {{LISTEN}}
listen.owner = {{LISTEN_OWNER}}
listen.group = {{LISTEN_GROUP}}

pm = {{PM}}
pm.max_children = {{PM_MAX_CHILDREN}}
pm.start_servers = {{PM_START_SERVERS}}
pm.min_spare_servers = {{PM_MIN_SPARE_SERVERS}}
pm.max_spare_servers = {{PM_MAX_SPARE_SERVERS}}

catch_workers_output = {{CATCH_WORKERS_OUTPUT}}
clear_env = {{CLEAR_ENV}}

{{ if ENABLE_PING }}
ping.path = {{ PING_PATH | default("/fpm-ping") }}
ping.response = {{ PING_RESPONSE | default("pong") }}
{{ endif }}

{{ if ENABLE_METRICS }}
pm.status_path = {{ STATUS_PATH | default("/fpm-status") }}
{{ endif }}

{{ if REQUEST_TERMINATE_TIMEOUT }}
request_terminate_timeout = {{REQUEST_TERMINATE_TIMEOUT}}
{{ endif }}

{{ if SLOWLOG }}
slowlog = {{SLOWLOG}}
{{ endif }}

{{ if REQUEST_SLOWLOG_TIMEOUT }}
request_slowlog_timeout = {{REQUEST_SLOWLOG_TIMEOUT}}
{{ endif }}
```

Then you can supply extra params:

```sh
phpctl fpm pool create api \
  --template /path/to/custom.pool.tpl \
  -p REQUEST_TERMINATE_TIMEOUT=60s \
  -p SLOWLOG=/proc/self/fd/2 \
  -p REQUEST_SLOWLOG_TIMEOUT=5s \
  --enable
```

---

## Set a global default custom template

If you want all `phpctl fpm pool create`, `render` and `generate` operations to use your custom template by default, set:

```sh
export PHPCTL_PHP_FPM_POOL_TEMPLATE=/path/to/custom.pool.tpl
```

After that:

```sh
phpctl fpm pool create api --enable
```

will use your custom template automatically.

You can still override it for a single command with `--template`.

---

## Import an existing config file

If you already have a ready PHP-FPM pool config, import it directly:

```sh
phpctl fpm pool import api --from /tmp/api.conf
```

Import and enable immediately:

```sh
phpctl fpm pool import api --from /tmp/api.conf --enable
```

This does not render a template. It simply copies the provided config file into the managed `available` directory.

Use import when:

- you already have a working pool config
- you want to migrate an existing setup into `phpctl`
- you do not need template rendering

Use `create` when:

- you want to generate the pool from parameters
- you want to keep the config reproducible
- you want to use the built-in or custom templating system

---

## Bundle import multiple pools from JSON

You can also import multiple pools from a JSON bundle:

```sh
phpctl fpm pool bundle import --json-file /tmp/pools.json --reload
```

Example JSON:

```json
{
  "enabled": true,
  "pools": [
    {
      "name": "api",
      "params": {
        "PM_MAX_CHILDREN": "16",
        "ENABLE_PING": "true",
        "ENABLE_METRICS": "true"
      }
    },
    {
      "name": "worker",
      "params": {
        "PM_MAX_CHILDREN": "8"
      }
    }
  ]
}
```

You can also specify a custom template per pool:

```json
{
  "enabled": true,
  "pools": [
    {
      "name": "api",
      "template": "/opt/templates/custom.pool.tpl",
      "params": {
        "PM_MAX_CHILDREN": "32",
        "REQUEST_TERMINATE_TIMEOUT": "60s"
      }
    }
  ]
}
```

---

## Template syntax

The pool renderer supports a small template language.

### Variable substitution

```ini
user = {{USER}}
```

### Variables with defaults

```ini
ping.path = {{ PING_PATH | default("/fpm-ping") }}
```

### Conditional blocks

```ini
{{ if ENABLE_PING }}
ping.path = {{ PING_PATH | default("/fpm-ping") }}
ping.response = {{ PING_RESPONSE | default("pong") }}
{{ endif }}
```

Supported conditional styles include:

- `{{ if ENABLE_PING }}`
- `{{ if VAR == "value" }}`
- `{{ if VAR != "value" }}`
- `{{ if empty VAR }}`
- `{{ if not empty VAR }}`

### Truthy values

For boolean-style conditions, these values are treated as true:

- `1`
- `true`
- `yes`
- `on`

---

## Suggested workflow

For simple use cases:

1. start with the built-in template
2. override values using `-p KEY=VALUE`
3. enable the pool
4. reload PHP-FPM if needed

Example:

```sh
phpctl fpm pool create api \
  -p PM_MAX_CHILDREN=16 \
  -p ENABLE_PING=true \
  -p ENABLE_METRICS=true \
  --enable

phpctl fpm reload
```

For advanced use cases:

1. write a custom template
2. render it with `phpctl fpm pool render`
3. create pools with `--template`
4. optionally set `PHPCTL_PHP_FPM_POOL_TEMPLATE` globally
