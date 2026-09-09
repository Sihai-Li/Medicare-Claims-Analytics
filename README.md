# Medicare Claims & Population Health Analytics

An end-to-end healthcare analytics portfolio project using the CMS Synthetic
Medicare Enrollment, Fee-for-Service Claims, and Prescription Drug Event data.

The project will combine Python, SQL, and Power BI to examine beneficiary
enrollment, healthcare utilization, cost, readmissions, chronic-condition
cohorts, and provider variation.

## Data disclaimer

The CMS files contain realistic-but-not-real synthetic data. Results from this
project demonstrate an analytics workflow and must not be interpreted as
findings about actual Medicare beneficiaries.

## Current milestone

Milestone 1 profiles every local CSV and ZIP file and produces:

- a dataset-level inventory and quality summary;
- a field-level completeness profile;
- a concise analysis data dictionary in CSV and Markdown formats.

Milestone 2 builds the normalized `beneficiary_year` table with one row per
beneficiary and reference year. The pipeline converts dates and numeric fields,
preserves identifiers as text, loads the result into SQLite, and produces
automated quality and completeness reports.

## Repository structure

```text
.
|-- data/
|   |-- raw/                 # Original CMS downloads; ignored by Git
|   `-- processed/           # Future analysis-ready tables
|-- docs/
|   |-- data_dictionary.csv  # Selected fields for the analytics model
|   |-- data_dictionary.md   # Human-readable dictionary
|   |-- beneficiary_year_schema.csv
|   `-- beneficiary_year_schema.md
|-- powerbi/                 # Future Power BI files and screenshots
|-- reports/
|   |-- data_profile.md      # Human-readable profiling report
|   |-- dataset_profile.csv  # One row per source file
|   |-- column_profile.csv   # One row per source column
|   |-- archive_profile.csv  # ZIP integrity and member inventory
|   |-- beneficiary_year_quality.md
|   |-- beneficiary_year_quality_checks.csv
|   |-- beneficiary_year_completeness.csv
|   `-- beneficiary_year_summary.csv
|-- sql/
|   `-- 01_create_beneficiary_year.sql
|-- src/
|   |-- profile_data.py      # Reproducible source profiling pipeline
|   `-- build_beneficiary_year.py
|-- .gitignore
|-- README.md
`-- requirements.txt
```

## Run the data profile

Create a Python environment, install the dependency, and run:

```bash
python -m pip install -r requirements.txt
python src/profile_data.py
```

The script expects source files under `data/raw`. It preserves identifiers and
codes as text so leading zeros are not lost.

## Build the beneficiary-year table

```bash
python src/build_beneficiary_year.py
```

This creates two equivalent local analytical outputs:

- `data/processed/beneficiary_year.csv`
- `data/processed/medicare_claims.sqlite`, table `beneficiary_year`

Generated data files are ignored by Git. The transformation code, SQL schema,
quality results, and documentation are intended to be committed.

## Planned analysis scope

1. Build beneficiary-year, claim-header, claim-line, and prescription-event
   tables.
2. Validate identifiers, dates, enrollment periods, duplicate lines, and
   financial fields.
3. Calculate utilization, cost, length of stay, 30-day readmission, PMPM, and
   high-cost-member metrics.
4. Create chronic-condition cohorts from diagnosis codes.
5. Publish a Power BI report and document the analytical limitations.

## Source

Centers for Medicare & Medicaid Services (CMS):
https://data.cms.gov/collection/synthetic-medicare-enrollment-fee-for-service-claims-and-prescription-drug-event
