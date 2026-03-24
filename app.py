"""
WaferSort – Interactive wafer filtering app.

Run with:  streamlit run app.py
"""

import io
import re
import streamlit as st
import pandas as pd
import requests
from typing import Optional

# ── Default Google Sheet config ──────────────────────────────────────────────
DEFAULT_SHEET_ID = "1H02GeS8IcWPYkZ69QWR8nspimKJOzNQVeQOYIz9FcLw"
DEFAULT_TABS = {
    "transport":      447846799,
    "iiiv":           209115541,
    "al":             1038107012,
    "afm":            1374164574,
    "sample_tracker": 868222470,
    "optical":        2129612815,
}


def _extract_sheet_id(url_or_id: str) -> Optional[str]:
    """Extract the Google Sheet ID from a URL or return the raw ID."""
    url_or_id = url_or_id.strip()
    if not url_or_id:
        return None
    # Match Google Sheets URL pattern
    m = re.search(r'/spreadsheets/d/([a-zA-Z0-9_-]+)', url_or_id)
    if m:
        return m.group(1)
    # If it looks like a bare ID (alphanumeric, dashes, underscores, ~44 chars)
    if re.match(r'^[a-zA-Z0-9_-]{20,}$', url_or_id):
        return url_or_id
    return None


def _check_sheet_accessible(sheet_id: str) -> tuple[bool, str]:
    """Check if a Google Sheet is publicly accessible. Returns (ok, message)."""
    test_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&tq=select+*+limit+1"
    try:
        resp = requests.get(test_url, timeout=10)
        if resp.status_code == 200:
            return True, "Sheet is accessible."
        elif resp.status_code == 401:
            return False, "This spreadsheet is not publicly viewable. Please open the sheet, click **Share**, and set General access to **Anyone with the link** (Viewer)."
        else:
            return False, f"Could not access sheet (HTTP {resp.status_code}). Check that the URL is correct and the sheet is shared publicly."
    except requests.RequestException as e:
        return False, f"Connection error: {e}"


@st.cache_data(ttl=300)
def _discover_tabs(sheet_id: str) -> dict:
    """
    Discover tab names and gids for a Google Sheet by fetching the htmlview page.
    Falls back to trying the default tab gids if discovery fails.
    """
    # If it's the default sheet, use known gids
    if sheet_id == DEFAULT_SHEET_ID:
        return DEFAULT_TABS

    # Try to discover tabs from htmlview
    try:
        url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/htmlview"
        resp = requests.get(url, timeout=15)
        if resp.status_code == 200:
            # Look for gid values in the page
            gids = re.findall(r'gid[=:](\d+)', resp.text)
            # Look for sheet names near gid references
            name_gid_pairs = re.findall(r'"?sheet-button-(\d+)"?[^>]*>([^<]+)<', resp.text)
            if name_gid_pairs:
                return {name.strip().lower().replace(" ", "_"): int(gid) for gid, name in name_gid_pairs}
            # Fallback: just use unique gids found
            if gids:
                unique_gids = list(dict.fromkeys(gids))  # preserve order, deduplicate
                return {f"sheet_{i}": int(g) for i, g in enumerate(unique_gids)}
    except requests.RequestException:
        pass

    # Last resort: try gid=0
    return {"sheet_0": 0}

# ── Helpers ──────────────────────────────────────────────────────────────────

def _safe_float(val) -> Optional[float]:
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _normalise_sample(name: str) -> str:
    s = str(name).strip()
    if s.upper().startswith("JS"):
        s = s[2:]
    digits = ""
    for ch in s:
        if ch.isdigit():
            digits += ch
        else:
            break
    return digits


def _has_al(sample_name: str) -> bool:
    s = str(sample_name).strip()
    return s.upper().endswith("J")


# ── Data fetching (cached) ───────────────────────────────────────────────────

@st.cache_data(ttl=300)  # Cache for 5 minutes
def fetch_tab(sheet_id: str, tab_name: str, tabs: dict) -> pd.DataFrame:
    gid = tabs[tab_name]
    url = (
        f"https://docs.google.com/spreadsheets/d/{sheet_id}"
        f"/gviz/tq?tqx=out:csv&gid={gid}"
    )
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    return pd.read_csv(io.StringIO(resp.text))


@st.cache_data(ttl=300)
def load_transport(sheet_id: str, tabs: dict) -> pd.DataFrame:
    df = fetch_tab(sheet_id, "transport", tabs)
    cols = df.columns.tolist()
    rename = {}
    for c in cols:
        cl = c.lower()
        if "sample" in cl:
            rename[c] = "sample"
        elif "toploader" in cl:
            rename[c] = "toploader"
        elif "μ_xx" in cl or "mu_xx" in cl:
            rename[c] = "mu_xx"
        elif "μ_yy" in cl or "mu_yy" in cl:
            rename[c] = "mu_yy"
        elif "average" in cl and ("μ" in cl or "mu" in cl):
            rename[c] = "avg_mu"
        elif "mean free path" in cl:
            rename[c] = "mfp_nm"
        elif "n" in cl and "cm" in cl:
            rename[c] = "n_cm2"
        elif "note" in cl:
            rename[c] = "notes"
    df = df.rename(columns=rename)
    keep = [c for c in ["sample", "toploader", "n_cm2", "mu_xx", "mu_yy", "avg_mu", "mfp_nm", "notes"] if c in df.columns]
    df = df[keep].copy()
    df = df.dropna(subset=["sample"])
    df = df[df["sample"].astype(str).str.strip() != ""]
    for col in ["n_cm2", "mu_xx", "mu_yy", "avg_mu", "mfp_nm"]:
        if col in df.columns:
            df[col] = df[col].apply(_safe_float)
    df["wafer_id"] = df["sample"].apply(_normalise_sample)
    df["has_al"] = df["sample"].apply(_has_al)
    return df


