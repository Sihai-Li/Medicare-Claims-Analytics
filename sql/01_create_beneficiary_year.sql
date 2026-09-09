DROP TABLE IF EXISTS beneficiary_year;

CREATE TABLE beneficiary_year (
    beneficiary_id TEXT NOT NULL,
    reference_year INTEGER NOT NULL,
    state_code TEXT,
    county_code TEXT,
    zip_code TEXT,
    birth_date TEXT,
    death_date TEXT,
    age_at_year_end INTEGER,
    sex_code TEXT,
    race_code TEXT,
    rti_race_code TEXT,
    original_entitlement_reason_code TEXT,
    current_entitlement_reason_code TEXT,
    esrd_indicator TEXT,
    part_a_coverage_months INTEGER,
    part_b_coverage_months INTEGER,
    state_buyin_months INTEGER,
    hmo_coverage_months INTEGER,
    part_d_coverage_months INTEGER,
    retiree_drug_subsidy_months INTEGER,
    dual_eligible_months INTEGER,
    coverage_start_date TEXT,
    enrollment_source TEXT,
    sample_group TEXT,
    enhanced_five_percent_flag TEXT,
    current_bic_code TEXT,
    valid_death_date_flag TEXT,
    source_file TEXT NOT NULL,
    PRIMARY KEY (beneficiary_id, reference_year),
    CHECK (reference_year BETWEEN 2015 AND 2025),
    CHECK (age_at_year_end IS NULL OR age_at_year_end BETWEEN 0 AND 120),
    CHECK (part_a_coverage_months IS NULL OR part_a_coverage_months BETWEEN 0 AND 12),
    CHECK (part_b_coverage_months IS NULL OR part_b_coverage_months BETWEEN 0 AND 12),
    CHECK (state_buyin_months IS NULL OR state_buyin_months BETWEEN 0 AND 12),
    CHECK (hmo_coverage_months IS NULL OR hmo_coverage_months BETWEEN 0 AND 12),
    CHECK (part_d_coverage_months IS NULL OR part_d_coverage_months BETWEEN 0 AND 12),
    CHECK (retiree_drug_subsidy_months IS NULL OR retiree_drug_subsidy_months BETWEEN 0 AND 12),
    CHECK (dual_eligible_months IS NULL OR dual_eligible_months BETWEEN 0 AND 12)
);

CREATE INDEX idx_beneficiary_year_year
    ON beneficiary_year (reference_year);

CREATE INDEX idx_beneficiary_year_state
    ON beneficiary_year (state_code, reference_year);

CREATE INDEX idx_beneficiary_year_beneficiary
    ON beneficiary_year (beneficiary_id);
