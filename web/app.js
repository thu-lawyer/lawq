/* 律问 · 前端逻辑 */
"use strict";

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const store = {
  get token() { return localStorage.getItem("lawq_token") || ""; },
  set token(v) { v ? localStorage.setItem("lawq_token", v) : localStorage.removeItem("lawq_token"); },
  get theme() { return localStorage.getItem("lawq_theme") || "light"; },
  set theme(v) { localStorage.setItem("lawq_theme", v); },
};

let PROTECTED = false;

/* ---------- 基础工具 ---------- */
function toast(msg, ms = 2600) {
  const t = $("#toast");
  t.textContent = msg;
  t.hidden = false;
  clearTimeout(t._h);
  t._h = setTimeout(() => (t.hidden = true), ms);
}

function esc(s) {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function cn2num(str) {
  if (/^\d+$/.test(str)) return parseInt(str, 10);
  const D = { 零: 0, 〇: 0, 一: 1, 二: 2, 两: 2, 三: 3, 四: 4, 五: 5, 六: 6, 七: 7, 八: 8, 九: 9 };
  const U = { 十: 10, 百: 100, 千: 1000, 万: 10000 };
  let total = 0, num = 0;
  for (const ch of str) {
    if (ch in D) num = D[ch];
    else if (ch in U) {
      if (!num) num = 1;
      if (U[ch] === 10000) { total = (total + num) * 10000; }
      else total += num * U[ch];
      num = 0;
    } else return null;
  }
  return total + num;
}

const shortLaw = (n) => n.replace(/^中华人民共和国/, "");

/* ---------- API ---------- */
async function api(path, opts = {}) {
  const headers = Object.assign({ "X-Token": store.token }, opts.headers || {});
  if (opts.json !== undefined) {
    headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(opts.json);
  }
  const resp = await fetch(path, Object.assign({}, opts, { headers }));
  if (resp.status === 401) { openLogin("口令已过期，请重新输入"); throw new Error("unauthorized"); }
  if (!resp.ok) {
    let msg = `请求失败(${resp.status})`;
    try { msg = (await resp.json()).detail || msg; } catch {}
    throw new Error(msg);
  }
  return resp;
}

/* ---------- 主题 ---------- */
function applyTheme() {
  document.body.classList.toggle("dark", store.theme === "dark");
  $("#themeBtn").textContent = store.theme === "dark" ? "☀️" : "🌙";
}
$("#themeBtn").onclick = () => { store.theme = store.theme === "dark" ? "light" : "dark"; applyTheme(); };

/* ---------- Tab 切换 ---------- */
$$(".tab-btn").forEach((btn) => {
  btn.onclick = () => {
    $$(".tab-btn").forEach((b) => b.classList.toggle("active", b === btn));
    $$(".tab").forEach((t) => t.classList.toggle("active", t.id === `tab-${btn.dataset.tab}`));
    if (btn.dataset.tab === "laws") initLaws();
  };
});

/* ---------- 登录 ---------- */
function openLogin(note) {
  $("#loginModal").hidden = false;
  $("#pwdErr").hidden = true;
  if (note) $(".modal .muted").textContent = note;
  setTimeout(() => $("#pwdInput").focus(), 60);
}
$("#loginBtn").onclick = () => openLogin("输入站点口令后开始使用，7 天内免登录。");
$("#pwdGo").onclick = async () => {
  try {
    const r = await fetch("/api/login", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password: $("#pwdInput").value }),
    });
    if (!r.ok) { $("#pwdErr").hidden = false; return; }
    store.token = (await r.json()).token;
    $("#loginModal").hidden = true;
    $("#pwdInput").value = "";
    toast("已登录 ✓");
  } catch { $("#pwdErr").hidden = false; }
};
$("#pwdInput").addEventListener("keydown", (e) => e.key === "Enter" && $("#pwdGo").click());

