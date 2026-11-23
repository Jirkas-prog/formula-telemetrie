'use strict';
// Shared by the offline viewer and the reproducible driving report.
const DriveAnalysis = {
  g:9.80665, stride:5, interval:[677,1007],
  bounds(array,stride,start,end){
    const search=value=>{let lo=0,hi=array.length/stride;while(lo<hi){const mid=(lo+hi)>>>1;if(array[mid*stride]<value)lo=mid+1;else hi=mid}return lo};
    const lo=search(start-0.0001);return [lo,end<start?lo:search(end+0.0001)];
  },
  body(data,mount){
    if(!mount||!Array.isArray(mount.rotation)||mount.rotation.length!==3)return new Float64Array();
    const [lo,hi]=this.bounds(data,18,650,1007),out=new Float64Array((hi-lo)*5);
    const theta=mount.theta_deg*Math.PI/180,co=Math.cos(theta),si=Math.sin(theta),r=mount.rotation;
    for(let i=lo;i<hi;i++){
      const p=i*18,q=(i-lo)*5;out[q]=(i+.5)/100;
      if(data[p+11]!==0||![12,13,14,15,16,17].every(c=>Number.isFinite(data[p+c]))){out.fill(NaN,q+1,q+5);continue}
      const a=[0,1,2].map(k=>data[p+12+k]-mount.zero[k]);
      const rotated=r.map(row=>row.reduce((sum,v,k)=>sum+v*a[k],0));
      out[q+1]=(co*rotated[0]+si*rotated[1])*this.g;
      out[q+2]=(-si*rotated[0]+co*rotated[1])*this.g;
      out[q+3]=r[2].reduce((sum,v,k)=>sum+v*(data[p+15+k]-mount.zero[k+3]),0);
      out[q+4]=rotated[2]*this.g;
    }
    return out;
  },
  stats(array,stride,col,start,end,badCol=null,scale=1){
    const [lo,hi]=this.bounds(array,stride,start,end);let n=0,mean=0,m2=0,sumSq=0,min=Infinity,max=-Infinity,minTime=null,maxTime=null;
    for(let i=lo;i<hi;i++){
      const p=i*stride,v=array[p+col]*scale;
      if((badCol!==null&&array[p+badCol]!==0)||!Number.isFinite(v))continue;
      n++;const delta=v-mean;mean+=delta/n;m2+=delta*(v-mean);sumSq+=v*v;
      if(v<min){min=v;minTime=array[p]}if(v>max){max=v;maxTime=array[p]}
    }
    return {n,total:hi-lo,mean:n?mean:null,std:n?Math.sqrt(Math.max(0,m2/n)):null,rms:n?Math.sqrt(sumSq/n):null,min:n?min:null,max:n?max:null,minTime,maxTime};
  },
  events(body,{threshold=.3,minDuration=.3,release=threshold/2,interval=this.interval}={}){
    if(!Number.isFinite(threshold)||threshold<.05||threshold>2||!Number.isFinite(minDuration)||minDuration<.05||minDuration>30||!(release>=0&&release<threshold))throw Error('Práh musí být 0,05–2 g a minimální délka 0,05–30 s.');
    const [lo,hi]=this.bounds(body,5,...interval),events=[];let active=null,previousValid=false;
    const finish=reason=>{
      if(!active)return;
      const duration=active.count*.01;
      if(duration+1e-8>=minDuration)events.push({...active,id:'B'+String(events.length+1).padStart(2,'0'),duration_s:duration,mean_g:active.sum/active.count,integral_ms:active.sum*.01*this.g,end_reason:reason,partial:active.partial||reason!=='release'});
      active=null;
    };
    for(let i=lo;i<hi;i++){
      const p=i*5,t=body[p],decel=-body[p+1]/this.g,lat=body[p+2]/this.g;
      const valid=Number.isFinite(decel)&&Number.isFinite(lat);
      if(!valid){finish('gap');previousValid=false;continue}
      if(previousValid&&i>lo&&t-body[(i-1)*5]>.015){finish('gap');previousValid=false}
      if(active&&decel<release)finish('release');
      if(!active&&decel>=threshold)active={start_s:t,end_s:t,peak_g:-Infinity,peak_time_s:t,peak_lat_g:lat,max_abs_lat_g:0,sum:0,count:0,partial:!previousValid};
      if(active){active.count++;active.sum+=decel;active.end_s=t;active.max_abs_lat_g=Math.max(active.max_abs_lat_g,Math.abs(lat));if(decel>active.peak_g){active.peak_g=decel;active.peak_time_s=t;active.peak_lat_g=lat}}
      previousValid=true;
    }
    finish('end');return events;
  },
  summarize(body,start,end,events=[],interval=this.interval){
    const a=Math.max(start,interval[0]),b=Math.min(end,interval[1]);
    const long=this.stats(body,5,1,a,b,null,1/this.g),lat=this.stats(body,5,2,a,b,null,1/this.g);
    const [lo,hi]=this.bounds(body,5,a,b);let valid=0,brake=0,power=0,combined=0;const lateral=[];
    for(let i=lo;i<hi;i++){
      const x=body[i*5+1]/this.g,y=body[i*5+2]/this.g;if(!Number.isFinite(x)||!Number.isFinite(y))continue;
      valid++;lateral.push(Math.abs(y));if(x<=-.3){brake++;if(Math.abs(y)>=.3)combined++}if(x>=.3)power++;
    }
    lateral.sort((x,y)=>x-y);
    return {start_s:a,end_s:b,valid_s:valid*.01,long,lat,braking_s:brake*.01,acceleration_s:power*.01,combined_braking_s:combined*.01,braking_fraction:valid?brake/valid:null,combined_fraction_of_braking:brake?combined/brake:null,lat_abs_p95_g:valid?lateral[Math.ceil(valid*.95)-1]:null,events_with_peak:events.filter(e=>e.peak_time_s>=a&&e.peak_time_s<=b).length};
  }
};
