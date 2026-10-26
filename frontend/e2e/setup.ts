import { execFileSync } from "node:child_process";
import { resolve } from "node:path";
import { writeFileSync } from "node:fs";
export default function setup() {
 const root=resolve(import.meta.dirname,"../..");
 const fixture=execFileSync(resolve(root,".venv/bin/python"),["-m","atlasops.cli","seed-scenario"],{cwd:root,encoding:"utf8"});
 writeFileSync(resolve(root,".local/e2e-fixture.json"),fixture,{mode:0o600});
}