/* ---------- Markdown 极简渲染 + 引用角标 ---------- */
function inlineMd(s) {
  s = esc(s);
  s = s.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  s = s.replace(/《([^《》]{2,40})》第([一二三四五六七八九十百千零〇0-9]+)条/g,
    (m, law, no) => `<a class="cite" data-law="${law}" data-no="${no}">《${law}》第${no}条</a>`);
  return s.replace(/\n/g, "<br>");
}
function mdLite(src) {
  let html = "";
  for (const block of src.split(/\n{2,}/)) {
    const b = block.trim();
    if (!b) continue;
    const lines = b.split("\n");
    if (lines.every((l) => /^\s*([-*]|\d+[.、)])\s+/.test(l))) {
      html += "<ul>" + lines.map((l) => `<li>${inlineMd(l.replace(/^\s*([-*]|\d+[.、)])\s+/, ""))}</li>`).join("") + "</ul>";
    } else if (/^#{1,4}\s/.test(b)) {
      html += `<p class="h">${inlineMd(b.replace(/^#{1,4}\s/, ""))}</p>`;
    } else {
      html += `<p>${inlineMd(b)}</p>`;
    }
  }
  return html || "<p></p>";
}

/* ---------- 问答 ---------- */
const chat = $("#chat");
let asking = false;

function addUserMsg(text) {
  const div = document.createElement("div");
  div.className = "msg user";
  div.innerHTML = `<div class="who">你</div><div class="bubble"></div>`;
  $(".bubble", div).textContent = text;
  chat.appendChild(div);
  chat.scrollTop = chat.scrollHeight;
}

function addAssistantMsg() {
  const div = document.createElement("div");
  div.className = "msg assistant";
  div.innerHTML = `<div class="who">律问</div><div class="bubble cursor"><p>正在检索法条…</p></div>`;
  chat.appendChild(div);
  chat.scrollTop = chat.scrollHeight;
  return div;
}

function markKeywords(text, question) {
  if (!text) return esc(text);
  const tokens = [...new Set(question.match(/[\u4e00-\u9fffA-Za-z]{2,6}/g) || [])].filter((t) => t.length >= 2);
  let out = esc(text);
  for (const t of tokens.slice(0, 8)) {
    out = out.split(t).join(`<mark>${t}</mark>`);
  }
  return out;
}

function renderHits(hits, question) {
  const box = $("#hits");
  box.innerHTML = "";
  if (!hits.length) {
    box.innerHTML = `<p class="hits-empty">未检索到相关法条，回答将基于一般性建议。</p>`;
    return;
  }
  const maxScore = Math.max(...hits.map((h) => h.score || 0), 0.001);
  hits.forEach((h, i) => {
    const card = document.createElement("div");
    card.className = "hit-card";
    card.dataset.i = i;
    const pct = Math.round(((h.score || 0) / maxScore) * 100);
    card.innerHTML = `
      <div class="hit-title">[${i + 1}] ${shortLaw(h.law_name)} · ${h.article_no}</div>
      <div class="hit-badges">
        <span class="badge">${h.law_department || ""}</span>
        <span class="badge">${h.level || ""}</span>
        <span class="badge ghost">${h.status || ""}</span>
        <span class="badge ${h.via === "直查" ? "gold" : "ghost"}">${h.via === "直查" ? "精确命中" : "相关检索"}</span>
      </div>
      <div class="score-bar" title="相关度 ${pct}%"><i style="width:${pct}%"></i></div>
      <div class="hit-text clamp">${markKeywords(h.article_text, question)}</div>`;
    $(".hit-text", card).onclick = () => $(".hit-text", card).classList.toggle("clamp") || $(".hit-text", card).classList.toggle("expanded");
    box.appendChild(card);
  });
  if (window.innerWidth <= 960) { $("#hitsToggle").hidden = false; }
}

function locateCite(law, no) {
  const target = cn2num(no);
  const cards = $$("#hits .hit-card");
  let best = null;
  for (const c of cards) {
    const h = currentHits[+c.dataset.i];
    if (!h) continue;
    if (shortLaw(h.law_name).includes(shortLaw(law)) && cn2num(h.article_no.replace(/[^\u4e00-\u9fff0-9]/g, "")) === target) best = c;
  }
  if (!best) { toast("该引用不在本次检索结果中"); return; }
  if (window.innerWidth <= 960) $("#hitsPanel").classList.add("open");
  best.scrollIntoView({ behavior: "smooth", block: "center" });
  best.classList.add("flash");
  setTimeout(() => best.classList.remove("flash"), 1600);
}

chat.addEventListener("click", (e) => {
  const cite = e.target.closest(".cite");
  if (cite) locateCite(cite.dataset.law, cite.dataset.no);
});

let currentHits = [];

