PRAGMA foreign_keys=ON;
CREATE TABLE beneficiary_year (
 beneficiary_year_key TEXT PRIMARY KEY, beneficiary_id TEXT NOT NULL, reference_year INTEGER NOT NULL,
 birth_date TEXT, death_date TEXT, coverage_start_date TEXT, age INTEGER,
 sex_code TEXT, state_code TEXT, esrd_indicator TEXT,
 part_a_months INTEGER, part_b_months INTEGER, hmo_months INTEGER,
 UNIQUE(beneficiary_id,reference_year)
);
CREATE TABLE member_month (
 member_month_key TEXT PRIMARY KEY, beneficiary_year_key TEXT NOT NULL REFERENCES beneficiary_year,
 beneficiary_id TEXT NOT NULL, month_start TEXT NOT NULL, month_end TEXT NOT NULL,
 entitlement_code TEXT, hmo_code TEXT, part_d_contract TEXT,
 eligible_ffs INTEGER NOT NULL CHECK(eligible_ffs IN (0,1)),
 eligible_part_d INTEGER NOT NULL CHECK(eligible_part_d IN (0,1)),
 exclusion_reason TEXT NOT NULL, eligibility_basis TEXT NOT NULL,
 source_file TEXT NOT NULL, source_row INTEGER NOT NULL
);
CREATE INDEX ix_member_patient_date ON member_month(beneficiary_id,month_start);
CREATE TABLE claim_header (
 claim_key TEXT PRIMARY KEY, service_category TEXT NOT NULL, claim_id TEXT,
 beneficiary_id TEXT, service_start TEXT, service_end TEXT, admission_date TEXT, discharge_date TEXT,
 payment_cents INTEGER, charge_cents INTEGER, pass_through_per_diem_cents INTEGER,
 utilization_days INTEGER, non_utilization_days INTEGER, discharge_status TEXT,
 provider_id TEXT, organization_npi TEXT, drg_code TEXT, principal_diagnosis TEXT,
 has_diabetes INTEGER NOT NULL, has_heart_failure INTEGER NOT NULL, has_copd INTEGER NOT NULL,
 header_conflict INTEGER NOT NULL DEFAULT 0,
 source_file TEXT NOT NULL, source_row INTEGER NOT NULL
);
CREATE INDEX ix_claim_patient_date ON claim_header(beneficiary_id,service_start);
CREATE TABLE claim_line (
 source_record_key TEXT PRIMARY KEY, claim_key TEXT NOT NULL REFERENCES claim_header,
 line_number INTEGER, revenue_center TEXT, hcpcs_code TEXT,
 service_start TEXT, service_end TEXT, line_payment_cents INTEGER, line_charge_cents INTEGER,
 source_file TEXT NOT NULL, source_row INTEGER NOT NULL
);
CREATE INDEX ix_claim_line_key ON claim_line(claim_key,line_number);
CREATE TABLE claim_diagnosis (
 claim_key TEXT NOT NULL REFERENCES claim_header, diagnosis_code TEXT NOT NULL,
 PRIMARY KEY(claim_key,diagnosis_code)
);
CREATE TABLE prescription_event (
 source_record_key TEXT PRIMARY KEY, event_id TEXT, beneficiary_id TEXT,
 service_date TEXT, product_service_id TEXT, days_supply INTEGER, quantity REAL,
 total_cost_cents INTEGER, covered_plan_payment_cents INTEGER, noncovered_plan_payment_cents INTEGER,
 patient_payment_cents INTEGER, other_payer_cents INTEGER,
 source_file TEXT NOT NULL, source_row INTEGER NOT NULL
);
CREATE INDEX ix_rx_patient_date ON prescription_event(beneficiary_id,service_date);
CREATE TABLE dq_exception (
 exception_id INTEGER PRIMARY KEY, dataset TEXT, source_file TEXT, source_row INTEGER,
 record_key TEXT, check_name TEXT, field TEXT, raw_value TEXT, detail TEXT
);
CREATE TABLE source_inventory (
 source_file TEXT PRIMARY KEY, dataset TEXT, source_rows INTEGER, normalized_headers INTEGER,
 sha256 TEXT, observed_start TEXT, observed_end TEXT
);
