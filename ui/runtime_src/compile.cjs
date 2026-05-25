/* Compile JSX -> JS using the bundled @babel/standalone (no network).
   Usage: node compile.cjs <babel.js> '[["in.jsx","out.js"],...]' */
const fs = require("fs");
const path = require("path");
const Babel = require(path.resolve(process.argv[2]));
const pairs = JSON.parse(process.argv[3]);
for (const [inp, out] of pairs) {
  const src = fs.readFileSync(inp, "utf8");
  const { code } = Babel.transform(src, {
    presets: [["react", { runtime: "classic" }]],
    compact: false,
  });
  fs.writeFileSync(out, code);
  console.log("  compiled", path.basename(inp), "->", code.length, "B");
}