async function ask(question) {
  if (asking || !question.trim()) return;
  asking = true;
  $("#send").disabled = true;
  $(".welcome")?.remove();
  addUserMsg(question);
  const bubble = $(".bubble", addAssistantMsg());

  try {
    const resp = await api("/api/ask", { method: "POST", json: { question } });
    const reader = resp.body.getReader();
    const dec = new TextDecoder();
    let buf = "", acc = "", rendered = "";
    const flushMd = () => { bubble.innerHTML = mdLite(acc); chat.scrollTop = chat.scrollHeight; };
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      let idx;
      while ((idx = buf.indexOf("\n\n")) >= 0) {
        const line = buf.slice(0, idx).trim();
        buf = buf.slice(idx + 2);
        if (!line.startsWith("data:")) continue;
        let ev;
        try { ev = JSON.parse(line.slice(5)); } catch { continue; }
        if (ev.type === "hits") {
          currentHits = ev.hits;
          renderHits(ev.hits, question);
          bubble.innerHTML = "<p>已检索到法条，正在组织回答…</p>";
        } else if (ev.type === "delta") {
          acc += ev.text;
          // 每 12 个增量块重渲染一次，平衡流畅与性能
          if (++rendered % 12 === 0) flushMd();
        } else if (ev.type === "done") {
          flushMd();
        } else if (ev.type === "error") {
          acc += `\n\n（出错：${ev.message}）`;
          flushMd();
        }
      }
    }
    flushMd();
  } catch (e) {
    if (e.message !== "unauthorized") bubble.innerHTML = `<p>（${esc(e.message)}）</p>`;
  } finally {
    asking = false;
    $("#send").disabled = false;
  }
}

$("#send").onclick = () => { const v = $("#q").value.trim(); if (v) { $("#q").value = ""; ask(v); } };
$("#q").addEventListener("keydown", (e) => {
  if ((e.metaKey || e.ctrlKey) && e.key === "Enter") { const v = $("#q").value.trim(); if (v) { $("#q").value = ""; ask(v); } }
});

/* 移动端法条面板 */
$("#hitsToggle").onclick = () => $("#hitsPanel").classList.add("open");
$("#hitsClose").onclick = () => $("#hitsPanel").classList.remove("open");

/* ---------- 法条库 ---------- */
let lawsInited = false;
let curDept = "";

async function initLaws() {
  if (lawsInited) return;
  lawsInited = true;
  try {
    const stats = await (await api("/api/stats")).json();
    $("#corpusBadge").hidden = false;
    $("#corpusBadge").textContent = `收录 ${stats.laws} 部法律 · ${stats.articles} 条`;
    const box = $("#deptList");
    box.innerHTML = `<button class="dept-item active" data-d="">全部部门法<span class="cnt">${stats.articles} 条</span></button>` +
      stats.departments.map((d) =>
        `<button class="dept-item" data-d="${d.name}">${d.name}<span class="cnt">${d.articles} 条</span></button>`).join("");
    $$(".dept-item", box).forEach((b) => {
      b.onclick = () => {
        curDept = b.dataset.d;
        $$(".dept-item", box).forEach((x) => x.classList.toggle("active", x === b));
        $("#lawSearch").value = "";
        loadLaws();
      };
    });
    await loadLaws();
  } catch (e) { if (e.message !== "unauthorized") toast(e.message); }
}

function lawCard(l) {
  const div = document.createElement("div");
  div.className = "law-card";
  div.innerHTML = `<h4>${esc(l.law_name)}</h4>
    <div class="hit-badges">
      <span class="badge">${l.law_department || ""}</span>
      <span class="badge ghost">${l.doc_type || ""}</span>
      <span class="badge ghost">${l.status || ""}</span>
      <span class="badge gold">现行 ${l.arts} 条</span>
    </div>
    <div class="meta">${esc(l.issuing_body || "")} · 版本 ${esc(l.version_date || "")}</div>`;
  div.onclick = () => openLaw(l);
  return div;
}

