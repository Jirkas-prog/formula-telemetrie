const assert=require('node:assert/strict'),fs=require('node:fs');
(async()=>{
 const {summarize,buildReport}=await import('../web/report.mjs');
 const rows=[
  [0,1,2,3,4,5,6,7,8,9,0,1,1,1,1],
  [1,2,3,4,999,999,999,999,999,999,1,0,1,1,0],
  [2,-3,-4,-5,-10,-20,-30,-7,-8,-9,0,1,0,1,1]
 ];
 const summary=summarize({length:rows.length,get:i=>rows[i]});
 assert.equal(summary.axes[0].min,-3);assert.equal(summary.axes[0].max,2);assert.equal(summary.axes[0].clipped,1);
 assert.equal(summary.axes[3].count,2);assert.equal(summary.axes[3].max,4);assert.equal(summary.axes[6].count,1);assert.equal(summary.axes[6].min,7);
 console.log('PASS: PDF statistics exclude repeated/stale/invalid values; extrema, fresh counts and clipping are correct.');
 if(!process.argv.includes('--render'))return;
 const data={length:6000,info:{name:'SIMULOVANÁ_DATA_Ověření_reportu_přední_nápravy.csv',crc:true,invalid:2,seqMissing:3,settings:{accel_range_g:2,gyro_range_dps:250,accel_rate_hz:500,gyro_rate_hz:500,mag_rate_hz:100}},get:i=>{
  const t=i/500,a=1.4*Math.sin(t*2),g=180*Math.cos(t*3);return [t,a,.9*Math.cos(t*4),1+.4*Math.sin(t),g,90*Math.sin(t),12*Math.cos(t),24+10*Math.sin(t),-8+3*Math.cos(t),42, i>1600&&i<1700?1:0,i%5===0?1:0,1,1,1];
 }};
 const {jsPDF}=require('../web/vendor/jspdf.umd.min.js');
 const fonts=['Regular','Bold'].map(s=>new Uint8Array(fs.readFileSync('web/pdfjs/standard_fonts/LiberationSans-'+s+'.ttf')));
 const {doc}=buildReport(jsPDF,data,...fonts,new Date('2026-10-21T12:00:00+02:00'));
 assert.equal(doc.getNumberOfPages(),4);
 fs.writeFileSync('.cache/report-sample.pdf',Buffer.from(doc.output('arraybuffer')));
 console.log('PASS: four-page PDF created with embedded Czech fonts and vector graphs.');
})().catch(e=>{console.error(e);process.exitCode=1;});
