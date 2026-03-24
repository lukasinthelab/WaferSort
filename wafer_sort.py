"""
WaferSort - Filter and search wafers from the ShabLab Google Sheet.

Fetches live data from the TestCharacterizationSummary spreadsheet and lets
you filter wafers by transport properties, Al characteristics, and availability.
"""

import argparse
import io
import sys
import textwrap
from typing import Optional

import pandas as pd
import requests

# ── Google Sheet config ──────────────────────────────────────────────────────
SHEET_ID = "1H02GeS8IcWPYkZ69QWR8nspimKJOzNQVeQOYIz9FcLw"
TABS = {
    "transport":      447846799,
    "iiiv":           209115541,
    "al":             1038107012,
    "afm":            1374164574,
    "sample_tracker": 868222470,
    "optical":        2129612815,
}


def fetch_tab(tab_name: str) -> pd.DataFrame:
    """Download a tab as CSV from Google Sheets and return a DataFrame."""
    gid = TABS[tab_name]
    url = (
        f"https://docs.google.com/spreadsheets/d/{SHEET_ID}"
        f"/gviz/tq?tqx=out:csv&gid={gid}"
    )
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    df = pd.read_csv(io.StringIO(resp.text))
    return df


# ── Parsing helpers ──────────────────────────────────────────────────────────

def _normalise_sample(name: str) -> str:
    """Extract the numeric wafer ID from a sample name like 'JS1070J' -> '1070'."""
    s = str(name).strip()
    # Remove leading "JS" prefix
    if s.upper().startswith("JS"):
        s = s[2:]
    # Remove trailing J (junction/Al marker) and other suffixes
    # Keep just the leading digits
    digits = ""
    for ch in s:
        if ch.isdigit():
            digits += ch
        else:
            break
    return digits


def _safe_float(val) -> Optional[float]:
    """Convert a value to float, returning None on failure."""
    try:
        f = float(val)
        return f
    except (ValueError, TypeError):
        return None


def _has_al(sample_name: str) -> bool:
    """Heuristic: sample names ending with 'J' have Al on top."""
    s = str(sample_name).strip().rstrip(" ")
    return s.upper().endswith("J")


# ── Data loaders ─────────────────────────────────────────────────────────────

def load_transport() -> pd.DataFrame:
    """Load and clean transport data."""
    df = fetch_tab("transport")
    # Fix column names (they may have embedded newlines from merged header rows)
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

    # Keep only relevant columns that exist
    keep = [c for c in ["sample", "toploader", "n_cm2", "mu_xx", "mu_yy", "avg_mu", "mfp_nm", "notes"] if c in df.columns]
    df = df[keep].copy()

    # Drop rows where sample is empty
    df = df.dropna(subset=["sample"])
    df = df[df["sample"].astype(str).str.strip() != ""]

    # Parse numeric columns
    for col in ["n_cm2", "mu_xx", "mu_yy", "avg_mu", "mfp_nm"]:
        if col in df.columns:
            df[col] = df[col].apply(_safe_float)

    # Add wafer_id column
    df["wafer_id"] = df["sample"].apply(_normalise_sample)
    df["has_al"] = df["sample"].apply(_has_al)

    return df


def load_al() -> pd.DataFrame:
    """Load and clean Al tab data."""
    df = fetch_tab("al")
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

    df["wafer_id"] = df["sample"].apply(_normalise_sample)
    return df


def load_sample_tracker() -> pd.DataFrame:
    """Load and clean sample tracker data."""
    df = fetch_tab("sample_tracker")
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
    # First column is the sample number
    first_col = cols[0]
    if first_col not in rename:
        rename[first_col] = "sample_num"
    df = df.rename(columns=rename)

    keep = [c for c in ["sample_num", "amount_remaining", "piece", "who", "date", "purpose", "tracker_notes"] if c in df.columns]
    df = df[keep].copy()

    df = df.dropna(subset=["sample_num"])
    df = df[df["sample_num"].astype(str).str.strip() != ""]

    # Normalise the sample number to just digits
    df["wafer_id"] = df["sample_num"].astype(str).apply(lambda x: x.strip())
    # Some tracker entries are just numbers, some might have JS prefix
    df["wafer_id"] = df["wafer_id"].apply(_normalise_sample)

    return df


def load_iiiv() -> pd.DataFrame:
    """Load and clean III-V materials tab."""
    df = fetch_tab("iiiv")
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

    # Determine has_al from growth_layers column
    if "growth_layers" in df.columns:
        df["has_al_growth"] = df["growth_layers"].astype(str).str.lower().str.contains("with al", na=False)

    return df


# ── Availability aggregator ─────────────────────────────────────────────────

def get_availability(tracker_df: pd.DataFrame) -> pd.DataFrame:
    """
    Summarise tracker into one row per wafer with amount remaining.
    Groups by wafer_id to consolidate multiple entries.
    """
    # Get the first non-empty 'amount_remaining' per wafer
    avail = (
        tracker_df
        .groupby("wafer_id")
        .agg(
            amount_remaining=("amount_remaining", "first"),
            tracker_entries=("wafer_id", "count"),
        )
        .reset_index()
    )
    return avail


