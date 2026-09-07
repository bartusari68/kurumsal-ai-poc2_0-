/* Offline asset preparation; no runtime dependency is added to the app. */
const sharp=require('C:/Users/Administrator/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/sharp');
const path=require('node:path');
const root=path.resolve(__dirname,'..');
const src=path.join(root,'tmp/experience-sources'),dest=path.join(root,'app/static/assets/experience');
(async()=>{
  await sharp(path.join(src,'earth-day.jpg')).resize(4096,2048,{withoutEnlargement:true}).webp({quality:91}).toFile(path.join(dest,'earth-day-4k.webp'));
  await sharp(path.join(src,'earth-night-high.jpg')).resize(4096,2048,{withoutEnlargement:true}).webp({quality:91}).toFile(path.join(dest,'earth-night-4k.webp'));
  for(const width of [1280,1920,3840]){
    await sharp(path.join(src,'stars-8k.jpg')).extract({left:1800,top:968,width:3840,height:2160}).resize(width,Math.round(width*9/16),{withoutEnlargement:true}).webp({quality:85}).toFile(path.join(dest,'stars-'+width+'.webp'));
  }
  console.log('4K maps and responsive star assets prepared.');
})().catch(error=>{console.error(error);process.exitCode=1;});
