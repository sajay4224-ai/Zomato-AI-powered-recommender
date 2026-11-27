import { cp, mkdir, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const projectRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const distDirectory = path.join(projectRoot, "dist");
const apiBaseUrl = (process.env.API_BASE_URL || "").trim().replace(/\/+$/, "");

await rm(distDirectory, { recursive: true, force: true });
await mkdir(path.join(distDirectory, "static"), { recursive: true });
await cp(
  path.join(projectRoot, "templates", "index.html"),
  path.join(distDirectory, "index.html"),
);
await cp(
  path.join(projectRoot, "static"),
  path.join(distDirectory, "static"),
  { recursive: true },
);
await writeFile(
  path.join(distDirectory, "static", "config.js"),
  `window.API_BASE_URL = ${JSON.stringify(apiBaseUrl)};\n`,
  "utf8",
);