@st.cache_data(ttl=300)
def load_al(sheet_id: str, tabs: dict) -> pd.DataFrame:
    df = fetch_tab(sheet_id, "al", tabs)
    cols = df.columns.tolist()
    rename = {}
    for c in cols:
        cl = c.lower().strip()
        if "sample" in cl:
            rename[c] = "sample"
        elif "growth rate" in cl:
            rename[c] = "al_growth_rate"
        elif "est" in cl and "thickness" in cl:
            rename[c] = "al_est_thickness_nm"
        elif "growth time" in cl:
            rename[c] = "al_growth_time"
        elif "avg" in cl:
            rename[c] = "al_resistance_avg"
        elif "north" in cl:
            rename[c] = "al_resistance_n"
        elif "west" in cl:
            rename[c] = "al_resistance_w"
        elif "south" in cl:
            rename[c] = "al_resistance_s"
        elif "east" in cl:
            rename[c] = "al_resistance_e"
        elif "tc" in cl:
            rename[c] = "al_tc_k"
        elif "bc" in cl:
            rename[c] = "al_bc_t"
        elif "measured" in cl and "thickness" in cl:
            rename[c] = "al_measured_thickness_nm"
        elif "wait" in cl:
            rename[c] = "al_wait_time"
    df = df.rename(columns=rename)
    keep = [c for c in [
        "sample", "al_growth_rate", "al_est_thickness_nm", "al_growth_time",
        "al_resistance_n", "al_resistance_w", "al_resistance_s", "al_resistance_e",
        "al_resistance_avg", "al_tc_k", "al_bc_t", "al_measured_thickness_nm"
    ] if c in df.columns]
    df = df[keep].copy()
    df = df.dropna(subset=["sample"])
    df = df[df["sample"].astype(str).str.strip() != ""]
    for col in ["al_growth_rate", "al_est_thickness_nm", "al_resistance_avg",
                 "al_resistance_n", "al_resistance_w", "al_resistance_s", "al_resistance_e",
                 "al_tc_k", "al_bc_t", "al_measured_thickness_nm"]:
        if col in df.columns:
            df[col] = df[col].apply(_safe_float)
    # Compute std of directional resistances (N/W/S/E)
    r_cols = ["al_resistance_n", "al_resistance_w", "al_resistance_s", "al_resistance_e"]
    r_present = [c for c in r_cols if c in df.columns]
    if r_present:
        df["al_resistance_std"] = df[r_present].std(axis=1)
    df["wafer_id"] = df["sample"].apply(_normalise_sample)
    return df


@st.cache_data(ttl=300)
def load_afm(sheet_id: str, tabs: dict) -> pd.DataFrame:
    df = fetch_tab(sheet_id, "afm", tabs)
    cols = df.columns.tolist()
    rename = {}
    for c in cols:
        cl = c.lower().strip()
        if "sample" in cl:
            rename[c] = "sample"
        elif "5x5 min" in cl:
            rename[c] = "afm_5x5_min_nm"
        elif "5x5 max" in cl:
            rename[c] = "afm_5x5_max_nm"
        elif "peak" in cl:
            rename[c] = "afm_peak_to_peak_nm"
        elif "avg" in cl and "roughness" not in cl and "anisotropy" not in cl:
            rename[c] = "afm_avg_nm"
        elif "rms" in cl and "roughness" not in cl and "anisotropy" not in cl:
            rename[c] = "afm_rms_nm"
        elif "20x20 roughness" in cl:
            rename[c] = "afm_20x20_roughness"
        elif "5x5 roughness" in cl:
            rename[c] = "afm_5x5_roughness"
        elif "1x1 roughness" in cl:
            rename[c] = "afm_1x1_roughness"
        elif cl.strip() == "20x20":
            rename[c] = "afm_20x20_img"
        elif cl.strip() == "5x5":
            rename[c] = "afm_5x5_img"
        elif cl.strip() == "1x1":
            rename[c] = "afm_1x1_img"
        elif "110 avg" in cl:
            rename[c] = "afm_110_avg_nm"
        elif "110 rms" in cl:
            rename[c] = "afm_110_rms_nm"
        elif "1-10 avg" in cl:
            rename[c] = "afm_1_10_avg_nm"
        elif "1-10 rms" in cl:
            rename[c] = "afm_1_10_rms_nm"
        elif "anisotropy avg" in cl:
            rename[c] = "afm_anisotropy_avg_nm"
        elif "anisotropy rms" in cl:
            rename[c] = "afm_anisotropy_rms_nm"
        elif "etched" in cl and "20x20 roughness" in cl:
            rename[c] = "afm_etched_20x20_roughness"
        elif "etched" in cl and "5x5 roughness" in cl:
            rename[c] = "afm_etched_5x5_roughness"
        elif "etched" in cl and "1x1 roughness" in cl:
            rename[c] = "afm_etched_1x1_roughness"
        elif "etched" in cl and "20x20" in cl:
            rename[c] = "afm_etched_20x20_img"
        elif "etched" in cl and "5x5" in cl:
            rename[c] = "afm_etched_5x5_img"
        elif "etched" in cl and "1x1" in cl:
            rename[c] = "afm_etched_1x1_img"
    df = df.rename(columns=rename)
    df = df.dropna(subset=["sample"])
    df = df[df["sample"].astype(str).str.strip() != ""]
    # Parse numeric columns
    numeric_cols = [c for c in df.columns if c.startswith("afm_") and "img" not in c]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = df[col].apply(_safe_float)
    df["wafer_id"] = df["sample"].apply(_normalise_sample)
    return df


