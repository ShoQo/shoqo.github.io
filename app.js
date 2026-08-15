// An empty filter set means "no restriction", not "match nothing".
const state = { jobs: [], companyId: null, types: new Set(), industries: new Set() };

const el = {
  list: document.getElementById("jobs"),
  meta: document.getElementById("meta"),
  search: document.getElementById("search"),
  typeFilter: document.getElementById("filter-type"),
  industryFilter: document.getElementById("filter-industry"),
};

// Builds one checkbox per distinct value found in the feed, so a new position
// type or industry needs no change here.
function buildFilter(container, values, selected) {
  for (const value of values) {
    const label = document.createElement("label");
    label.className = "filter-option";

    const box = document.createElement("input");
    box.type = "checkbox";
    box.value = value;
    box.addEventListener("change", () => {
      if (box.checked) selected.add(value);
      else selected.delete(value);
      render(visibleJobs());
    });

    label.append(box, document.createTextNode(value));
    container.append(label);
  }
}

function distinct(jobs, pick) {
  return [...new Set(jobs.map(pick).filter(Boolean))].sort();
}

function render(jobs) {
  el.list.replaceChildren();

  if (jobs.length === 0) {
    const li = document.createElement("li");
    li.className = "empty";
    li.textContent = "No jobs match.";
    el.list.append(li);
    return;
  }

  for (const job of jobs) {
    const li = document.createElement("li");
    li.className = "job";

    li.append(logoElement(job.company, 32));

    const body = document.createElement("div");

    const a = document.createElement("a");
    a.href = job.url;
    a.target = "_blank";
    a.rel = "noopener";
    a.textContent = job.title;

    const company = document.createElement("span");
    company.className = "company";
    company.textContent = job.company.name;

    const details = document.createElement("span");
    details.className = "details";
    details.textContent = [job.location, job.type, job.posted_at]
      .filter(Boolean)
      .join(" · ");

    body.append(a, company, details);
    li.append(body);
    el.list.append(li);
  }
}

function visibleJobs() {
  const q = el.search.value.trim().toLowerCase();

  return state.jobs.filter((job) => {
    if (state.companyId && job.company.id !== state.companyId) return false;
    if (state.types.size && !state.types.has(job.type)) return false;
    if (state.industries.size && !state.industries.has(job.company.industry)) return false;
    if (!q) return true;
    return [job.title, job.company.name, job.location]
      .filter(Boolean)
      .some((field) => field.toLowerCase().includes(q));
  });
}

// #company=<id> lets the companies page link straight to a filtered job list.
function readCompanyFromHash() {
  const match = location.hash.match(/company=([^&]+)/);
  state.companyId = match ? decodeURIComponent(match[1]) : null;
}

el.search.addEventListener("input", () => render(visibleJobs()));
window.addEventListener("hashchange", () => {
  readCompanyFromHash();
  render(visibleJobs());
});

readCompanyFromHash();

loadData()
  .then(({ jobs, updatedAt }) => {
    state.jobs = jobs;
    buildFilter(el.typeFilter, distinct(jobs, (j) => j.type), state.types);
    buildFilter(el.industryFilter, distinct(jobs, (j) => j.company.industry), state.industries);
    el.meta.textContent = `${jobs.length} jobs · updated ${formatUpdated(updatedAt)}`;
    render(visibleJobs());
  })
  .catch((err) => {
    el.meta.textContent = `Could not load jobs: ${err.message}`;
  });
