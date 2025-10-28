# WhyLine Denver — Theming & Branding Guide

**Last Updated:** 2025-10-27
**Status:** ✅ Complete (Phase 8, 9, 10)

---

## Overview

WhyLine Denver features a custom **"Vintage Transit"** visual identity designed to be professional, accessible, and distinctive—moving far beyond typical Streamlit app aesthetics. The design evokes vintage transit signage and mid-century public infrastructure while maintaining modern usability.

---

## Design Philosophy

**Core Principles:**
- **Professional-Fun Retro:** Inspired by 1950s-60s public transit posters and signage
- **Easy on the Eyes:** Warm, muted tones instead of harsh blacks and bright blues
- **Accessible to All:** Works for both technical and non-technical users
- **Not Streamlit-looking:** Heavy CSS overrides to create a custom web app feel

**Tagline:** *"Ask anything about Denver transit — in your own words"*

---

## Color Palette

### Vintage Transit Colors

**Primary & Accent:**
```css
--primary:   #87a7b3  /* Dusty Sky Blue - vintage transit signage */
--accent:    #d4a574  /* Vintage Gold - warm, retro, inviting */
```

**Semantic Colors:**
```css
--success:   #a3b88c  /* Sage Green - positive metrics, on-time */
--warning:   #e8b863  /* Soft Amber - attention, delays */
--error:     #c77f6d  /* Terra Cotta - critical, failures */
```

**Backgrounds (Warm Dark):**
```css
--bg-primary:    #232129  /* Deep Plum-Gray - main background */
--bg-secondary:  #322e38  /* Card/Panel background */
--bg-tertiary:   #1a171d  /* Sidebar, code blocks */
--border:        #433f4c  /* Subtle dividers */
```

**Text:**
```css
--text-primary:    #e8d5c4  /* Warm Cream - primary text (like aged paper) */
--text-secondary:  #c4b5a0  /* Muted Beige - labels, secondary */
--text-muted:      #9a8e7e  /* Soft Brown-Gray - captions, hints */
```

### Chart Palette

For data visualizations, we use a 5-color sequential palette:

```python
CHART_COLORS = [
    "#87a7b3",  # Dusty Sky Blue (primary)
    "#a3b88c",  # Sage Green (success)
    "#d4a574",  # Vintage Gold (accent)
    "#e8b863",  # Soft Amber (warning)
    "#c77f6d",  # Terra Cotta (error)
]
```

**Usage:**
- **Route delay charts:** Green → Amber → Red gradient
- **Time series:** Multi-line charts use all 5 colors
- **Bar charts:** Gradient from primary to accent

---

## Typography

### Font Stack

**Headers (Space Grotesk):**
- Geometric sans-serif with a retro-modern feel
- Used for: Page title, section headers (h1, h2, h3), button labels
- Loaded via Google Fonts: `Space Grotesk (400, 500, 600, 700)`

**Body (Inter):**
- Clean, highly readable professional sans-serif
- Used for: Body text, inputs, labels, tooltips
- Loaded via Google Fonts: `Inter (300, 400, 500, 600)`

**Code (JetBrains Mono):**
- Monospace font for SQL code blocks
- Fallback: `Courier New, monospace`

### Type Scale

```css
h1: 2.5rem (40px)   - Page title, gradient text
h2: 1.75rem (28px)  - Section headers (Accent color)
h3: 1.25rem (20px)  - Sub-sections (Success color)
body: 1rem (16px)   - Default text
caption: 0.875rem (14px) - Hints, footnotes
```

---

## Visual Components

### 1. Branded Header

**Location:** Top of app, immediately after page load
**Components:**
- Logo (80px height, PNG @512px resolution)
- App name with gradient text (Primary → Accent)
- Tagline in muted beige

**Styling:**
- Gradient background: `rgba(135, 167, 179, 0.08)` → `rgba(212, 165, 116, 0.05)`
- Border: 1px solid border color
- Border radius: 12px
- Padding: 1.5rem
- Drop shadow on logo

**Fallback:** If logo not found, displays 🚌 emoji + text-only header

---

### 2. Buttons

