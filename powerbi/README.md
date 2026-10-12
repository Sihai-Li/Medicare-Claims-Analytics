# Three-page Power BI project

Open **Medicare_Analytics.pbip** in Power BI Desktop, then **Home > Refresh**.
The project contains three report pages, nine Power Query import tables,
19 explicit DAX measures, and dimension-to-fact single-direction relationships.
It has passed Microsoft PBIR/PBIP JSON schema validation and model field-reference
checks. **Desktop refresh, DAX execution, slicer interaction, and visual rendering
still require validation. A schema pass is not a rendered dashboard.**

## Open and refresh

1. Open `Medicare_Analytics.pbip`. If the project format is unavailable, enable
   the relevant Power BI Project/enhanced report features in Desktop settings
   or update Desktop. Do not use the Report Server-specific Desktop edition.
2. Power Query parameter `DataFolder` initially points to this checkout's
   `data/processed/powerbi/`. If the checkout moves, change the parameter under
   **Transform data > Manage parameters**. Refresh. No SQLite ODBC driver is needed.
3. If privacy is requested for these local synthetic CSVs, select a consistent
   local privacy level. Check that nine tables load without conversion errors.
4. Review all three pages with 2022 selected, then with 2016-2022 selected.
   Verify no visual errors, sensible numeric formats, and readable year slicers.
5. Save the project. Optionally **Save As > PBIX**; only Desktop performs this
   conversion. Capture the three pages under `powerbi/screenshots/` for the portfolio.

Pages:

- **01 Cost and Utilization:** base medical payment, inferred FFS PMPM, medical
  claims, Part D plan payment, annual trends, service contribution, paid/charge ratio.
- **02 Cohorts and Service Drivers:** retrospective ESRD/diabetes/other cohorts,
  utilization, PMPM, all-medical top-10% member concentration, DRG contribution.
- **03 Readmissions and Quality:** eligible temporal episodes, 30-day all-cause
  returns, rates, follow-up exclusions, and full-source quality finding counts.

Primary comparison years are 2016-2022 in Power Query. Annual FFS inference,
synthetic data, unadjusted all-cause returns, and temporal episode limitations
are explained in `docs/metric_definitions.md`. Quality is across all source years
and not filtered by year. Patient concentration is all-medical and not filtered
by service. DRG summary is all-cohort. Titles indicate these scopes.

## Independent reference values

SQL/Python validation generates `reports/powerbi_expected_values.csv`. Compare
2022 and the all-primary-years selection with the matching filter scope:
Medical Claim Payment, Eligible FFS Member Months, Medical PMPM,
Medical Claim Count, Eligible Index Episodes, 30 Day Readmitted Episodes,
30 Day All Cause Return Rate. Currency display may round; stored values should agree.
Return rates should be compared within numerical tolerance, not formatted strings.

Schema/reference validation is reproducible with:

```powershell
python src/validate_powerbi.py
```

This optional validator requires `jsonschema` (already installed with the local
Jupyter environment) and downloads only Microsoft schemas, cached under ignored
processed data. It does not publish anything or connect to a cloud workspace.

Official format references:
[PBIP](https://learn.microsoft.com/en-us/power-bi/developer/projects/projects-overview),
[report](https://learn.microsoft.com/en-us/power-bi/developer/projects/projects-report),
[semantic model](https://learn.microsoft.com/en-us/power-bi/developer/projects/projects-dataset).
