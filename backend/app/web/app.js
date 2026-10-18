/* Scorix Guest Web Player: zero-install, zero-account viewing (FR-4.2) with progressive sign-in (FR-4.4). */
(function () {
  "use strict";

  var $ = function (id) { return document.getElementById(id); };
  var store = {
    get: function (k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
    set: function (k, v) { try { localStorage.setItem(k, v); } catch (e) { /* private mode */ } }
  };

  // ------------------------------------------------------------ routing
  var parts = location.pathname.replace(/\/+$/, "").split("/").filter(Boolean); // ["web", kind, id, view]
  var page = { kind: parts[1] || "matches", id: decodeURIComponent(parts[2] || ""), view: parts[3] || "live" };
  var state = {
    guest: store.get("nascon_guest"), member: store.get("nascon_member"), cart: 0,
    room: null, seen: {}, pending: null, variant: "var-jersey-001-L"
  };

  function localUrl(url) {
    // Media URLs are issued for localhost; rewrite to the host this page was opened on (phone on LAN, grid node).
    return url ? url.replace("//localhost:", "//" + location.hostname + ":") : url;
  }

  function api(method, path, body, token) {
    var headers = { "Content-Type": "application/json" };
    if (token) headers.Authorization = "Bearer " + token;
    return fetch(path, { method: method, headers: headers, body: body ? JSON.stringify(body) : undefined })
      .then(function (r) {
        return r.text().then(function (t) {
          var data = t ? JSON.parse(t) : {};
          if (!r.ok) { var e = new Error((data.error && data.error.message) || r.statusText); e.status = r.status; e.code = data.error && data.error.code; throw e; }
          return data;
        });
      });
  }

  function guestToken() {
    if (state.guest) return Promise.resolve(state.guest);
    return api("POST", "/api/v1/guest/session").then(function (s) {
      state.guest = s.guest_token; store.set("nascon_guest", s.guest_token); return s.guest_token;
    });
  }

  // ------------------------------------------------------------ score + overlays
  function setScore(home, away) {
    if (home == null || away == null) return;
    var text = home + " - " + away;
    $("score").textContent = text;
    $("overlay-score").textContent = text;
  }

  var STATUS_TEXT = { upcoming: "Starts soon", in_progress: "Live now", completed: "Full time",
    postponed: "Postponed", cancelled: "Cancelled", abandoned: "Abandoned" };

  function applyMatch(m) {
    if (m.home && m.home.name) $("home-name").textContent = m.home.name;
    if (m.away && m.away.name) $("away-name").textContent = m.away.name;
    if (m.home && m.away) setScore(m.home.score, m.away.score);
    if (m.status) $("match-status").textContent = STATUS_TEXT[m.status] || m.status;
  }

  function applyMerch(p) {
    if (!p) return;
    var v = (p.variants || []).filter(function (x) { return x.variant_id === state.variant; })[0] || (p.variants || [])[0];
    $("merch-name").textContent = p.name || "Pinned by the club";
    if (v) {
      state.variant = v.variant_id;
      $("merch-price").textContent = "PKR " + (v.price_minor / 100).toLocaleString("en-PK");
      $("merch-size").textContent = (v.attributes && v.attributes.size) || "";
    }
    $("overlay-merch").textContent = p.name ? "🛒 " + p.name : "";
  }

  // ------------------------------------------------------------ chat
  function addMessage(m) {
    var key = m.message_id || (m.seq != null ? m.chat_room_id + ":" + m.seq : null);
    if (key && state.seen[key]) return;
    if (key) state.seen[key] = true;
    var list = $("messages");
    var empty = list.querySelector(".empty");
    if (empty) empty.remove();
    var li = document.createElement("li");
    var who = document.createElement("span");
    who.className = "who"; who.textContent = m.sender || "fan";
    li.appendChild(who);
    li.appendChild(document.createTextNode(m.text));
    list.appendChild(li);
    list.scrollTop = list.scrollHeight;
  }

  function loadChat(room) {
    state.room = room;
    return api("GET", "/api/v1/guest/chat/" + encodeURIComponent(room)).then(function (h) {
      if (!h.messages.length) {
        var li = document.createElement("li"); li.className = "empty"; li.textContent = "No messages yet. Say hello!";
        $("messages").appendChild(li);
      }
      h.messages.forEach(addMessage);
    }).catch(function () { /* chat history is optional */ });
  }

  function sendChat(text) {
    var token = state.member || state.guest;
    return api("POST", "/api/v1/chat", { chat_room_id: state.room, text: text }, token).then(function (m) {
      addMessage(m);
      $("chat-input").value = "";
    }).catch(function (e) {
      if (e.status === 403 || e.status === 401) {
        state.pending = text;           // resent after sign-in
        openModal();
      } else {
        $("video-status").textContent = e.message;
      }
    });
  }

  // ------------------------------------------------------------ realtime
  function onEvent(msg) {
    if (msg.type === "snapshot") { applyMatch(msg); applyMerch(msg.pinned_product); return; }
    if (msg.type === "match_updated") { applyMatch(msg); return; }
    if (msg.type === "chat") { if (!msg.flagged || msg.text) addMessage(msg); return; }
    if (msg.type === "product_pinned") { applyMerch(msg.product); return; }
    if (msg.type === "costream_updated") { applyCostream(msg); }
  }

  function listenMatch(id) {
    if (!window.EventSource) return listenSocket("/ws/matches/" + encodeURIComponent(id));
    var es = new EventSource("/api/v1/matches/" + encodeURIComponent(id) + "/stream");
    es.onmessage = function (e) { try { onEvent(JSON.parse(e.data)); } catch (x) { /* ignore */ } };
  }

  function listenSocket(path) {
    var proto = location.protocol === "https:" ? "wss://" : "ws://";
    var ws = new WebSocket(proto + location.host + path);
    ws.onmessage = function (e) { try { onEvent(JSON.parse(e.data)); } catch (x) { /* ignore */ } };
    ws.onclose = function () { setTimeout(function () { listenSocket(path); }, 1000); };
  }

  // ------------------------------------------------------------ video: WHEP (low latency) then HLS fallback
  function playWhep(url, video) {
    if (!window.RTCPeerConnection) return Promise.reject(new Error("no webrtc"));
    var pc = new RTCPeerConnection();
    pc.addTransceiver("video", { direction: "recvonly" });
    pc.addTransceiver("audio", { direction: "recvonly" });
    pc.ontrack = function (e) { if (video.srcObject !== e.streams[0]) video.srcObject = e.streams[0]; };
    return pc.createOffer().then(function (offer) { return pc.setLocalDescription(offer); }).then(function () {
      var ctrl = new AbortController();
      setTimeout(function () { ctrl.abort(); }, 3000);
      return fetch(url, { method: "POST", headers: { "Content-Type": "application/sdp" }, body: pc.localDescription.sdp, signal: ctrl.signal });
    }).then(function (r) {
      if (!r.ok) throw new Error("whep " + r.status);
      return r.text();
    }).then(function (answer) { return pc.setRemoteDescription({ type: "answer", sdp: answer }); })
      .catch(function (e) { pc.close(); throw e; });
  }

  function playHls(url, video) {
    if (video.canPlayType("application/vnd.apple.mpegurl")) { video.src = url; return; }
    if (window.Hls && window.Hls.isSupported()) {
      var hls = new window.Hls({ lowLatencyMode: true, liveSyncDurationCount: 2 });
      hls.loadSource(url);
      hls.attachMedia(video);
      hls.on(window.Hls.Events.ERROR, function (_, d) {
        if (d.fatal) { $("video-status").textContent = "The stream is offline. Retrying…"; setTimeout(function () { hls.loadSource(url); }, 4000); }
      });
    }
  }

  function startVideo(playback) {
    var video = $("video");
    video.addEventListener("playing", function () { $("video-status").textContent = ""; });
    if (!playback) return;
    var t = parseFloat(new URLSearchParams(location.search).get("t") || "0");
    if (t > 0) video.addEventListener("loadedmetadata", function () { try { video.currentTime = t; } catch (e) { /* live */ } }, { once: true });
    playWhep(localUrl(playback.whep), video).catch(function () { playHls(localUrl(playback.hls), video); });
  }

  // ------------------------------------------------------------ guest cart
  function setCart(n) { state.cart = n; $("cart-count").textContent = String(n); }

  function addToCart() {
    setCart(state.cart + 1);
    guestToken().then(function (tok) {
      return api("POST", "/api/v1/guest/cart", { variant_id: state.variant, quantity: 1 }, tok);
    }).then(function (r) { setCart(r.count); }).catch(function () { /* keep the local count */ });
  }

  // ------------------------------------------------------------ progressive auth modal
  var lastFocus = null;

  function openModal() {
    lastFocus = document.activeElement;
    $("auth-backdrop").hidden = false;
    $("auth-modal").hidden = false;
    $("auth-error").textContent = "";
    $("auth-email").focus();
  }

  function closeModal() {
    $("auth-backdrop").hidden = true;
    $("auth-modal").hidden = true;
    if (lastFocus) lastFocus.focus();
  }

  function trapFocus(e) {
    if ($("auth-modal").hidden) return;
    if (e.key === "Escape") { closeModal(); return; }
    if (e.key !== "Tab") return;
    var items = $("auth-modal").querySelectorAll("input, button, a");
    var first = items[0], last = items[items.length - 1];
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  }

  function signIn(ev) {
    ev.preventDefault();
    $("auth-submit").disabled = true;
    api("POST", "/api/v1/auth/login", { email: $("auth-email").value, password: $("auth-password").value })
      .then(function (s) {
        state.member = s.token; store.set("nascon_member", s.token);
        $("viewer-badge").textContent = "Signed in as " + s.user.name;
        var merge = state.cart > 0 && state.guest
          ? api("POST", "/api/v1/cart/merge", { guest_token: state.guest }, s.token).catch(function () { return null; })
          : Promise.resolve(null);
        return merge.then(function () {
          closeModal();
          if (state.pending) { var text = state.pending; state.pending = null; return sendChat(text); }
          var t = $("video").currentTime || 0;            // resume at the same playback position
          if (t > 0) history.replaceState(null, "", location.pathname + "?t=" + t.toFixed(1));
        });
      })
      .catch(function (e) { $("auth-error").textContent = e.message || "Could not sign in."; })
      .then(function () { $("auth-submit").disabled = false; });
  }

  // ------------------------------------------------------------ page types
  function applyCostream(c) {
    $("home-name").textContent = "Host";
    $("away-name").textContent = c.participant_count + " live";
    var host = (c.names && c.names[c.active_host]) || c.active_host || "—";
    $("score").textContent = c.status === "active" ? host : "Ended";
    $("match-status").textContent = c.status === "active" ? "Co-stream · " + c.layout.replace("_", " ") : "This co-stream has ended";
  }

  function boot() {
    var title = $("page-title");
    if (page.kind === "matches") {
      title.textContent = { preview: "Match preview", vod: "Match replay", notice: "Match update" }[page.view] || "Live match";
      if (page.view === "notice") {
        var st = new URLSearchParams(location.search).get("state") || "postponed";
        $("notice").hidden = false;
        $("notice").textContent = "This match has been " + st + ". The score and chat stay available here.";
      }
      api("GET", "/api/v1/guest/matches/" + encodeURIComponent(page.id)).then(function (m) {
        applyMatch(m); applyMerch(m.pinned_product); startVideo(m.playback); loadChat(m.chat_room_id);
      }).catch(function (e) { $("video-status").textContent = e.message; });
      listenMatch(page.id);
    } else if (page.kind === "costream") {
      title.textContent = "Live co-stream";
      api("GET", "/api/v1/guest/costream/" + encodeURIComponent(page.id)).then(function (c) {
        applyCostream(c); startVideo(c.playback); loadChat(c.chat_room_id);
        listenSocket("/ws/chat/" + encodeURIComponent(c.chat_room_id));
        listenSocket("/ws/costream/" + encodeURIComponent(page.id));
      }).catch(function (e) { $("video-status").textContent = e.message; });
      api("GET", "/api/v1/guest/matches/match-m1").then(function (m) { applyMerch(m.pinned_product); }).catch(function () {});
    } else {
      title.textContent = page.kind === "players" ? "Athlete" : "Club";
      $("match-status").textContent = page.id;
      api("GET", "/api/v1/guest/matches/match-m1").then(function (m) { applyMerch(m.pinned_product); }).catch(function () {});
      loadChat("chat-" + page.id);
    }
    if (state.member) $("viewer-badge").textContent = "Signed in";
    guestToken().catch(function () { /* retried on first write */ });

    $("add-to-cart").addEventListener("click", addToCart);
    $("checkout").addEventListener("click", function () { if (!state.member) openModal(); });
    $("chat-form").addEventListener("submit", function (e) {
      e.preventDefault();
      var text = $("chat-input").value.trim();
      if (text) sendChat(text);
    });
    $("auth-form").addEventListener("submit", signIn);
    $("auth-cancel").addEventListener("click", closeModal);
    $("auth-backdrop").addEventListener("click", closeModal);
    $("auth-register").addEventListener("click", function (e) { e.preventDefault(); $("auth-error").textContent = "Registration opens at the venue desk. Use a demo account for now."; });
    document.addEventListener("keydown", trapFocus);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot); else boot();
})();
