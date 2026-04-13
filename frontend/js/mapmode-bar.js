// Mapmode Bar — populate the top-of-screen #mmbar with one button per
// registered mapmode. Click activates. Keyboard shortcuts 1-9 + 0 + qwe.
(function(){
  function buildBar() {
    const host = document.getElementById('mmbar');
    if (!host || !window.Mapmode) return;
    const list = window.Mapmode.list();
    if (!list.length) {
      // mapmodes-data.js hasn't run yet; retry shortly
      setTimeout(buildBar, 300);
      return;
    }
    // Preserve the label; append buttons
    const label = host.querySelector('.mmbar-label');
    host.innerHTML = '';
    if (label) host.appendChild(label);
    list.forEach(mm => {
      const btn = document.createElement('button');
      btn.className = 'mmbar-btn';
      btn.dataset.mm = mm.id;
      btn.textContent = mm.name;
      btn.title = mm.legend?.title || mm.name;
      btn.addEventListener('click', () => window.Mapmode.activate(mm.id));
      host.appendChild(btn);
    });
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