# ── Master merge ─────────────────────────────────────────────────────────────

def build_master_table() -> pd.DataFrame:
    """Fetch all tabs and merge into one master table keyed by wafer_id."""
    print("Fetching transport data...", file=sys.stderr)
    transport = load_transport()

    print("Fetching Al data...", file=sys.stderr)
    al = load_al()

    print("Fetching sample tracker...", file=sys.stderr)
    tracker = load_sample_tracker()
    avail = get_availability(tracker)

    print("Fetching III-V growth data...", file=sys.stderr)
    iiiv = load_iiiv()

    # Start with transport as the base
    master = transport.copy()

    # Merge Al data
    al_dedup = al.drop_duplicates(subset=["wafer_id"], keep="first")
    master = master.merge(al_dedup.drop(columns=["sample"], errors="ignore"),
                          on="wafer_id", how="left")

    # Merge availability
    avail_dedup = avail.drop_duplicates(subset=["wafer_id"], keep="first")
    master = master.merge(avail_dedup, on="wafer_id", how="left")

    # Merge III-V growth info
    iiiv_dedup = iiiv.drop_duplicates(subset=["wafer_id"], keep="first")
    iiiv_cols = [c for c in ["wafer_id", "growth_date", "substrate", "grower",
                              "growth_layers", "t_gb", "t_qw", "growth_comments",
                              "has_al_growth"] if c in iiiv_dedup.columns]
    master = master.merge(iiiv_dedup[iiiv_cols], on="wafer_id", how="left")

    # Refine has_al: True if ANY of these indicate Al:
    #  1) Sample name ends in J (name heuristic from transport tab)
    #  2) Growth layers column says "with Al" (III-V tab)
    #  3) Wafer appears in Al tab with resistance data
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


# ── Filter engine ────────────────────────────────────────────────────────────

def apply_filters(df: pd.DataFrame, args) -> pd.DataFrame:
    """Apply CLI filters to the master table."""
    result = df.copy()

    # ── Sample range filter ──────────────────────────────────────────────
    if args.sample_min is not None or args.sample_max is not None:
        wafer_num = pd.to_numeric(result["wafer_id"], errors="coerce")
        if args.sample_min is not None:
            result = result[wafer_num >= args.sample_min]
            wafer_num = pd.to_numeric(result["wafer_id"], errors="coerce")
        if args.sample_max is not None:
            result = result[wafer_num <= args.sample_max]

    # ── Transport filters ────────────────────────────────────────────────
    if args.min_mobility is not None:
        result = result[result["avg_mu"].notna() & (result["avg_mu"] >= args.min_mobility)]

    if args.max_mobility is not None:
        result = result[result["avg_mu"].notna() & (result["avg_mu"] <= args.max_mobility)]

    if args.min_density is not None:
        result = result[result["n_cm2"].notna() & (result["n_cm2"] >= args.min_density)]

    if args.max_density is not None:
        result = result[result["n_cm2"].notna() & (result["n_cm2"] <= args.max_density)]

    if args.min_mfp is not None:
        result = result[result["mfp_nm"].notna() & (result["mfp_nm"] >= args.min_mfp)]

    # ── Al filters ───────────────────────────────────────────────────────
    if args.has_al is not None:
        result = result[result["has_al"] == args.has_al]

    if args.max_al_resistance is not None:
        col = "al_resistance_avg"
        if col in result.columns:
            result = result[result[col].notna() & (result[col] <= args.max_al_resistance)]

    if args.min_al_thickness is not None:
        for col in ["al_measured_thickness_nm", "al_est_thickness_nm"]:
            if col in result.columns:
                result = result[
                    result[col].notna() & (result[col] >= args.min_al_thickness)
                ]
                break

    if args.max_al_resistance is not None and "al_resistance_avg" not in result.columns:
        pass  # column didn't exist, skip silently

    # ── Availability filter ──────────────────────────────────────────────
    if args.available_only:
        # Keep wafers where amount_remaining is NOT "None" and NOT empty
        result = result[
            result["amount_remaining"].notna()
            & (result["amount_remaining"].astype(str).str.strip() != "")
            & (result["amount_remaining"].astype(str).str.strip().str.lower() != "none")
        ]

    # ── Keyword search ───────────────────────────────────────────────────
    if args.search:
        pattern = args.search.lower()
        mask = result.apply(
            lambda row: any(pattern in str(v).lower() for v in row.values), axis=1
        )
        result = result[mask]

    return result


# ── Display ──────────────────────────────────────────────────────────────────

