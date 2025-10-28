# WhyLine Denver App Structure

The Streamlit application has been refactored into a clean, modular component-based architecture for better maintainability and extensibility.

## Directory Structure

```
app/
├── streamlit_app.py          # Main entry point (~100 lines)
├── streamlit_app_old.py      # Backup of monolithic version (1,254 lines)
│
├── components/               # UI Components
│   ├── __init__.py
│   ├── branding.py           # CSS, header, footer, brand constants
│   ├── charts.py             # Chart building logic
│   ├── prebuilt_questions.py # Prebuilt question buttons
│   ├── question_input.py     # Step 1: Natural language input
│   ├── sql_editor.py         # Step 2: SQL review and validation
│   ├── results_viewer.py     # Step 3: Results display
│   └── sidebar.py            # Sidebar with filters and controls
│
├── utils/                    # Utility Functions
│   ├── __init__.py
│   ├── data_loaders.py       # Load routes, weather, dates, models
│   ├── filters.py            # SQL WHERE clause injection
│   ├── formatting.py         # Bytes/timestamp formatting
│   └── session.py            # Session state initialization
│
└── assets/
    └── whylinedenver-logo@512.png
```

---

## Component Responsibilities

### Main Entry Point

**`streamlit_app.py`** (~100 lines)
- **Purpose**: Orchestrate all components
- **Responsibilities**:
  - Page configuration
  - Load models and build guardrails
  - Call component render functions in sequence
  - Pass data between components

**Example flow**:
```python
# Initialize
branding.inject_custom_css()
branding.render_header()
session.initialize()

# Sidebar
engine, filters = sidebar.render()

# Main content
prebuilt_questions.render(engine, models, guardrail_config)
question = question_input.render(engine, filters, schema_brief, models, guardrail_config)
sql_editor.render(engine, models, guardrail_config)
results_viewer.render(engine, question, models, guardrail_config, allowlist)

# Footer
branding.render_footer()
```

---

### Components

#### `branding.py`
**Exports**:
- `BRAND_PRIMARY`, `BRAND_ACCENT`, `BRAND_SUCCESS`, `BRAND_WARNING`, `BRAND_ERROR`, `BRAND_NAME`, `BRAND_TAGLINE`
- `CHART_COLORS` - 5-color sequential palette
- `inject_custom_css()` - Apply vintage transit CSS theme
- `render_header()` - Branded header with logo
- `render_footer()` - Footer with attributions

**Why separate?**
- Theming is a cross-cutting concern used by all components
- Brand constants are referenced in charts, buttons, alerts
- Easy to swap out themes or A/B test different color schemes

#### `charts.py`
**Exports**:
- `build_chart(df: pd.DataFrame) -> alt.Chart | None`

**Why separate?**
- Chart logic is complex (150+ lines)
- Reusable across different result types
- Phase 9 will add heatmaps and small multiples here

#### `sidebar.py`
**Exports**:
- `render() -> tuple[str, dict]` - Returns `(engine, filters_dict)`

**Responsibilities**:
- Engine selector (DuckDB vs BigQuery)
- Date range, routes, stop ID, weather filters
- Active Filters summary
- Freshness indicators
- Resources links

**Why separate?**
- Sidebar is self-contained with complex state management
- Filters logic is independent of main content
- Easy to add new filter types without touching main app

#### `prebuilt_questions.py`
**Exports**:
- `PREBUILT` - List of (label, SQL) tuples
- `render(engine, models, guardrail_config) -> None`

**Why separate?**
- Prebuilt questions are a distinct feature
- Easy to add new questions without cluttering main app
- Can be disabled/enabled per deployment

#### `question_input.py` (Step 1)
**Exports**:
- `render(engine, filters, schema_brief, models, guardrail_config) -> str`

**Responsibilities**:
- Natural language text area
- "Generate SQL" button
- LLM prompt construction
- SQL caching and validation
- Filter injection

