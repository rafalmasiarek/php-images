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
