// Kein Inline-JavaScript: die Content-Security-Policy erlaubt nur Skripte von 'self'.
(function () {
  // Krankmeldungs-Formular
  const from = document.getElementById("date_from");
  const to = document.getElementById("date_to");
  if (from && to) {
    // Bis-Datum nie vor Von-Datum zulassen
    from.addEventListener("change", () => {
      to.min = from.value;
      if (to.value && to.value < from.value) to.value = from.value;
    });
  }

  // Hinweis, wenn sich der Zeitraum mit einer eigenen Meldung überschneidet
  const hint = document.getElementById("overlap-hint");
  if (from && to && hint) {
    const reports = JSON.parse(hint.dataset.reports || "[]");
    const list = document.getElementById("overlap-list");
    const confirmField = document.getElementById("confirm_overlap");
    const check = () => {
      const start = from.value;
      const end = to.value || start;
      const clashes = start ? reports.filter((r) => r.from <= end && start <= r.to) : [];
      hint.hidden = clashes.length === 0;
      list.textContent = clashes.map((r) => r.text).join(", ");
      // Wer den Hinweis gesehen hat, bestätigt die Überschneidung mit dem Absenden
      confirmField.value = clashes.length ? "1" : "";
    };
    from.addEventListener("change", check);
    to.addEventListener("change", check);
    check();
  }

  // Doppeltes Absenden verhindern
  document.querySelectorAll("form[data-once]").forEach((form) => {
    form.addEventListener("submit", () => {
      const btn = form.querySelector("button[type=submit]");
      if (btn) {
        btn.disabled = true;
        btn.textContent = btn.dataset.busy || "Wird gesendet …";
      }
    });
  });

  // Sicherheitsabfrage vor dem Löschen
  document.querySelectorAll("form[data-confirm]").forEach((form) => {
    form.addEventListener("submit", (event) => {
      if (!window.confirm(form.dataset.confirm)) event.preventDefault();
    });
  });

  // CSV-Import direkt nach der Dateiauswahl starten
  document.querySelectorAll("input[data-autosubmit]").forEach((input) => {
    input.addEventListener("change", () => {
      if (input.files.length) input.form.submit();
    });
  });

  // Admin: jede Minute neu laden, damit neue Meldungen erscheinen –
  // aber nicht, solange gerade etwas eingetippt wird.
  if (document.body.classList.contains("admin-page")) {
    let dirty = false;
    document.addEventListener("input", () => { dirty = true; });
    setInterval(() => {
      const el = document.activeElement;
      const typing = el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA");
      if (!dirty && !typing) window.location.reload();
    }, 60000);
  }
})();