**Why separate?**
- Complex LLM integration logic
- Handles both cache hits and fresh generation
- Independent of SQL editing and execution

#### `sql_editor.py` (Step 2)
**Exports**:
- `render(engine, models, guardrail_config) -> None`

**Responsibilities**:
- Editable SQL text area
- Real-time validation
- BigQuery bytes estimation
- Query explanation display

**Why separate?**
- SQL validation is complex
- BigQuery dry-run logic is specific to this step
- Easy to add syntax highlighting or autocomplete later

#### `results_viewer.py` (Step 3)
**Exports**:
- `render(engine, question, models, guardrail_config, allowlist) -> None`

**Responsibilities**:
- "Run Query" button
- Query execution (DuckDB or BigQuery)
- Results caching
- Results table display
- Chart rendering (via `charts.build_chart()`)
- CSV download button

**Why separate?**
- Query execution logic is isolated
- Easy to add new export formats (Excel, Parquet, etc.)
- Can split into sub-components for Phase 9 enhancements

---

### Utils

#### `data_loaders.py`
**Exports**:
- `load_allowed_models()` - Load dbt artifacts
- `load_route_options(engine)` - Populate route filter
- `load_weather_bins(engine)` - Populate weather filter
- `load_service_date_range(engine)` - Get min/max dates
- `read_duckdb_freshness()` - DuckDB sync timestamp
- `read_bigquery_freshness()` - BigQuery build timestamp

**Why separate?**
- Data loading is slow (database queries)
- All functions are cached with `@st.cache_data`
- Reusable across sidebar and main content

#### `filters.py`
**Exports**:
- `add_filter_clauses(sql, filters)` - Inject WHERE conditions
- `_inject_condition(sql, column, condition)` - Smart SQL injection

**Why separate?**
- SQL manipulation is error-prone
- Reusable in LLM generation and manual editing
- Easy to unit test independently

#### `formatting.py`
**Exports**:
- `human_readable_bytes(value)` - Format bytes as KB/MB/GB
- `format_timestamp(ts)` - ISO timestamp to readable string

**Why separate?**
- Pure utility functions
- No Streamlit dependencies
- Easy to unit test

#### `session.py`
**Exports**:
- `initialize()` - Initialize session state defaults

**Why separate?**
- Session state is global and used everywhere
- Centralized initialization prevents bugs
- Easy to add new state variables

---

## Benefits of This Structure

### 1. **Maintainability**
- **Before**: 1,254 lines in one file - hard to navigate
- **After**: No file >150 lines - easy to understand

### 2. **Testability**
- Each component can be unit tested independently
- Pure functions in `utils/` have no Streamlit dependencies
- Easy to mock components in integration tests

### 3. **Extensibility** (Phase 9 features)
- **Add heatmap**: Create `components/heatmap.py`, call from `results_viewer.py`
- **Add CSV export**: Enhance `results_viewer.render()` only
- **Add new filter**: Modify `sidebar.render()` and `filters.add_filter_clauses()`

### 4. **Team Collaboration**
- Multiple developers can work on different components
- Git conflicts are rare (each person edits different files)
- Code reviews are easier (smaller, focused PRs)

### 5. **Reusability**
- `charts.py` can be used in future dashboards
- `filters.py` logic could power a REST API
- `branding.py` can be shared across multiple Streamlit apps

---

## Migration Notes

### For Developers
- **Old app preserved**: `streamlit_app_old.py` (backup)
- **New app active**: `streamlit_app.py` (101 lines)
- **No functionality changed**: All features work identically
- **Imports**: Use `from components import branding` and `from utils import session`

### For Future Features
When adding a new feature:

1. **Identify the component**:
   - UI change? Add to appropriate `components/*.py`
   - Data loading? Add to `utils/data_loaders.py`
   - SQL manipulation? Add to `utils/filters.py`

