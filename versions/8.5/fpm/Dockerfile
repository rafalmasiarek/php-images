# syntax=docker/dockerfile:1.23
FROM php:8.5.4-fpm-alpine3.23 AS builder

ARG PECL_FILE=pecl.txt
ARG PHPCTL_VERSION=0.3.6

COPY ${PECL_FILE} /tmp/pecl.txt

RUN set -eux; \
  apk add --no-cache bash ca-certificates tzdata git curl; \
  curl -fsSL -o /usr/local/bin/phpctl "https://github.com/rafalmasiarek/php-images/releases/download/phpctl-v${PHPCTL_VERSION}/phpctl"; \
  curl -fsSL -o /tmp/phpctl.sha256 "https://github.com/rafalmasiarek/php-images/releases/download/phpctl-v${PHPCTL_VERSION}/phpctl.sha256"; \
  awk '{print $1 "  /usr/local/bin/phpctl"}' /tmp/phpctl.sha256 | sha256sum -c -; \
  chmod +x /usr/local/bin/phpctl; \
  rm -f /tmp/phpctl.sha256; \
  phpctl version; \
  apk add --no-cache --virtual .build-deps \
    $PHPIZE_DEPS linux-headers pkgconfig re2c \
    icu-dev libzip-dev zlib-dev bzip2-dev curl-dev openssl-dev oniguruma-dev \
    sqlite-dev postgresql-dev libxml2-dev libxslt-dev tidyhtml-dev gmp-dev \
    freetype-dev libpng-dev libjpeg-turbo-dev gettext-dev \
    openldap-dev imap-dev krb5-dev net-snmp-dev \
    rabbitmq-c-dev libssh2-dev libmemcached-dev \
    imagemagick-dev imagemagick; \
  phpctl ext install gd --type core --jobs "$(nproc)" --configure --with-freetype --configure --with-jpeg --verbose --no-cleanup; \
  phpctl ext install ldap --type core --jobs "$(nproc)" --verbose --no-cleanup; \
  phpctl ext install \
    bcmath bz2 calendar \
    curl exif ftp \
    gettext gmp \
    intl mysqli \
    pcntl \
    pdo_mysql pdo_pgsql \
    pgsql \
    soap sockets \
    tidy xsl zip \
    snmp \
    --type core --jobs "$(nproc)" --verbose --no-cleanup; \
  sed -e 's/#.*$//' -e 's/[[:space:]]*$//' -e 's/^[[:space:]]*//' /tmp/pecl.txt \
    | sed '/^$/d' \
    | xargs -r phpctl ext install --verbose --no-cleanup; \
  phpctl ext cleanup; \
  apk del .build-deps

FROM php:8.5.4-fpm-alpine3.23 AS runtime

RUN set -eux; \
  apk add --no-cache \
    bash ca-certificates tzdata curl \
    icu-libs libzip zlib bzip2 openssl oniguruma \
    sqlite-libs postgresql-libs libxml2 libxslt tidyhtml gmp \
    freetype libpng libjpeg-turbo gettext \
    openldap cyrus-sasl krb5 net-snmp-libs \
    rabbitmq-c libssh2 libmemcached imagemagick

COPY --from=builder /usr/local/bin/phpctl /usr/local/bin/phpctl
COPY --from=builder /usr/local/lib/php/extensions/ /usr/local/lib/php/extensions/
COPY --from=builder /usr/local/etc/php/conf.d/available/ /usr/local/etc/php/conf.d/available/
COPY .hotfixes-selected/ /opt/hotfixes-selected/
COPY rootfs/ /

RUN set -eux; \
  phpctl version; \
  mkdir -p /usr/local/etc/php/conf.d /usr/local/etc/php/conf.d/available; \
  rm -f /usr/local/etc/php/conf.d/docker-php-ext-*.ini || true; \
  rm -f /usr/local/etc/php/conf.d/zz-*.ini || true; \
  if [ -d /opt/hotfixes-selected ]; then \
    find /opt/hotfixes-selected -maxdepth 1 -type f -name '*.sh' | sort | while read -r f; do \
      echo "[hotfix] loading: $f"; \
      chmod +x "$f"; \
      /bin/sh "$f"; \
    done; \
  fi

COPY .lifecycle.env /usr/local/share/php-image-lifecycle.env

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD ["php-fpm"]
