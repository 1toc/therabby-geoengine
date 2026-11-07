/**
 * Opt-in, procedural city appearance for the existing GeoEngine WebGL viewer.
 * Inspired by the architectural approach of Procedural Tokyo; original code.
 * Does not change map geometry, source attribution, road rules or collision data.
 */
import * as THREE from 'three';
import {buildEstimatedRoadPaint,isProceduralFacadeMaterial} from './geoengine-procedural-rules.mjs';

const FACADE_VERSION = 'therabby-procedural-facade-v01';

export class ProceduralCity {
  constructor({scene, sunlight, hemisphere}) {
    this.scene=scene;this.sunlight=sunlight;this.hemisphere=hemisphere;
    this.base={
      sky:scene.background.clone(),
      fog:scene.fog?.color.clone()??null,
      sun:intensityOf(sunlight),
      ambient:intensityOf(hemisphere),
      position:sunlight.position.clone(),
    };
    this.enabled=false;this.hour=14;
    this.strength={value:0};this.night={value:0};this.distance={value:260};
  }
  setQuality(quality) {
    this.distance.value=quality==='high'?540:quality==='standard'?380:210;
  }
  setEnabled(enabled) {
    this.enabled=Boolean(enabled);
    this.strength.value=this.enabled?1:0;
    this.setTime(this.hour);
  }
  setTime(hour) {
    this.hour=Math.min(23,Math.max(5,Number(hour)||14));
    if(!this.enabled) {
      this.night.value=0;
      this.scene.background.copy(this.base.sky);
      if(this.scene.fog&&this.base.fog)this.scene.fog.color.copy(this.base.fog);
      this.sunlight.intensity=this.base.sun;
      this.sunlight.position.copy(this.base.position);
      this.hemisphere.intensity=this.base.ambient;
      return;
    }
    // Artistic lighting preview, not astronomical time or measured illuminance.
    const dawn=smoothstep(5.5,8.0,this.hour);
    const dusk=1-smoothstep(17.0,20.0,this.hour);
    const day=dawn*dusk;
    const night=1-day;
    const twilight=Math.max(0,1-Math.abs(this.hour-18.4)/2.1)
      +Math.max(0,1-Math.abs(this.hour-6.2)/1.5);
    const sky=this.base.sky.clone().lerp(new THREE.Color(0xc78472),Math.min(0.7,twilight*0.6))
      .lerp(new THREE.Color(0x101b30),night*0.93);
    this.scene.background.copy(sky);
    if(this.scene.fog)this.scene.fog.color.copy(sky);
    this.sunlight.intensity=this.base.sun*(0.1+0.9*day);
    this.sunlight.position.set(-1100+500*Math.sin((this.hour-12)*Math.PI/12),180+2300*day,520);
    this.hemisphere.intensity=this.base.ambient*(0.25+0.75*day);
    this.night.value=night;
  }
  installFacades(root, kind) {
    if(!root||!['building','osmBuilding'].includes(kind))return 0;
    const used=new Set();let patched=0;
    const stats={kind,materials:0,eligible:0,patched:0,unmatched:[],alreadyPatched:0};
    root.traverse(object=>{
      if(!object.isMesh)return;
      for(const mat of Array.isArray(object.material)?object.material:[object.material]) {
        if(!mat||used.has(mat))continue;
        used.add(mat);stats.materials++;
        if(!mat.isMeshStandardMaterial||!isProceduralFacadeMaterial(mat.name,kind)){
          if(stats.unmatched.length<8)stats.unmatched.push(String(mat.name??'(unnamed)'));
          continue;
        }
        stats.eligible++;
        if(mat.userData.geoProceduralFacade){stats.alreadyPatched++;continue;}
        mat.userData.geoProceduralFacade=true;
        const original=mat.onBeforeCompile,oldKey=mat.customProgramCacheKey.bind(mat);
        const tint=new THREE.Color(kind==='building'?0xbab8ae:0x9f836b);
        mat.onBeforeCompile=(shader,renderer)=>{
          if(original)original.call(mat,shader,renderer);
          const vertexCommon='#include <common>';
          const vertexProject='#include <project_vertex>';
          const fragmentCommon='#include <common>';
          const fragmentColor='#include <color_fragment>';
          if(!shader.vertexShader.includes(vertexCommon)||!shader.vertexShader.includes(vertexProject)||
             !shader.fragmentShader.includes(fragmentCommon)||!shader.fragmentShader.includes(fragmentColor)){
            console.warn('Procedural facade shader: unsupported Three.js shader chunks');return;
          }
          shader.uniforms.uGeoProcEnable=this.strength;
          shader.uniforms.uGeoProcNight=this.night;
          shader.uniforms.uGeoProcRange=this.distance;
          shader.uniforms.uGeoProcTint={value:tint};
          shader.vertexShader=shader.vertexShader.replace(vertexCommon,
            vertexCommon+'\n varying vec3 vGeoProcWorld; varying vec3 vGeoProcNormal;');
          shader.vertexShader=shader.vertexShader.replace(vertexProject,
            'vGeoProcWorld=(modelMatrix*vec4(transformed,1.0)).xyz;'+
            'vGeoProcNormal=normalize(mat3(modelMatrix)*normal);\n'+vertexProject);
          shader.fragmentShader=shader.fragmentShader.replace(fragmentCommon,fragmentCommon+`
            varying vec3 vGeoProcWorld;
            varying vec3 vGeoProcNormal;
            uniform float uGeoProcEnable;
            uniform float uGeoProcNight;
            uniform float uGeoProcRange;
            uniform vec3 uGeoProcTint;
            float geoProcWindowGlow=0.0;
          `);
          shader.fragmentShader=shader.fragmentShader.replace(fragmentColor,fragmentColor+`
            if(uGeoProcEnable>0.001 && abs(normalize(vGeoProcNormal).y)<0.55){
              float distanceToEye=distance(vGeoProcWorld,cameraPosition);
              float fade=1.0-smoothstep(uGeoProcRange*0.50,uGeoProcRange,distanceToEye);
              if(fade>0.001) {
                vec3 n=normalize(vGeoProcNormal);
                float lateral=abs(n.x)>abs(n.z)?vGeoProcWorld.z:vGeoProcWorld.x;
                float seed=fract(sin(dot(floor(vGeoProcWorld.xz/24.0),vec2(12.9898,78.233)))*43758.5453);
                float bay=2.65+seed*0.75;
                float floorHeight=3.05+seed*0.42;
                vec2 cell=fract(vec2(lateral/bay,vGeoProcWorld.y/floorHeight));
                float win= smoothstep(0.11,0.145,cell.x)*(1.0-smoothstep(0.85,0.89,cell.x))
                          *smoothstep(0.24,0.27,cell.y)*(1.0-smoothstep(0.81,0.85,cell.y));
                float mullion=1.0-smoothstep(0.009,0.018,abs(cell.x-0.5));
                vec2 room=floor(vec2(lateral/bay,vGeoProcWorld.y/floorHeight));
                float lit=step(0.60,fract(sin(dot(room,vec2(127.1,311.7)))*43758.5453));
                vec3 wall=mix(diffuseColor.rgb,uGeoProcTint,0.7);
                wall*=0.94+0.06*seed;
                float sill=1.0-smoothstep(0.025,0.055,abs(cell.y-0.2));
                wall=mix(wall,wall*0.68,sill*0.22);
                vec3 glass=mix(vec3(0.048,0.095,0.13),vec3(0.60,0.43,0.20),uGeoProcNight*lit);
                glass=mix(glass,wall*0.50,mullion);
                float effect=uGeoProcEnable*fade;
                diffuseColor.rgb=mix(diffuseColor.rgb,mix(wall,glass,win),effect);
                geoProcWindowGlow=effect*win*(1.0-mullion)*lit*uGeoProcNight;
              }
            }
          `);
          if(shader.fragmentShader.includes('#include <emissivemap_fragment>')){
            shader.fragmentShader=shader.fragmentShader.replace('#include <emissivemap_fragment>',
              '#include <emissivemap_fragment>\n totalEmissiveRadiance += vec3(0.48,0.31,0.12)*geoProcWindowGlow;');
          }
        };
        mat.customProgramCacheKey=()=>oldKey()+'-'+FACADE_VERSION;
        mat.needsUpdate=true;
        patched++;
      }
    });
    stats.patched=patched;
    root.userData.geoProceduralFacadeStats=stats;
    return patched;
  }
  installRoadPaint(root) {
    if(!root?.userData?.geoProceduralRoadFactory)return null;
    let group=root.userData.geoProceduralRoadGroup;
    if(!group){
      group=root.userData.geoProceduralRoadFactory();
      root.userData.geoProceduralRoadGroup=group;
      root.add(group);
    }
    group.visible=this.enabled;
    return group;
  }
  toggleRoadPaint(root){
    if(!root)return;
    if(this.enabled)this.installRoadPaint(root);
    else if(root.userData.geoProceduralRoadGroup)root.userData.geoProceduralRoadGroup.visible=false;
  }
}

