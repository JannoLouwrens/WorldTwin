// Mapmode Bar — populate the top-of-screen #mmbar with mapmode buttons,
// GROUPED into 5 logical clusters so the user sees structure not a flat row.
//
// Five questions a mapmode answers (from a country reader's perspective):
//   POLITICS    — who governs, who do they belong to
//   ECONOMY     — how big, how wealthy, how indebted
//   PEOPLE      — how long they live, how connected
//   THREATS     — military spend, water/food stress, composite risk
//   ENVIRONMENT — emissions, renewable share
//
// Any mapmode not in a group goes into "OTHER" (forward-compat).
(function(){
  const GROUPS = [
    { id: 'politics',    label: 'Politics',    ids: ['political', 'democracy', 'religion', 'ethnicity'] },
    { id: 'economy',     label: 'Economy',     ids: ['gdp', 'gdp_pc', 'population', 'urban', 'inflation', 'debt'] },
    { id: 'people',      label: 'People',      ids: ['life', 'internet'] },
    { id: 'threats',     label: 'Threats',     ids: ['military', 'water_stress', 'food', 'pulse'] },
    { id: 'environment', label: 'Environment', ids: ['co2', 'pollution', 'renewable'] },
  ];

  function buildBar() {
    const host = document.getElementById('mmbar');
    if (!host || !window.Mapmode) return;
    const list = window.Mapmode.list();
    if (!list.length) { setTimeout(buildBar, 300); return; }

    const byId = Object.fromEntries(list.map(m => [m.id, m]));
    const placed = new Set();
    host.innerHTML = '';
    host.classList.add('mmbar-grouped');

    for (const g of GROUPS) {
      const group = document.createElement('div');
      group.className = 'mmbar-group';
      group.dataset.group = g.id;
      group.innerHTML = `<span class="mmbar-grouplabel">${g.label}</span>`;
      let added = 0;
      for (const id of g.ids) {
        const mm = byId[id];
        if (!mm) continue;
        placed.add(id);
        const btn = document.createElement('button');
        btn.className = 'mmbar-btn';
        btn.dataset.mm = mm.id;
        btn.title = mm.legend?.title || mm.name;
        btn.textContent = mm.name;
        btn.addEventListener('click', () => window.Mapmode.activate(mm.id));
        group.appendChild(btn);
        added++;
      }
      if (added) host.appendChild(group);
    }

    // Catch any mapmode not in a group
    const orphans = list.filter(m => !placed.has(m.id));
    if (orphans.length) {
      const group = document.createElement('div');
      group.className = 'mmbar-group';
      group.dataset.group = 'other';
      group.innerHTML = `<span class="mmbar-grouplabel">Other</span>`;
      for (const mm of orphans) {
        const btn = document.createElement('button');
        btn.className = 'mmbar-btn';
        btn.dataset.mm = mm.id;
        btn.textContent = mm.name;
        btn.addEventListener('click', () => window.Mapmode.activate(mm.id));
        group.appendChild(btn);
      }
      host.appendChild(group);
    }
  }

  // Keyboard: 1-9 + 0 = first 10 mapmodes; q w e r t = next 5
  document.addEventListener('keydown', (e) => {
    if (document.activeElement && ['INPUT','TEXTAREA'].includes(document.activeElement.tagName)) return;
    if (!window.Mapmode) return;
    const list = window.Mapmode.list();
    const key = e.key.toLowerCase();
    const idxMap = {'1':0,'2':1,'3':2,'4':3,'5':4,'6':5,'7':6,'8':7,'9':8,'0':9,'q':10,'w':11,'e':12,'r':13,'t':14};
    if (key in idxMap) {
      const i = idxMap[key];
      if (list[i]) {
        window.Mapmode.activate(list[i].id);
      }
    }
  });

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', buildBar);
  } else {
    setTimeout(buildBar, 400);
  }
})();