@st.cache_data(ttl=300)
def load_sample_tracker(sheet_id: str, tabs: dict) -> pd.DataFrame:
    df = fetch_tab(sheet_id, "sample_tracker", tabs)
    cols = df.columns.tolist()
    rename = {}
    for c in cols:
        cl = c.lower().strip()
        if "amount" in cl or "remaining" in cl:
            rename[c] = "amount_remaining"
        elif "piece" in cl:
            rename[c] = "piece"
        elif "who" in cl:
            rename[c] = "who"
        elif "date" in cl:
            rename[c] = "date"
        elif "purpose" in cl:
            rename[c] = "purpose"
        elif "note" in cl:
            rename[c] = "tracker_notes"
    first_col = cols[0]
    if first_col not in rename:
        rename[first_col] = "sample_num"
    df = df.rename(columns=rename)
    keep = [c for c in ["sample_num", "amount_remaining", "piece", "who", "date", "purpose", "tracker_notes"] if c in df.columns]
    df = df[keep].copy()
    df = df.dropna(subset=["sample_num"])
    df = df[df["sample_num"].astype(str).str.strip() != ""]
    df["wafer_id"] = df["sample_num"].astype(str).apply(lambda x: _normalise_sample(x.strip()))
    return df


@st.cache_data(ttl=300)
def load_iiiv(sheet_id: str, tabs: dict) -> pd.DataFrame:
    df = fetch_tab(sheet_id, "iiiv", tabs)
    cols = df.columns.tolist()
    rename = {}
    for c in cols:
        cl = c.lower().strip()
        if "sample" in cl:
            rename[c] = "sample"
        elif "date" in cl:
            rename[c] = "growth_date"
        elif "substrate" in cl:
            rename[c] = "substrate"
        elif "grower" in cl:
            rename[c] = "grower"
        elif "growth layers" in cl or "layer" in cl:
            rename[c] = "growth_layers"
        elif "t_gb" in cl:
            rename[c] = "t_gb"
        elif "si doping" in cl or "doping" in cl:
            rename[c] = "si_doping"
        elif "t_qw" in cl:
            rename[c] = "t_qw"
        elif "comment" in cl:
            rename[c] = "growth_comments"
        elif "block" in cl:
            rename[c] = "block"
    df = df.rename(columns=rename)
    keep = [c for c in ["sample", "growth_date", "substrate", "grower", "growth_layers",
                         "t_gb", "si_doping", "t_qw", "growth_comments", "block"] if c in df.columns]
    df = df[keep].copy()
    df = df.dropna(subset=["sample"])
    df = df[df["sample"].astype(str).str.strip() != ""]
    df["wafer_id"] = df["sample"].apply(_normalise_sample)
    if "growth_layers" in df.columns:
        df["has_al_growth"] = df["growth_layers"].astype(str).str.lower().str.contains("with al", na=False)
    return df


# ── Master table builder ────────────────────────────────────────────────────

