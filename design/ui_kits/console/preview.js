// Static design specimen. Real data, access rules, and persistence live in the shared app.
const EMPLOYEES = {
  "image-desk": { name: "Image desk", description: "Receives images and prepares structured records.", status: "active", workflows: ["Image to Excel", "Vendor intake"], reviewMode: "Only exceptions", updates: true },
  "accounts-desk": { name: "Accounts desk", description: "Keeps account records ready for review.", status: "active", workflows: ["Account reconciliation", "Vendor intake"], digest: false }
};
const WORKFLOWS = [
  { id: "image-to-excel-test", name: "Image to Excel", description: "Test image extraction and spreadsheet output.", status: "active", owners: ["Image desk"], approval: true, format: "Excel" },
  { id: "account-reconciliation", name: "Account reconciliation", description: "Example workflow awaiting setup.", status: "paused", owners: ["Accounts desk"], cadence: "Daily" },
  { id: "vendor-intake", name: "Vendor intake", description: "Example planned workflow.", status: "planned", owners: ["Image desk", "Accounts desk"] }
];
const TASKS = {
  receipt: { title: "Extract the latest receipt", status: "running", progress: 65, summary: "Image received. Fields are being checked.", events: [["Image received", 15], ["Fields extracted", 65]] },
  review: { title: "Review a low-confidence field", status: "attention", progress: 80, summary: "The date needs a quick human check.", events: [["Image received", 15], ["Date needs review", 80]] },
  handoff: { title: "Hand off the approved sheet", status: "handoff", progress: 90, summary: "Waiting for the next owner.", events: [["Sheet prepared", 80], ["Ready to hand off", 90]] }
};
const TITLES = { dashboard: "Dashboard", employees: "Employees", "employee-detail": "Employee", workflows: "Workflows", "workflow-detail": "Workflow", "task-detail": "Task", access: "Access" };
const THEMES = ["minkops-light", "minkops-dark", "slate-light", "slate-dark"];

