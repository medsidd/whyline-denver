# Hugging Face Space – Streamlit Deployment

This guide walks through deploying the WhyLine Denver Streamlit app to a Hugging Face
Space so it can be reverse-proxied behind Cloudflare at `https://whylinedenver.com/app`.

## 1. Create the Space
- **Type**: Streamlit
- **Slug**: `whylinedenver` (under your user/org)
- **Hardware**: The default CPU basic is sufficient.
- Leave the SDK version at the latest Streamlit release.

The Space may be linked to this GitHub repo or updated via `git push`.

## 2. Required repository layout
At minimum the Space needs the following tracked files:

```
.
├── app/
│   ├── streamlit_app.py
│   ├── assets/
│   └── components/, utils/, ...
├── dbt/target/{catalog.json, manifest.json, run_results.json, …}
├── src/whylinedenver/  # Python package
├── .streamlit/config.toml
├── pyproject.toml
└── requirements.txt
```

> **Tip**  
> If you only copy a subset of the main repository, ensure `pyproject.toml`, `src/`,
> and `dbt/target` are kept together; `pip install -e .` relies on them to expose the
> `whylinedenver` package and dbt metadata.

## 3. Streamlit configuration
The Space reads the repo’s `.streamlit/config.toml`. The important section is:

```toml
[server]
baseUrlPath = "app"
headless = true
enableCORS = false
port = 7860
```

This makes the app available at `/app`, which matches the Cloudflare Pages reverse
proxy plan. No additional nginx rules are required inside the Space.

## 4. Dependency management
- Copy the root `requirements.txt` into the Space so it installs the same versions as
  local development.
- Hugging Face caches dependencies between builds; subsequent deploys are fast.
- If the build ever times out, remove unused extras (e.g., `black`, `ruff`) from a
  Space-specific copy of `requirements.txt`.

## 5. Secrets and environment variables
Set the following Space secrets as needed:

| Key | Purpose |
| --- | ------- |
| `WHYLINE_ENV` | Set to `prod` to enable production defaults. |
| `WHYLINE_BIGQUERY_SERVICE_ACCOUNT` | Optional – enables the BigQuery engine; paste the JSON service account. |
| `GEMINI_API_KEY` | Optional – enables Gemini SQL generation. |
| `GCS_BUCKET` / `DUCKDB_PATH` | Only needed if overriding default storage locations. |

Environment variables can be set via the Space settings UI or the `.env` file if you
commit one (avoid committing secrets to Git).

## 6. Verifying the build
1. Trigger a Space build (push or “Restart” from the UI).
2. Once live, visit `https://<org>-whylinedenver.hf.space/app`.
3. Confirm that the header, sidebar filters, and DuckDB engine load without errors.
4. If assets fail to load, make sure `app/assets/` is committed and the proxy path is
   `/app/*` in Cloudflare.

When this succeeds the Space is ready for the Cloudflare reverse proxy. The nightly
workflow that refreshes `warehouse.duckdb` can now push directly to the Space repo.
