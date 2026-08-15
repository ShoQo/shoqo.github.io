// Shared data loading + company rendering for both pages.

// Cache-bust so GitHub Pages does not serve a stale feed after the action runs.
async function loadJSON(path) {
  const res = await fetch(`${path}?t=${Date.now()}`);
  if (!res.ok) throw new Error(`${path}: HTTP ${res.status}`);
  return res.json();
}

async function loadData() {
  const [jobsData, companiesData] = await Promise.all([
    loadJSON("data/jobs.json"),
    loadJSON("data/companies.json"),
  ]);

  const companies = companiesData.companies ?? [];
  const byId = new Map(companies.map((c) => [c.id, c]));

  // A job whose company_id is missing from companies.json still renders, so a
  // scraper mistake shows up on the page instead of silently dropping rows.
  const jobs = (jobsData.jobs ?? []).map((job) => ({
    ...job,
    company: byId.get(job.company_id) ?? {
      id: job.company_id,
      name: job.company_id,
      logo: null,
      industry: null,
    },
  }));

  return { jobs, companies, updatedAt: jobsData.updated_at };
}

function monogram(name) {
  return (name ?? "?").trim().charAt(0).toUpperCase();
}

// Returns an <img> when a logo file is configured, falling back to a monogram
// tile if the path is absent or the file 404s.
function logoElement(company, size) {
  const fallback = document.createElement("span");
  fallback.className = "logo logo-fallback";
  fallback.style.setProperty("--logo-size", `${size}px`);
  fallback.textContent = monogram(company.name);

  if (!company.logo) return fallback;

  const img = document.createElement("img");
  img.className = "logo";
  img.style.setProperty("--logo-size", `${size}px`);
  img.src = company.logo;
  img.alt = `${company.name} logo`;
  img.loading = "lazy";
  img.addEventListener("error", () => img.replaceWith(fallback), { once: true });
  return img;
}

function formatUpdated(updatedAt) {
  return updatedAt ? new Date(updatedAt).toLocaleDateString() : "unknown";
}
