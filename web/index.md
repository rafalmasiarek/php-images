---
layout: page
title: PHP Images
subtitle: Alpine-based multi-arch PHP images built in CI with Trivy reports.
---

<div class="hero">
  <div class="card">
    <p>
      This repo builds lightweight PHP images on Alpine (amd64/arm64) and publishes them to GHCR.
      Each build runs Trivy scans and publishes HTML reports.
    </p>

    <p><a href="{{ site.baseurl }}/images">→ Browse images catalog</a></p>
  </div>

  <div class="card">
    <div class="badges">
      <img src="https://github.com/rafalmasiarek/php-images/actions/workflows/build.yml/badge.svg?branch=main" alt="build" loading="lazy" />
      <img src="https://img.shields.io/github/license/rafalmasiarek/php-images" alt="license" loading="lazy" />
      <img src="https://img.shields.io/endpoint?url=https%3A%2F%2Fphp-images.masiarek.dev%2Fbadges%2Ftrivy-total.json" alt="trivy-total" loading="lazy" />
      <img src="https://img.shields.io/endpoint?url=https%3A%2F%2Fphp-images.masiarek.dev%2Fbadges%2Fbuilt.json" alt="built" loading="lazy" />
    </div>

```sh
# Example
docker pull ghcr.io/rafalmasiarek/php:8.3-cli

# Install extra extensions
docker run --rm -it ghcr.io/rafalmasiarek/php:8.3-cli php -v
```
