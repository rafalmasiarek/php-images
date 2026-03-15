# syntax=docker/dockerfile:1.22
FROM php:8.3.30-cli-alpine3.22 AS builder

ARG PECL_FILE=pecl.txt
ARG PHPCTL_VERSION=0.3.2

COPY rootfs/ /
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
    phpctl ext install gd --type core --jobs "$(nproc)" --configure --with-freetype --configure --with-jpeg; \
    phpctl ext install imap --type core --jobs "$(nproc)" --configure --with-kerberos --configure --with-imap-ssl; \
    phpctl ext install ldap --type core --jobs "$(nproc)"; \
    for ext in \
    bcmath bz2 calendar \
    curl exif ftp \
    gettext gmp \
    intl mbstring mysqli \
    opcache pcntl \
    pdo pdo_mysql pdo_pgsql pdo_sqlite \
    pgsql \
    soap sockets \
    tidy xsl zip \
    snmp \
    ; do \
    phpctl ext install "$ext" --type core --jobs "$(nproc)"; \
    done; \
    pecl channel-update pecl.php.net; \
    sed -e 's/#.*$//' -e 's/[[:space:]]*$//' -e 's/^[[:space:]]*//' /tmp/pecl.txt | sed '/^$/d' | while IFS= read -r ext; do \
    [ -n "${ext}" ] || continue; \
    phpctl ext install "${ext}"; \
    done; \
    apk del .build-deps

FROM php:8.3.30-cli-alpine3.22 AS runtime

ARG PHPCTL_VERSION=0.3.2

RUN set -eux; \
    apk add --no-cache \
    bash ca-certificates tzdata curl \
    icu-libs libzip zlib bzip2 openssl oniguruma \
    sqlite-libs postgresql-libs libxml2 libxslt tidyhtml gmp \
    freetype libpng libjpeg-turbo gettext \
    openldap cyrus-sasl krb5 net-snmp-libs \
    rabbitmq-c libssh2 libmemcached imagemagick; \
    curl -fsSL -o /usr/local/bin/phpctl "https://github.com/rafalmasiarek/php-images/releases/download/phpctl-v${PHPCTL_VERSION}/phpctl"; \
    curl -fsSL -o /tmp/phpctl.sha256 "https://github.com/rafalmasiarek/php-images/releases/download/phpctl-v${PHPCTL_VERSION}/phpctl.sha256"; \
    awk '{print $1 "  /usr/local/bin/phpctl"}' /tmp/phpctl.sha256 | sha256sum -c -; \
    chmod +x /usr/local/bin/phpctl; \
    rm -f /tmp/phpctl.sha256; \
    phpctl version

COPY --from=builder /usr/local/lib/php/extensions/ /usr/local/lib/php/extensions/
COPY --from=builder /opt/php-ext/conf.d/available/ /opt/php-ext/conf.d/available/
COPY .hotfixes-selected/ /opt/hotfixes-selected/
COPY .lifecycle.env /usr/local/share/php-image-lifecycle.env
COPY rootfs/ /

RUN set -eux; \
    mkdir -p /usr/local/etc/php/conf.d; \
    rm -f /usr/local/etc/php/conf.d/*.ini || true; \
    if [ -d /opt/hotfixes-selected ]; then \
    find /opt/hotfixes-selected -maxdepth 1 -type f -name '*.sh' | sort | while read -r f; do \
    echo "[hotfix] loading: $f"; \
    chmod +x "$f"; \
    /bin/sh "$f"; \
    done; \
    fi

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD ["php", "-a"]