import { execFileSync } from "node:child_process";

function requireCompiler(name) {
  const command = process.env[name];
  if (!command) {
    throw new Error(
      `${name} is not set; native addon builds need an explicit compiler.\n` +
        "xcode-select: error: command line tools are required, use xcode-select --install"
    );
  }
  return command;
}

const cc = requireCompiler("CC");
const cxx = requireCompiler("CXX");

execFileSync(cc, ["--version"], { stdio: "ignore" });
execFileSync(cxx, ["--version"], { stdio: "ignore" });
console.log("compiler probe passed");
