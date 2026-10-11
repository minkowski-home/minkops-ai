# Shared console preview

Open `index.html` through a local file server to inspect the current base app design. This static specimen reuses `design/styles.css`, `design/console.css`, and `design/login.css` from the connected app. `preview.css` contains only preview-specific adjustments, and `preview.js` provides local sample data.

The preview includes sign-in/sign-up, Dashboard and resizable Activity pane, Employees and employee detail, Workflows and workflow detail, task progress, Access, sidebar collapse, and all four themes. Settings changes in this specimen last only until the page reloads. Sign-in is simulated; no credentials are sent. The Image to Excel test run is available only in the connected app.

The sample belongs to a mock tenant. It illustrates two employees, three workflows in active/paused/planned states, and three task states. It is not a production seed or a claim that these workflows execute. The real app enforces tenant access and saves settings through the API. A new PR Infra tenant has no employees or workflows.

Use this kit for visual review, and use the running app for end-to-end testing.

`accounts.html` adds the Accounts desk launch, editable run configuration,
searchable discovery mapping, bill evidence/review and verified local-save
states. It imports the same `design/accounts.css` used by the app and supports
Minkops Light, Minkops Dark, Slate Light and Slate Dark. Its buttons are disabled
because execution belongs to the authenticated running app, not this specimen.

The Accounts specimen also shows full Tally discovery with a voucher-only date
range, reusable client notes, company selection and a company decision beside
each bill. These additions reuse the current controls and tokens; the connected
app remains the executable reference.
