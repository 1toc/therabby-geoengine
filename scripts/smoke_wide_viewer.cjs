// Optional development smoke test. Requires Playwright on the development PC.
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

(async () => {
  const root = path.resolve(__dirname, '..');
  const output = path.join(root, 'dist', 'real', 'fukushima-east-1km');
  const browser = await chromium.launch({
    headless: true,
    executablePath: 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
    args: ['--no-sandbox', '--enable-unsafe-swiftshader', '--disable-gpu-sandbox'],
  });
  const page = await browser.newPage({viewport:{width:1280,height:720}});
  const failures=[];
  page.on('pageerror',error=>failures.push(error.message));
  page.on('console',message=>{
    if(message.type()==='error'&&!message.text().includes('Failed to load resource'))
      failures.push(message.text());
  });
  page.on('response',response=>{
    if(response.status()>=400&&!response.url().endsWith('/favicon.ico'))
      failures.push(`${response.status()} ${response.url()}`);
  });
  const base=process.env.GEOENGINE_URL || 'http://127.0.0.1:8767/viewer/wide-preview.html';
  await page.goto(base,{waitUntil:'domcontentloaded'});
  const waitFor = async (size,core) => {
    await page.waitForFunction(([tileSize,quality])=>{
      const state=document.getElementById('state').textContent;
      return state.includes(`中心 ${quality}`) &&
        document.getElementById('tile-size').value===tileSize &&
        state.includes('視点 道路') && /タイル \d+_\d+/.test(state) &&
        /表示 [1-9]/.test(state);
    },[size,core],{timeout:45000});
  };
  await waitFor('250','軽量');
  await page.waitForFunction(()=>document.getElementById('state').textContent.includes('読込中 0'),
                             null,{timeout:45000});
  await page.screenshot({path:path.join(output,'wide_browser_250_low_street.png')});
  await page.locator('#quality').selectOption('high');
  await waitFor('250','高精細');
  await page.screenshot({path:path.join(output,'wide_browser_250_high_street.png')});
  const roadApi=await page.evaluate(async()=>{
    const {RoadTileProvider}=await import('/viewer/geoengine-road-api.js');
    const base='/dist/real/fukushima-east-1km/tiles-250/';
    const manifest=await fetch(base+'tileset.json').then(response=>response.json());
    const route=await fetch(base+'route.json').then(response=>response.json());
    const provider=new RoadTileProvider(base,manifest);
    const network=await provider.loadNetwork();
    const terrain=await provider.loadTerrain();
    const officialEdge=network.edges.find(edge=>edge.drivable&&edge.official_extent_samples===3);
    const from=provider.nodes.get(officialEdge.from).position;
    const to=provider.nodes.get(officialEdge.to).position;
    const official=await provider.roadExtentAt((from[0]+to[0])/2,(from[1]+to[1])/2);
    const point=route.points.reduce((best,p)=>p[0]**2+p[1]**2<best[0]**2+best[1]**2?p:best);
    return {edges:network.edges.length,official,coverage:network.official_extent_mean_sample_coverage,
            originTp:terrain.height_origin_tp_m,terrainAtPoint:provider.terrainHeightAt(...point),
            nearest:provider.nearestRoad(...point,2),
            surface:await provider.surfaceAt(...point)};
  });
  if(roadApi.edges<100||!roadApi.nearest||!roadApi.surface||roadApi.surface.collision_ready||
     !roadApi.official||roadApi.official.collision_ready||roadApi.coverage<.7||
     !Number.isFinite(roadApi.originTp)||!Number.isFinite(roadApi.terrainAtPoint.height_m)||
     !Number.isFinite(roadApi.surface.ground_height_m)||
     roadApi.surface.height_m!==null||roadApi.surface.road_deck_verified)
    failures.push('RoadTileProvider did not return road graph and flat surface');
  await page.locator('#quality').selectOption('low');
  await waitFor('250','軽量');
  await page.locator('#tile-size').selectOption('100');
  await waitFor('100','軽量');
  await page.screenshot({path:path.join(output,'wide_browser_100_low_street.png')});
  await page.locator('#tile-size').selectOption('500');
  await waitFor('500','軽量');
  await page.screenshot({path:path.join(output,'wide_browser_500_low_street.png')});
  await page.locator('#tour').click();
  const before=await page.locator('#state').textContent();
  await page.waitForTimeout(1200);
  const after=await page.locator('#state').textContent();
  if(before===after)failures.push('Tour did not update location/status');
  await page.locator('#diagnostics summary').click();
  await page.locator('#benchmark').click();
  await page.waitForTimeout(700);
  const downloadPromise=page.waitForEvent('download',{timeout:10000});
  await page.locator('#benchmark-stop').click();
  const download=await downloadPromise;
  const reportPath=path.join(output,'wide_benchmark_smoke.json');
  await download.saveAs(reportPath);
  const report=JSON.parse(fs.readFileSync(reportPath,'utf8'));
  if(!report.partial||report.tile_size_m!==500||report.drawing_buffer[0]!==1280)
    failures.push('Benchmark JSON fields are invalid');
  await browser.close();
  if(failures.length)throw new Error(failures.join('\n'));
  console.log('PASS wide viewer: street view at 250m/100m/500m, road API, tour, benchmark JSON');
})().catch(error=>{console.error(error);process.exitCode=1;});
