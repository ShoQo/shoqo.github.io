const el = {
  grid: document.getElementById("companies"),
  meta: document.getElementById("meta"),
};

function render(companies, counts) {
  el.grid.replaceChildren();

  for (const company of companies) {
    const li = document.createElement("li");
    li.className = "company-card";

    li.append(logoElement(company, 48));

    const body = document.createElement("div");

    const name = document.createElement("a");
    name.href = `index.html#company=${encodeURIComponent(company.id)}`;
    name.className = "company-name";
    name.textContent = company.name;

    const count = counts.get(company.id) ?? 0;
    const sub = document.createElement("span");
    sub.className = "details";
    sub.textContent = [company.industry, count === 1 ? "1 open role" : `${count} open roles`]
      .filter(Boolean)
      .join(" · ");

    body.append(name, sub);
    li.append(body);
    el.grid.append(li);
  }
}

loadData()
  .then(({ jobs, companies, updatedAt }) => {
    const counts = new Map();
    for (const job of jobs) {
      counts.set(job.company.id, (counts.get(job.company.id) ?? 0) + 1);
    }

    const sorted = [...companies].sort((a, b) => a.name.localeCompare(b.name));
    el.meta.textContent = `${sorted.length} companies · updated ${formatUpdated(updatedAt)}`;
    render(sorted, counts);
  })
  .catch((err) => {
    el.meta.textContent = `Could not load companies: ${err.message}`;
  });