**Default Buttons:**
- Gradient: Primary → Accent
- Text: Dark background color (#232129)
- Border radius: 8px
- Padding: 0.6rem × 1.5rem
- Font: Space Grotesk, 600 weight
- Hover: Lift effect (translateY -2px) + enhanced shadow

**Primary Buttons (Generate SQL, Run Query):**
- Gradient: Accent → Warning (more eye-catching)
- Font weight: 700 (bold)
- Same hover/active states

**Download Button:**
- Border: 2px solid Success color
- Background: Secondary background
- Hover: Fills with Success color, inverts text

---

### 3. Input Fields

**Text Inputs, Textareas, Selects:**
- Background: Secondary background (#322e38)
- Border: 2px solid border color (#433f4c)
- Border radius: 8px
- Font: Inter
- Focus: Border changes to Primary color + subtle glow

**Multiselect Tags:**
- Background: Primary color
- Text: Dark background
- Font weight: 500

---

### 4. Sidebar

**Styling:**
- Background: Tertiary background (#1a171d) - darker than main
- Border-right: 1px solid border color
- Section headers (h2): Accent color, 1.5rem

**Contents:**
- Engine selector (DuckDB / BigQuery)
- Date range picker
- Route multiselect
- Stop ID search
- Weather bins filter
- Freshness timestamps
- Resources links

---

### 5. Charts (Altair)

All charts are styled consistently:

**Axes:**
- Label color: Secondary text (#c4b5a0)
- Title color: Primary text (#e8d5c4)
- Grid color: Border color (#433f4c)

**Titles:**
- Color: Accent (#d4a574)
- Font: Space Grotesk, 18px
- Anchor: start (left-aligned)

**Bars:**
- Corner radius: 4px
- Color scales: Use brand colors (see Chart Palette above)

**Lines:**
- Stroke width: 3px
- Point size: 80
- Color scales: Use CHART_COLORS for multi-line

---

### 6. Alerts & Status Messages

**Success (✓):**
- Background: `rgba(163, 184, 140, 0.1)`
- Border-left: 4px solid Success color
- Text: Success color

**Warning (⚠):**
- Background: `rgba(232, 184, 99, 0.1)`
- Border-left: 4px solid Warning color
- Text: Warning color

**Error (❌):**
- Background: `rgba(199, 127, 109, 0.1)`
- Border-left: 4px solid Error color
- Text: Error color

**Info (ℹ️, ⚡):**
- Background: `rgba(135, 167, 179, 0.1)`
- Border-left: 4px solid Primary color
- Text: Primary color

---

### 7. Footer

**Location:** Bottom of page after results
**Content:**
- App name + attribution ("Built with ♥")
- Data source links (RTD, Denver Open Data, NOAA, Census)
- GitHub + dbt docs links

**Styling:**
- Centered text
- Muted text color (#9a8e7e)
- Links: Primary/Accent colors
- Padding: 2rem vertical

---

## Implementation Files

### Configuration

1. **`.streamlit/config.toml`** - Base Streamlit theme
   ```toml
   [theme]
   primaryColor = "#87a7b3"
   backgroundColor = "#232129"
   secondaryBackgroundColor = "#322e38"
   textColor = "#e8d5c4"
   font = "sans serif"
   ```

2. **`.env` / `.env.example`** - Brand variables
   ```bash
   APP_BRAND_NAME=WhyLine Denver
   APP_TAGLINE=Ask anything about Denver transit — in your own words
   APP_PRIMARY_COLOR=#87a7b3
   APP_ACCENT_COLOR=#d4a574
   APP_SUCCESS_COLOR=#a3b88c
   APP_WARNING_COLOR=#e8b863
   APP_ERROR_COLOR=#c77f6d
   ```

### App Code

3. **`app/streamlit_app.py`** - Main theming implementation
   - Lines 37-49: Brand constants from env vars
   - Lines 62-282: `inject_custom_css()` - Heavy CSS overrides
   - Lines 285-331: `render_branded_header()` - Logo + title
   - Lines 335-336: Apply theming on load
   - Lines 527-674: `build_chart()` - Branded Altair charts
   - Lines 1038-1063: Footer with attributions

### Assets

4. **`app/assets/`** - Logo files
   ```
   whylinedenver-logo.svg       (2.7MB - vector)
   whylinedenver-logo@512.png   (234KB)
   whylinedenver-logo@1024.png  (801KB)
   whylinedenver-logo@2048.png  (2.0MB)
   whylinedenver-logo@4096.png  (5.2MB)
   ```

   **Usage:** App loads `@512.png` by default (good balance of quality/size)

---

## CSS Overrides

### Hidden Streamlit Elements

```css
#MainMenu { visibility: hidden; }     /* Hamburger menu */
footer { visibility: hidden; }         /* "Made with Streamlit" */
header { visibility: hidden; }         /* Default header */
```

### Custom Styling

- **Block container:** Reduced padding, full width
- **Buttons:** Gradient backgrounds, hover lift effects
- **Inputs:** Custom borders, focus states
- **Dataframes:** Rounded corners
- **Expanders:** Custom background, Space Grotesk font
- **Code blocks:** Tertiary background, Sage Green text
- **Dividers:** Border color, 2rem margin

---

## Testing Checklist

✅ Logo displays in header (80px height)
✅ Gradient text on app name (Primary → Accent)
✅ Tagline shows in header
✅ All buttons use gradient backgrounds
✅ Primary buttons (Generate SQL, Run Query) use Accent → Warning gradient
✅ Input fields have custom borders and focus states
✅ Sidebar has darker background than main content
✅ Charts use brand colors (not default Altair blue)
✅ Chart axes/titles use custom colors and Space Grotesk font
✅ Success/Warning/Error/Info alerts have correct colors
✅ Footer displays with attribution links
✅ Streamlit branding (menu, footer) is hidden
✅ Google Fonts (Space Grotesk, Inter) load correctly

---

## Browser Compatibility

**Tested on:**
- Chrome/Edge (Chromium) ✅
- Firefox ✅
- Safari ✅

**Known Issues:**
- `-webkit-background-clip` (gradient text) may not work on older browsers
  - Fallback: Solid Primary color text

---

## Customization Guide

### Change Brand Colors

1. Edit `.env`:
   ```bash
   APP_PRIMARY_COLOR=#your-color
   APP_ACCENT_COLOR=#your-color
   # ... etc
   ```

2. Restart Streamlit:
   ```bash
   make app
   ```

### Change Logo

1. Replace files in `app/assets/`:
   - Recommended: PNG at 512px width minimum
   - Transparent background preferred
   - SVG supported but must be < 256KB

2. Update logo path in `streamlit_app.py` (line 287):
   ```python
   logo_path = Path(__file__).parent / "assets" / "your-logo.png"
   ```

### Change Fonts

Edit `inject_custom_css()` in `streamlit_app.py` (line 68):

```python
@import url('https://fonts.googleapis.com/css2?family=YourFont&display=swap');
```

Then update CSS selectors:
```python
font-family: 'YourFont', sans-serif !important;
```

---

## Performance Notes

- **CSS:** Injected once on page load (~15KB uncompressed)
- **Logo:** Base64-encoded PNG loaded from disk (234KB for @512)
- **Google Fonts:** ~50KB total for Space Grotesk + Inter
- **Total Overhead:** ~300KB initial load (minimal impact)

**Optimization:**
- Logo cached by browser after first load
- CSS inlined (no external stylesheet HTTP request)
- Fonts loaded async via Google Fonts CDN

---

## Attribution

**Design & Implementation:**
WhyLine Denver Branding System v1.0 (2025)

**Inspiration:**
- Vintage RTD transit maps (1960s-1970s)
- Mid-century public infrastructure signage
- Modern data visualization best practices (Edward Tufte, Nate Silver)

**Tools:**
- Streamlit 1.37+ (base framework)
- Altair (declarative visualization)
- Google Fonts (typography)
- Custom CSS3 (theming)

---

## Future Enhancements

**Potential Improvements:**
- [ ] Dark/light mode toggle
- [ ] High-contrast accessibility mode
- [ ] Animated logo on hover
- [ ] Custom loading spinners with brand colors
- [ ] PDF export with branded header/footer
- [ ] Custom error pages (404, 500) with branding

---

**For questions or customization requests, see [README.md](../README.md) or open an issue on GitHub.**
