# Offline Swagger UI assets

Upstream: https://github.com/swagger-api/swagger-ui/tree/v5.33.0

Distribution: https://registry.npmjs.org/swagger-ui-dist/-/swagger-ui-dist-5.33.0.tgz

Only prebuilt UI assets and license/package metadata are vendored. The npm
package is not installed or executed; no npm dependencies or postinstall hooks
are used. Apache-2.0 license and bundled dependency notices are included.

SHA-256:

- swagger-ui-bundle.js: `62df541529080464a7660adc793eab7128c6193ce3be24ddc1e0e0a4a63edc2f`
- swagger-ui.css: `1ac324f7dcd27e4b9386b4bd6421271ec147e922a22c05ba24b11515e9aa6321`

The older Python swagger-ui-bundle package shipped a UI unable to render
FastAPI's OpenAPI 3.1 document. These v5 assets support it. Remote Swagger schema
validation is explicitly disabled. See upstream compatibility documentation and
FastAPI's self-hosting guide:

- https://github.com/swagger-api/swagger-ui#compatibility
- https://fastapi.tiangolo.com/how-to/custom-docs-ui-assets/
