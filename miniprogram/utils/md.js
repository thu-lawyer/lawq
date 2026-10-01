// 律问 · 极简 Markdown → rich-text nodes（支持段落/加粗/列表/标题行）
const CITE_RE = /《([^《》]{2,40})》第([一二三四五六七八九十百千零〇0-9]+)条/g;

function inlineNodes(text) {
  // 按 **加粗** 与《…》第…条 引用拆分成节点
  const nodes = [];
  let rest = text;
  const re = /\*\*([^*]+)\*\*|《([^《》]{2,40})》第([一二三四五六七八九十百千零〇0-9]+)条/g;
  let m;
  while ((m = re.exec(rest))) {
    if (m.index > 0) nodes.push({ type: "text", text: rest.slice(0, m.index) });
    if (m[1] !== undefined) {
      nodes.push({ name: "strong", children: [{ type: "text", text: m[1] }] });
    } else {
      nodes.push({
        name: "cite", attrs: { "data-law": m[2], "data-no": m[3] },
        children: [{ type: "text", text: `《${m[2]}》第${m[3]}条` }],
      });
    }
    rest = rest.slice(m.index + m[0].length);
  }
  if (rest) nodes.push({ type: "text", text: rest });
  return nodes;
}

function mdToNodes(md) {
  const out = [];
  for (const block of md.split(/\n{2,}/)) {
    const b = block.trim();
    if (!b) continue;
    const lines = b.split("\n");
    if (lines.every((l) => /^\s*([-*]|\d+[.、)])\s+/.test(l))) {
      out.push({
        name: "ul",
        children: lines.map((l) => ({
          name: "li",
          children: inlineNodes(l.replace(/^\s*([-*]|\d+[.、)])\s+/, "")),
        })),
      });
    } else {
      out.push({ name: "p", children: inlineNodes(b) });
    }
  }
  return out;
}

// 提取回答里的法条引用（去重），供点击定位
function extractCites(md) {
  const seen = new Set();
  const cites = [];
  let m;
  CITE_RE.lastIndex = 0;
  while ((m = CITE_RE.exec(md))) {
    const key = m[1] + "|" + m[2];
    if (!seen.has(key)) { seen.add(key); cites.push({ law: m[1], no: m[2], label: `《${m[1]}》第${m[2]}条` }); }
  }
  return cites;
}

module.exports = { mdToNodes, extractCites };