async function loadLaws(q = "") {
  const box = $("#lawList");
  box.innerHTML = `<p class="laws-pager">加载中…</p>`;
  $("#articleList").hidden = true;
  box.hidden = false;
  $("#lawListHead").textContent = curDept ? `「${curDept}」` : "全部部门法";
  try {
    const data = await (await api(`/api/laws?department=${encodeURIComponent(curDept)}&q=${encodeURIComponent(q)}`)).json();
    box.innerHTML = "";
    if (!data.laws.length) { box.innerHTML = `<p class="laws-pager">没有匹配的法律</p>`; return; }
    for (const l of data.laws) box.appendChild(lawCard(l));
    $("#lawListHead").innerHTML += `<span>${data.laws.length} 部</span>`;
  } catch (e) { if (e.message !== "unauthorized") box.innerHTML = `<p class="laws-pager">${esc(e.message)}</p>`; }
}

async function openLaw(l) {
  const box = $("#lawList"), art = $("#articleCards");
  $("#lawListHead").innerHTML = `<span>《${esc(l.law_name)}》</span><span class="badge">${esc(l.status || "")}</span>`;
  box.hidden = true;
  art.innerHTML = `<p class="laws-pager">加载中…</p>`;
  $("#articleList").hidden = false;
  try {
    const data = await (await api(`/api/laws/${l.law_id}`)).json();
    art.innerHTML = "";
    for (const a of data.articles) {
      const div = document.createElement("div");
      div.className = "article-card";
      div.innerHTML = `<div class="no">${esc(a.article_no || "")}
          ${a.status !== "现行有效" ? `<span class="badge ghost">${esc(a.status)}</span>` : ""}
          ${a.chapter ? `<span class="badge ghost">${esc(a.chapter)}</span>` : ""}</div>
        <div class="txt">${esc(a.article_text || "")}</div>`;
      art.appendChild(div);
    }
  } catch (e) { art.innerHTML = `<p class="laws-pager">${esc(e.message)}</p>`; }
}

$("#backToLaws").onclick = () => {
  $("#articleList").hidden = true;
  $("#lawList").hidden = false;
};

let searchTimer;
$("#lawSearch").addEventListener("input", () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(async () => {
    const q = $("#lawSearch").value.trim();
    if (!q) { loadLaws(); return; }
    const box = $("#lawList");
    $("#articleList").hidden = true;
    box.hidden = false;
    $("#lawListHead").textContent = `搜索「${q}」`;
    box.innerHTML = `<p class="laws-pager">搜索中…</p>`;
    try {
      const data = await (await api(`/api/search?q=${encodeURIComponent(q)}`)).json();
      box.innerHTML = "";
      if (!data.articles.length) { box.innerHTML = `<p class="laws-pager">没有匹配的条文</p>`; return; }
      for (const a of data.articles) {
        const div = document.createElement("div");
        div.className = "article-card";
        const re = new RegExp(q.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "g");
        div.innerHTML = `<div class="no">${esc(shortLaw(a.law_name))} · ${esc(a.article_no || "")}
            ${a.status !== "现行有效" ? `<span class="badge ghost">${esc(a.status)}</span>` : ""}</div>
          <div class="txt">${esc(a.article_text || "").replace(re, (m) => `<mark>${m}</mark>`)}</div>`;
        box.appendChild(div);
      }
      $("#lawListHead").innerHTML += `<span>前 ${data.articles.length} 条</span>`;
    } catch (e) { box.innerHTML = `<p class="laws-pager">${esc(e.message)}</p>`; }
  }, 350);
});

/* ---------- 初始化 ---------- */
(async function init() {
  applyTheme();
  // 深链接：/?q=问题 自动提问；/?tab=laws 直达法条库
  const params = new URLSearchParams(location.search);
  if (params.get("tab") === "laws") { $('.tab-btn[data-tab="laws"]').click(); }
  try {
    const h = await (await fetch("/api/health")).json();
    PROTECTED = h.protected;
    $("#loginBtn").hidden = !PROTECTED;
    if (PROTECTED) {
      const ok = await fetch("/api/stats", { headers: { "X-Token": store.token } });
      if (ok.status === 401) openLogin("输入站点口令后开始使用，7 天内免登录。");
    }
  } catch {}
  try {
    const s = await (await fetch("/api/suggest")).json();
    const box = $("#suggests");
    for (const q of s.questions) {
      const b = document.createElement("button");
      b.textContent = q;
      b.onclick = () => ask(q);
      box.appendChild(b);
    }
  } catch {}
  const q = params.get("q");
  if (q) { $("#q").value = q; ask(q); }
})();
