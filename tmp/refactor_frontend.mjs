import fs from 'node:fs';
import path from 'node:path';

const root = process.cwd();
const source = path.join(root, 'app/static/index_tusas_faz31.html');
const html = fs.readFileSync(source, 'utf8');
const scripts = [...html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g)];
if (scripts.length !== 3 || !html.includes('tusas-phase31-focus-ai')) {
  throw new Error('Expected the original three inline script blocks; refusing repeat migration.');
}
const backup = path.join(root, 'backups/20260904-brand');
if (fs.existsSync(path.join(backup, 'index_tusas_faz31.html'))) throw new Error('Backup exists; refusing overwrite.');
for (const dir of [backup, 'app/static/css', 'app/static/js', 'app/static/assets/brand']) fs.mkdirSync(path.resolve(root, dir), {recursive:true});
fs.copyFileSync(source, path.join(backup, 'index_tusas_faz31.html'));
fs.writeFileSync(path.join(backup, 'disabled-phase31.js'), scripts[2][1].trim()+'\n');
fs.writeFileSync(path.join(root, 'app/static/js/app.js'), scripts[0][1].trim()+'\n');
fs.writeFileSync(path.join(root, 'app/static/js/i18n-tr.js'), scripts[1][1].trim()+'\n');
const assets = [...html.matchAll(/data:image\/png;base64,([A-Za-z0-9+/=]+)/g)];
fs.writeFileSync(path.join(root, 'app/static/assets/brand/logo-white.png'), Buffer.from(assets[0][1], 'base64'));
fs.writeFileSync(path.join(root, 'app/static/assets/brand/emblem-color.png'), Buffer.from(assets[1][1], 'base64'));
let count=0;
let shell=html.replace(/<style(?:\s[^>]*)?>[\s\S]*?<\/style>/g, '')
  .replace(/<!-- TUSAS_PHASE1_BRAND_THEME_(?:START|END) -->/g, '')
  .replace(/<script(?:\s[^>]*)?>[\s\S]*?<\/script>/g, () => {
    count++;
    return count === 1 ? '<script src="/static/js/app.js" defer></script>' : count === 2 ? '<script src="/static/js/i18n-tr.js" defer></script>' : '';
  })
  .replace('</head>', '<link rel="stylesheet" href="/static/css/platform.css">\n</head>')
  .replace(/\n{3,}/g,'\n\n');
fs.writeFileSync(source,shell);
console.log(JSON.stringify({backup,scriptFiles:2,brandAssets:2,htmlBytes:Buffer.byteLength(shell)},null,2));
