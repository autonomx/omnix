// Keep launcher and root npm commands on the repository's supported Node runtime.
import { spawn, spawnSync } from 'node:child_process';
import { existsSync, readFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const version = readFileSync(join(root, '.node-version'), 'utf8').trim();
if (!/^22\.\d+\.\d+$/.test(version)) throw new Error('Invalid pinned Node version');
const portable = join(root, '.tools', `node-v${version}-win-x64`, 'node.exe');
const node = process.env.OMNIX_NODE_EXECUTABLE || (process.platform === 'win32' && existsSync(portable) ? portable : process.execPath);
const probe = spawnSync(node, ['--version'], { encoding: 'utf8', windowsHide: true });
const match = /^v(\d+)\.(\d+)\./.exec(probe.stdout?.trim() || '');
if (!match || !(Number(match[1]) > 22 || (Number(match[1]) === 22 && Number(match[2]) >= 12))) {
  throw new Error('Omnix requires Node 22.12 or newer. Run python scripts/install_node_toolchain.py or use .node-version with your version manager.');
}
const args = process.argv.slice(2);
const adjacentNpm = join(dirname(node), 'node_modules', 'npm', 'bin', 'npm-cli.js');
const npm = existsSync(adjacentNpm) ? adjacentNpm : process.env.npm_execpath;
if (args[0] !== '--version' && (!npm || !existsSync(npm))) {
  throw new Error('Node toolchain has no npm CLI. Run python scripts/install_node_toolchain.py or configure OMNIX_NODE_EXECUTABLE.');
}
const command = args[0] === '--version' ? ['--version'] : [npm, '--prefix', join(root, 'src', 'apps', 'web'), 'run', ...args];
const child = spawn(node, command, {
  cwd: root, stdio: 'inherit', windowsHide: true,
  env: { ...process.env, PATH: `${dirname(node)}${process.platform === 'win32' ? ';' : ':'}${process.env.PATH || ''}` },
});
child.on('error', (error) => { console.error(error.message); process.exitCode = 1; });
child.on('exit', (code) => { process.exitCode = code ?? 1; });
