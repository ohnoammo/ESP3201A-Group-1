(() => {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const el = (tag, cls, text) => {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined) e.textContent = text;
    return e;
  };

  const TYPE_LABEL = { title_description: "Description", commits: "Commit messages", hunk: "Diff",
    review_thread: "Review comment", conversation: "Conversation", file_nodiff: "File", fixed: "Chunk" };
  const CITE = /\[\s*PR\s*#?\s*(\d+)\s*-\s*c\s*(\d+)\s*\]/gi;
  const state = { mode: "strict", retriever: "dense", wantRetriever: "dense", chunking: "structural", denseOk: true,
    models: [], busy: false, final: {}, repos: [] };

  // ---------- sidebar & drawer ----------
  // Compact mode: only when the window is narrow, e.g. snapped to half the screen next to
  // GitHub (Win + left/right). The sidebar then opens over the chat.
  const NARROW = 820;
  try { localStorage.removeItem("prExplainerCompact"); } catch (e) { /* old manual setting */ }
  const isCompact = () => innerWidth < NARROW;
  function applyCompact() {
    const on = isCompact();
    $("app").classList.toggle("compact", on);
    if (on) $("app").classList.remove("collapsed"); else $("app").classList.remove("side-open");
    $("expand").hidden = !on && !$("app").classList.contains("collapsed");
  }
  addEventListener("resize", applyCompact);

  $("collapse").addEventListener("click", () => setSidebar(false));
  $("expand").addEventListener("click", () => setSidebar(true));
  function setSidebar(open) {
    if (isCompact()) $("app").classList.toggle("side-open", open);
    else $("app").classList.toggle("collapsed", !open);
    $("expand").hidden = open && !isCompact();
  }
  applyCompact();

  function openDrawer(open) {
    $("drawer").hidden = !open; $("scrim").hidden = !open;
    $("gear").setAttribute("aria-expanded", String(open));
    if (open) $("closeDrawer").focus();
  }
  $("gear").addEventListener("click", () => openDrawer($("drawer").hidden));
  $("settingsTool").addEventListener("click", () => openDrawer(true));
  $("closeDrawer").addEventListener("click", () => openDrawer(false));
  $("scrim").addEventListener("click", () => openDrawer(false));
  document.addEventListener("keydown", (ev) => { if (ev.key === "Escape" && !$("drawer").hidden) openDrawer(false); });

  function seg(id, key, onChange) {
    const box = $(id);
    box.addEventListener("click", (ev) => {
      const b = ev.target.closest("button");
      if (!b || b.disabled) return;
      box.querySelectorAll("button").forEach((x) => x.classList.toggle("on", x === b));
      state[key] = b.dataset.v;
      setupText();
      if (onChange) onChange();
    });
  }
  function setSeg(id, value) {
    $(id).querySelectorAll("button").forEach((b) => b.classList.toggle("on", b.dataset.v === value));
  }
  seg("modeSeg", "mode");
  seg("retrSeg", "retriever", () => { state.wantRetriever = state.retriever; warmup(); });
  seg("chunkSeg", "chunking", () => { refreshStatus().then(warmup); });
  $("pool").addEventListener("change", () => { setupText(); warmup(); refreshStatus(); });
  $("links").addEventListener("change", setupText);
  $("compare").addEventListener("change", setupText);
  $("model").addEventListener("change", () => { setupText(); refreshStatus(); });
  $("gate").addEventListener("change", () => {
    setupText();
    if ($("gate").checked) fetch("/api/gate_warmup", { method: "POST" }).catch(() => {});   // loads MiniCheck
  });

  // Experimental support check (Exp 2 gate): strict answers only, so it's off in standard mode.
  function syncGate() {
    const gs = state.gateStatus;
    const standardOnly = !$("compare").checked && state.mode === "standard";
    const missing = gs && !gs.available;
    $("gate").disabled = standardOnly || !!missing;
    if ($("gate").disabled) $("gate").checked = false;
    $("gateNote").textContent = missing ? `Unavailable: ${gs.problem}`
      : standardOnly ? "The gate needs cited answers (strict mode)"
      : "Holds back strict answers whose cited excerpts don't clearly support them. Experimental, and not hallucination protection.";
  }

  function settings() {
    const modes = $("compare").checked ? ["standard", "strict"] : [state.mode];
    return { repo: current ? current.repo : defaultRepo(), pool: $("pool").value || "A2000", chunking: state.chunking, retriever: state.retriever,
      links: $("links").checked, modes, model: $("model").value, gate: $("gate").checked && !$("gate").disabled };
  }
  function setupText() {
    syncGate();
    const s = settings();
    const isFinal = state.final.finalized && s.retriever === state.final.retriever && s.chunking === state.final.chunking
      && s.links === state.final.links && s.modes.length === 1 && s.modes[0] === state.final.mode
      && (!state.final.pool || s.pool === state.final.pool) && (!state.final.model || s.model === state.final.model);
    $("setupText").textContent = (isFinal ? (state.transfer ? "Django's final setup · " : "Final setup · ") : "Experimental · ")
      + `${s.retriever} · ${s.chunking === "fixed" ? "fixed 512" : "structural"} · links ${s.links ? "on" : "off"} · `
      + (s.modes.length > 1 ? "compare" : s.modes[0]) + (s.gate ? " · support check" : "");
    // What a check covers depends on the settings, so that part of the note follows them.
    const note = state.repoNote ? `${state.repoNote} ${isFinal ? state.repoFinalNote
      : "The settings selected here differ from Django's final setup."}` : "";
    $("repoNote").textContent = note; $("repoNote").hidden = !note;
  }

  // ---------- status ----------
  let polling = null;
  async function refreshStatus() {
    const s = settings();
    let st;
    try {
      st = await (await fetch(`/api/status?repo=${encodeURIComponent(s.repo)}&pool=${encodeURIComponent(s.pool)}&chunking=${s.chunking}`)).json();
    } catch (e) {
      banner("Can't reach the local server. Is app/server.py running?", true);
      if (!polling) polling = setInterval(refreshStatus, 1500);     // recovers when it's back
      return;
    }
    if (s.repo !== settings().repo) return;              // the chat changed repo meanwhile

    const poolSel = $("pool");
    if (st.pools.map((p) => p.label).join() !== [...poolSel.options].map((o) => o.text).join()) {
      const prev = poolSel.value, fp = state.final.pool;
      poolSel.innerHTML = "";
      st.pools.forEach((p) => poolSel.append(new Option(p.label, p.id)));
      const has = (id) => st.pools.some((p) => p.id === id);
      if (has(prev)) poolSel.value = prev; else if (has(fp)) poolSel.value = fp;
    }
    state.gateStatus = st.gate || null;
    state.transfer = !!st.repo_note;
    state.repoNote = st.repo_note || ""; state.repoFinalNote = st.repo_final_note || "";
    const models = st.ollama.models || [];
    if (models.join() !== state.models.join()) {
      state.models = models;
      const sel = $("model"); const prev = sel.value; sel.innerHTML = "";
      if (!models.length) sel.append(new Option("qwen3:4b-instruct-2507-q4_K_M", "qwen3:4b-instruct-2507-q4_K_M"));
      models.forEach((m) => sel.append(new Option(m, m)));
      const pref = models.find((m) => m === prev) || models.find((m) => m.startsWith("qwen3:4b-instruct")) || models[0];
      if (pref) sel.value = pref;
    }
    // product mode: final settings from app/final_settings.json (applied once, on first load)
    if (!state.finalApplied) {
      state.finalApplied = true;
      const f = state.final = st.final || {};
      if (f.finalized) {
        state.mode = f.mode; setSeg("modeSeg", f.mode);
        state.retriever = state.wantRetriever = f.retriever; setSeg("retrSeg", f.retriever);
        state.chunking = f.chunking; setSeg("chunkSeg", f.chunking);
        $("links").checked = f.links;
        if (f.pool && [...$("pool").options].some((o) => o.value === f.pool)) $("pool").value = f.pool;
        if (f.model && [...$("model").options].some((o) => o.value === f.model)) $("model").value = f.model;
        note("Defaults are the final settings chosen from Experiments 1 and 2"
          + (f.evidence ? `: ${f.evidence}.` : ".") + " Change them here to compare.");
      } else {
        note(f.problem || "Final settings not decided yet (app/final_settings.json): all options are experimental.");
      }
    }
    state.denseOk = !!st.dense_cache;
    $("retrSeg").querySelectorAll("button").forEach((b) => {
      const needsDense = b.dataset.v !== "bm25";
      b.disabled = needsDense && !state.denseOk;
      b.title = b.disabled ? st.dense_problem : "";
    });
    // Dense can be unavailable for one repo or chunking only, so the choice comes back afterwards.
    const usable = state.denseOk ? state.wantRetriever : "bm25";
    if (usable !== state.retriever) { state.retriever = usable; setSeg("retrSeg", usable); }
    const denseWarning = (!state.denseOk && state.final.finalized && state.final.retriever !== "bm25")
      ? `${st.dense_problem}, so BM25 is used instead of the final dense setup. `
        + "Results will differ from the final system." : null;

    const ok = st.ollama.running;
    $("localDot").className = "dot " + (ok ? "ok" : "bad");
    $("localTitle").textContent = ok ? "Runs locally" : "Ollama not running";
    $("localText").textContent = ok ? `${$("model").value} on this computer. No data leaves it.`
      : "Start the Ollama app to get answers. Until then you'll see the retrieved sources only.";
    const ix = st.index;
    $("idxText").textContent = ix.n_prs
      ? `Index: ${ix.n_prs.toLocaleString()} ${ix.item}s · synced ${(ix.synced || "").slice(0, 10)}` : `Index: ${ix.pool_label}`;
    setRepos(st.repos);
    setupText();

    const e = st.engine;
    if (e.state === "loading") {
      banner(e.message + (e.progress != null ? "" : "…"), false, e.progress);
      if (!polling) polling = setInterval(refreshStatus, 1500);
    } else {
      if (polling) { clearInterval(polling); polling = null; }
      if (e.state === "error") banner(e.message, true);
      else if (!ok) banner("Ollama isn't running. Start it (open the Ollama app) to get answers.");
      else banner(denseWarning);
    }
  }
  function note(msg) { $("finalNote").textContent = msg; $("finalNote").hidden = !msg; }
  function banner(msg, isError, progress) {
    const b = $("banner");
    if (!msg) { b.hidden = true; return; }
    b.hidden = false; b.className = "banner" + (isError ? " error" : "");
    b.textContent = msg;
    if (progress != null) { const p = el("progress"); p.max = 1; p.value = progress; b.append(p); }
  }
  async function warmup() {
    try {
      await fetch("/api/warmup", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: "-", ...settings() }) });
    } catch (e) { /* status poll reports problems */ }
    setTimeout(refreshStatus, 300);
  }

  // ---------- repositories ----------
  // The server lists the repos whose PRs are in this folder (engine.REPOS). Adding another one
  // means downloading it first, which the app can't do, so that entry is shown disabled.
  const REPO_ICON = '<svg viewBox="0 0 24 24" width="15" height="15" aria-hidden="true"><path fill="currentColor" d="M4 4a2 2 0 0 1 2-2h12v16H6a1 1 0 0 0 0 2h12v2H6a3 3 0 0 1-3-3zm2 0v12.2A3 3 0 0 1 6 16h10V4z"/></svg>';
  function setRepos(repos) {
    if (JSON.stringify(repos) === JSON.stringify(state.repos)) return;
    state.repos = repos;
    const list = $("repoList"); list.innerHTML = "";
    repos.forEach((r) => {
      const li = el("li"); const b = el("button"); b.type = "button";
      b.innerHTML = REPO_ICON; b.append(el("span", null, r.id));
      if (r.prs) b.append(el("span", "count", `${r.prs.toLocaleString()} ${r.item}s`));
      b.title = `Start a new chat about ${r.id}`;
      b.addEventListener("click", () => newConversation(r.id));
      li.append(b); list.append(li);
    });
    const li = el("li"); const add = el("button"); add.type = "button"; add.disabled = true;
    add.innerHTML = '<svg viewBox="0 0 24 24" width="15" height="15" aria-hidden="true"><path fill="currentColor" d="M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6z"/></svg>';
    add.append(el("span", null, "Add repository"));
    add.title = "Not available yet: a new repo needs its PRs downloaded and an index built (github_prs.py), which the app can't do on its own.";
    li.append(add); list.append(li);
    const sel = $("repoSel"); sel.innerHTML = "";
    repos.forEach((r) => sel.append(new Option(r.id, r.id)));
    if (current) sel.value = current.repo;
  }
  $("repoSel").addEventListener("change", () => {
    if (!current) return;
    current.repo = $("repoSel").value; save(); renderConversation();
  });
  // A chat's repo decides the pools, dense availability and index, so re-read them on a change.
  function syncRepo() {
    if (current.repo === state.activeRepo) return;
    state.activeRepo = current.repo;
    refreshStatus().then(warmup);
  }

  // ---------- conversations (kept in this browser only) ----------
  const CKEY = "prExplainerConversations";
  let convs = [];
  try { convs = JSON.parse(localStorage.getItem(CKEY)) || []; } catch (e) { convs = []; }
  let current = null;
  function save() {
    for (let keep = 30; keep > 0; keep = Math.floor(keep / 2)) {
      try { localStorage.setItem(CKEY, JSON.stringify(convs.slice(0, keep))); return; } catch (e) { /* too big: keep fewer */ }
    }
  }
  function defaultRepo() { return (state.repos[0] && state.repos[0].id) || "django/django"; }
  function newConversation(repo) {
    current = { id: String(Date.now()), title: "New chat", repo: repo || (current && current.repo) || defaultRepo(),
      messages: [] };
    renderConversation(); renderConvList(); $("question").focus();
    if (isCompact()) setSidebar(false);
  }
  function openConversation(id) {
    current = convs.find((c) => c.id === id) || current;
    renderConversation(); renderConvList();
    if (isCompact()) setSidebar(false);
  }
  function deleteConversation(id) {
    convs = convs.filter((c) => c.id !== id); save();
    if (current && current.id === id) newConversation(); else renderConvList();
  }
  function renderConvList() {
    const list = $("convList"); list.innerHTML = "";
    if (!convs.length) { list.append(el("li", "conv-empty", "No chats yet")); return; }
    convs.forEach((c) => {
      const li = el("li", current && c.id === current.id ? "on" : "");
      const b = el("button", "open"); b.type = "button"; b.title = `${c.title} (${c.repo})`;
      b.append(el("span", null, c.title));
      b.addEventListener("click", () => openConversation(c.id));
      const d = el("button", "del", "✕"); d.type = "button"; d.title = "Delete chat"; d.setAttribute("aria-label", "Delete chat");
      d.addEventListener("click", () => deleteConversation(c.id));
      li.append(b, d); list.append(li);
    });
  }
  function renderConversation() {
    closeViewer();                                   // its excerpts belong to the old chat
    setQuote("");
    $("log").innerHTML = "";
    current.messages.forEach((m) => $("log").append(userMsg(m.body), botMsg(m)));
    const chatting = current.messages.length > 0;
    $("hero").hidden = chatting; $("app").classList.toggle("chatting", chatting);
    $("heroRepo").textContent = current.repo;
    syncRepo();
    if ([...$("repoSel").options].some((o) => o.value === current.repo)) $("repoSel").value = current.repo;
    scrollToEnd();
  }
  $("newChat").addEventListener("click", () => newConversation());
  $("clearHistory").addEventListener("click", () => { convs = []; save(); newConversation(); openDrawer(false); });

  $("exportBtn").addEventListener("click", () => {
    if (!current || !current.messages.length) return;
    const lines = [`# ${current.title}`, "", `Repository: ${current.repo}`, ""];
    current.messages.forEach((m) => {
      lines.push(`## Q: ${m.body.question}`, "");
      if (m.body.quote) lines.push(...m.body.quote.split("\n").map((l) => `> ${l}`), "");
      if (m.body.code) lines.push("```", m.body.code, "```", "");
      if (m.error) lines.push(`Error: ${m.error}`, "");
      (m.data ? m.data.answers : []).forEach((a) => lines.push(
        (m.data.answers.length > 1 ? `**${a.mode}:** ` : "") + (a.not_found ? "_Not found in the PR history._" : a.answer), ""));
      if (m.data) lines.push(`Sources: ${[...new Set(m.data.retrieval.sources.map((s) => (m.data.retrieval.prefix || "#") + s.pr))].join(", ")}`, "");
    });
    const a = el("a"); a.href = URL.createObjectURL(new Blob([lines.join("\n")], { type: "text/markdown" }));
    a.download = `${current.title.replace(/[^\w-]+/g, "_").slice(0, 40) || "chat"}.md`; a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  });

  // ---------- composer ----------
  function setCode(code) { $("code").value = code || ""; showCode(!!code); }
  function showCode(on) {
    $("codeRow").hidden = !on;
    $("codeToggle").classList.toggle("on", on);
    $("codeToggle").setAttribute("aria-pressed", String(on));
  }
  $("codeToggle").addEventListener("click", () => {
    const on = $("codeRow").hidden; showCode(on); (on ? $("code") : $("question")).focus();
  });
  function autosize() {
    const q = $("question"); q.style.height = "auto"; q.style.height = Math.min(q.scrollHeight, 180) + "px";
  }
  $("question").addEventListener("input", autosize);
  $("question").addEventListener("keydown", (ev) => {
    if (ev.key === "Enter" && !ev.shiftKey && !ev.isComposing) { ev.preventDefault(); ask(); }
  });
  $("askForm").addEventListener("submit", (ev) => { ev.preventDefault(); ask(); });

  function scrollToEnd() { const c = $("chat"); c.scrollTop = c.scrollHeight; }

  // ---------- asking ----------
  async function ask() {
    const question = $("question").value.trim();
    if (!question || state.busy) { $("question").focus(); return; }
    const conv = current;
    const body = { question, quote: state.quote || "", code: $("code").value.trim(), repo: conv.repo, ...settings() };
    state.busy = true; $("askBtn").disabled = true;
    $("hero").hidden = true; $("app").classList.add("chatting");
    $("question").value = ""; autosize(); setCode(""); setQuote("");

    $("log").append(userMsg(body));
    const pending = statusMsg("Searching the PR history…");
    $("log").append(pending); scrollToEnd();

    const t0 = performance.now();
    const tick = setInterval(() => {
      pending.querySelector(".elapsed").textContent = `${Math.round((performance.now() - t0) / 1000)} s`;
    }, 1000);
    let entry;
    try {
      // Streamed: one JSON object per line (retrieval, tokens, answers, done).
      const r = await fetch("/api/ask_stream", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body) });
      if (!r.ok) { const d = await r.json().catch(() => ({})); throw new Error(d.detail || "Request failed"); }
      const data = { retrieval: null, answers: [], error: null };
      const live = {};                                   // mode -> streaming text element
      const reader = r.body.getReader(); const dec = new TextDecoder(); let buf = "";
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        let nl;
        while ((nl = buf.indexOf("\n")) >= 0) {
          const ev = JSON.parse(buf.slice(0, nl)); buf = buf.slice(nl + 1);
          if (ev.type === "retrieval") {
            data.retrieval = ev.retrieval;
            const rt = ev.retrieval;
            setStatus(pending, `Found ${rt.sources.length} excerpts from ${rt.n_prs} ${rt.item || "PR"}s `
              + `(${rt.retrieve_seconds.toFixed(1)} s) · writing the answer…`);
          } else if (ev.type === "token" && body.gate && ev.mode === "strict") {
            // Gated answers are shown only once the support check has decided.
            setStatus(pending, "Writing the answer (shown after the experimental support check)…");
          } else if (ev.type === "checking") {
            setStatus(pending, "Running the experimental support check…");
          } else if (ev.type === "token") {
            if (!live[ev.mode]) {
              if (body.modes.length > 1) pending.querySelector(".bubble").append(
                el("span", "mode-tag live-tag", ev.mode === "strict" ? "Strict grounding" : "Standard RAG"));
              live[ev.mode] = el("div", "answer-text streaming");
              pending.querySelector(".bubble").append(live[ev.mode]);
            }
            live[ev.mode].textContent += ev.text; scrollToEnd();
          } else if (ev.type === "answer") {
            data.answers.push(ev.answer);
          } else if (ev.type === "error") {
            data.error = ev.error;
          }
        }
      }
      if (!data.retrieval) throw new Error(data.error || "The server ended the answer early.");
      entry = { body, data };
    } catch (e) {
      entry = { body, error: e.message };
      refreshStatus();
    } finally {
      clearInterval(tick); pending.remove();
      state.busy = false; $("askBtn").disabled = false;
    }
    if (!conv.messages.length) {
      conv.title = question.length > 60 ? question.slice(0, 57) + "…" : question;
      convs.unshift(conv);
    } else {                                          // most recently used chat first
      convs = [conv, ...convs.filter((c) => c !== conv)];
    }
    conv.messages.push(entry); save(); renderConvList();
    if (conv === current) {
      const msg = botMsg(entry); $("log").append(msg);
      msg.scrollIntoView({ block: "start" });
      $("question").focus();
    }
  }

  // ---------- messages ----------
  function userMsg(body) {
    const li = el("li", "msg user");
    const b = el("div", "bubble");
    if (body.quote) b.append(el("div", "q-quote", body.quote));
    b.append(el("div", "q", body.question));
    if (body.code) b.append(el("pre", "q-code", body.code));
    li.append(b);
    return li;
  }
  function statusMsg(text) {
    const li = el("li", "msg bot pending");
    const b = el("div", "bubble");
    const row = el("div", "status");
    row.append(el("span", "spinner"), el("span", "status-text", text), el("span", "elapsed", "0 s"));
    b.append(row); li.append(b);
    return li;
  }
  function setStatus(li, text) { li.querySelector(".status-text").textContent = text; }
  function botMsg(entry) {
    const li = el("li", "msg bot");
    const b = el("div", "bubble");
    li.append(b);
    if (entry.error) {
      const nf = el("div", "not-found"); nf.append(el("span", "icon", "⚠"), el("div", null, entry.error));
      b.append(nf); return li;
    }
    const { body, data } = entry;
    const ret = data.retrieval;
    const srcById = Object.fromEntries(ret.sources.map((s) => [s.id.toLowerCase(), s]));
    const srcBox = el("details", "sources");
    const ctx = { srcBox, highlights: {}, cited: new Set(), sources: ret.sources, pool: body.pool || "A2000",
      repo: body.repo || "django/django", item: ret.item || "PR", host: ret.host || "GitHub",
      ref: (n) => `${ret.item || "PR"} ${ret.prefix || "#"}${n}` };

    if (data.error && !data.answers.length) {
      const nf = el("div", "not-found"); nf.append(el("span", "icon", "⚠"), el("div", null, data.error)); b.append(nf);
    }
    data.answers.forEach((a) => a.citations.forEach((c) => {
      if (!c.in_context) return;
      const k = c.id.toLowerCase(); ctx.cited.add(k);
      (ctx.highlights[k] = ctx.highlights[k] || []).push(...c.highlights);
    }));
    const answers = el("div", "answers" + (data.answers.length > 1 ? " two" : ""));
    data.answers.forEach((a) => answers.append(answerBlock(body, a, srcById, ctx, data.answers.length > 1)));
    b.append(answers);
    if (data.error && data.answers.length) b.append(el("div", "warn-uncited", data.error));

    const meta = el("div", "meta-line");
    meta.textContent = [
      body.repo || "django/django",
      `${body.retriever} · ${body.chunking === "fixed" ? "fixed 512" : body.chunking}`,
      body.links ? `links α=${ret.alpha} (${ret.n_linked} linked)` : "links off",
      `${ret.sources.length} chunks from ${ret.n_prs} ${ctx.item}s · ${ret.tokens.toLocaleString()}/2,560 tokens`,
      `retrieved in ${ret.retrieve_seconds.toFixed(2)} s`,
      ...(body.quote ? ["with a quote (not part of the experiments)"] : []),
    ].join("  ·  ");
    b.append(meta);

    const sum = el("summary");
    sum.append(el("span", null, `Sources (${ret.sources.length})`),
      el("span", "muted", ctx.cited.size ? ` · ${ctx.cited.size} cited` : ""));
    srcBox.append(sum);
    srcBox.addEventListener("toggle", () => { if (srcBox.open && !srcBox.dataset.done) {
      srcBox.dataset.done = "1"; renderSources(srcBox, ret.sources, ctx); } });
    b.append(srcBox);
    return li;
  }

  function answerBlock(body, a, srcById, ctx, labelled) {
    const card = el("div", "answer");
    if (labelled) {
      const head = el("div", "answer-head");
      head.append(el("span", "mode-tag", a.mode === "strict" ? "Strict grounding" : "Standard RAG"));
      card.append(head);
    }
    if (a.not_found) {
      const nf = el("div", "not-found");
      const t = el("div"); t.append(el("strong", null, "I didn't find a stated reason in the excerpts I read."),
        document.createTextNode("Rather than guess, I'm not answering. The reason may still be in the excerpts: "
          + "it's worth checking them yourself."));
      const show = el("button", "inline-btn", "Show the excerpts"); show.type = "button";
      show.addEventListener("click", () => { ctx.srcBox.open = true;
        requestAnimationFrame(() => ctx.srcBox.scrollIntoView({ behavior: "smooth", block: "start" })); });
      t.append(el("br"), show);
      nf.append(el("span", "icon", "∅"), t); card.append(nf);
    } else {
      const p = el("div", "answer-text");
      let last = 0; const text = a.answer; let m; CITE.lastIndex = 0; let cites = 0;
      while ((m = CITE.exec(text))) {
        p.append(document.createTextNode(text.slice(last, m.index)));
        p.append(citeChip(m[1], m[2], srcById, ctx)); cites++;
        last = m.index + m[0].length;
      }
      p.append(document.createTextNode(text.slice(last)));
      const g = a.gate;
      if (g && g.status === "scored" && g.passed === false) {
        // Held back: the answer text is kept as it is, behind "Show anyway".
        const held = el("div", "not-found held");
        const t = el("div");
        t.append(el("strong", null, "The sources don't clearly support this answer"),
          document.createTextNode(g.held_back_reason === "no_citation"
            ? "Experimental support check: the answer cites no excerpt from the context, so it was held back."
            : `Experimental support check: score ${g.score.toFixed(2)}, below the ${g.threshold.toFixed(2)} threshold.`));
        const anyway = el("button", "inline-btn", "Show anyway"); anyway.type = "button";
        const show = el("button", "inline-btn", "Show the excerpts"); show.type = "button";
        const body2 = el("div", "held-answer"); body2.hidden = true;
        body2.append(p);
        if (!cites) body2.append(el("div", "warn-uncited", "No citations: this answer isn't linked to any source excerpt."));
        anyway.addEventListener("click", () => {
          body2.hidden = !body2.hidden; anyway.textContent = body2.hidden ? "Show anyway" : "Hide answer";
        });
        show.addEventListener("click", () => { ctx.srcBox.open = true;
          requestAnimationFrame(() => ctx.srcBox.scrollIntoView({ behavior: "smooth", block: "start" })); });
        t.append(el("br"), anyway, show);
        held.append(el("span", "icon", "?"), t);
        card.append(held, body2);
      } else {
        card.append(p);
        if (!cites) card.append(el("div", "warn-uncited", "No citations: this answer isn't linked to any source excerpt."));
        if (g && g.status === "scored" && g.passed) card.append(el("div", "gate-line",
          `Experimental support check: passed (score ${g.score.toFixed(2)} ≥ ${g.threshold.toFixed(2)}).`));
        if (g && g.status === "error") card.append(el("div", "warn-uncited",
          `Experimental support check failed (${g.error}). The answer is shown unchecked.`));
      }
    }
    if (a.not_found && a.gate) card.append(el("div", "gate-line", "Experimental support check: refusals are not scored."));
    const foot = el("div", "answer-foot");
    let fb;
    try { fb = feedbackRow(body, a, ctx); } catch (e) { fb = null; }   // never break the answer view
    if (fb) foot.append(fb.row);
    foot.append(el("span", "timing", `answered in ${(a.answer_seconds || 0).toFixed(1)} s`
      + (a.gate && a.gate.seconds ? ` · support check ${a.gate.seconds.toFixed(1)} s` : "")));
    card.append(foot);
    if (fb) card.append(fb.panel);
    return card;
  }

  function citeChip(pr, c, srcById, ctx) {
    const id = `PR${pr}-c${c}`; const src = srcById[id.toLowerCase()];
    const b = el("button", "cite" + (src ? "" : " missing")); b.type = "button";
    b.textContent = src ? `${ctx.ref(pr)} · ${TYPE_LABEL[src.type] || "chunk"}` : `${ctx.ref(pr)} · not in context`;
    b.title = src ? `${id}: ${src.title} (opens the whole PR)` : `${id} was cited but is not among the retrieved excerpts`;
    if (src) b.addEventListener("click", () => openViewer(ctx, src.pr, src.id));
    return b;
  }

  // Feedback goes to feedback/feedback.jsonl for human review only (feedback/README.md); the app
  // never learns from it. Each click or report appends one line. A failed save shows a short
  // message here and nothing else: the answer view stays as it is.
  const REPORTS = [["wrong_answer", "Wrong answer"], ["invented_reason", "Invented reason"],
    ["borrowed_from_other_pr", "Borrowed from another PR"], ["what_not_why", "Describes what, not why"]];
  function feedbackRow(body, a, ctx) {
    const row = el("div", "feedback");
    const panel = el("div", "fb-panel"); panel.hidden = true;
    const status = el("span", "fb-status"); status.setAttribute("role", "status");
    let rating = null;
    const thumbs = [["up", "👍", "Helpful"], ["down", "👎", "Not helpful"]].map(([v, label, title]) => {
      const b = el("button", "fb-thumb", label); b.type = "button"; b.title = title; b.dataset.v = v;
      b.setAttribute("aria-label", title); b.setAttribute("aria-pressed", "false");
      b.addEventListener("click", () => {
        rating = v;
        thumbs.forEach((t) => { t.classList.toggle("on", t === b); t.setAttribute("aria-pressed", String(t === b)); });
        if (v === "down") panel.hidden = false;
        send({ rating: v });
      });
      return b;
    });
    const report = el("select", "fb-report"); report.title = "Report a problem with this answer";
    report.append(new Option("Report…", ""));
    REPORTS.forEach(([v, label]) => report.append(new Option(label, v)));
    report.addEventListener("change", () => { panel.hidden = false; });

    const pr = el("input", "fb-pr"); pr.type = "text"; pr.placeholder = "Correct PR (optional), e.g. 12345";
    pr.setAttribute("aria-label", "Correct PR (optional)");
    const comment = el("input", "fb-comment"); comment.type = "text"; comment.placeholder = "Comment (optional)";
    comment.setAttribute("aria-label", "Comment (optional)");
    const sendBtn = el("button", "fb-send", "Send"); sendBtn.type = "button";
    sendBtn.addEventListener("click", async () => {
      if (!report.value && !pr.value.trim() && !comment.value.trim()) {
        setFbStatus(status, "Pick a report type or write something first.", false); return;
      }
      if (await send({ rating, report_type: report.value || null, correct_pr: pr.value, comment: comment.value })) {
        report.value = ""; pr.value = ""; comment.value = ""; panel.hidden = true;
      }
    });
    comment.addEventListener("keydown", (ev) => { if (ev.key === "Enter") { ev.preventDefault(); sendBtn.click(); } });
    panel.append(pr, comment, sendBtn);
    row.append(...thumbs, report, status);

    async function send(fields) {
      try {
        const sources = (ctx && ctx.sources) || [];
        const payload = { question: body.question, answer: a.answer || "", mode: a.mode || "", model: body.model || "",
          settings: { repo: body.repo, pool: body.pool, chunking: body.chunking, retriever: body.retriever,
            links: body.links, modes: body.modes, model: body.model, gate: !!body.gate },
          gate: a.gate || null,
          context_chunk_ids: sources.map((s) => s.chunk_id || s.id),
          cited_ids: [...new Set((a.citations || []).map((c) => c.id))], ...fields };
        setFbStatus(status, "Saving…", null);
        const r = await fetch("/api/feedback", { method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload) });
        if (!r.ok) {
          const d = await r.json().catch(() => ({}));
          throw new Error(typeof d.detail === "string" ? d.detail : `server replied ${r.status}`);
        }
        setFbStatus(status, "Thanks — saved", true);
        return true;
      } catch (e) {
        setFbStatus(status, `Not saved (${e.message || "network error"}). Your answer is unaffected.`, false);
        return false;
      }
    }
    return { row, panel };
  }
  function setFbStatus(node, text, ok) {
    node.textContent = text;
    node.className = "fb-status" + (ok === true ? " ok" : ok === false ? " bad" : "");
  }

  function renderSources(box, sources, ctx) {
    const list = [...sources].sort((x, y) => (ctx.cited.has(y.id.toLowerCase()) - ctx.cited.has(x.id.toLowerCase())));
    list.forEach((s) => {
      const isCited = ctx.cited.has(s.id.toLowerCase());
      const card = el("article", "src" + (isCited ? " cited" : "")); card.dataset.src = s.id.toLowerCase();
      const head = el("div", "src-head");
      head.append(el("span", "src-id", ctx.ref(s.pr)), el("span", "badge", TYPE_LABEL[s.type] || s.type || "chunk"));
      if (isCited) head.append(el("span", "badge cited", "Cited"));
      if (s.linked) head.append(el("span", "badge linked", "Linked"));
      const title = el("span", "src-title", s.title + (s.file ? `  —  ${s.file}` : "")); title.title = title.textContent;
      const view = el("button", "link-like", `View in ${ctx.item}`); view.type = "button";
      view.title = "Open the whole pull request with this excerpt highlighted";
      view.addEventListener("click", () => openViewer(ctx, s.pr, s.id));
      const a = el("a", null, `${ctx.host} ↗`); a.href = s.url; a.target = "_blank"; a.rel = "noopener noreferrer";
      head.append(title, view, a); card.append(head);
      card.append(sourceBody(s, ctx.highlights[s.id.toLowerCase()] || []));
      box.append(card);
    });
  }

  // Render a source: diff colouring per line + highlighted cited passages (by char offsets).
  function sourceBody(s, spans) {
    const text = s.text;
    const isCode = s.type === "hunk" || s.type === "fixed" || /^@@ /m.test(text);
    const pre = el("pre", "src-body" + (isCode ? "" : " prose"));
    const marked = new Uint8Array(text.length);
    spans.forEach(([a, b]) => { for (let i = Math.max(0, a); i < Math.min(text.length, b); i++) marked[i] = 1; });
    let pos = 0;
    text.split("\n").forEach((line) => {
      const start = pos; pos += line.length + 1;
      let cls = "ln";
      if (isCode) {
        if (line.startsWith("@@")) cls += " hunk";
        else if (line.startsWith("+") && !line.startsWith("+++")) cls += " add";
        else if (line.startsWith("-") && !line.startsWith("---")) cls += " del";
      }
      const span = el("span", cls);
      let i = 0;
      while (i < line.length) {
        const m = marked[start + i]; let j = i;
        while (j < line.length && marked[start + j] === m) j++;
        const seg = line.slice(i, j);
        span.append(m ? el("mark", null, seg) : document.createTextNode(seg));
        i = j;
      }
      if (!line.length) span.append(document.createTextNode(" "));
      pre.append(span);
    });
    return pre;
  }

  // ---------- text size (Aa): scales all text in the app, via the --fs CSS variable ----------
  const SIZES = [0.85, 1, 1.15, 1.3, 1.5, 1.75], SKEY = "prExplainerTextSize";
  let sizeIdx = 1;
  try { const v = parseFloat(localStorage.getItem(SKEY)); if (SIZES.includes(v)) sizeIdx = SIZES.indexOf(v); } catch (e) { /* ignore */ }
  function applySize() {
    document.documentElement.style.setProperty("--fs", SIZES[sizeIdx]);
    $("aaVal").textContent = `${Math.round(SIZES[sizeIdx] * 100)}%`;
    $("aaDown").disabled = sizeIdx === 0; $("aaUp").disabled = sizeIdx === SIZES.length - 1;
    try { localStorage.setItem(SKEY, String(SIZES[sizeIdx])); } catch (e) { /* ignore */ }
    autosize();
  }
  const stepSize = (d) => { sizeIdx = Math.max(0, Math.min(SIZES.length - 1, sizeIdx + d)); applySize(); };
  $("aaDown").addEventListener("click", () => stepSize(-1));
  $("aaUp").addEventListener("click", () => stepSize(1));
  $("aaReset").addEventListener("click", () => { sizeIdx = 1; applySize(); });
  function openAa(open) { $("aaPop").hidden = !open; $("aaBtn").setAttribute("aria-expanded", String(open)); }
  $("aaBtn").addEventListener("click", (ev) => { ev.stopPropagation(); openAa($("aaPop").hidden); });
  document.addEventListener("click", (ev) => { if (!$("aaPop").hidden && !ev.target.closest(".aa-wrap")) openAa(false); });
  document.addEventListener("keydown", (ev) => { if (ev.key === "Escape" && !$("aaPop").hidden) { openAa(false); $("aaBtn").focus(); } });
  applySize();

  // ---------- PR viewer: the whole pull request, with the model's excerpts shaded ----------
  // Excerpt offsets come from retrieval (start/end in the PR document). Cited highlights are
  // offsets inside the excerpt text, which ends with document[start:end] (structural chunks
  // add a file header in front), so excerpt offset i maps to (end - text.length + i).
  const prCache = {};
  let viewerReq = 0;
  async function openViewer(ctx, pr, focusId) {
    const req = ++viewerReq;
    $("viewer").hidden = false; $("app").classList.add("viewing");
    // Tabs: cited PRs only. The other PRs the model was given sit behind a toggle and are
    // labelled "not cited", so they don't read as evidence for the answer.
    const prs = [...new Set(ctx.sources.map((s) => s.pr))];
    const isCited = (n) => ctx.sources.some((s) => s.pr === n && ctx.cited.has(s.id.toLowerCase()));
    const citedPrs = prs.filter(isCited), others = prs.filter((n) => !isCited(n));
    if (!citedPrs.length || others.includes(pr)) ctx.showOthers = true;
    const tabs = $("viewerTabs"); tabs.innerHTML = "";
    const tab = (n, cited) => {
      const t = el("button", "viewer-tab" + (n === pr ? " on" : "") + (cited ? " cited" : " uncited"),
        cited ? ctx.ref(n) : `${ctx.ref(n)} · not cited`);
      t.type = "button"; t.setAttribute("role", "tab"); t.setAttribute("aria-selected", String(n === pr));
      t.title = cited ? "The answer cites this PR" : "The model read this PR but didn't cite it";
      t.addEventListener("click", () => openViewer(ctx, n, null));
      tabs.append(t);
    };
    citedPrs.forEach((n) => tab(n, true));
    if (others.length) {
      if (ctx.showOthers) others.forEach((n) => tab(n, false));
      const tog = el("button", "viewer-more", ctx.showOthers && citedPrs.length
        ? "Hide uncited" : `+${others.length} read, not cited`);
      tog.type = "button";
      tog.title = "Other PRs the search gave the model as background. The answer doesn't cite them.";
      if (citedPrs.length) tog.addEventListener("click", () => {
        ctx.showOthers = !ctx.showOthers;
        openViewer(ctx, ctx.showOthers || !others.includes(pr) ? pr : citedPrs[0], null);
      });
      else tog.disabled = true;
      if (citedPrs.length || !ctx.showOthers) tabs.append(tog);
    }
    const prCited = isCited(pr);
    $("citedLegend").hidden = !prCited;
    $("viewerNote").hidden = prCited;
    $("viewerNote").textContent = citedPrs.length
      ? "Not cited: the search gave this PR to the model as background, but the answer doesn't use it."
      : "Not cited: the answer didn't cite any PR. These are the PRs the model read.";
    $("viewerNum").textContent = ctx.ref(pr); $("viewerTitle").textContent = "";
    $("viewerLink").href = ctx.sources.find((s) => s.pr === pr).url;
    $("viewerLink").textContent = `${ctx.host} ↗`;
    const body = $("viewerBody"); body.innerHTML = ""; body.append(el("p", "muted", "Loading the pull request…"));
    const key = `${ctx.repo}:${ctx.pool}:${pr}`;
    try {
      if (!prCache[key]) {
        const r = await fetch(`/api/pr/${pr}?repo=${encodeURIComponent(ctx.repo)}&pool=${encodeURIComponent(ctx.pool)}`);
        const d = await r.json();
        if (!r.ok) throw new Error(d.detail || "Couldn't load the pull request");
        prCache[key] = d;
      }
    } catch (e) { body.innerHTML = ""; body.append(el("p", "warn-uncited", e.message)); return; }
    if (req !== viewerReq) return;                       // another PR was opened (or closed) meanwhile
    const doc = prCache[key];
    $("viewerTitle").textContent = doc.title; $("viewerLink").href = doc.url;
    renderPR(body, doc, ctx.sources.filter((s) => s.pr === pr), ctx, focusId);
  }
  // Panel width: drag its left edge (or arrow keys on the handle). Kept between 320 px, so the
  // PR text stays readable, and a width that leaves the chat at least 380 px. Remembered.
  const VMIN = 320, CHAT_MIN = 380, WKEY = "prExplainerViewerWidth";
  let viewerW = null;
  try { viewerW = parseInt(localStorage.getItem(WKEY), 10) || null; } catch (e) { /* ignore */ }
  function vmax() {
    const side = $("app").classList.contains("collapsed") ? 0 : $("sidebar").getBoundingClientRect().width;
    return Math.max(VMIN, innerWidth - side - CHAT_MIN - 20);
  }
  function setViewerWidth(w, save) {
    viewerW = w == null ? null : Math.round(Math.min(vmax(), Math.max(VMIN, w)));
    if (viewerW == null) document.documentElement.style.removeProperty("--viewer-w");
    else document.documentElement.style.setProperty("--viewer-w", viewerW + "px");
    $("viewerResize").setAttribute("aria-valuenow", String(viewerW || ""));
    if (save) try { viewerW == null ? localStorage.removeItem(WKEY) : localStorage.setItem(WKEY, String(viewerW)); }
      catch (e) { /* ignore */ }
  }
  if (viewerW) setViewerWidth(viewerW, false);
  addEventListener("resize", () => { if (viewerW) setViewerWidth(viewerW, false); });   // keep within the window
  $("viewerResize").addEventListener("pointerdown", (ev) => {
    ev.preventDefault();
    const handle = $("viewerResize"); handle.setPointerCapture(ev.pointerId);
    const right = $("viewer").getBoundingClientRect().right;
    $("app").classList.add("resizing");
    const move = (e) => setViewerWidth(right - e.clientX, false);
    const up = () => {
      handle.removeEventListener("pointermove", move); handle.removeEventListener("pointerup", up);
      handle.removeEventListener("pointercancel", up);
      $("app").classList.remove("resizing"); setViewerWidth(viewerW, true);
    };
    handle.addEventListener("pointermove", move); handle.addEventListener("pointerup", up);
    handle.addEventListener("pointercancel", up);
  });
  $("viewerResize").addEventListener("dblclick", () => setViewerWidth(null, true));
  $("viewerResize").addEventListener("keydown", (ev) => {
    const step = ev.shiftKey ? 80 : 24;
    const cur = viewerW || $("viewer").getBoundingClientRect().width;
    if (ev.key === "ArrowLeft") { setViewerWidth(cur + step, true); ev.preventDefault(); }
    else if (ev.key === "ArrowRight") { setViewerWidth(cur - step, true); ev.preventDefault(); }
  });

  function closeViewer() { $("viewer").hidden = true; $("app").classList.remove("viewing"); viewerReq++; }
  $("closeViewer").addEventListener("click", closeViewer);
  document.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape" && $("drawer").hidden && !$("viewer").hidden) closeViewer();
  });

  function renderPR(box, doc, excerpts, ctx, focusId) {
    const text = doc.text;
    const level = new Uint8Array(text.length);           // 1 = given to the model, 2 = cited
    let focusAt = null, hasOffsets = false;
    excerpts.forEach((s) => {
      if (s.start == null) return;
      hasOffsets = true;
      for (let i = s.start; i < Math.min(s.end, text.length); i++) level[i] = Math.max(level[i], 1);
      const base = s.end - s.text.length;
      (ctx.highlights[s.id.toLowerCase()] || []).forEach(([a, b]) => {
        for (let i = Math.max(s.start, base + a); i < Math.min(s.end, base + b, text.length); i++) level[i] = 2;
      });
      if (s.id === focusId) focusAt = s.start;
    });
    if (focusAt == null && hasOffsets) {                // tab click: first cited, else first excerpt
      const first = excerpts.find((s) => ctx.cited.has(s.id.toLowerCase())) || excerpts[0];
      if (first && first.start != null) focusAt = first.start;
    }
    const hunks = doc.parts.filter((p) => p.type === "hunk");
    const inHunk = (pos) => hunks.some((p) => pos >= p.start && pos < p.end);
    const SECTION = /^(Title:|Description:|Commit messages:|File: |Review thread on |Comment by @)/;

    box.innerHTML = "";
    if (!hasOffsets) box.append(el("p", "muted note",
      "This chat was saved before the viewer existed, so its excerpts can't be shaded. Ask again to see them."));
    const pre = el("pre", "pr-doc");
    let pos = 0, focusEl = null;
    text.split("\n").forEach((line) => {
      const start = pos; pos += line.length + 1;
      let cls = "ln";
      if (SECTION.test(line)) cls += " sec";
      else if (inHunk(start)) {
        if (line.startsWith("@@")) cls += " hunk";
        else if (line.startsWith("+")) cls += " add";
        else if (line.startsWith("-")) cls += " del";
      }
      const span = el("span", cls);
      let i = 0;
      while (i < line.length) {
        const lv = level[start + i]; let j = i;
        while (j < line.length && level[start + j] === lv) j++;
        const seg = line.slice(i, j);
        span.append(lv === 2 ? el("mark", null, seg) : lv === 1 ? el("span", "ex", seg) : document.createTextNode(seg));
        i = j;
      }
      if (!line.length) span.append(document.createTextNode(" "));
      if (focusAt != null && !focusEl && pos > focusAt) focusEl = span;
      pre.append(span);
    });
    box.append(pre);
    box.scrollTop = 0;
    if (focusEl) requestAnimationFrame(() => {
      focusEl.scrollIntoView({ block: "center" });
      focusEl.classList.add("flash"); setTimeout(() => focusEl.classList.remove("flash"), 1600);
    });
  }

  // ---------- quoting: select text in an answer, a source or a PR, then "Quote" ----------
  const QUOTE_MAX = 1500;
  function setQuote(text) {
    state.quote = text; $("quoteText").textContent = text; $("quoteRow").hidden = !text;
  }
  function quotableSelection() {
    const sel = getSelection();
    if (!sel.rangeCount || sel.isCollapsed) return null;
    const node = sel.getRangeAt(0).commonAncestorContainer;
    const host = (node.nodeType === 1 ? node : node.parentElement);
    if (!host.closest(".msg.bot, #viewerBody, .q-quote") || !sel.toString().trim()) return null;
    return sel;
  }
  function placeQuoteBtn() {
    const sel = quotableSelection(), btn = $("quoteBtn");
    if (!sel) { btn.hidden = true; return; }
    const r = sel.getRangeAt(0).getBoundingClientRect();
    btn.hidden = false;
    btn.style.left = `${Math.max(8, Math.min(innerWidth - btn.offsetWidth - 8, r.left + r.width / 2 - btn.offsetWidth / 2))}px`;
    btn.style.top = `${r.top > btn.offsetHeight + 12 ? r.top - btn.offsetHeight - 6 : r.bottom + 6}px`;
  }
  document.addEventListener("selectionchange", placeQuoteBtn);
  $("chat").addEventListener("scroll", placeQuoteBtn);
  $("viewerBody").addEventListener("scroll", placeQuoteBtn);
  $("quoteBtn").addEventListener("mousedown", (ev) => ev.preventDefault());   // keeps the selection
  $("quoteBtn").addEventListener("click", () => {
    const sel = quotableSelection();
    if (!sel) return;
    setQuote(sel.toString().trim().slice(0, QUOTE_MAX));
    sel.removeAllRanges(); $("quoteBtn").hidden = true; $("question").focus();
  });
  $("quoteClear").addEventListener("click", () => { setQuote(""); $("question").focus(); });

  // ---------- start ----------
  newConversation();                                  // syncRepo reads the status and warms up
})();
