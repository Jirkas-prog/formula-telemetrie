from pathlib import Path
p=Path(__file__).resolve().parent/'app/viewer.html'
t=p.read_text(encoding='utf-8')
a="ctx.textAlign='center';for(let j=0;j<5;j++){let tt=start+(end-start)*j/4;ctx.fillText(fmt(tt,1),xx(tt),h-7)}"
b="const ticks=w<400?2:4;for(let j=0;j<=ticks;j++){let tt=start+(end-start)*j/ticks;ctx.textAlign=j===0?'left':j===ticks?'right':'center';ctx.fillText(fmt(tt,1),xx(tt),h-7)}"
if a in t:t=t.replace(a,b)
t=t.replace('.welcome h2{font-size:26px}', '.welcome h2{font-size:26px}.player p{display:none}')
t=t.replace("function pause(){playing=false;$('play').textContent='▶ Přehrát'}", "function pause(){playing=false;$('play').textContent='▶ Přehrát';$('play').setAttribute('aria-label','Přehrát')}")
t=t.replace("playing=true;$('play').textContent='Ⅱ Pozastavit';", "playing=true;$('play').textContent='Ⅱ Pozastavit';$('play').setAttribute('aria-label','Pozastavit');")
p.write_text(t,encoding='utf-8')
