// A1.1 regression guard: the production image must serve apps/web/public.
// Next's standalone output does not include public/, so the runtime stage of
// apps/web/Dockerfile must copy it explicitly. Run with: npm run check:public-asset
import { strict as assert } from "node:assert";
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const webDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

const loaderPath = path.join(webDir, "public", "widget", "v1", "loader.js");
assert.ok(
  existsSync(loaderPath),
  `missing repo file: apps/web/public/widget/v1/loader.js (expected at ${loaderPath})`,
);

const dockerfile = readFileSync(path.join(webDir, "Dockerfile"), "utf8");
assert.ok(
  dockerfile.includes(
    "COPY --from=builder --chown=node:node /workspace/apps/web/public ./apps/web/public",
  ),
  "apps/web/Dockerfile runtime stage does not copy apps/web/public",
);

console.log("check:public-asset OK");
