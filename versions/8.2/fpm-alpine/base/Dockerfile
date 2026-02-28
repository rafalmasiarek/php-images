# syntax=docker/dockerfile:1.7
ARG BASE_IMAGE

FROM ${BASE_IMAGE} AS builder

RUN apk add --no-cache \
    bash ca-certificates tzdata \
    $PHPIZE_DEPS linux-headers pkgconfig re2c git

RUN apk add --no-cache \
    icu-dev libzip-dev zlib-dev bzip2-dev curl-dev openssl-dev oniguruma-dev \
    sqlite-dev postgresql-dev libxml2-dev libxslt-dev tidyhtml-dev gmp-dev \
    freetype-dev libpng-dev libjpeg-turbo-dev gettext-dev

RUN apk add --no-cache \
    openldap-dev imap-dev krb5-dev net-snmp-dev unixodbc-dev \
    rabbitmq-c-dev libssh2-dev libmemcached-dev \
    imagemagick-dev imagemagick \
    || true

RUN docker-php-ext-configure gd --with-freetype --with-jpeg
RUN if apk info -e imap-dev; then docker-php-ext-configure imap --with-kerberos --with-imap-ssl; fi
RUN if apk info -e openldap-dev; then docker-php-ext-configure ldap; fi

RUN docker-php-ext-install -j"$(nproc)" \
    bcmath bz2 calendar \
    curl exif ftp \
    gd gettext gmp \
    intl mbstring mysqli \
    opcache pcntl \
    pdo pdo_mysql pdo_pgsql pdo_sqlite \
    pgsql \
    soap sockets \
    tidy xsl zip

RUN if apk info -e net-snmp-dev; then docker-php-ext-install snmp; fi
RUN if apk info -e imap-dev; then docker-php-ext-install imap; fi
RUN if apk info -e openldap-dev; then docker-php-ext-install ldap; fi
RUN if apk info -e unixodbc-dev; then \
    export CPPFLAGS="-I/usr/include" LDFLAGS="-L/usr/lib"; \
    docker-php-ext-configure odbc --with-unixODBC=shared,/usr; \
    docker-php-ext-install -j"$(nproc)" odbc; \
    fi

RUN pecl channel-update pecl.php.net
ARG PECL_FILE=pecl.txt
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
    fi

RUN mkdir -p /opt/php-ext/conf.d/available \
    && if [ -d /usr/local/etc/php/conf.d ]; then \
    for f in /usr/local/etc/php/conf.d/*.ini; do \
    [ -e "$f" ] || continue; \
    mv "$f" "/opt/php-ext/conf.d/available/$(basename "$f")"; \
    done; \
    fi

FROM ${BASE_IMAGE} AS runtime

RUN apk add --no-cache \
    bash ca-certificates tzdata \
    icu-libs libzip zlib bzip2 curl openssl oniguruma \
    sqlite-libs postgresql-libs libxml2 libxslt tidyhtml gmp \
    freetype libpng libjpeg-turbo gettext \
    openldap cyrus-sasl krb5 net-snmp-libs unixodbc \
    rabbitmq-c libssh2 libmemcached imagemagick \
    || true

COPY --from=builder /usr/local/lib/php/extensions/ /usr/local/lib/php/extensions/
COPY --from=builder /opt/php-ext/conf.d/available/ /opt/php-ext/conf.d/available/

RUN mkdir -p /usr/local/etc/php/conf.d \
    && rm -f /usr/local/etc/php/conf.d/*.ini || true

COPY rootfs/ /