function setTheme(id) {
  const theme = THEMES.includes(id) ? id : "minkops-light";
  document.documentElement.dataset.theme = theme;
  document.querySelectorAll("[data-theme-picker]").forEach((picker) => { picker.value = theme; });
  try { localStorage.setItem("minkops.theme", theme); } catch { /* Preview still works. */ }
}
function showScreen(name) {
  document.querySelectorAll("[data-screen]").forEach((screen) => { screen.hidden = screen.dataset.screen !== name; });
  const section = name === "employee-detail" ? "employees" : name === "workflow-detail" ? "workflows" : name === "task-detail" ? "dashboard" : name;
  document.querySelectorAll(".console-nav-item[data-route]").forEach((item) => { item.classList.toggle("is-active", item.dataset.route === section); });
  document.getElementById("route-title").textContent = TITLES[name];
}
function employeeDetail(id) {
  const employee = EMPLOYEES[id];
  const controls = id === "image-desk"
    ? '<label class="config-field">Review mode<select name="reviewMode"><option>Only exceptions</option><option>All outputs</option></select></label><label class="switch-row"><input type="checkbox" name="updates"> In-app updates</label>'
    : '<label class="switch-row"><input type="checkbox" name="digest"> Daily digest</label>';
  document.getElementById("employee-detail").innerHTML =
    '<header class="detail-heading"><div><h2>' + employee.name + '</h2><p>' + employee.description + '</p></div><span class="status status--active">Active</span></header>' +
    '<div class="detail-grid"><form class="config-panel" id="employee-settings"><div class="section-heading"><div><h2>Settings</h2><p>A few useful controls for this employee.</p></div></div>' + controls +
    '<button class="button button-primary">Save settings</button><p class="form-message" role="status"></p></form>' +
    '<aside class="related-panel"><h2>Workflows</h2>' + employee.workflows.map((name) => '<div class="related-row">' + name + '</div>').join("") + '</aside></div>';
  const form = document.getElementById("employee-settings");
  if (id === "image-desk") { form.elements.reviewMode.value = employee.reviewMode; form.elements.updates.checked = employee.updates; }
  else { form.elements.digest.checked = employee.digest; }
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    if (id === "image-desk") { employee.reviewMode = form.elements.reviewMode.value; employee.updates = form.elements.updates.checked; }
    else { employee.digest = form.elements.digest.checked; }
    form.querySelector(".form-message").textContent = "Settings saved in this preview.";
  });
  showScreen("employee-detail");
}
function workflowList() {
  const group = document.getElementById("group-workflows").value;
  const sort = document.getElementById("sort-workflows").value;
  const items = [...WORKFLOWS].sort((a, b) => sort === "name" ? a.name.localeCompare(b.name) : a.status.localeCompare(b.status) || a.name.localeCompare(b.name));
  const groups = group === "employee" ? ["Image desk", "Accounts desk"] : ["active", "paused", "planned"];
  document.getElementById("workflow-list").innerHTML = groups.map((label) => {
    const rows = items.filter((workflow) => group === "employee" ? workflow.owners.includes(label) : workflow.status === label);
    return '<section class="workflow-group"><h3>' + (group === "employee" ? label : label[0].toUpperCase() + label.slice(1)) + '</h3><div class="workflow-list">' + rows.map((workflow) =>
      '<button class="workflow-row" data-workflow="' + workflow.id + '"><span><h4>' + workflow.name + '</h4><p>' + workflow.description + '</p><small>' + workflow.owners.join(", ") + '</small></span><span class="status status--' + workflow.status + '">' + workflow.status + '</span><span class="preview-chevron"></span></button>'
    ).join("") + '</div></section>';
  }).join("");
}
function workflowDetail(id) {
  const workflow = WORKFLOWS.find((item) => item.id === id);
  const controls = id === "image-to-excel-test"
    ? '<label class="switch-row"><input type="checkbox" name="approval"> Ask before saving</label><label class="config-field">Output format<select name="format"><option>Excel</option><option>CSV</option></select></label>'
    : id === "account-reconciliation" ? '<label class="config-field">Check cadence<select name="cadence"><option>Daily</option><option>Weekly</option></select></label>'
      : '<p class="quiet-state">No additional settings are needed yet.</p>';
  document.getElementById("workflow-detail").innerHTML =
    '<header class="detail-heading"><div><h2>' + workflow.name + '</h2><p>' + workflow.description + '</p></div><span class="status status--' + workflow.status + '">' + workflow.status + '</span></header>' +
    '<div class="detail-grid"><form class="config-panel" id="workflow-settings"><div class="section-heading"><div><h2>Settings</h2><p>Choose only what this workflow needs.</p></div></div>' +
    '<label class="config-field">Status<select name="status"><option>active</option><option>paused</option><option>planned</option></select></label>' + controls +
    '<button class="button button-primary">Save settings</button><p class="form-message" role="status"></p></form><aside class="related-panel"><h2>Employees</h2>' +
    workflow.owners.map((name) => '<div class="related-row">' + name + '</div>').join("") + '</aside></div>';
  const form = document.getElementById("workflow-settings");
  form.elements.status.value = workflow.status;
  if (id === "image-to-excel-test") { form.elements.approval.checked = workflow.approval; form.elements.format.value = workflow.format; }
  if (id === "account-reconciliation") form.elements.cadence.value = workflow.cadence;
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    workflow.status = form.elements.status.value;
    if (id === "image-to-excel-test") { workflow.approval = form.elements.approval.checked; workflow.format = form.elements.format.value; }
    if (id === "account-reconciliation") workflow.cadence = form.elements.cadence.value;
    form.querySelector(".form-message").textContent = "Settings saved in this preview.";
    workflowList();
  });
  showScreen("workflow-detail");
}
function taskDetail(id) {
  const task = TASKS[id];
  document.getElementById("task-detail").innerHTML =
    '<header class="detail-heading"><div><h2>' + task.title + '</h2><p>' + task.summary + '</p></div><span class="status status--' + task.status + '">' + task.status + '</span></header>' +
    '<div class="task-progress"><div class="progress-ring" style="--progress:' + task.progress + '%"><strong>' + task.progress + '%</strong><span>progress</span></div>' +
    '<div><h3>What is happening</h3><p>' + task.summary + '</p><div class="progress-track"><span style="width:' + task.progress + '%"></span></div></div></div>' +
    '<section class="timeline"><h3>Progress</h3><ol>' + task.events.map((event) => '<li><span class="timeline-point"></span><div><strong>' + event[0] + '</strong><small>' + event[1] + '% complete</small></div></li>').join("") + '</ol></section>';
  showScreen("task-detail");
}
function setPaneWidth(width) {
  const value = Math.max(260, Math.min(500, width));
  document.querySelector(".dashboard-workspace").style.setProperty("--pane-width", value + "px");
  document.querySelector(".pane-resizer").setAttribute("aria-valuenow", String(value));
}

