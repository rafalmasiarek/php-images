# syntax=docker/dockerfile:1.7
FROM php:8.3-cli-alpine3.20 AS builder

ARG PECL_FILE=pecl.txt

RUN set -eux; \
    apk add --no-cache bash ca-certificates tzdata git; \
    apk add --no-cache --virtual .build-deps \
    $PHPIZE_DEPS linux-headers pkgconfig re2c \
    icu-dev libzip-dev zlib-dev bzip2-dev curl-dev openssl-dev oniguruma-dev \
    sqlite-dev postgresql-dev libxml2-dev libxslt-dev tidyhtml-dev gmp-dev \
    freetype-dev libpng-dev libjpeg-turbo-dev gettext-dev \
    openldap-dev imap-dev krb5-dev net-snmp-dev \
    rabbitmq-c-dev libssh2-dev libmemcached-dev \
    imagemagick-dev imagemagick \
    ; \
    \
    docker-php-ext-configure gd --with-freetype --with-jpeg; \
    docker-php-ext-configure imap --with-kerberos --with-imap-ssl; \
    docker-php-ext-configure ldap; \
    \
    docker-php-ext-install -j"$(nproc)" \
    bcmath bz2 calendar \
    curl exif ftp \
    gd gettext gmp \
    intl mbstring mysqli \
    opcache pcntl \
    pdo pdo_mysql pdo_pgsql pdo_sqlite \
    pgsql \
    soap sockets \
    tidy xsl zip \
    snmp imap ldap \
    ; \
    \
    pecl channel-update pecl.php.net; \
    \
    mkdir -p /opt/php-ext/conf.d/available; \
    if [ -d /usr/local/etc/php/conf.d ]; then \
    for f in /usr/local/etc/php/conf.d/*.ini; do \
    [ -e "$f" ] || continue; \
    mv "$f" "/opt/php-ext/conf.d/available/$(basename "$f")"; \
    done; \
    fi; \
    \
    apk del .build-deps

COPY ${PECL_FILE} /tmp/pecl.txt

RUN set -euo pipefail; \
    mods=""; \
    while IFS= read -r line; do \
    line="$(echo "$line" | sed -e 's/#.*$//' -e 's/[[:space:]]*$//' -e 's/^[[:space:]]*//')"; \
    [ -z "$line" ] && continue; \
    mods="$mods $line"; \
    done < /tmp/pecl.txt; \
    if [ -n "${mods// }" ]; then \
    pecl install $mods; \
    docker-php-ext-enable $mods; \
    mkdir -p /opt/php-ext/conf.d/available; \
    if [ -d /usr/local/etc/php/conf.d ]; then \
    for f in /usr/local/etc/php/conf.d/*.ini; do \
    [ -e "$f" ] || continue; \
    mv "$f" "/opt/php-ext/conf.d/available/$(basename "$f")"; \
    done; \
    fi; \
    fi

FROM php:8.3-cli-alpine3.20 AS runtime

RUN set -eux; \
    apk add --no-cache \
    bash ca-certificates tzdata \
    icu-libs libzip zlib bzip2 curl openssl oniguruma \
    sqlite-libs postgresql-libs libxml2 libxslt tidyhtml gmp \
    freetype libpng libjpeg-turbo gettext \
    openldap cyrus-sasl krb5 net-snmp-libs \
    rabbitmq-c libssh2 libmemcached imagemagick

COPY --from=builder /usr/local/lib/php/extensions/ /usr/local/lib/php/extensions/
COPY --from=builder /opt/php-ext/conf.d/available/ /opt/php-ext/conf.d/available/

RUN set -eux; \
    mkdir -p /usr/local/etc/php/conf.d; \
    rm -f /usr/local/etc/php/conf.d/*.ini || true

COPY rootfs/ /