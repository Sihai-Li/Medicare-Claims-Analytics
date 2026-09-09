"""Build and validate the longitudinal beneficiary_year analytical table."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import re
import sqlite3

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RAW_DIR = ROOT / "data" / "raw"
DEFAULT_PROCESSED_DIR = ROOT / "data" / "processed"
DEFAULT_REPORT_DIR = ROOT / "reports"
DEFAULT_DOCS_DIR = ROOT / "docs"
DEFAULT_DDL = ROOT / "sql" / "01_create_beneficiary_year.sql"

SOURCE_TO_TARGET = {
    "BENE_ID": "beneficiary_id",
    "BENE_ENROLLMT_REF_YR": "reference_year",
    "STATE_CODE": "state_code",
    "COUNTY_CD": "county_code",
    "ZIP_CD": "zip_code",
    "BENE_BIRTH_DT": "birth_date",
    "BENE_DEATH_DT": "death_date",
    "AGE_AT_END_REF_YR": "age_at_year_end",
    "SEX_IDENT_CD": "sex_code",
    "BENE_RACE_CD": "race_code",
    "RTI_RACE_CD": "rti_race_code",
    "ENTLMT_RSN_ORIG": "original_entitlement_reason_code",
    "ENTLMT_RSN_CURR": "current_entitlement_reason_code",
    "ESRD_IND": "esrd_indicator",
    "BENE_HI_CVRAGE_TOT_MONS": "part_a_coverage_months",
    "BENE_SMI_CVRAGE_TOT_MONS": "part_b_coverage_months",
    "BENE_STATE_BUYIN_TOT_MONS": "state_buyin_months",
    "BENE_HMO_CVRAGE_TOT_MONS": "hmo_coverage_months",
    "PTD_PLAN_CVRG_MONS": "part_d_coverage_months",
    "RDS_CVRG_MONS": "retiree_drug_subsidy_months",
    "DUAL_ELGBL_MONS": "dual_eligible_months",
    "COVSTART": "coverage_start_date",
    "ENRL_SRC": "enrollment_source",
    "SAMPLE_GROUP": "sample_group",
    "ENHANCED_FIVE_PERCENT_FLAG": "enhanced_five_percent_flag",
    "CRNT_BIC_CD": "current_bic_code",
    "VALID_DEATH_DT_SW": "valid_death_date_flag",
}

TEXT_COLUMNS = [
    "beneficiary_id",
    "state_code",
    "county_code",
    "zip_code",
    "sex_code",
    "race_code",
    "rti_race_code",
    "original_entitlement_reason_code",
    "current_entitlement_reason_code",
    "esrd_indicator",
    "enrollment_source",
    "sample_group",
    "enhanced_five_percent_flag",
    "current_bic_code",
    "valid_death_date_flag",
]

INTEGER_COLUMNS = [
    "reference_year",
    "age_at_year_end",
    "part_a_coverage_months",
    "part_b_coverage_months",
    "state_buyin_months",
    "hmo_coverage_months",
    "part_d_coverage_months",
    "retiree_drug_subsidy_months",
    "dual_eligible_months",
]

DATE_COLUMNS = ["birth_date", "death_date", "coverage_start_date"]
COVERAGE_COLUMNS = [
    "part_a_coverage_months",
    "part_b_coverage_months",
    "state_buyin_months",
    "hmo_coverage_months",
    "part_d_coverage_months",
    "retiree_drug_subsidy_months",
    "dual_eligible_months",
]

SCHEMA_DEFINITIONS = {
    "beneficiary_id": ("TEXT", "Primary key", "Synthetic beneficiary identifier used across CMS files."),
    "reference_year": ("INTEGER", "Primary key", "Calendar year represented by the enrollment record."),
    "state_code": ("TEXT", "Dimension", "CMS beneficiary state code."),
    "county_code": ("TEXT", "Dimension", "CMS beneficiary county code."),
    "zip_code": ("TEXT", "Dimension", "Beneficiary ZIP code; stored as text to preserve leading zeros."),
    "birth_date": ("DATE", "Dimension", "Beneficiary date of birth in ISO format."),
    "death_date": ("DATE", "Dimension", "Beneficiary date of death when present, in ISO format."),
    "age_at_year_end": ("INTEGER", "Dimension", "Beneficiary age at the end of the reference year."),
    "sex_code": ("TEXT", "Dimension", "CMS sex identification code."),
    "race_code": ("TEXT", "Dimension", "CMS beneficiary race code."),
    "rti_race_code": ("TEXT", "Dimension", "Research Triangle Institute race code."),
    "original_entitlement_reason_code": ("TEXT", "Dimension", "Original reason for Medicare entitlement."),
    "current_entitlement_reason_code": ("TEXT", "Dimension", "Current reason for Medicare entitlement."),
    "esrd_indicator": ("TEXT", "Dimension", "End-stage renal disease indicator."),
    "part_a_coverage_months": ("INTEGER", "Measure", "Months with Part A coverage during the year."),
    "part_b_coverage_months": ("INTEGER", "Measure", "Months with Part B coverage during the year."),
    "state_buyin_months": ("INTEGER", "Measure", "Months with state buy-in coverage during the year."),
    "hmo_coverage_months": ("INTEGER", "Measure", "Months with HMO or managed-care coverage."),
    "part_d_coverage_months": ("INTEGER", "Measure", "Months with Part D plan coverage."),
    "retiree_drug_subsidy_months": ("INTEGER", "Measure", "Months with retiree drug subsidy coverage."),
    "dual_eligible_months": ("INTEGER", "Measure", "Months with Medicare-Medicaid dual eligibility."),
    "coverage_start_date": ("DATE", "Dimension", "Coverage start date supplied by the source."),
    "enrollment_source": ("TEXT", "Lineage", "Enrollment source code."),
    "sample_group": ("TEXT", "Lineage", "Synthetic sample group identifier."),
    "enhanced_five_percent_flag": ("TEXT", "Lineage", "Enhanced five-percent sample flag."),
    "current_bic_code": ("TEXT", "Dimension", "Current beneficiary identification code."),
    "valid_death_date_flag": ("TEXT", "Quality", "Source indicator for a validated death date."),
    "source_file": ("TEXT", "Lineage", "Raw file from which the row was loaded."),
}


def clean_text(series: pd.Series) -> pd.Series:
    return series.astype("string").str.strip().replace("", pd.NA)


def parse_source_year(path: Path) -> int:
    match = re.search(r"beneficiary_(\d{4})\.csv$", path.name, flags=re.IGNORECASE)
    if not match:
        raise ValueError(f"Unexpected beneficiary filename: {path.name}")
    return int(match.group(1))


def load_source(path: Path) -> tuple[pd.DataFrame, dict[str, pd.Series]]:
    source_year = parse_source_year(path)
    raw = pd.read_csv(
        path,
        sep="|",
        dtype=str,
        keep_default_na=False,
        usecols=list(SOURCE_TO_TARGET),
        low_memory=False,
    )
    renamed = raw.rename(columns=SOURCE_TO_TARGET)
    original_nonblank = {
        column: clean_text(renamed[column]).notna() for column in DATE_COLUMNS
    }

    for column in TEXT_COLUMNS:
        renamed[column] = clean_text(renamed[column])
    for column in INTEGER_COLUMNS:
        renamed[column] = pd.to_numeric(clean_text(renamed[column]), errors="coerce").astype("Int64")
    for column in DATE_COLUMNS:
        renamed[column] = pd.to_datetime(
            clean_text(renamed[column]), format="%d-%b-%Y", errors="coerce"
        )

    renamed["source_file"] = path.name
    renamed["source_year"] = source_year
    return renamed, original_nonblank


def add_check(
    checks: list[dict],
    name: str,
    severity: str,
    failed_rows: int,
    population: int,
    details: str,
) -> None:
    checks.append(
        {
            "check_name": name,
            "severity": severity,
            "status": "PASS" if failed_rows == 0 else "WARN" if severity == "warning" else "FAIL",
            "failed_rows_or_entities": int(failed_rows),
            "population": int(population),
            "failed_pct": round(100 * failed_rows / population, 4) if population else 0,
            "details": details,
        }
    )


def run_quality_checks(
    frame: pd.DataFrame,
    invalid_date_counts: dict[str, int],
) -> pd.DataFrame:
    checks: list[dict] = []
    total = len(frame)
    missing_key = frame[["beneficiary_id", "reference_year"]].isna().any(axis=1).sum()
    duplicate_key = frame.duplicated(["beneficiary_id", "reference_year"]).sum()
    source_year_mismatch = (frame["reference_year"] != frame["source_year"]).sum()
    add_check(checks, "required_primary_key", "error", missing_key, total, "beneficiary_id and reference_year are required.")
    add_check(checks, "unique_beneficiary_year", "error", duplicate_key, total, "Expected one row per beneficiary and reference year.")
    add_check(checks, "filename_year_matches_record", "error", source_year_mismatch, total, "Reference year must match the year in the source filename.")

    for column in DATE_COLUMNS:
        add_check(
            checks,
            f"valid_{column}",
            "error",
            invalid_date_counts[column],
            total,
            "Nonblank source values must parse using the CMS day-month-year format.",
        )

    birth_after_death = (
        frame["birth_date"].notna()
        & frame["death_date"].notna()
        & (frame["birth_date"] > frame["death_date"])
    ).sum()
    add_check(checks, "birth_before_death", "error", birth_after_death, total, "Birth date must not occur after death date.")

    bad_age_range = (~frame["age_at_year_end"].between(0, 120) & frame["age_at_year_end"].notna()).sum()
    add_check(checks, "plausible_age_range", "error", bad_age_range, total, "Age must be between 0 and 120 inclusive.")
    age_above_110 = (frame["age_at_year_end"].gt(110) & frame["age_at_year_end"].notna()).sum()
    add_check(checks, "age_above_110", "warning", age_above_110, total, "Retain valid source values but document ages above 110 in the synthetic data.")

    expected_age = frame["reference_year"] - frame["birth_date"].dt.year
    bad_age_match = (
        frame["age_at_year_end"].notna()
        & expected_age.notna()
        & (frame["age_at_year_end"] != expected_age)
    ).sum()
    add_check(checks, "age_matches_birth_year", "warning", bad_age_match, total, "Age at year end should equal reference year minus birth year.")

    for column in COVERAGE_COLUMNS:
        failed = (~frame[column].between(0, 12) & frame[column].notna()).sum()
        add_check(checks, f"{column}_range", "error", failed, total, "Coverage months must be between 0 and 12 inclusive.")

    birth_variants = frame.groupby("beneficiary_id", dropna=True)["birth_date"].nunique(dropna=True)
    inconsistent_birth = (birth_variants > 1).sum()
    add_check(checks, "birth_date_consistent_across_years", "error", inconsistent_birth, len(birth_variants), "A beneficiary should not have multiple nonblank birth dates.")

    age_sorted = frame.sort_values(["beneficiary_id", "reference_year"])
    consecutive = age_sorted.groupby("beneficiary_id")["reference_year"].diff().eq(1)
    age_change = age_sorted.groupby("beneficiary_id")["age_at_year_end"].diff()
    bad_progression = (consecutive & age_change.notna() & age_change.ne(1)).sum()
    add_check(checks, "age_progresses_across_consecutive_years", "warning", bad_progression, int(consecutive.sum()), "Age should increase by one across consecutive annual records.")

    after_death = (
        frame["death_date"].notna()
        & frame["reference_year"].notna()
        & (frame["reference_year"] > frame["death_date"].dt.year)
    ).sum()
    add_check(checks, "no_record_after_death_year", "warning", after_death, total, "Review beneficiary-year records occurring after a reported death year.")
    return pd.DataFrame(checks)


def build_yearly_summary(frame: pd.DataFrame) -> pd.DataFrame:
    first_year = frame.groupby("beneficiary_id")["reference_year"].transform("min")
    work = frame.assign(
        is_first_observed_year=frame["reference_year"].eq(first_year),
        death_reported=frame["death_date"].notna(),
        full_part_a=frame["part_a_coverage_months"].eq(12),
        full_part_b=frame["part_b_coverage_months"].eq(12),
        any_hmo=frame["hmo_coverage_months"].gt(0),
        any_part_d=frame["part_d_coverage_months"].gt(0),
        any_dual=frame["dual_eligible_months"].gt(0),
    )
    summary = work.groupby("reference_year", as_index=False).agg(
        beneficiary_year_rows=("beneficiary_id", "size"),
        unique_beneficiaries=("beneficiary_id", "nunique"),
        newly_observed_beneficiaries=("is_first_observed_year", "sum"),
        deaths_reported=("death_reported", "sum"),
        average_age=("age_at_year_end", "mean"),
        full_part_a_beneficiaries=("full_part_a", "sum"),
        full_part_b_beneficiaries=("full_part_b", "sum"),
        beneficiaries_with_hmo=("any_hmo", "sum"),
        beneficiaries_with_part_d=("any_part_d", "sum"),
        dual_eligible_beneficiaries=("any_dual", "sum"),
    )
    summary["average_age"] = summary["average_age"].round(1)
    return summary


def build_completeness(frame: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for column in [c for c in frame.columns if c != "source_year"]:
        blank = int(frame[column].isna().sum())
        rows.append(
            {
                "column_name": column,
                "rows": len(frame),
                "non_blank_rows": len(frame) - blank,
                "blank_rows": blank,
                "blank_pct": round(100 * blank / len(frame), 2),
            }
        )
    return pd.DataFrame(rows)


def build_schema() -> pd.DataFrame:
    rows = []
    reverse = {target: source for source, target in SOURCE_TO_TARGET.items()}
    for position, column in enumerate([*SOURCE_TO_TARGET.values(), "source_file"], start=1):
        data_type, role, definition = SCHEMA_DEFINITIONS[column]
        rows.append(
            {
                "position": position,
                "column_name": column,
                "source_column": reverse.get(column, "derived"),
                "data_type": data_type,
                "role": role,
                "definition": definition,
            }
        )
    return pd.DataFrame(rows)


def markdown_table(frame: pd.DataFrame) -> str:
    display = frame.fillna("").astype(str)
    headers = display.columns.tolist()
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for values in display.itertuples(index=False, name=None):
        lines.append("| " + " | ".join(value.replace("|", "\\|") for value in values) + " |")
    return "\n".join(lines)


def write_quality_markdown(
    frame: pd.DataFrame,
    checks: pd.DataFrame,
    yearly: pd.DataFrame,
    output: Path,
) -> None:
    status_counts = checks["status"].value_counts()
    pass_count = int(status_counts.get("PASS", 0))
    warning_count = int(status_counts.get("WARN", 0))
    failure_count = int(status_counts.get("FAIL", 0))
    lines = [
        "# Beneficiary-year data quality report",
        "",
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        "## Build result",
        "",
        f"- Beneficiary-year rows: {len(frame):,}",
        f"- Unique beneficiaries: {frame['beneficiary_id'].nunique():,}",
        f"- Reference years: {int(frame['reference_year'].min())}–{int(frame['reference_year'].max())}",
        f"- Columns in analytical table: {len([c for c in frame.columns if c != 'source_year'])}",
        f"- Quality checks: {len(checks)} ({pass_count} pass, {warning_count} warning{'s' if warning_count != 1 else ''}, {failure_count} failure{'s' if failure_count != 1 else ''})",
        "",
        "## Quality checks",
        "",
        markdown_table(checks),
        "",
        "## Annual enrollment summary",
        "",
        markdown_table(yearly),
        "",
        "## Interpretation",
        "",
        "Warnings identify synthetic-data patterns that require documentation; they do not automatically invalidate the table.",
        "The source contains one annual snapshot per beneficiary and should be joined to claims using beneficiary_id plus an appropriate service-year rule.",
        "",
    ]
    output.write_text("\n".join(lines), encoding="utf-8")


def export_sqlite(frame: pd.DataFrame, database_path: Path, ddl_path: Path) -> None:
    export_columns = [c for c in frame.columns if c != "source_year"]
    database_path.unlink(missing_ok=True)
    with sqlite3.connect(database_path) as connection:
        connection.executescript(ddl_path.read_text(encoding="utf-8"))
        placeholders = ", ".join(["?"] * len(export_columns))
        columns_sql = ", ".join(export_columns)
        insert_sql = f"INSERT INTO beneficiary_year ({columns_sql}) VALUES ({placeholders})"
        database_frame = frame[export_columns].astype(object).where(frame[export_columns].notna(), None)
        connection.executemany(insert_sql, database_frame.itertuples(index=False, name=None))
        connection.commit()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    parser.add_argument("--processed-dir", type=Path, default=DEFAULT_PROCESSED_DIR)
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument("--docs-dir", type=Path, default=DEFAULT_DOCS_DIR)
    parser.add_argument("--ddl", type=Path, default=DEFAULT_DDL)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    paths = sorted(args.raw_dir.resolve().glob("beneficiary_*.csv"))
    if not paths:
        raise FileNotFoundError(f"No beneficiary files found in {args.raw_dir}")

    frames = []
    invalid_date_counts = {column: 0 for column in DATE_COLUMNS}
    for path in paths:
        print(f"Loading {path.name} ...", flush=True)
        frame, original_nonblank = load_source(path)
        for column in DATE_COLUMNS:
            invalid_date_counts[column] += int((original_nonblank[column] & frame[column].isna()).sum())
        frames.append(frame)

    beneficiary_year = pd.concat(frames, ignore_index=True).sort_values(
        ["beneficiary_id", "reference_year"]
    ).reset_index(drop=True)
    checks = run_quality_checks(beneficiary_year, invalid_date_counts)
    yearly = build_yearly_summary(beneficiary_year)
    completeness = build_completeness(beneficiary_year)
    schema = build_schema()

    args.processed_dir.mkdir(parents=True, exist_ok=True)
    args.report_dir.mkdir(parents=True, exist_ok=True)
    args.docs_dir.mkdir(parents=True, exist_ok=True)

    checks.to_csv(args.report_dir / "beneficiary_year_quality_checks.csv", index=False)
    yearly.to_csv(args.report_dir / "beneficiary_year_summary.csv", index=False)
    completeness.to_csv(args.report_dir / "beneficiary_year_completeness.csv", index=False)
    schema.to_csv(args.docs_dir / "beneficiary_year_schema.csv", index=False)
    (args.docs_dir / "beneficiary_year_schema.md").write_text(
        "# beneficiary_year schema\n\n" + markdown_table(schema) + "\n",
        encoding="utf-8",
    )
    write_quality_markdown(beneficiary_year, checks, yearly, args.report_dir / "beneficiary_year_quality.md")

    failures = checks.loc[checks["status"] == "FAIL"]
    if not failures.empty:
        raise RuntimeError(f"Critical data quality checks failed: {failures['check_name'].tolist()}")

    export_frame = beneficiary_year.drop(columns="source_year").copy()
    for column in DATE_COLUMNS:
        export_frame[column] = export_frame[column].dt.strftime("%Y-%m-%d")
    export_frame.to_csv(args.processed_dir / "beneficiary_year.csv", index=False)
    export_sqlite(export_frame, args.processed_dir / "medicare_claims.sqlite", args.ddl)
    print(
        f"Built {len(export_frame):,} beneficiary-year rows for "
        f"{export_frame['beneficiary_id'].nunique():,} beneficiaries."
    )


if __name__ == "__main__":
    main()
