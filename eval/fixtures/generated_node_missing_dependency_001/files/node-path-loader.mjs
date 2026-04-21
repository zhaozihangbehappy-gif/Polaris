import { access } from "node:fs/promises";
import { delimiter } from "node:path";
import { pathToFileURL } from "node:url";

export async function resolve(specifier, context, defaultResolve) {
  const isBare = !specifier.startsWith(".") && !specifier.startsWith("/") && !specifier.includes(":");

  if (isBare && process.env.NODE_PATH) {
    for (const root of process.env.NODE_PATH.split(delimiter).filter(Boolean)) {
      const candidate = new URL(`${specifier}/index.mjs`, pathToFileURL(`${root}/`));

      try {
        await access(candidate);
        return { shortCircuit: true, url: candidate.href };
      } catch {
        // Try the next NODE_PATH entry, then fall back to Node's resolver.
      }
    }
  }

  return defaultResolve(specifier, context, defaultResolve);
}
