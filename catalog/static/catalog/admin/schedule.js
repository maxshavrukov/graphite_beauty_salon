/* Страница «Расписание»: выбор дней в календаре и отправка формы. */
(function () {
  var grid = document.getElementById("sched-grid");
  var form = document.getElementById("sched-form");
  var datesInput = document.getElementById("sched-dates");
  var counter = document.getElementById("sched-count");
  var cells = Array.prototype.slice.call(grid.querySelectorAll(".sched-cell"));
  var selectable = cells.filter(function (cell) { return !cell.disabled; });

  function refresh() {
    var picked = cells.filter(function (cell) {
      return cell.classList.contains("is-selected");
    });
    counter.textContent = picked.length;
    datesInput.value = picked.map(function (cell) {
      return cell.dataset.date;
    }).join(",");
  }

  function setSelected(cell, on) {
    if (!cell.disabled) { cell.classList.toggle("is-selected", on); }
  }

  function selectWhere(test) {
    selectable.forEach(function (cell) {
      setSelected(cell, test(cell));
    });
    refresh();
  }

  cells.forEach(function (cell) {
    cell.addEventListener("click", function () {
      setSelected(cell, !cell.classList.contains("is-selected"));
      refresh();
    });
  });

  // Клик по «Пн», «Вт»… выбирает (или снимает) весь столбец.
  grid.querySelectorAll(".sched-wd").forEach(function (button) {
    button.addEventListener("click", function () {
      var column = selectable.filter(function (cell) {
        return cell.dataset.weekday === button.dataset.weekday;
      });
      var allOn = column.length > 0 && column.every(function (cell) {
        return cell.classList.contains("is-selected");
      });
      column.forEach(function (cell) { setSelected(cell, !allOn); });
      refresh();
    });
  });

  document.getElementById("sched-weekdays").addEventListener("click", function () {
    selectWhere(function (cell) { return Number(cell.dataset.weekday) < 5; });
  });
  document.getElementById("sched-all").addEventListener("click", function () {
    selectWhere(function () { return true; });
  });
  document.getElementById("sched-none").addEventListener("click", function () {
    selectWhere(function () { return false; });
  });

  // После ошибки сервера возвращаем выбранные дни.
  var preselected = (grid.dataset.preselected || "").split(",");
  cells.forEach(function (cell) {
    if (preselected.indexOf(cell.dataset.date) !== -1) { setSelected(cell, true); }
  });
  refresh();

  form.addEventListener("submit", function (event) {
    refresh();
    if (!datesInput.value) {
      event.preventDefault();
      alert("Сначала выберите дни в календаре.");
      return;
    }
    var submitter = event.submitter;
    if (submitter && submitter.value === "clear" &&
        !confirm("Снять рабочие дни у выбранных дней (" + counter.textContent + ")?")) {
      event.preventDefault();
    }
  });
})();
