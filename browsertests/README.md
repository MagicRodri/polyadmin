# browsertests

Playwright coverage for the flows a unit test cannot see: the login
gate, the five mutating flows, the htmx-driven list, the error pages,
and the layout facts only a browser can measure.

## Running

```bash
pip install playwright pytest-playwright
playwright install chromium
pytest browsertests
```

The suite starts the reference app itself on port 3100 (override with
`POLYADMIN_TEST_PORT`) and stops it afterwards, so nothing needs to be
running first.

## The rule these tests follow

Every assertion checks state the server actually holds, or a style the
browser actually resolved. Two failures are the reason:

- throwaway scripts that asserted the absence of an error string, and
  passed against a form that had never been submitted;
- a login page that shipped with a panel the same colour as the page
  behind it, past twenty passing assertions and two unit suites.

So after a mutation, reload and count the rows. For layout, read
`getComputedStyle` or a bounding box and compare — never assert on a
class name.