@st.cache_data(ttl=300)
def build_master_table(sheet_id: str, tabs: dict) -> pd.DataFrame:
    transport = load_transport(sheet_id, tabs)
    al = load_al(sheet_id, tabs) if "al" in tabs else pd.DataFrame()
    tracker = load_sample_tracker(sheet_id, tabs) if "sample_tracker" in tabs else pd.DataFrame()
    iiiv = load_iiiv(sheet_id, tabs) if "iiiv" in tabs else pd.DataFrame()

    master = transport.copy()

    # Merge Al
    if not al.empty and "wafer_id" in al.columns:
        al_dedup = al.drop_duplicates(subset=["wafer_id"], keep="first")
        master = master.merge(al_dedup.drop(columns=["sample"], errors="ignore"),
                              on="wafer_id", how="left")

    # Merge availability
    if not tracker.empty and "wafer_id" in tracker.columns:
        avail = (
            tracker.groupby("wafer_id")
            .agg(amount_remaining=("amount_remaining", "first"))
            .reset_index()
        )
        master = master.merge(avail.drop_duplicates(subset=["wafer_id"], keep="first"),
                              on="wafer_id", how="left")

    # Merge III-V
    if not iiiv.empty and "wafer_id" in iiiv.columns:
        iiiv_dedup = iiiv.drop_duplicates(subset=["wafer_id"], keep="first")
        iiiv_cols = [c for c in ["wafer_id", "growth_date", "substrate", "grower",
                                  "growth_layers", "t_gb", "t_qw", "si_doping",
                                  "growth_comments", "has_al_growth"] if c in iiiv_dedup.columns]
        master = master.merge(iiiv_dedup[iiiv_cols], on="wafer_id", how="left")

    # Refine has_al
    has_al_from_al_tab = master["al_resistance_avg"].notna() | master.get("al_est_thickness_nm", pd.Series(dtype=float)).notna()
    if "has_al_growth" in master.columns:
        master["has_al"] = (
            master["has_al"]
            | master["has_al_growth"].fillna(False)
            | has_al_from_al_tab
        )
        master = master.drop(columns=["has_al_growth"])
    else:
        master["has_al"] = master["has_al"] | has_al_from_al_tab

    return master


# ── Detail data for a single wafer ──────────────────────────────────────────

def get_wafer_detail(wafer_id: str, sheet_id: str, tabs: dict) -> dict:
    """Gather all available data for a single wafer across all tabs."""
    detail = {}

    # Transport
    transport = load_transport(sheet_id, tabs)
    t_rows = transport[transport["wafer_id"] == wafer_id]
    if not t_rows.empty:
        detail["transport"] = t_rows.iloc[0].to_dict()

    # Al
    if "al" in tabs:
        al = load_al(sheet_id, tabs)
        a_rows = al[al["wafer_id"] == wafer_id]
        if not a_rows.empty:
            detail["al"] = a_rows.iloc[0].to_dict()

    # AFM
    if "afm" in tabs:
        afm = load_afm(sheet_id, tabs)
        afm_rows = afm[afm["wafer_id"] == wafer_id]
        if not afm_rows.empty:
            detail["afm"] = afm_rows.iloc[0].to_dict()

    # III-V growth
    if "iiiv" in tabs:
        iiiv = load_iiiv(sheet_id, tabs)
        g_rows = iiiv[iiiv["wafer_id"] == wafer_id]
        if not g_rows.empty:
            detail["growth"] = g_rows.iloc[0].to_dict()

    # Sample tracker (all entries for this wafer)
    if "sample_tracker" in tabs:
        tracker = load_sample_tracker(sheet_id, tabs)
        tr_rows = tracker[tracker["wafer_id"] == wafer_id]
        if not tr_rows.empty:
            detail["tracker"] = tr_rows.to_dict("records")

    return detail


