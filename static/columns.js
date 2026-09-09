document.addEventListener('DOMContentLoaded', function () {
  document.querySelectorAll('[data-column-toggle]').forEach(function (panel) {
    var storageKey = panel.getAttribute('data-column-toggle');
    var table = document.querySelector(panel.getAttribute('data-table'));
    if (!table) return;

    var hidden = [];
    try {
      hidden = JSON.parse(localStorage.getItem(storageKey) || '[]');
    } catch (e) {
      hidden = [];
    }

    function apply() {
      table.querySelectorAll('[data-col]').forEach(function (el) {
        el.hidden = hidden.indexOf(el.getAttribute('data-col')) !== -1;
      });
    }

    panel.querySelectorAll('input[type="checkbox"]').forEach(function (cb) {
      cb.checked = hidden.indexOf(cb.value) === -1;
      cb.addEventListener('change', function () {
        if (cb.checked) {
          hidden = hidden.filter(function (c) { return c !== cb.value; });
        } else {
          hidden.push(cb.value);
        }
        try {
          localStorage.setItem(storageKey, JSON.stringify(hidden));
        } catch (e) {}
        apply();
      });
    });

    apply();
  });
});
