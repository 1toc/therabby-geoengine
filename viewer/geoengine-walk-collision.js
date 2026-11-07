import * as THREE from './vendor/three/build/three.module.js';

const cache=new WeakMap();
export function insideWalkArea(area,east,north){
  return Number.isFinite(east)&&Number.isFinite(north)&&
    Math.abs(east-area.center_east_m)<=area.half_size_m&&Math.abs(north-area.center_north_m)<=area.half_size_m;
}
export function walkElevationAllowed(currentEye,groundHeight,distance){
  return Number.isFinite(currentEye)&&Number.isFinite(groundHeight)&&Number.isFinite(distance)&&distance>=0&&
    Math.abs(groundHeight+1.6-currentEye)<=0.25+distance*0.75;
}
function collisionMeshes(root){
  if(cache.has(root))return cache.get(root);
  root.updateWorldMatrix(true,true);
  const found=[];root.traverse(object=>{
    if(!object.isMesh||!object.geometry)return;
    if(!object.geometry.boundingBox)object.geometry.computeBoundingBox();
    if(!object.geometry.boundingBox)return;
    found.push({mesh:object,bounds:object.geometry.boundingBox.clone().applyMatrix4(object.matrixWorld)});
  });
  cache.set(root,found);return found;
}

// Returns the first short-range mesh hit while keeping rendering material sides intact.
export function findWalkCollision(buildings,position,movement,ray){
  const direction=movement.clone().normalize(),side=new THREE.Vector3(-direction.z,0,direction.x);
  const end=position.clone().add(movement);
  const box=new THREE.Box3().setFromPoints([position,end]).expandByScalar(0.7);
  box.min.y-=1.35;
  const candidates=[];
  for(const root of buildings)for(const item of collisionMeshes(root))
    if(item.bounds.intersectsBox(box))candidates.push(item.mesh);
  if(!candidates.length)return null;
  const materials=new Map();
  for(const mesh of candidates)for(const material of Array.isArray(mesh.material)?mesh.material:mesh.material?[mesh.material]:[])
    if(!materials.has(material)){materials.set(material,material.side);material.side=THREE.DoubleSide;}
  try{
    for(const h of [-1.35,-0.7,0])for(const offset of [-0.25,0,0.25]){
      ray.set(position.clone().addScaledVector(side,offset).add(new THREE.Vector3(0,h,0)),direction);
      ray.near=0;ray.far=movement.length()+0.4;
      const hit=ray.intersectObjects(candidates,false)[0];
      if(hit)return hit;
    }
    return null;
  }finally{for(const [material,sideValue] of materials)material.side=sideValue;}
}

// Reject points under a nearby building roof, including a doorway or a thin
// wall missed by the horizontal probes. Open or incomplete models remain approximate.
export function findWalkInterior(buildings,position,ray){
  const candidates=[];
  for(const root of buildings)for(const {mesh,bounds} of collisionMeshes(root)){
    if(position.x>=bounds.min.x&&position.x<=bounds.max.x&&position.z>=bounds.min.z&&position.z<=bounds.max.z&&
      position.y<bounds.max.y&&bounds.min.y-position.y<300)candidates.push(mesh);
  }
  if(!candidates.length)return null;
  const materials=new Map();
  for(const mesh of candidates)for(const material of Array.isArray(mesh.material)?mesh.material:mesh.material?[mesh.material]:[])
    if(!materials.has(material)){materials.set(material,material.side);material.side=THREE.DoubleSide;}
  try{
    ray.set(position,new THREE.Vector3(0,1,0));ray.near=.01;ray.far=300;
    return ray.intersectObjects(candidates,false)[0]??null;
  }finally{for(const [material,side] of materials)material.side=side;}
}

export function walkSlide(movement,collision){
  if(!collision?.face)return null;
  const normal=collision.face.normal.clone().transformDirection(collision.object.matrixWorld);normal.y=0;
  if(normal.lengthSq()<1e-8)return null;
  normal.normalize();const along=movement.clone().addScaledVector(normal,-movement.dot(normal));
  return along.lengthSq()>0.000001?along:null;
}