def fmt(val, unit="") -> str:
    """Format a value for display."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return "—"
    if isinstance(val, float):
        if abs(val) >= 1e4 or (abs(val) < 0.01 and val != 0):
            return f"{val:.2e} {unit}".strip()
        return f"{val:.1f} {unit}".strip()
    return f"{val} {unit}".strip()


# ── Streamlit App ────────────────────────────────────────────────────────────

def main():
    st.set_page_config(page_title="WaferSort", page_icon="🔬", layout="wide")
    st.title("WaferSort")
    st.caption("Filter ShabLab wafers by transport, Al, and availability — data live from Google Sheets")

    # ── Sidebar: Sheet source & filters ──────────────────────────────────
    with st.sidebar:
        st.header("Data Source")
        sheet_input = st.text_input(
            "Google Sheet URL or ID",
            value=f"https://docs.google.com/spreadsheets/d/{DEFAULT_SHEET_ID}/edit",
            help="Paste any publicly viewable Google Sheet URL. The sheet must have a Transport tab with Sample, n, and mobility columns.",
        )

        # Resolve sheet ID
        sheet_id = _extract_sheet_id(sheet_input)
        if not sheet_id:
            st.error("Could not parse a Google Sheet ID from the input. Paste a full URL or sheet ID.")
            return

        # Check accessibility
        accessible, msg = _check_sheet_accessible(sheet_id)
        if not accessible:
            st.warning(msg)
            return

        # Discover tabs
        tabs = _discover_tabs(sheet_id)
        sheet_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit"

        if "transport" not in tabs:
            st.error("Could not find a 'Transport' tab in this sheet. WaferSort requires a Transport tab with Sample, n, and mobility columns.")
            return

        st.divider()
        st.header("Filters")

        st.subheader("Sample Range")
        range_col1, range_col2 = st.columns(2)
        with range_col1:
            sample_min = st.number_input("From sample #", value=0, step=1, min_value=0,
                                          help="e.g. 750 for JS750. 0 = no limit")
        with range_col2:
            sample_max = st.number_input("To sample #", value=0, step=1, min_value=0,
                                          help="e.g. 823 for JS823. 0 = no limit")

        st.subheader("Transport")
        min_mobility = st.number_input("Min avg mobility (cm²/Vs)", value=0, step=1000, min_value=0)
        max_mobility = st.number_input("Max avg mobility (cm²/Vs)", value=0, step=1000, min_value=0,
                                        help="0 = no limit")
        min_density = st.text_input("Min electron density (cm⁻²)", value="", placeholder="e.g. 5e11")
        max_density = st.text_input("Max electron density (cm⁻²)", value="", placeholder="e.g. 1e12")
        min_mfp = st.number_input("Min mean free path (nm)", value=0, step=50, min_value=0)

        st.subheader("Aluminium")
        al_option = st.radio("Al on top", ["Any", "Yes", "No"], horizontal=True)
        max_al_resistance = st.number_input("Max Al resistance avg (Ohm)", value=0.0, step=1.0, min_value=0.0,
                                             help="0 = no limit")
        min_al_thickness = st.number_input("Min Al thickness (nm)", value=0.0, step=5.0, min_value=0.0,
                                            help="0 = no limit")

        st.subheader("Availability")
        available_only = st.checkbox("Only available wafers", value=False)

        st.subheader("Search")
        search_text = st.text_input("Keyword search", value="", placeholder="e.g. JS959")

        st.subheader("Compare Wafer")
        compare_input = st.text_input("Add wafer(s) to compare", value="", placeholder="e.g. JS979, 984, JS1048",
                                       help="Comma-separated list. Looks up wafers even if they don't match filters. Failed criteria are highlighted red.")

        refresh = st.button("Refresh data from sheet")
        if refresh:
            st.cache_data.clear()

    # ── Load & filter ────────────────────────────────────────────────────
    with st.spinner("Fetching data from Google Sheets..."):
        try:
            master = build_master_table(sheet_id, tabs)
        except Exception as e:
            st.error(f"Failed to load data: {e}")
            return

    filtered = master.copy()

    # Apply filters
    # Sample number range
    if sample_min > 0 or sample_max > 0:
        wafer_num = pd.to_numeric(filtered["wafer_id"], errors="coerce")
        if sample_min > 0:
            filtered = filtered[wafer_num >= sample_min]
            wafer_num = pd.to_numeric(filtered["wafer_id"], errors="coerce")
        if sample_max > 0:
            filtered = filtered[wafer_num <= sample_max]

    if min_mobility > 0:
        filtered = filtered[filtered["avg_mu"].notna() & (filtered["avg_mu"] >= min_mobility)]
    if max_mobility > 0:
        filtered = filtered[filtered["avg_mu"].notna() & (filtered["avg_mu"] <= max_mobility)]
    if min_density:
        try:
            v = float(min_density)
            filtered = filtered[filtered["n_cm2"].notna() & (filtered["n_cm2"] >= v)]
        except ValueError:
            st.sidebar.error("Invalid min density format")
    if max_density:
        try:
            v = float(max_density)
            filtered = filtered[filtered["n_cm2"].notna() & (filtered["n_cm2"] <= v)]
        except ValueError:
            st.sidebar.error("Invalid max density format")
    if min_mfp > 0:
        filtered = filtered[filtered["mfp_nm"].notna() & (filtered["mfp_nm"] >= min_mfp)]
    if al_option == "Yes":
        filtered = filtered[filtered["has_al"] == True]
    elif al_option == "No":
        filtered = filtered[filtered["has_al"] == False]
    if max_al_resistance > 0 and "al_resistance_avg" in filtered.columns:
        filtered = filtered[filtered["al_resistance_avg"].notna() & (filtered["al_resistance_avg"] <= max_al_resistance)]
    if min_al_thickness > 0:
        for col in ["al_measured_thickness_nm", "al_est_thickness_nm"]:
            if col in filtered.columns and filtered[col].notna().any():
                filtered = filtered[filtered[col].notna() & (filtered[col] >= min_al_thickness)]
                break
    if available_only:
        filtered = filtered[
            filtered["amount_remaining"].notna()
            & (filtered["amount_remaining"].astype(str).str.strip() != "")
            & (filtered["amount_remaining"].astype(str).str.strip().str.lower() != "none")
        ]
    if search_text:
        pattern = search_text.lower()
        mask = filtered.apply(lambda row: any(pattern in str(v).lower() for v in row.values), axis=1)
        filtered = filtered[mask]

    # Sort by mobility
    filtered = filtered.sort_values("avg_mu", ascending=False, na_position="last")

    # ── Results table ────────────────────────────────────────────────────
    st.subheader(f"Results: {len(filtered)} wafers")

    if filtered.empty:
        st.warning("No wafers match your criteria. Try relaxing the filters.")
        return

    # Build display table
    display_cols = ["sample", "n_cm2", "avg_mu", "mu_xx", "mu_yy", "mfp_nm", "has_al"]
    if al_option != "No":
        for c in ["al_resistance_avg", "al_resistance_std", "al_est_thickness_nm"]:
            if c in filtered.columns:
                display_cols.append(c)
    display_cols.append("amount_remaining")
    display_cols = [c for c in display_cols if c in filtered.columns]

    # Columns to display in scientific notation
    SCI_COLS = {"n_cm2", "avg_mu", "mu_xx", "mu_yy"}

    # Unicode labels look better but crash Safari/older browsers.
    # Default to Unicode; add ?ascii=1 to the URL as an escape hatch.
    force_ascii = st.query_params.get("ascii", "0") == "1"
    if force_ascii:
        RENAME_MAP = {
            "sample": "Sample",
            "n_cm2": "n (cm-2)",
            "avg_mu": "Avg mu (cm2/Vs)",
            "mu_xx": "mu_xx",
            "mu_yy": "mu_yy",
            "mfp_nm": "MFP (nm)",
            "has_al": "Al?",
            "al_resistance_avg": "Al R_avg (Ohm)",
            "al_resistance_std": "Al R_std (Ohm)",
            "al_est_thickness_nm": "Al t_est (nm)",
            "amount_remaining": "Remaining",
        }
    else:
        RENAME_MAP = {
            "sample": "Sample",
            "n_cm2": "n (cm\u207b\u00b2)",
            "avg_mu": "Avg \u03bc (cm\u00b2/Vs)",
            "mu_xx": "\u03bc_xx",
            "mu_yy": "\u03bc_yy",
            "mfp_nm": "MFP (nm)",
            "has_al": "Al?",
            "al_resistance_avg": "Al R_avg (\u03a9)",
            "al_resistance_std": "Al R_std (\u03a9)",
            "al_est_thickness_nm": "Al t_est (nm)",
            "amount_remaining": "Remaining",
        }

    def _format_sci(df, cols_before_rename):
        """Format specified columns as scientific notation strings."""
        out = df.copy()
        for col in cols_before_rename:
            renamed = RENAME_MAP.get(col, col)
            if renamed in out.columns:
                out[renamed] = out[renamed].apply(
                    lambda v: f"{v:.2e}" if pd.notna(v) and isinstance(v, (int, float)) else v
                )
        return out

    display_df = filtered[display_cols].copy()
    display_df = display_df.rename(columns=RENAME_MAP)
    display_df = _format_sci(display_df, SCI_COLS)

    # Show clickable table
    event = st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
    )

    # ── Compare wafers ───────────────────────────────────────────────────
    compare_found_rows = []
    compare_detail_wafer_id = None
    compare_detail_sample = None
    compare_detail_has_al = False
    if compare_input:
        # Parse comma-separated wafer names
        compare_ids = [_normalise_sample(s.strip()) for s in compare_input.split(",") if s.strip()]
        compare_ids = [cid for cid in compare_ids if cid]  # drop empties

        if compare_ids:
            # Helper: determine which renamed columns a row fails
            def _get_failed_cols(r, renamed_cols):
                failed = set()
                wn = pd.to_numeric(r.get("wafer_id"), errors="coerce")
                if sample_min > 0 and (pd.isna(wn) or wn < sample_min):
                    failed.add("Sample")
                if sample_max > 0 and (pd.isna(wn) or wn > sample_max):
                    failed.add("Sample")

                mu = r.get("avg_mu")
                if min_mobility > 0 and (pd.isna(mu) or mu < min_mobility):
                    failed.add(RENAME_MAP["avg_mu"])
                if max_mobility > 0 and (pd.isna(mu) or mu > max_mobility):
                    failed.add(RENAME_MAP["avg_mu"])

                n = r.get("n_cm2")
                if min_density:
                    try:
                        if pd.isna(n) or n < float(min_density):
                            failed.add(RENAME_MAP["n_cm2"])
                    except ValueError:
                        pass
                if max_density:
                    try:
                        if pd.isna(n) or n > float(max_density):
                            failed.add(RENAME_MAP["n_cm2"])
                    except ValueError:
                        pass

                mfp = r.get("mfp_nm")
                if min_mfp > 0 and (pd.isna(mfp) or mfp < min_mfp):
                    failed.add(RENAME_MAP["mfp_nm"])

                has_al_val = r.get("has_al")
                if al_option == "Yes" and not has_al_val:
                    failed.add(RENAME_MAP["has_al"])
                elif al_option == "No" and has_al_val:
                    failed.add(RENAME_MAP["has_al"])

                al_r = r.get("al_resistance_avg")
                if max_al_resistance > 0 and (pd.isna(al_r) or al_r > max_al_resistance):
                    if RENAME_MAP["al_resistance_avg"] in renamed_cols:
                        failed.add(RENAME_MAP["al_resistance_avg"])

                if min_al_thickness > 0:
                    al_t = r.get("al_measured_thickness_nm") if pd.notna(r.get("al_measured_thickness_nm")) else r.get("al_est_thickness_nm")
                    if pd.isna(al_t) or al_t < min_al_thickness:
                        if RENAME_MAP["al_est_thickness_nm"] in renamed_cols:
                            failed.add(RENAME_MAP["al_est_thickness_nm"])

                remaining = str(r.get("amount_remaining", "")).strip().lower()
                if available_only and (not remaining or remaining == "nan" or remaining == "none"):
                    failed.add(RENAME_MAP["amount_remaining"])

                return failed

            # Collect rows and per-row failures
            found_rows = []
            not_found = []
            per_row_failed = []  # list of sets, one per found row

            for cid in compare_ids:
                rows = master[master["wafer_id"] == cid]
                if rows.empty:
                    not_found.append(cid)
                else:
                    found_rows.append(rows.iloc[[0]])
                    per_row_failed.append(_get_failed_cols(rows.iloc[0], set(RENAME_MAP.values())))

            if not_found:
                st.warning(f"Wafer(s) not found: {', '.join(not_found)}")

            compare_found_rows.extend(found_rows)
            if found_rows:
                comp_all = pd.concat(found_rows, ignore_index=True)
                comp_df = comp_all[display_cols].copy()
                comp_renamed = comp_df.rename(columns=RENAME_MAP)
                comp_renamed = _format_sci(comp_renamed, SCI_COLS)

                names = [r.iloc[0]["sample"] for r in found_rows]
                st.divider()
                st.subheader(f"Comparison: {', '.join(names)}")

                # Selectable table with red highlights
                def highlight_failed(row):
                    row_idx = row.name
                    failed = per_row_failed[row_idx] if row_idx < len(per_row_failed) else set()
                    return [
                        "background-color: #ffcccc; color: #cc0000; font-weight: bold" if col in failed else ""
                        for col in row.index
                    ]

                styled = comp_renamed.style.apply(highlight_failed, axis=1)
                compare_event = st.dataframe(
                    styled,
                    use_container_width=True,
                    hide_index=True,
                    on_select="rerun",
                    selection_mode="single-row",
                    key="compare_table_select",
                )

                # Summary
                all_failed = set()
                for f in per_row_failed:
                    all_failed |= f
                if all_failed:
                    st.caption(f"Red cells indicate criteria not met: {', '.join(sorted(all_failed))}")
                all_pass = [names[i] for i, f in enumerate(per_row_failed) if not f]
                if all_pass:
                    st.success(f"Meets all criteria: {', '.join(all_pass)}")

                compare_selected = compare_event.selection.rows if compare_event.selection else []
                if compare_selected:
                    cidx = compare_selected[0]
                    cr = comp_all.iloc[cidx]
                    compare_detail_wafer_id = cr["wafer_id"]
                    compare_detail_sample = cr["sample"]
                    compare_detail_has_al = cr.get("has_al", False)

    # ── Detail panel function ────────────────────────────────────────────
    def render_detail(wafer_id, sample_name, has_al_flag, source_label=""):
        """Render the full detail panel for a wafer."""
        label = f"Wafer Detail: {sample_name}"
        if source_label:
            label += f" ({source_label})"
        st.divider()
        st.header(label)
        st.markdown(f"[View in Google Sheet]({sheet_url})")

        detail = get_wafer_detail(wafer_id, sheet_id, tabs)

        col1, col2, col3 = st.columns(3)

        with col1:
            st.subheader("Transport / Hall")
            t = detail.get("transport", {})
            if t:
                st.metric("Electron density n", fmt(t.get("n_cm2"), "cm⁻²"))
                st.metric("Avg mobility μ", fmt(t.get("avg_mu"), "cm²/Vs"))
                st.metric("μ_xx", fmt(t.get("mu_xx"), "cm²/Vs"))
                st.metric("μ_yy", fmt(t.get("mu_yy"), "cm²/Vs"))
                st.metric("Mean free path", fmt(t.get("mfp_nm"), "nm"))
                if t.get("notes") and str(t.get("notes")) != "nan":
                    st.info(f"**Note:** {t['notes']}")
            else:
                st.caption("No transport data available")

        with col2:
            st.subheader("Aluminium")
            a = detail.get("al", {})
            if a:
                st.metric("Est. thickness", fmt(a.get("al_est_thickness_nm"), "nm"))
                st.metric("Measured thickness", fmt(a.get("al_measured_thickness_nm"), "nm"))
                st.metric("Growth rate", fmt(a.get("al_growth_rate"), "ML/s"))
                st.markdown("**Resistance (Ω):**")
                r_data = {
                    "Direction": ["North", "West", "South", "East", "**Average**", "**Std Dev**"],
                    "R (Ω)": [
                        fmt(a.get("al_resistance_n")),
                        fmt(a.get("al_resistance_w")),
                        fmt(a.get("al_resistance_s")),
                        fmt(a.get("al_resistance_e")),
                        fmt(a.get("al_resistance_avg")),
                        fmt(a.get("al_resistance_std")),
                    ],
                }
                st.table(pd.DataFrame(r_data))
                st.metric("Tc", fmt(a.get("al_tc_k"), "K"))
                st.metric("Bc//", fmt(a.get("al_bc_t"), "T"))
            else:
                if has_al_flag:
                    st.caption("Al wafer — no detailed Al tab data")
                else:
                    st.caption("No Al on this wafer")

        with col3:
            st.subheader("AFM Roughness")
            afm = detail.get("afm", {})
            if afm:
                st.markdown("**5x5 μm scan:**")
                afm_data = {
                    "Metric": ["Min", "Max", "Peak-to-peak", "Average", "RMS"],
                    "Value (nm)": [
                        fmt(afm.get("afm_5x5_min_nm")),
                        fmt(afm.get("afm_5x5_max_nm")),
                        fmt(afm.get("afm_peak_to_peak_nm")),
                        fmt(afm.get("afm_avg_nm")),
                        fmt(afm.get("afm_rms_nm")),
                    ],
                }
                st.table(pd.DataFrame(afm_data))
                roughness_data = {
                    "Scale": ["20x20 μm", "5x5 μm", "1x1 μm"],
                    "Roughness": [
                        fmt(afm.get("afm_20x20_roughness")),
                        fmt(afm.get("afm_5x5_roughness")),
                        fmt(afm.get("afm_1x1_roughness")),
                    ],
                }
                st.table(pd.DataFrame(roughness_data))
                if afm.get("afm_anisotropy_avg_nm") is not None:
                    st.markdown("**Anisotropy:**")
                    st.metric("[110] avg", fmt(afm.get("afm_110_avg_nm"), "nm"))
                    st.metric("[1-10] avg", fmt(afm.get("afm_1_10_avg_nm"), "nm"))
                    st.metric("Anisotropy avg", fmt(afm.get("afm_anisotropy_avg_nm"), "nm"))
                etched_vals = [afm.get("afm_etched_20x20_roughness"),
                               afm.get("afm_etched_5x5_roughness"),
                               afm.get("afm_etched_1x1_roughness")]
                if any(v is not None and not (isinstance(v, float) and pd.isna(v)) for v in etched_vals):
                    st.markdown("**Etched roughness:**")
                    etched_data = {
                        "Scale": ["20x20 μm", "5x5 μm", "1x1 μm"],
                        "Roughness": [
                            fmt(afm.get("afm_etched_20x20_roughness")),
                            fmt(afm.get("afm_etched_5x5_roughness")),
                            fmt(afm.get("afm_etched_1x1_roughness")),
                        ],
                    }
                    st.table(pd.DataFrame(etched_data))
                st.caption("AFM images are embedded in the Google Sheet — click the link above to view them.")
            else:
                st.caption("No AFM data available for this wafer")

        st.divider()
        gcol1, gcol2 = st.columns(2)

        with gcol1:
            st.subheader("Growth Info (III-V)")
            g = detail.get("growth", {})
            if g:
                info_items = [
                    ("Growth date", g.get("growth_date")),
                    ("Substrate", g.get("substrate")),
                    ("Grower", g.get("grower")),
                    ("Growth layers", g.get("growth_layers")),
                    ("T_GB", g.get("t_gb")),
                    ("T_QW", g.get("t_qw")),
                    ("Si Doping", g.get("si_doping")),
                    ("Comments", g.get("growth_comments")),
                ]
                for label, val in info_items:
                    sv = str(val) if val is not None else ""
                    if sv and sv != "nan":
                        st.markdown(f"**{label}:** {sv}")
            else:
                st.caption("No growth data available")

        with gcol2:
            st.subheader("Sample Tracker")
            tracker_entries = detail.get("tracker", [])
            if tracker_entries:
                first = tracker_entries[0]
                rem = first.get("amount_remaining", "")
                if rem and str(rem) != "nan":
                    st.metric("Amount remaining", str(rem))
                else:
                    st.metric("Amount remaining", "Unknown")
                history = [e for e in tracker_entries if str(e.get("who", "")).strip() or str(e.get("purpose", "")).strip()]
                if history:
                    st.markdown("**Usage history:**")
                    hist_df = pd.DataFrame(history)
                    show_cols = [c for c in ["piece", "who", "date", "purpose", "tracker_notes"] if c in hist_df.columns]
                    hist_display = hist_df[show_cols].copy()
                    hist_display = hist_display.rename(columns={
                        "piece": "Piece", "who": "Who", "date": "Date",
                        "purpose": "Purpose", "tracker_notes": "Notes",
                    })
                    hist_display = hist_display[hist_display.apply(
                        lambda r: any(str(v).strip() and str(v) != "nan" for v in r.values), axis=1
                    )]
                    if not hist_display.empty:
                        st.dataframe(hist_display, use_container_width=True, hide_index=True)
            else:
                st.caption("No tracker data available")

    # ── Detail from main results table ───────────────────────────────────
    selected_rows = event.selection.rows if event.selection else []

    if selected_rows:
        idx = selected_rows[0]
        row = filtered.iloc[idx]
        render_detail(row["wafer_id"], row["sample"], row.get("has_al", False))

    # ── Detail from compared wafers ──────────────────────────────────────
    if compare_detail_wafer_id is not None:
        render_detail(compare_detail_wafer_id, compare_detail_sample, compare_detail_has_al, "compared")


if __name__ == "__main__":
    main()
