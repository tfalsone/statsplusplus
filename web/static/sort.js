document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("th[data-sort]").forEach(th => {
    th.style.cursor = "pointer";
    th.addEventListener("click", () => sortTable(th));
  });
});

function sortTable(th) {
  const table = th.closest("table");
  const tbody = table.querySelector("tbody");
  const idx = Array.from(th.parentNode.children).indexOf(th);
  const type = th.dataset.sort;
  const rows = Array.from(tbody.querySelectorAll("tr"));

  const asc = th.classList.contains("sort-asc");
  table.querySelectorAll("th").forEach(h => h.classList.remove("sort-asc", "sort-desc"));
  th.classList.add(asc ? "sort-desc" : "sort-asc");
  const dir = asc ? -1 : 1;

  rows.sort((a, b) => {
    const cellA = a.children[idx], cellB = b.children[idx];
    if (type === "num") {
      const va = parseFloat(cellA.textContent.replace(/[$M,]/g, "")) || 0;
      const vb = parseFloat(cellB.textContent.replace(/[$M,]/g, "")) || 0;
      return (va - vb) * dir;
    }
    if (type === "pos") {
      const va = parseInt(cellA.dataset.sortValue) || 99;
      const vb = parseInt(cellB.dataset.sortValue) || 99;
      return (va - vb) * dir;
    }
    return cellA.textContent.trim().localeCompare(cellB.textContent.trim()) * dir;
  });

  rows.forEach(r => tbody.appendChild(r));

  // Re-number rank column if present
  const firstTh = table.querySelector("thead th");
  if (firstTh && firstTh.textContent.trim() === "#") {
    const n = rows.length;
    // Apply smart numbering to numeric columns and any column with data-sort-best
    if (type === "num" || th.dataset.sortBest) {
      const bestIsLow = th.dataset.sortBest === "low";
      const descending = th.classList.contains("sort-desc");
      const topIsFirst = descending !== bestIsLow;
      rows.forEach((r, i) => {
        r.children[0].textContent = topIsFirst ? i + 1 : n - i;
      });
    } else {
      rows.forEach((r, i) => { r.children[0].textContent = i + 1; });
    }
  }
}
