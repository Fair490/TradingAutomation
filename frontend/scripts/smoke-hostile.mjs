/**
 * Runs the headless render check against the hostile stub API: an overlay
 * index that returned nothing, failed series, all-null series, a zero-decline
 * session. These are the shapes real Yahoo data produces and synthetic demo
 * data never does - they are what blanked the page once.
 */
import { spawn } from "node:child_process";
import { setTimeout as sleep } from "node:timers/promises";

const stub = spawn(process.execPath, ["scripts/stub-api.mjs"], { stdio: "ignore" });
try {
  await sleep(800);
  const smoke = spawn(process.execPath, ["scripts/smoke.mjs"], {
    stdio: "inherit",
    env: { ...process.env, API_BASE: "http://127.0.0.1:8099" },
  });
  const code = await new Promise((resolve) => smoke.on("exit", resolve));
  process.exitCode = code ?? 1;
} finally {
  stub.kill();
}