def display_results(df: pd.DataFrame, args):
    """Pretty-print filtered results."""
    if df.empty:
        print("\nNo wafers match your criteria.")
        return

    # Choose columns to display
    display_cols = ["sample", "wafer_id"]

    # Always show transport data if present
    for c in ["n_cm2", "avg_mu", "mu_xx", "mu_yy", "mfp_nm"]:
        if c in df.columns:
            display_cols.append(c)

    # Show Al data if relevant
    if args.has_al is not False:
        for c in ["al_resistance_avg", "al_est_thickness_nm", "al_measured_thickness_nm", "al_tc_k"]:
            if c in df.columns:
                display_cols.append(c)

    display_cols.append("has_al")

    # Show availability
    for c in ["amount_remaining"]:
        if c in df.columns:
            display_cols.append(c)

    # Show notes
    if "notes" in df.columns:
        display_cols.append("notes")

    # Deduplicate while preserving order
    seen = set()
    display_cols = [c for c in display_cols if c in df.columns and not (c in seen or seen.add(c))]

    out = df[display_cols].copy()

    # Sort by avg_mu descending (best mobility first)
    if "avg_mu" in out.columns:
        out = out.sort_values("avg_mu", ascending=False, na_position="last")

    # Limit output
    total = len(out)
    if args.limit and total > args.limit:
        out = out.head(args.limit)

    # Format display
    pd.set_option("display.max_rows", None)
    pd.set_option("display.max_columns", None)
    pd.set_option("display.width", 200)
    pd.set_option("display.max_colwidth", 30)
    pd.set_option("display.float_format", lambda x: f"{x:.2e}" if abs(x) >= 1e4 or (abs(x) < 0.01 and x != 0) else f"{x:.1f}")

    print(f"\n{'='*80}")
    print(f"  WaferSort Results: {len(out)} wafers shown (of {total} matching)")
    print(f"{'='*80}\n")
    print(out.to_string(index=False))
    print()


# ── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="WaferSort - Filter ShabLab wafers by transport, Al, and availability.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
        Examples:
          # High-mobility wafers with Al
          python wafer_sort.py --min-mobility 10000 --has-al

          # High-mobility, low-resistance Al wafers that are available
          python wafer_sort.py --min-mobility 10000 --has-al --max-al-resistance 10 --available

          # All wafers with density > 1e12
          python wafer_sort.py --min-density 1e12

          # Search for a specific wafer
          python wafer_sort.py --search JS959

          # Show top 20 wafers by mobility
          python wafer_sort.py --limit 20
        """),
    )

    # Sample range
    sample = parser.add_argument_group("Sample range")
    sample.add_argument("--sample-min", type=int, metavar="N",
                        help="Minimum sample number (e.g. 750 for JS750)")
    sample.add_argument("--sample-max", type=int, metavar="N",
                        help="Maximum sample number (e.g. 823 for JS823)")

    # Transport filters
    transport = parser.add_argument_group("Transport filters")
    transport.add_argument("--min-mobility", type=float, metavar="N",
                          help="Minimum average mobility (cm^2/Vs)")
    transport.add_argument("--max-mobility", type=float, metavar="N",
                          help="Maximum average mobility (cm^2/Vs)")
    transport.add_argument("--min-density", type=float, metavar="N",
                          help="Minimum electron density (cm^-2)")
    transport.add_argument("--max-density", type=float, metavar="N",
                          help="Maximum electron density (cm^-2)")
    transport.add_argument("--min-mfp", type=float, metavar="N",
                          help="Minimum mean free path (nm)")

    # Al filters
    al_group = parser.add_argument_group("Aluminium filters")
    al_group.add_argument("--has-al", action="store_true", default=None, dest="has_al",
                          help="Only wafers WITH Al on top")
    al_group.add_argument("--no-al", action="store_false", dest="has_al",
                          help="Only wafers WITHOUT Al on top")
    al_group.add_argument("--max-al-resistance", type=float, metavar="N",
                          help="Maximum Al resistance average (Ohm)")
    al_group.add_argument("--min-al-thickness", type=float, metavar="N",
                          help="Minimum Al thickness in nm (measured or estimated)")

    # Availability
    avail = parser.add_argument_group("Availability")
    avail.add_argument("--available", action="store_true", dest="available_only",
                       help="Only show wafers with material remaining")

    # General
    general = parser.add_argument_group("General")
    general.add_argument("--search", type=str, metavar="TEXT",
                        help="Search for text in any field")
    general.add_argument("--limit", type=int, metavar="N", default=50,
                        help="Max rows to display (default: 50)")
    general.add_argument("--all-columns", action="store_true",
                        help="Show all available columns")
    general.add_argument("--csv", action="store_true",
                        help="Output as CSV instead of table")
    general.add_argument("--tabs", action="store_true",
                        help="List available sheet tabs and exit")

    args = parser.parse_args()

    if args.tabs:
        print("Available tabs in TestCharacterizationSummary:")
        for name, gid in TABS.items():
            print(f"  {name:20s}  gid={gid}")
        return

    # Build and filter
    master = build_master_table()
    filtered = apply_filters(master, args)

    if args.csv:
        filtered.to_csv(sys.stdout, index=False)
    elif args.all_columns:
        pd.set_option("display.max_columns", None)
        pd.set_option("display.width", 300)
        print(filtered.to_string(index=False))
    else:
        display_results(filtered, args)


if __name__ == "__main__":
    main()
