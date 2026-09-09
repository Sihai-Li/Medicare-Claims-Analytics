"""Profile CMS synthetic Medicare claims files and build a concise dictionary."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
from pathlib import Path
import zipfile

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RAW_DIR = ROOT / "data" / "raw"
DEFAULT_REPORT_DIR = ROOT / "reports"
DEFAULT_DOCS_DIR = ROOT / "docs"
CHUNK_SIZE = 100_000
SAMPLE_LIMIT = 50_000


DATASET_INFO = {
    "beneficiary": ("Master Beneficiary Summary", "one beneficiary per reference year"),
    "carrier": ("Carrier", "professional-service claim line"),
    "dme": ("Durable Medical Equipment", "DME claim line"),
    "hha": ("Home Health Agency", "home-health claim line"),
    "hospice": ("Hospice", "hospice claim line"),
    "inpatient": ("Inpatient", "inpatient claim line"),
    "outpatient": ("Outpatient", "outpatient claim line"),
    "snf": ("Skilled Nursing Facility", "SNF claim line"),
    "pde": ("Part D Event", "prescription drug event"),
}

FIELD_DEFINITIONS = {
    "BENE_ID": ("key", "Synthetic beneficiary identifier used to link enrollment and claims."),
    "CLM_ID": ("key", "Claim identifier; it may repeat because a claim can contain multiple service lines."),
    "PDE_ID": ("key", "Unique Part D prescription drug event identifier."),
    "BENE_ENROLLMT_REF_YR": ("date", "Reference year for the beneficiary enrollment record."),
    "BENE_BIRTH_DT": ("date", "Beneficiary date of birth."),
    "BENE_DEATH_DT": ("date", "Beneficiary date of death when present."),
    "AGE_AT_END_REF_YR": ("dimension", "Age at the end of the beneficiary reference year."),
    "SEX_IDENT_CD": ("dimension", "CMS sex identification code."),
    "BENE_RACE_CD": ("dimension", "CMS beneficiary race code."),
    "RTI_RACE_CD": ("dimension", "Research Triangle Institute race code."),
    "STATE_CODE": ("dimension", "Beneficiary state code."),
    "COUNTY_CD": ("dimension", "Beneficiary county code."),
    "ZIP_CD": ("dimension", "Beneficiary ZIP code; retain as text to preserve leading zeros."),
    "ESRD_IND": ("dimension", "End-stage renal disease indicator."),
    "ENTLMT_RSN_ORIG": ("dimension", "Original reason for Medicare entitlement."),
    "ENTLMT_RSN_CURR": ("dimension", "Current reason for Medicare entitlement."),
    "BENE_HI_CVRAGE_TOT_MONS": ("metric", "Months of Part A hospital-insurance coverage in the reference year."),
    "BENE_SMI_CVRAGE_TOT_MONS": ("metric", "Months of Part B supplementary-medical-insurance coverage."),
    "BENE_HMO_CVRAGE_TOT_MONS": ("metric", "Months of HMO or managed-care coverage."),
    "PTD_PLAN_CVRG_MONS": ("metric", "Months of Part D plan coverage."),
    "DUAL_ELGBL_MONS": ("metric", "Months with Medicare-Medicaid dual eligibility."),
    "CLM_FROM_DT": ("date", "First service date represented by the claim."),
    "CLM_THRU_DT": ("date", "Last service date represented by the claim."),
    "CLM_ADMSN_DT": ("date", "Inpatient admission date."),
    "NCH_BENE_DSCHRG_DT": ("date", "Beneficiary discharge date recorded on the claim."),
    "SRVC_DT": ("date", "Date of the Part D prescription drug event."),
    "CLM_PMT_AMT": ("metric", "Medicare payment amount at the claim level; deduplicate claim headers before aggregation."),
    "CLM_TOT_CHRG_AMT": ("metric", "Total provider charge at the claim level; deduplicate claim headers before aggregation."),
    "CLM_UTLZTN_DAY_CNT": ("metric", "Utilization-day count reported on an institutional claim."),
    "PTNT_DSCHRG_STUS_CD": ("dimension", "Patient discharge status code."),
    "PRVDR_NUM": ("dimension", "CMS provider number on an institutional claim."),
    "PRVDR_STATE_CD": ("dimension", "Provider state code."),
    "ORG_NPI_NUM": ("dimension", "Organization National Provider Identifier."),
    "RNDRNG_PHYSN_NPI": ("dimension", "Rendering clinician National Provider Identifier."),
    "PRNCPAL_DGNS_CD": ("diagnosis", "Principal diagnosis code for the claim."),
    "ADMTG_DGNS_CD": ("diagnosis", "Diagnosis code recorded at admission."),
    "ICD_DGNS_CD1": ("diagnosis", "First additional diagnosis code."),
    "CLM_LINE_NUM": ("key", "Institutional claim line number."),
    "LINE_NUM": ("key", "Carrier or DME claim line number."),
    "HCPCS_CD": ("procedure", "HCPCS procedure or service code reported on the claim line."),
    "LINE_SRVC_CNT": ("metric", "Number of services represented by a carrier or DME line."),
    "LINE_ALOWD_CHRG_AMT": ("metric", "Allowed charge amount at the service-line level."),
    "LINE_NCH_PMT_AMT": ("metric", "Medicare payment amount at the service-line level."),
    "LINE_BENE_PMT_AMT": ("metric", "Beneficiary payment amount at the service-line level."),
    "REV_CNTR_TOT_CHRG_AMT": ("metric", "Total charge amount for an institutional revenue-center line."),
    "PROD_SRVC_ID": ("drug", "Product or service identifier, generally an NDC for Part D events."),
    "QTY_DSPNSD_NUM": ("metric", "Quantity dispensed for the Part D event."),
    "DAYS_SUPLY_NUM": ("metric", "Days of medication supply dispensed."),
    "PTNT_PAY_AMT": ("metric", "Amount paid by the patient for the Part D event."),
    "CVRD_D_PLAN_PD_AMT": ("metric", "Covered amount paid by the Part D plan."),
    "NCVRD_PLAN_PD_AMT": ("metric", "Non-covered amount paid by the plan."),
    "TOT_RX_CST_AMT": ("metric", "Total prescription cost for the Part D event."),
    "BRND_GNRC_CD": ("dimension", "Brand-versus-generic drug indicator."),
}

IMPORTANT_FIELDS = set(FIELD_DEFINITIONS)
SERVICE_DATE_CANDIDATES = ["CLM_FROM_DT", "CLM_THRU_DT", "SRVC_DT"]


def dataset_key(path: Path) -> str:
    name = path.stem.lower()
    if name.startswith("beneficiary_"):
        return "beneficiary"
    if name.startswith("inpatient"):
        return "inpatient"
    return name


def semantic_type(column: str) -> str:
    if column in FIELD_DEFINITIONS:
        return FIELD_DEFINITIONS[column][0]
    if column.endswith("_DT") or "_YR" in column:
        return "date"
    if column.endswith("_AMT") or column.endswith("_CNT") or column.endswith("_NUM"):
        return "numeric candidate"
    if column.endswith("_ID") or "NPI" in column:
        return "identifier"
    if column.endswith("_CD") or column.endswith("_SW") or column.endswith("_IND"):
        return "coded dimension"
    return "text or coded value"


def profile_csv(path: Path, master_beneficiaries: set[str]) -> tuple[dict, list[dict]]:
    key = dataset_key(path)
    label, grain = DATASET_INFO.get(key, (key.title(), "source row"))
    header = pd.read_csv(path, sep="|", nrows=0).columns.tolist()
    missing = pd.Series(0, index=header, dtype="int64")
    rows = 0
    beneficiaries: set[str] = set()
    record_ids: set[str] = set()
    record_field = "PDE_ID" if "PDE_ID" in header else "CLM_ID" if "CLM_ID" in header else "BENE_ID"
    date_fields = [c for c in SERVICE_DATE_CANDIDATES if c in header]
    min_date = None
    max_date = None
    sample_parts: list[pd.DataFrame] = []
    sampled = 0

    for chunk in pd.read_csv(
        path,
        sep="|",
        dtype=str,
        keep_default_na=False,
        chunksize=CHUNK_SIZE,
        low_memory=False,
    ):
        rows += len(chunk)
        missing = missing.add((chunk == "").sum(), fill_value=0).astype("int64")
        if "BENE_ID" in chunk:
            beneficiaries.update(v for v in chunk["BENE_ID"] if v)
        if record_field in chunk:
            record_ids.update(v for v in chunk[record_field] if v)
        for field in date_fields:
            parsed = pd.to_datetime(chunk[field], errors="coerce")
            chunk_min, chunk_max = parsed.min(), parsed.max()
            if pd.notna(chunk_min) and (min_date is None or chunk_min < min_date):
                min_date = chunk_min
            if pd.notna(chunk_max) and (max_date is None or chunk_max > max_date):
                max_date = chunk_max
        if sampled < SAMPLE_LIMIT:
            take = min(SAMPLE_LIMIT - sampled, len(chunk))
            sample_parts.append(chunk.iloc[:take].copy())
            sampled += take

    sample = pd.concat(sample_parts, ignore_index=True) if sample_parts else pd.DataFrame(columns=header)
    column_rows = []
    for position, column in enumerate(header, start=1):
        non_null = rows - int(missing[column])
        sample_nonblank = sample.loc[sample[column] != "", column]
        column_rows.append(
            {
                "file": path.name,
                "dataset": label,
                "column_position": position,
                "column_name": column,
                "semantic_type": semantic_type(column),
                "important_for_mvp": column in IMPORTANT_FIELDS,
                "non_blank_rows": non_null,
                "blank_rows": int(missing[column]),
                "blank_pct": round(100 * int(missing[column]) / rows, 2) if rows else 0,
                "distinct_in_first_50000_rows": int(sample_nonblank.nunique()),
                "sample_value": sample_nonblank.iloc[0] if len(sample_nonblank) else "",
            }
        )

    unique_records = len(record_ids)
    summary = {
        "file": path.name,
        "dataset": label,
        "grain": grain,
        "size_mb": round(path.stat().st_size / 1_048_576, 2),
        "rows": rows,
        "columns": len(header),
        "unique_beneficiaries": len(beneficiaries),
        "record_id_field": record_field,
        "unique_records": unique_records,
        "rows_per_record": round(rows / unique_records, 2) if unique_records else None,
        "service_date_min": min_date.date().isoformat() if min_date is not None else "",
        "service_date_max": max_date.date().isoformat() if max_date is not None else "",
        "unmatched_beneficiary_ids": len(beneficiaries - master_beneficiaries) if key != "beneficiary" else 0,
    }
    return summary, column_rows


def collect_master_beneficiaries(csv_paths: list[Path]) -> set[str]:
    identifiers: set[str] = set()
    for path in csv_paths:
        if dataset_key(path) != "beneficiary":
            continue
        for chunk in pd.read_csv(path, sep="|", dtype=str, usecols=["BENE_ID"], keep_default_na=False, chunksize=CHUNK_SIZE):
            identifiers.update(v for v in chunk["BENE_ID"] if v)
    return identifiers


def profile_archives(raw_dir: Path) -> pd.DataFrame:
    rows = []
    for path in sorted(raw_dir.glob("*.zip")):
        with zipfile.ZipFile(path) as archive:
            bad_member = archive.testzip()
            for member in archive.infolist():
                rows.append(
                    {
                        "archive": path.name,
                        "archive_size_mb": round(path.stat().st_size / 1_048_576, 2),
                        "valid_crc": bad_member is None,
                        "member": member.filename,
                        "member_size_mb": round(member.file_size / 1_048_576, 2),
                    }
                )
    return pd.DataFrame(rows)


def build_dictionary(column_profile: pd.DataFrame) -> pd.DataFrame:
    available = column_profile[column_profile["column_name"].isin(IMPORTANT_FIELDS)][
        ["dataset", "column_name"]
    ].drop_duplicates()
    rows = []
    for column_name, group in available.groupby("column_name"):
        role, definition = FIELD_DEFINITIONS[column_name]
        rows.append(
            {
                "column_name": column_name,
                "field_role": role,
                "plain_language_definition": definition,
                "analysis_note": "Keep as text" if role in {"key", "dimension", "diagnosis", "procedure", "drug"} else "Parse as date" if role == "date" else "Convert to numeric after validation",
                "available_in": "; ".join(sorted(group["dataset"].unique())),
            }
        )
    return pd.DataFrame(rows).sort_values(["field_role", "column_name"])


def write_dictionary_markdown(dictionary: pd.DataFrame, output: Path) -> None:
    lines = [
        "# Concise CMS data dictionary",
        "",
        "This dictionary contains the fields selected for the first analytical model.",
        "Code values should be interpreted using the official CMS/CCW codebooks.",
        "",
        markdown_table(dictionary),
        "",
    ]
    output.write_text("\n".join(lines), encoding="utf-8")


def markdown_table(frame: pd.DataFrame) -> str:
    """Render a small DataFrame as Markdown without an optional dependency."""
    display = frame.fillna("").astype(str)
    headers = display.columns.tolist()
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for values in display.itertuples(index=False, name=None):
        escaped = [value.replace("|", "\\|").replace("\n", " ") for value in values]
        lines.append("| " + " | ".join(escaped) + " |")
    return "\n".join(lines)


def write_markdown(
    summary: pd.DataFrame,
    archives: pd.DataFrame,
    master_beneficiary_count: int,
    output: Path,
) -> None:
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    total_rows = int(summary["rows"].sum())
    min_date = summary.loc[summary["service_date_min"] != "", "service_date_min"].min()
    max_date = summary.loc[summary["service_date_max"] != "", "service_date_max"].max()
    lines = [
        "# CMS synthetic Medicare data profile",
        "",
        f"Generated: {generated}",
        "",
        "## Overview",
        "",
        f"- CSV source files: {len(summary):,}",
        f"- Total source rows: {total_rows:,}",
        f"- Unique beneficiaries across enrollment files: {master_beneficiary_count:,}",
        f"- Claims service-date coverage: {min_date} through {max_date}",
        f"- ZIP archives inspected: {len(archives):,}",
        "",
        "## Dataset inventory",
        "",
        markdown_table(summary),
        "",
        "## Initial quality findings",
        "",
        "- All source files use the pipe (`|`) delimiter.",
        "- Identifiers and coded fields must be loaded as text to preserve leading zeros.",
        "- Claim files contain service lines, so row counts are not claim counts; use distinct `CLM_ID`.",
        "- Claim-level payment and charge values may repeat across lines and must be deduplicated before aggregation.",
        "- 2023 claims are partial because the available service dates end in early March 2023.",
        "- Synthetic results demonstrate methods and should not be interpreted as real Medicare population estimates.",
        "",
        "## Generated artifacts",
        "",
        "- `dataset_profile.csv`: dataset-level size, grain, dates, and identifiers.",
        "- `column_profile.csv`: completeness and sample cardinality for every source field.",
        "- `archive_profile.csv`: ZIP member inventory and CRC validation.",
        "- `../docs/data_dictionary.csv`: curated fields for the planned analytical model.",
        "- `../docs/data_dictionary.md`: human-readable version of the curated dictionary.",
        "",
    ]
    output.write_text("\n".join(lines), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument("--docs-dir", type=Path, default=DEFAULT_DOCS_DIR)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    raw_dir = args.raw_dir.resolve()
    report_dir = args.report_dir.resolve()
    docs_dir = args.docs_dir.resolve()
    csv_paths = sorted(raw_dir.glob("*.csv"))
    if not csv_paths:
        raise FileNotFoundError(f"No CSV files found in {raw_dir}")

    report_dir.mkdir(parents=True, exist_ok=True)
    docs_dir.mkdir(parents=True, exist_ok=True)
    master_beneficiaries = collect_master_beneficiaries(csv_paths)
    summaries: list[dict] = []
    columns: list[dict] = []
    for path in csv_paths:
        print(f"Profiling {path.name} ...", flush=True)
        summary, column_rows = profile_csv(path, master_beneficiaries)
        summaries.append(summary)
        columns.extend(column_rows)

    summary_df = pd.DataFrame(summaries)
    column_df = pd.DataFrame(columns)
    archive_df = profile_archives(raw_dir)
    dictionary_df = build_dictionary(column_df)

    summary_df.to_csv(report_dir / "dataset_profile.csv", index=False, quoting=csv.QUOTE_MINIMAL)
    column_df.to_csv(report_dir / "column_profile.csv", index=False, quoting=csv.QUOTE_MINIMAL)
    archive_df.to_csv(report_dir / "archive_profile.csv", index=False, quoting=csv.QUOTE_MINIMAL)
    dictionary_df.to_csv(docs_dir / "data_dictionary.csv", index=False, quoting=csv.QUOTE_MINIMAL)
    write_dictionary_markdown(dictionary_df, docs_dir / "data_dictionary.md")
    write_markdown(
        summary_df,
        archive_df,
        len(master_beneficiaries),
        report_dir / "data_profile.md",
    )
    print(f"Profiled {len(summary_df)} CSV files and wrote reports to {report_dir}")


if __name__ == "__main__":
    main()
