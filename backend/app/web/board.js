/* Scorix QR board: every code is the stable short link; the server decides where it lands at scan time. */
(function () {
  "use strict";
  var LABELS = { in_progress: "Live", upcoming: "Upcoming", completed: "Full time", postponed: "Postponed",
    cancelled: "Cancelled", abandoned: "Abandoned", active: "Active", terminated: "Ended" };

  function local(url) { return url ? url.replace("//localhost:", "//" + location.hostname + ":") : url; }

  function card(item) {
    var node = document.getElementById("card").content.firstElementChild.cloneNode(true);
    var q = function (sel) { return node.querySelector(sel); };
    var title = item.title || item.entity_id;
    q(".qr").src = "/audit/v1/qr/" + encodeURIComponent(item.entity_id) + "/export.svg";
    q(".qr").alt = "QR code for " + title;
    var pill = q(".pill");
    pill.textContent = LABELS[item.entity_status] || item.entity_type;
    if (item.entity_status === "in_progress") pill.classList.add("live");
    q(".title").textContent = title;
    q(".sub").textContent = item.subtitle || "";
    q(".score").textContent = item.entity_type === "match" && item.entity_status !== "upcoming" ? (item.score || "") : "";
    var short = local(item.short_url);
    q(".short").href = short;
    q(".short").textContent = short.replace(/^https?:\/\//, "");
    q(".open").href = item.target_route;
    q(".open").setAttribute("aria-label", "Open " + title);
    q(".png").href = local(item.export_formats.png);
    q(".png").setAttribute("aria-label", "Download QR image for " + title);
    q(".pdf").href = local(item.export_formats.pdf);
    q(".pdf").setAttribute("aria-label", "Printable poster for " + title);
    q(".scans").textContent = item.scan_count + (item.scan_count === 1 ? " scan" : " scans");
    return node;
  }

  function fill(id, items) {
    var el = document.getElementById(id);
    el.innerHTML = "";
    items.forEach(function (i) { el.appendChild(card(i)); });
    if (!items.length) el.innerHTML = '<p class="loading">Nothing here right now.</p>';
  }

  function load() {
    fetch("/api/v1/guest/qr-board").then(function (r) { return r.json(); }).then(function (b) {
      fill("matches", b.matches);
      fill("players", b.players);
      fill("clubs", b.clubs);
      document.getElementById("costreams-section").hidden = !b.costreams.length;
      fill("costreams", b.costreams);
    }).catch(function () {
      document.getElementById("matches").innerHTML = '<p class="loading">Could not reach the server. Retrying…</p>';
    });
  }

  load();
  setInterval(load, 15000);  // statuses and scan counts stay fresh on a venue screen
})();