function intensityOf(light){return Number(light.intensity)||0;}
function smoothstep(a,b,v){const t=Math.max(0,Math.min(1,(v-a)/(b-a)));return t*t*(3-2*t);}

export function createEstimatedMarkingMeshes(tile, sampleHeight, {maxQuads=2400}={}) {
  const data=buildEstimatedRoadPaint(tile.edges,sampleHeight,{maxQuads});
  const group=new THREE.Group();
  group.name='手続き生成の推定路面標示（交通規制・車線の正確性未確認）';
  group.userData.estimatedVisual=true;
  group.userData.roadPaintDiagnostics=data.diagnostics;
  for(const [key,color] of [['yellow',0xf1ca69],['white',0xf5f4eb]]){
    if(!data[key].length)continue;
    const geometry=new THREE.BufferGeometry();
    geometry.setAttribute('position',new THREE.Float32BufferAttribute(data[key],3));
    geometry.computeVertexNormals();
    const material=new THREE.MeshBasicMaterial({
      color,side:THREE.DoubleSide,depthWrite:false,
      polygonOffset:true,polygonOffsetFactor:-1,polygonOffsetUnits:-1,
    });
    const mesh=new THREE.Mesh(geometry,material);
    mesh.userData.estimatedRoadPaint=true;
    mesh.renderOrder=4;
    group.add(mesh);
  }
  return group;
}
