<section class="grid hero">
  <article>
    <p>
      This repo builds lightweight PHP images on Alpine (amd64/arm64) and publishes them to GHCR.
      Each build runs Trivy scans and publishes HTML reports.
    </p>

    <p class="hero-actions">
      <a href="{{ site.baseurl }}/images" role="button">Browse images catalog</a>
      <a href="{{ site.baseurl }}/reports/" class="secondary" role="button">View Trivy reports</a>
    </p>

    <h3>Quick start</h3>
    <pre class="hero-code"><code>docker pull ghcr.io/rafalmasiarek/php:8.3-cli
docker run --rm -it ghcr.io/rafalmasiarek/php:8.3-cli php -v</code></pre>
  </article>

  <article>
    <header><strong>Status</strong></header>

    <div class="badges">
      <img src="https://github.com/rafalmasiarek/php-images/actions/workflows/build.yml/badge.svg?branch=main" alt="build" loading="lazy" />
      <img src="https://img.shields.io/github/license/rafalmasiarek/php-images" alt="license" loading="lazy" />
      <img src="https://img.shields.io/endpoint?url=https%3A%2F%2Fphp-images.masiarek.dev%2Fbadges%2Ftrivy-total.json" alt="trivy-total" loading="lazy" />
      <img src="https://img.shields.io/endpoint?url=https%3A%2F%2Fphp-images.masiarek.dev%2Fbadges%2Fbuilt.json" alt="built" loading="lazy" />
    </div>

    <hr />

    <p><strong>Registry</strong><br><code>ghcr.io/rafalmasiarek/php</code></p>

    <p><strong>Tag scheme</strong></p>
    <ul>
      <li><code>&lt;php&gt;-&lt;variant&gt;</code> — moving</li>
      <li><code>&lt;php&gt;-&lt;variant&gt;-YYYY-MM-DD</code> — date</li>
      <li><code>&lt;php&gt;-&lt;variant&gt;-sha-&lt;gitsha7&gt;</code> — immutable</li>
    </ul>
  </article>
</section>
