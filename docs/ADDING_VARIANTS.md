# Adding variants (example: cli)

This repo supports multiple official PHP image variants that exist for Alpine, e.g.:

- fpm
- cli

To add a new variant:

1) Create directories:
   versions/<php>/<variant>-alpine/{base,fat}

2) Copy Dockerfile + pecl.txt from an existing variant (e.g. fpm).

3) Add entries in versions.json with:
   - php
   - variant (fpm/cli)
   - alpine_tag (alpine or alpine3.xx)
   - flavor (base/fat)
   - context (path)

The build workflow will automatically pick it up because it uses the matrix from versions.json.
