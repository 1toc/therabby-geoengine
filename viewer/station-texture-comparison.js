// Comparison-only crop; never overwrites the official JPEG or a 3D asset.
const sourceUrl='../data/derived/station-photo-pilot/a4fdf53b-4765-4cbc-ae1b-92f25562ddc1.jpg';
const rect={x:0,y:0,w:738,h:267},scale=2;
const byId=id=>document.getElementById(id);
function load(url){return new Promise((resolve,reject)=>{const image=new Image();image.onload=()=>resolve(image);image.onerror=reject;image.src=url;});}
function draw(canvas,image,rectOnImage){
  canvas.width=rect.w*scale;canvas.height=rect.h*scale;
  const ctx=canvas.getContext('2d',{willReadFrequently:true});
  ctx.imageSmoothingEnabled=true;ctx.imageSmoothingQuality='high';
  ctx.drawImage(image,rectOnImage.x,rectOnImage.y,rectOnImage.w,rectOnImage.h,0,0,canvas.width,canvas.height);
  return ctx;
}
function sharpen(image){
  const ctx=draw(byId('sharp'),image,rect),w=ctx.canvas.width,h=ctx.canvas.height;
  const input=ctx.getImageData(0,0,w,h),output=ctx.createImageData(w,h),amount=Number(byId('strength').value);
  const src=input.data,dst=output.data;
  for(let y=0;y<h;y++)for(let x=0;x<w;x++){
    const i=(y*w+x)*4;
    for(let c=0;c<3;c++){
      const v=src[i+c];
      if(x===0||y===0||x===w-1||y===h-1){dst[i+c]=v;continue;}
      const edge=v-(src[i-4+c]+src[i+4+c]+src[i-w*4+c]+src[i+w*4+c])/4;
      dst[i+c]=Math.max(0,Math.min(255,v+Math.max(-18,Math.min(18,edge))*amount));
    }
    dst[i+3]=src[i+3];
  }
  ctx.putImageData(output,0,0);byId('strength-value').value=amount.toFixed(1);
}
try{
  const source=await load(sourceUrl);draw(byId('original'),source,rect);sharpen(source);
  byId('strength').addEventListener('input',()=>sharpen(source));
}catch{document.querySelector('main').insertAdjacentText('beforeend','元JPEGを読み込めません。ローカルHTTPサーバーで開いてください。');}