2. **Create new component if needed**:
   ```python
   # app/components/heatmap.py
   def render(df: pd.DataFrame) -> None:
       """Render heatmap visualization."""
       # Implementation here
   ```

3. **Import and call in main**:
   ```python
   # app/streamlit_app.py
   from components import heatmap

   # In results section:
   if st.checkbox("Show heatmap"):
       heatmap.render(results_df)
   ```

---

## Testing Strategy

### Component Tests
```python
# tests/test_charts.py
from app.components.charts import build_chart

def test_build_chart_time_series():
    df = pd.DataFrame({
        "service_date_mst": ["2025-01-01", "2025-01-02"],
        "pct_on_time": [85.0, 90.0],
        "route_id": ["1", "1"]
    })
    chart = build_chart(df)
    assert chart is not None
    assert chart.mark == "line"
```

### Utility Tests
```python
# tests/test_filters.py
from app.utils.filters import add_filter_clauses

def test_add_filter_clauses_date_range():
    sql = "SELECT * FROM mart_reliability_by_route_day ORDER BY service_date_mst"
    filters = {"start_date": "2025-01-01", "end_date": "2025-01-31"}
    result = add_filter_clauses(sql, filters)
    assert "service_date_mst BETWEEN DATE '2025-01-01' AND DATE '2025-01-31'" in result
```

### Integration Tests
```bash
# Syntax check
python -m py_compile app/streamlit_app.py

# Import check
python -c "from app.components import branding, sidebar"

# Full app smoke test
streamlit run app/streamlit_app.py --server.headless=true
```

---

## Performance Considerations

### Caching Strategy
- **Data loaders**: `@st.cache_data` with TTL=60s for freshness
- **dbt models**: `@st.cache_data` (immutable, cache forever)
- **Query results**: In-memory dict cache (session-scoped)

### Import Optimization
- Components import only what they need
- Streamlit imports isolated to component files
- Faster startup time (no circular imports)

### Code Splitting
- Lazy loading possible: Import components only when needed
- Reduces memory footprint for simple queries

---

## Future Architecture Improvements

### Phase 9 Enhancements
1. **Add `components/heatmap.py`** - Spatial reliability heatmap
2. **Add `components/small_multiples.py`** - Weather impact charts
3. **Add `components/export_modal.py`** - Full mart CSV download with safety caps

### Phase 10 (Production)
1. **Add `components/auth.py`** - User authentication (if deploying to Hugging Face with auth)
2. **Add `utils/telemetry.py`** - Usage analytics and error tracking
3. **Add `tests/integration/`** - End-to-end Streamlit tests

### Post-Launch
1. **Split results_viewer**: `components/results_table.py`, `components/download.py`
2. **Add component library**: Reusable widgets for other transit apps
3. **API layer**: Expose components as REST endpoints (FastAPI)

---

## FAQs

**Q: Why not use Streamlit's native `@st.fragment` for components?**
A: We're using Python modules for better IDE support, testing, and version control. Fragments are great for performance but harder to test independently.

**Q: Can I still use the old monolithic version?**
A: Yes! `streamlit_app_old.py` is preserved as a backup. Run with `streamlit run app/streamlit_app_old.py`.

**Q: How do I add a new component?**
A: Create `app/components/my_feature.py`, add a `render()` function, import in `streamlit_app.py`, and call it where needed.

**Q: Do I need to update tests?**
A: The refactoring is transparent to end-users, but you should add unit tests for new components in `tests/`.

**Q: What if I want to revert the refactoring?**
A: Run `cp streamlit_app_old.py streamlit_app.py` to restore the old version.

---

## Related Documentation

- [README.md](../README.md) - Project overview and quickstart
- [ARCHITECTURE.md](ARCHITECTURE.md) - Data pipeline architecture
- [QA_Validation_Guide.md](QA_Validation_Guide.md) - Testing procedures
- [THEMING.md](THEMING.md) - Brand identity and visual design