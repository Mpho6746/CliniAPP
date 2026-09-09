document.addEventListener('DOMContentLoaded', function () {
  var container = document.getElementById('dash-widgets');
  if (!container) return;

  var dragging = null;

  function getDragAfterElement(y) {
    var els = Array.prototype.slice.call(container.querySelectorAll('.dash-widget:not(.dash-widget-dragging)'));
    var closest = { offset: -Infinity, element: null };
    els.forEach(function (child) {
      var box = child.getBoundingClientRect();
      var offset = y - box.top - box.height / 2;
      if (offset < 0 && offset > closest.offset) {
        closest = { offset: offset, element: child };
      }
    });
    return closest.element;
  }

  function saveOrder() {
    var order = Array.prototype.map.call(container.querySelectorAll('.dash-widget'), function (w) {
      return w.getAttribute('data-widget-key');
    });
    fetch('/dashboard/layout/reorder', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ order: order }),
    }).catch(function () {});
  }

  container.querySelectorAll('.dash-widget').forEach(function (widget) {
    widget.addEventListener('dragstart', function () {
      dragging = widget;
      widget.classList.add('dash-widget-dragging');
    });
    widget.addEventListener('dragend', function () {
      widget.classList.remove('dash-widget-dragging');
      dragging = null;
      saveOrder();
    });
  });

  container.addEventListener('dragover', function (e) {
    if (!dragging) return;
    e.preventDefault();
    var after = getDragAfterElement(e.clientY);
    if (after == null) {
      container.appendChild(dragging);
    } else {
      container.insertBefore(dragging, after);
    }
  });
});