setTheme((() => { try { return localStorage.getItem("minkops.theme"); } catch { return null; } })());
document.querySelectorAll("[data-theme-picker]").forEach((picker) => picker.addEventListener("change", (event) => setTheme(event.target.value)));
document.getElementById("auth-toggle").addEventListener("click", () => {
  const signup = document.getElementById("auth-form-heading").textContent === "Sign in";
  document.getElementById("auth-message").hidden = true;
  document.getElementById("auth-heading").textContent = signup ? "Make room for better work" : "Welcome back";
  document.getElementById("auth-intro").textContent = signup ? "Create your account, then join your workspace." : "Your workspace is ready when you are.";
  document.getElementById("auth-form-heading").textContent = signup ? "Create an account" : "Sign in";
  document.getElementById("auth-submit").textContent = signup ? "Create account" : "Sign in";
  document.getElementById("auth-toggle-copy").textContent = signup ? "Already have an account?" : "New to Minkops?";
  document.getElementById("auth-toggle").textContent = signup ? "Sign in" : "Create an account";
  document.querySelectorAll(".signup-only").forEach((field) => { field.hidden = !signup; });
});
document.getElementById("auth-form").addEventListener("submit", (event) => {
  event.preventDefault();
  if (document.getElementById("auth-form-heading").textContent !== "Sign in") {
    const message = document.getElementById("auth-message");
    message.textContent = "In the connected app, you would receive an email to verify your account.";
    message.hidden = false;
    return;
  }
  document.getElementById("auth").hidden = true;
  document.getElementById("workspace").hidden = false;
  showScreen("dashboard");
});
document.getElementById("sign-out").addEventListener("click", () => { document.getElementById("workspace").hidden = true; document.getElementById("auth").hidden = false; });
document.getElementById("collapse-nav").addEventListener("click", () => {
  const collapsed = document.getElementById("workspace").classList.toggle("is-collapsed");
  document.getElementById("collapse-nav").setAttribute("aria-label", collapsed ? "Expand navigation" : "Collapse navigation");
});
document.addEventListener("click", (event) => {
  const route = event.target.closest("[data-route]");
  const employee = event.target.closest("[data-employee]");
  const workflow = event.target.closest("[data-workflow]");
  const task = event.target.closest("[data-task]");
  if (route) showScreen(route.dataset.route);
  else if (employee) employeeDetail(employee.dataset.employee);
  else if (workflow) workflowDetail(workflow.dataset.workflow);
  else if (task) taskDetail(task.dataset.task);
});
document.getElementById("group-workflows").addEventListener("change", workflowList);
document.getElementById("sort-workflows").addEventListener("change", workflowList);
workflowList();
const resizer = document.querySelector(".pane-resizer");
resizer.addEventListener("keydown", (event) => {
  const width = Number(resizer.getAttribute("aria-valuenow"));
  if (event.key === "ArrowLeft") { event.preventDefault(); setPaneWidth(width + 20); }
  if (event.key === "ArrowRight") { event.preventDefault(); setPaneWidth(width - 20); }
});
resizer.addEventListener("pointerdown", (event) => {
  resizer.setPointerCapture(event.pointerId);
  const move = (motion) => setPaneWidth(document.querySelector(".dashboard-workspace").getBoundingClientRect().right - motion.clientX);
  resizer.addEventListener("pointermove", move);
  resizer.addEventListener("pointerup", () => resizer.removeEventListener("pointermove", move), { once: true });
});
