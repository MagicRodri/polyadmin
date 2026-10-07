# Changelog

## [Unreleased]

## [0.1.0b7] — 2026-10-08

### Changed

- **Breaking:** framework and ORM integrations moved under
  `polyadmin.contrib`: `polyadmin.fastapi` is now
  `polyadmin.contrib.fastapi`, and `polyadmin.sqlalchemy` is now
  `polyadmin.contrib.sqlalchemy`. There are no compatibility aliases.
  Install extras are unchanged.
- `compute_permissions` lives in `polyadmin.core.permissions`, so core no
  longer reaches into the FastAPI adapter for it.

### Fixed

- Form errors now appear in the browser. htmx 1.x does not swap a 422
  response, so a form re-rendered with validation errors, or refused with
  `RecordFormError`, left the page unchanged.

### Documentation

- README sections on contributing and the license.
- Examples in the docs use neutral sample domains.
- The example app gains SQLAlchemy-backed Clients and Projects under a
  **Projects** sidebar group.

## [0.1.0b6] — 2026-10-01

### Fixed

- A relation filter's lookup only offers the records the filter can match.

## [0.1.0b5] — 2026-09-30

### Added

- `polyadmin.sqlalchemy.SQLAlchemyModelAdmin`: a `ModelAdmin` served from a
  SQLAlchemy 2.x or SQLModel async session. Search, filters, ordering and
  paging run in SQL, writes flush through the ORM so mapper events fire, and
  `default_filters` apply until the user picks that filter.
- `RecordFormError`: a `ModelAdmin` can refuse a save with messages shown on
  the form (status 422), or a delete with the reason shown on the delete page.
- `ActionError`: an action fails with a notification at the level it chooses,
  and the records it already handled are audited. The built-in bulk delete and
  bulk edit stop this way at the first failure.
- `ChoiceFilter` accepts `(value, label)` pairs.

## [0.1.0b4] — 2026-09-30

### Added

- Actions that ask for input: a form page before the action runs.
- Actions can answer with a file (`Download`).
- Bulk edit (`bulk_edit_fields`): change selected fields on many records.
- Dashboard filters (`DateRangeFilter`, `SelectFilter`, optionally
  searchable) carried in the URL.
- Lazy, filter-aware widgets loaded from their own route, including
  `Donut` and `Tabs`.
- `MetricGroup` and `DataTable` widgets. `DataTable` pages, searches and
  colours cells with `tones`.
- Dashboard exports (`DashboardExport`).
- Widgets placed above the filter bar (`placement="top"`).

## [0.1.0b3] — 2026-09-24

### Changed

- Image fields render and upload more reliably.
- The login page is improved.

## [0.1.0b2] — 2026-09-23

### Fixed

- Async bulk deletion is awaited.

## [0.1.0b1] — 2026-09-22

First beta:

- `ModelAdmin` CRUD with search, filters, sorting and pagination.
- A widget dashboard.
- Relations with lookup comboboxes.
- Inlines.
- Actions.
- Delete previews.
- CSV and XLSX export.
- Authentication and permissions hooks.
- CSRF protection.
- French and Russian translations.
- The FastAPI adapter.

[Unreleased]: https://github.com/MagicRodri/polyadmin/compare/v0.1.0b7...HEAD
[0.1.0b7]: https://github.com/MagicRodri/polyadmin/compare/v0.1.0b6...v0.1.0b7
[0.1.0b6]: https://github.com/MagicRodri/polyadmin/compare/v0.1.0b5...v0.1.0b6
[0.1.0b5]: https://github.com/MagicRodri/polyadmin/compare/v0.1.0b4...v0.1.0b5
[0.1.0b4]: https://github.com/MagicRodri/polyadmin/compare/v0.1.0b3...v0.1.0b4
[0.1.0b3]: https://github.com/MagicRodri/polyadmin/compare/v0.1.0b2...v0.1.0b3
[0.1.0b2]: https://github.com/MagicRodri/polyadmin/compare/v0.1.0b1...v0.1.0b2
[0.1.0b1]: https://github.com/MagicRodri/polyadmin/releases/tag/v0.1.0b1
