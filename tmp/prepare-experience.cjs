const sharp=require('C:/Users/Administrator/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/sharp');
const path=require('node:path');
const root=path.resolve(__dirname,'..');
(async()=>{
  const target=path.join(root,'app/static/assets/experience');
  await sharp('C:/Users/Administrator/.codex/generated_images/01a07a5b-0f2e-79f2-a5c3-1e621c26dc1d/exec-e297d7d2-77f5-4318-98e3-7e05afdb0910.png').webp({quality:86}).toFile(path.join(target,'earth-day-night.webp'));
  for(const kind of ['day','night'])await sharp(path.join(root,'tmp/experience-sources/earth-'+kind+'.jpg')).resize(2048,1024).webp({quality:87}).toFile(path.join(target,'earth-'+kind+'.webp'));
})();
