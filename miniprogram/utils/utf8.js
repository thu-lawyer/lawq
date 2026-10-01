// 增量 UTF-8 解码：SSE 分包可能把多字节汉字切成两半，需缓存不完整字节
function createUtf8Decoder() {
  let leftover = [];

  function flush(bytes) {
    let s = "";
    let i = 0;
    while (i < bytes.length) {
      const b = bytes[i];
      let cp, len;
      if (b < 0x80) { cp = b; len = 1; }
      else if ((b & 0xe0) === 0xc0) { cp = b & 0x1f; len = 2; }
      else if ((b & 0xf0) === 0xe0) { cp = b & 0x0f; len = 3; }
      else { cp = b & 0x07; len = 4; }
      if (i + len > bytes.length) return { text: s, rest: bytes.slice(i) };
      for (let k = 1; k < len; k++) cp = (cp << 6) | (bytes[i + k] & 0x3f);
      s += String.fromCodePoint(cp);
      i += len;
    }
    return { text: s, rest: [] };
  }

  return function decode(arrayBuffer) {
    const incoming = new Uint8Array(arrayBuffer);
    const all = leftover.concat(Array.from(incoming));
    const { text, rest } = flush(all);
    leftover = rest;
    return text;
  };
}

module.exports = { createUtf8Decoder };
