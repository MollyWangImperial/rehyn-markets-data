(function(){
"use strict";
var $=function(id){return document.getElementById(id)};
var reduce=window.matchMedia&&window.matchMedia("(prefers-reduced-motion: reduce)").matches;
var TIER={OPEN:"Free to use",TERMS:"Check terms",PERMISSION:"Permission needed",FEE:"Licence fee"};
var STATE={live:"In database",partial:"Partial",not_collected:"Not collected",blocked:"Access refused",held:"Not on this site"};
var EXAMPLES=["What did Brent do after OPEC decisions?","Compare gold and bitcoin since 2020","Nvidia revenue"];
var PUBLIC_EXAMPLES=["Nvidia revenue","Apple insider trades","US yield curve"];
var data=null,charts=[];

/* Inside Rehyn Markets the host owns navigation and colour mode. The two pages only talk to an allowed origin. */
var EMBED=document.documentElement.classList.contains("embed");
var HOST=new URLSearchParams(location.search).get("host")||"";
if(!/^https?:\/\/(localhost|127\.0\.0\.1)(:\d+)?$|^https:\/\/[a-z0-9-]+\.onrender\.com$/.test(HOST))HOST="";
function tell(){if(!EMBED||!HOST||window.parent===window)return;window.parent.postMessage({type:"rm-db",route:location.hash||"#/",recent:recent(),categories:data?data.categories.map(function(c){return {id:c.id,name:c.name}}):[]},HOST)}

function esc(s){return String(s==null?"":s).replace(/[&<>"']/g,function(c){return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]})}
function safe(u){return /^https?:\/\//i.test(u||"")?u:""}
function compact(n){if(n==null)return "";var a=Math.abs(n);if(a>=1e9)return (n/1e9).toFixed(2)+"bn";if(a>=1e6)return (n/1e6).toFixed(1)+"m";if(a>=1e4)return Math.round(n/1e3)+"k";return Number(n).toLocaleString("en-GB")}
function fmtDay(d){if(!d)return "";var p=String(d).slice(0,10).split("-");if(p.length<3)return d;return (+p[2])+" "+["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"][+p[1]-1]+" "+p[0]}
function lic(t){return '<span class="lic '+esc(t)+'">'+esc(TIER[t]||t)+'</span>'}
var FEE={Required:"Fee required"};
function fee(f){return FEE[f]?'<span class="lic fee '+esc(f)+'">'+esc(FEE[f])+'</span>':""}
/* One label per dataset, which opens the terms behind it. A fee label carries the cost, and replaces the tier label. */
function labels(d){
  var id=esc(d.id),req=d.licence_fee==="Required";
  var amt=d.price_short||"On request",kind=d.fee_kind==="access"?"Fee":"Licence fee";
  var low=amt.charAt(0).toLowerCase()+amt.slice(1);
  var txt=req?(/^Free/.test(amt)?kind+", "+low:/^[$€£]/.test(amt)?kind+" "+amt:kind+" "+low):(TIER[d.tier]||d.tier);
  var cls=req?"lic fee Required":"lic "+esc(d.tier);
  return '<button type="button" class="'+cls+' licbtn" data-terms="'+id+'" aria-expanded="false" title="See the terms">'+esc(txt)+'</button>';
}
function termsHTML(d){
  if(!d)return "";
  var u=safe(d.terms_url),row=function(k,v){return v?'<dt>'+esc(k)+'</dt><dd>'+v+'</dd>':""};
  return '<div class="terms" hidden><dl class="kv">'+row("Licence",esc(d.licence))+row("What it means",esc(d.licence_note))+row("Condition to meet",d.attribution?"Show this credit line: "+esc(d.attribution):"")+
    row("Next step",esc(d.licence_route))+row("Cost",esc(d.price_note))+row("Terms",u?'<a href="'+esc(u)+'" target="_blank" rel="noopener noreferrer">Read the source\u2019s terms</a>':"Not published")+'</dl></div>';
}
function api(url,opt){return fetch(url,opt).then(function(r){if(!r.ok)throw new Error("status "+r.status);return r.json()})}
var tt;function toast(m){var t=$("toast");t.textContent=m;t.classList.add("on");clearTimeout(tt);tt=setTimeout(function(){t.classList.remove("on")},2400)}

/* Recent searches stay in this browser only */
function recent(){try{return JSON.parse(localStorage.getItem("rm-recent")||"[]")}catch(e){return []}}
function remember(q){try{var r=recent().filter(function(x){return x!==q});r.unshift(q);localStorage.setItem("rm-recent",JSON.stringify(r.slice(0,8)))}catch(e){}renderNav();tell()}

/* Sidebar, ribbon and home */
function renderNav(){
  if(!data)return;
  var route=location.hash||"#/",h='<div class="hgroup">Browse</div>';
  h+=data.categories.map(function(c){var on=route==="#/library/"+c.id;return '<a class="hitem'+(on?" on":"")+'" href="#/library/'+esc(c.id)+'"><span class="t">'+esc(c.name)+'</span><span class="n">'+(c.rows?compact(c.rows):c.datasets.length)+'</span></a>'}).join("");
  var r=recent();
  if(r.length)h+='<div class="hgroup">Recent</div>'+r.map(function(q){return '<a class="hitem" href="#/ask/'+encodeURIComponent(q)+'"><span class="t">'+esc(q)+'</span></a>'}).join("");
  $("nav").innerHTML=h;
}
function spark(vals,col,w,h,id){
  if(!vals||vals.length<2)return "";
  var mx=Math.max.apply(null,vals),mn=Math.min.apply(null,vals),rg=(mx-mn)||1;
  var xy=vals.map(function(v,i){return [(i*(w-6)/(vals.length-1)+3),(h-4-(v-mn)/rg*(h-8))]});
  var d=xy.map(function(p,i){return (i?"L":"M")+p[0].toFixed(1)+" "+p[1].toFixed(1)}).join(" ");
  var last=xy[xy.length-1];
  return '<svg viewBox="0 0 '+w+' '+h+'" preserveAspectRatio="none" aria-hidden="true" style="width:100%;height:100%"><path d="'+d+' L'+last[0].toFixed(1)+' '+h+' L3 '+h+' Z" fill="'+col+'" opacity=".1"/><path d="'+d+'" fill="none" stroke="'+col+'" stroke-width="1.8" stroke-linejoin="round" stroke-linecap="round" vector-effect="non-scaling-stroke"/></svg>';
}
function chg(v){if(v==null)return "";return (v>=0?"▲ ":"▼ ")+Math.abs(v*100).toFixed(1)+"%"}
/* The public library holds no daily prices, so the home page offers what it can answer. */
function renderPublic(){
  EXAMPLES=PUBLIC_EXAMPLES;renderChips();
  $("homeInput").placeholder=EXAMPLES[0];$("dockInput").placeholder=EXAMPLES[1];
  document.querySelector(".lede").textContent="Company filings and financials, Treasury rates, economic data, positioning and geopolitics in one place. Ask in plain English and see the numbers, where they came from and what licence they carry. Daily market prices are not included.";
  document.querySelector(".chips-inline").innerHTML='<span class="pill">Companies</span><span class="pill">Rates</span><span class="pill">Macro</span><span class="pill">Geopolitics</span><span class="pill">SQL</span>';
  document.querySelector(".snap").style.display="none";
}
function renderShell(){
  if(data.public)renderPublic();
  var tape=data.tape.map(function(t){return '<span><b>'+esc(t.name)+'</b>'+esc(t.text)+' <span class="'+(t.r1d>=0?"tu":"td")+'">'+esc(chg(t.r1d))+'</span></span>'}).join("");
  $("tape").innerHTML=tape+tape;
  var day=data.tape.length?data.tape[0].as_of:"";
  $("snapLabel").textContent="LAST CLOSE";
  $("snapWhen").textContent=day?"Closes to "+fmtDay(day):"";
  var total=data.rows;
  $("heroBadge").textContent=compact(total)+" rows of collected data, nothing simulated";
  $("dbText").textContent=compact(total)+" rows · "+(data.bytes/1e9).toFixed(2)+" GB";
  var sum=0,t=data.tiers;Object.keys(t).forEach(function(k){sum+=t[k]});
  var cols={OPEN:"var(--up)",TERMS:"var(--ink-2)",PERMISSION:"var(--mid)",FEE:"var(--down)"};
  $("mix").innerHTML=["OPEN","TERMS","PERMISSION","FEE"].map(function(k){return '<i style="width:'+(sum?t[k]/sum*100:0).toFixed(1)+'%;background:'+cols[k]+'"></i>'}).join("");
  $("mixKey").innerHTML='<span>'+(sum?Math.round(t.OPEN/sum*100):0)+'% free to use</span><span>'+(sum?Math.round((t.PERMISSION+t.FEE)/sum*100):0)+'% restricted</span>';
  var pick=["SPX","BRENT","XAU/USD","VIX"];
  $("sgrid").innerHTML=pick.map(function(s){var x=data.tape.filter(function(t){return t.symbol===s})[0];if(!x)return "";var up=(x.r1d||0)>=0;return '<div class="stile"><span class="sl">'+esc(x.name)+'</span><span class="sv">'+esc(x.text)+'</span><span class="sc '+(up?"u":"d")+'">'+esc(chg(x.r1d))+' last day</span><div class="ss">'+spark(x.spark,up?"var(--up)":"var(--down)",140,30,"s"+s)+'</div></div>'}).join("");
  renderNav();
}
function catsHTML(){
  return data.categories.map(function(c,i){return '<a class="frow" href="#/library/'+esc(c.id)+'"><span class="fn">'+(i+1)+'</span><span class="ft">'+esc(c.name)+'<small>'+esc(c.blurb)+'</small></span><span class="fc">'+(c.rows?compact(c.rows):c.datasets.length+" listed")+'</span></a>'}).join("")+(EMBED?'<a class="frow phone-only" href="#/licences"><span class="fn">'+(data.categories.length+1)+'</span><span class="ft">Licence register<small>What each source allows</small></span><span class="fc"></span></a>':"");
}
function renderChips(){$("chips").innerHTML=EXAMPLES.map(function(q){return '<button type="button" class="chip" data-q="'+esc(q)+'">'+esc(q)+'</button>'}).join("")}
renderChips();

/* Charts. One line or bar system, sized to the real container so text stays legible on phones. */
function ticks(mn,mx,n){var span=(mx-mn)||Math.abs(mx)||1,raw=span/n,mag=Math.pow(10,Math.floor(Math.log10(raw))),r=raw/mag,step=(r<1.5?1:r<3?2:r<7?5:10)*mag,out=[],v=Math.ceil(mn/step)*step;for(;v<=mx+step*.001;v+=step)out.push(+v.toPrecision(12));return out}
function shortNum(v){var a=Math.abs(v);if(a>=1e12)return (v/1e12).toFixed(1)+"tn";if(a>=1e9)return (v/1e9).toFixed(a>=1e10?0:1)+"bn";if(a>=1e6)return (v/1e6).toFixed(a>=1e7?0:1)+"m";if(a>=1e4)return (v/1e3).toFixed(0)+"k";if(a>=100)return Math.round(v).toLocaleString("en-GB");if(a>=1)return v.toFixed(2).replace(/\.?0+$/,"");return v.toFixed(a<.01?4:3).replace(/\.?0+$/,"")}
function timeOf(s){return Date.parse(String(s).slice(0,10)+"T00:00:00Z")}
function drawLines(host,cfg){
  var W=Math.max(300,host.clientWidth),H=W<520?230:300,m={l:48,r:cfg.multi?54:18,t:12,b:24};
  var series=cfg.series,all=[];series.forEach(function(s){s.points.forEach(function(p){all.push(p)})});
  var candles=cfg.mode==="candles",lo=Infinity,hi=-Infinity;
  all.forEach(function(p){var a=candles&&p.l!=null?p.l:p.v,b=candles&&p.h!=null?p.h:p.v;if(a<lo)lo=a;if(b>hi)hi=b});
  var pad=(hi-lo)*.06||Math.abs(hi)*.05||1;lo-=pad;hi+=pad;
  var yt=ticks(lo,hi,5),t0=timeOf(all[0].t),t1=t0;all.forEach(function(p){var t=timeOf(p.t);if(t<t0)t0=t;if(t>t1)t1=t});
  var X=function(t){return m.l+(t-t0)/((t1-t0)||1)*(W-m.l-m.r)},Y=function(v){return m.t+(hi-v)/((hi-lo)||1)*(H-m.t-m.b)};
  var g="";
  yt.forEach(function(v){g+='<line x1="'+m.l+'" x2="'+(W-m.r)+'" y1="'+Y(v).toFixed(1)+'" y2="'+Y(v).toFixed(1)+'" stroke="var(--rule)"/><text class="svg-m" x="'+(m.l-7)+'" y="'+(Y(v)+3.5).toFixed(1)+'" text-anchor="end">'+esc(shortNum(v))+'</text>'});
  var years=(t1-t0)/31557600000,xt=[],d0=new Date(t0),d1=new Date(t1);
  if(years>2.2){var stepY=Math.max(1,Math.ceil(years/(W<520?4:7)));for(var y=d0.getUTCFullYear()+1;y<=d1.getUTCFullYear();y+=stepY)xt.push([Date.UTC(y,0,1),String(y)])}
  else{var months=Math.max(1,Math.ceil(years*12/(W<520?3:6)));var cur=new Date(Date.UTC(d0.getUTCFullYear(),d0.getUTCMonth()+1,1));while(cur.getTime()<=t1){xt.push([cur.getTime(),cur.toLocaleDateString("en-GB",{month:"short",year:"2-digit",timeZone:"UTC"})]);cur=new Date(Date.UTC(cur.getUTCFullYear(),cur.getUTCMonth()+months,1))}}
  xt.forEach(function(x){g+='<text class="svg-m" x="'+X(x[0]).toFixed(1)+'" y="'+(H-6)+'" text-anchor="middle">'+esc(x[1])+'</text>'});
  if(candles){
    var pts=series[0].points,w=Math.max(1.2,Math.min(8,(W-m.l-m.r)/pts.length*.62));
    pts.forEach(function(p){var o=p.o==null?p.v:p.o,c=p.v,h=p.h==null?Math.max(o,c):p.h,l=p.l==null?Math.min(o,c):p.l,x=X(timeOf(p.t)),col=c>=o?"var(--up)":"var(--down)";
      g+='<line x1="'+x.toFixed(1)+'" x2="'+x.toFixed(1)+'" y1="'+Y(h).toFixed(1)+'" y2="'+Y(l).toFixed(1)+'" stroke="'+col+'"/><rect x="'+(x-w/2).toFixed(1)+'" y="'+Math.min(Y(o),Y(c)).toFixed(1)+'" width="'+w.toFixed(1)+'" height="'+Math.max(1,Math.abs(Y(o)-Y(c))).toFixed(1)+'" fill="'+col+'"/>'});
  } else series.forEach(function(s,i){
    var col=s.color,d=s.points.map(function(p,k){return (k?"L":"M")+X(timeOf(p.t)).toFixed(1)+" "+Y(p.v).toFixed(1)}).join(" ");
    if(series.length===1){var base=Math.min(H-m.b,Math.max(m.t,Y(Math.max(lo,Math.min(hi,lo)))));g+='<path d="'+d+' L'+X(timeOf(s.points[s.points.length-1].t)).toFixed(1)+' '+base.toFixed(1)+' L'+X(timeOf(s.points[0].t)).toFixed(1)+' '+base.toFixed(1)+' Z" fill="'+col+'" opacity=".1"/>'}
    g+='<path d="'+d+'" fill="none" stroke="'+col+'" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>';
    var e=s.points[s.points.length-1];g+='<circle cx="'+X(timeOf(e.t)).toFixed(1)+'" cy="'+Y(e.v).toFixed(1)+'" r="4" fill="'+col+'" stroke="var(--card)" stroke-width="2"/>';
    /* Labels that would collide are dropped, not nudged. The table and tooltip still carry the value. */
    if(cfg.multi&&!(cfg._labelY||(cfg._labelY=[])).some(function(y){return Math.abs(y-Y(e.v))<13})){cfg._labelY.push(Y(e.v));g+='<text class="svg-t" x="'+(X(timeOf(e.t))+8).toFixed(1)+'" y="'+(Y(e.v)+3.5).toFixed(1)+'">'+esc(shortNum(e.v))+'</text>'}
  });
  cfg._labelY=null;
  g+='<g class="cross" style="display:none"><line y1="'+m.t+'" y2="'+(H-m.b)+'" stroke="var(--ink-2)"/></g>';
  host.innerHTML='<svg viewBox="0 0 '+W+' '+H+'" height="'+H+'" role="img" tabindex="0" aria-label="'+esc(cfg.title)+'. Use the arrow keys to read values.">'+g+'</svg><div class="tip"></div>';
  var svg=host.querySelector("svg"),tip=host.querySelector(".tip"),cross=svg.querySelector(".cross"),line=cross.querySelector("line"),ref=series[0].points,idx=ref.length-1;
  function show(i){
    idx=Math.max(0,Math.min(ref.length-1,i));
    var p=ref[idx],t=timeOf(p.t),x=X(t);
    cross.style.display="";line.setAttribute("x1",x);line.setAttribute("x2",x);
    tip.textContent="";
    var hd=document.createElement("div");hd.textContent=fmtDay(p.t);tip.appendChild(hd);
    series.forEach(function(s){var q=s.points.reduce(function(a,b){return Math.abs(timeOf(b.t)-t)<Math.abs(timeOf(a.t)-t)?b:a});var r=document.createElement("div");var k=document.createElement("i");k.className="tk";k.style.background=s.color;var v=document.createElement("span");v.className="tv";v.textContent=shortNum(q.v)+(cfg.unit==="%"?"%":"");r.appendChild(k);r.appendChild(v);if(series.length>1){var nm=document.createElement("span");nm.textContent=" "+s.name;r.appendChild(nm)}tip.appendChild(r)});
    if(cfg.mode==="candles"&&p.o!=null){var o=document.createElement("div");o.textContent="O "+shortNum(p.o)+"  H "+shortNum(p.h)+"  L "+shortNum(p.l);tip.appendChild(o)}
    tip.classList.add("on");
    var scale=host.clientWidth/W,px=x*scale,tw=tip.offsetWidth;tip.style.left=(px+12+tw>host.clientWidth?Math.max(0,px-tw-12):px+12)+"px";
  }
  function hide(){cross.style.display="none";tip.classList.remove("on")}
  function at(e){var r=svg.getBoundingClientRect(),x=(e.clientX-r.left)/r.width*W,t=t0+(x-m.l)/(W-m.l-m.r)*(t1-t0),lo2=0,hi2=ref.length-1;while(hi2-lo2>1){var mid=(lo2+hi2)>>1;if(timeOf(ref[mid].t)<t)lo2=mid;else hi2=mid}return Math.abs(timeOf(ref[lo2].t)-t)<Math.abs(timeOf(ref[hi2].t)-t)?lo2:hi2}
  svg.addEventListener("pointermove",function(e){show(at(e))});
  svg.addEventListener("pointerleave",hide);
  svg.addEventListener("blur",hide);
  svg.addEventListener("focus",function(){show(idx)});
  svg.addEventListener("keydown",function(e){if(e.key==="ArrowLeft"){e.preventDefault();show(idx-1)}if(e.key==="ArrowRight"){e.preventDefault();show(idx+1)}});
}
function drawColumns(host,cfg){
  var W=Math.max(300,host.clientWidth),H=W<520?220:270,m={l:48,r:12,t:18,b:24},bars=cfg.bars,vals=bars.map(function(b){return b.value});
  var mx=Math.max.apply(null,vals.concat([0])),mn=Math.min.apply(null,vals.concat([0])),yt=ticks(mn,mx,5);mx=Math.max(mx,yt[yt.length-1]);mn=Math.min(mn,yt[0]);
  var Y=function(v){return m.t+(mx-v)/((mx-mn)||1)*(H-m.t-m.b)},band=(W-m.l-m.r)/bars.length,bw=Math.max(3,Math.min(24,band-2)),g="";
  yt.forEach(function(v){g+='<line x1="'+m.l+'" x2="'+(W-m.r)+'" y1="'+Y(v).toFixed(1)+'" y2="'+Y(v).toFixed(1)+'" stroke="var(--rule)"/><text class="svg-m" x="'+(m.l-7)+'" y="'+(Y(v)+3.5).toFixed(1)+'" text-anchor="end">'+esc(shortNum(v))+'</text>'});
  var every=Math.ceil(bars.length/(W<520?5:10));
  bars.forEach(function(b,i){var x=m.l+band*i+(band-bw)/2,y0=Y(0),y1=Y(b.value),top=Math.min(y0,y1),h=Math.max(1,Math.abs(y1-y0)),r=Math.min(4,bw/2,h),up=b.value>=0;
    var path=up?"M"+x+" "+(top+h)+"V"+(top+r)+"Q"+x+" "+top+" "+(x+r)+" "+top+"H"+(x+bw-r)+"Q"+(x+bw)+" "+top+" "+(x+bw)+" "+(top+r)+"V"+(top+h)+"Z":"M"+x+" "+top+"V"+(top+h-r)+"Q"+x+" "+(top+h)+" "+(x+r)+" "+(top+h)+"H"+(x+bw-r)+"Q"+(x+bw)+" "+(top+h)+" "+(x+bw)+" "+(top+h-r)+"V"+top+"Z";
    g+='<path class="bar" data-i="'+i+'" d="'+path+'" fill="var(--ink-2)"/><rect data-i="'+i+'" x="'+(m.l+band*i)+'" y="'+m.t+'" width="'+band+'" height="'+(H-m.t-m.b)+'" fill="transparent"/>';
    if(i%every===0||i===bars.length-1&&bars.length<=every)g+='<text class="svg-m" x="'+(x+bw/2).toFixed(1)+'" y="'+(H-6)+'" text-anchor="middle">'+esc(b.label)+'</text>';
  });
  var last=bars[bars.length-1],lx=m.l+band*(bars.length-1)+band/2;
  g+='<text class="svg-t" x="'+Math.min(W-m.r,lx).toFixed(1)+'" y="'+(Y(Math.max(last.value,0))-6).toFixed(1)+'" text-anchor="end">'+esc(last.note||shortNum(last.value))+'</text>';
  host.innerHTML='<svg viewBox="0 0 '+W+' '+H+'" height="'+H+'" role="img" aria-label="'+esc(cfg.title)+'">'+g+'</svg><div class="tip"></div>';
  hoverBars(host,bars,W,cfg);
}
function hoverBars(host,bars,W,cfg){
  var tip=host.querySelector(".tip"),svg=host.querySelector("svg");
  svg.addEventListener("pointermove",function(e){
    var el=e.target.closest?e.target.closest("[data-i]"):null;if(!el){tip.classList.remove("on");return}
    var b=bars[+el.getAttribute("data-i")];tip.textContent="";
    var a=document.createElement("div");a.textContent=b.label;tip.appendChild(a);
    var v=document.createElement("div");v.className="tv";v.textContent=b.note&&!cfg.keepNote?b.note:shortNum(b.value)+(cfg.unit==="%"?"%":"");tip.appendChild(v);
    if(cfg.keepNote&&b.note){var n=document.createElement("span");n.className="tn";n.textContent=b.note;tip.appendChild(n)}
    tip.classList.add("on");var r=host.getBoundingClientRect(),x=e.clientX-r.left,y=e.clientY-r.top,tw=tip.offsetWidth;
    tip.style.left=(x+12+tw>r.width?Math.max(0,x-tw-12):x+12)+"px";tip.style.top=Math.max(0,y-30)+"px";
  });
  svg.addEventListener("pointerleave",function(){tip.classList.remove("on")});
}
function drawDiverging(host,cfg){
  var W=Math.max(300,host.clientWidth),bars=cfg.bars,rh=W<520?24:26,lab=W<520?84:112,top=6,H=top+bars.length*rh+24,mx=Math.max.apply(null,bars.map(function(b){return Math.abs(b.value)}))||1;
  var gut=W<520?54:64,cx=lab+gut+(W-lab-2*gut)/2,half=(W-lab-2*gut)/2,yt=ticks(-mx,mx,4),g="";
  yt.forEach(function(v){if(Math.abs(v)>mx*1.02)return;var x=cx+v/mx*half;g+='<line x1="'+x.toFixed(1)+'" x2="'+x.toFixed(1)+'" y1="'+top+'" y2="'+(H-22)+'" stroke="var(--rule)"/><text class="svg-m" x="'+x.toFixed(1)+'" y="'+(H-7)+'" text-anchor="middle">'+esc(shortNum(v))+'%</text>'});
  bars.forEach(function(b,i){var y=top+i*rh,w=Math.max(1.5,Math.abs(b.value)/mx*half),up=b.value>=0,x=up?cx:cx-w,col=up?"var(--up)":"var(--down)",h=Math.min(14,rh-8),r=Math.min(4,w);
    var dx=up?"M"+x+" "+(y+4)+"H"+(x+w-r)+"Q"+(x+w)+" "+(y+4)+" "+(x+w)+" "+(y+4+r)+"V"+(y+4+h-r)+"Q"+(x+w)+" "+(y+4+h)+" "+(x+w-r)+" "+(y+4+h)+"H"+x+"Z":"M"+(x+w)+" "+(y+4)+"H"+(x+r)+"Q"+x+" "+(y+4)+" "+x+" "+(y+4+r)+"V"+(y+4+h-r)+"Q"+x+" "+(y+4+h)+" "+(x+r)+" "+(y+4+h)+"H"+(x+w)+"Z";
    g+='<text class="svg-t" x="0" y="'+(y+15)+'">'+esc(b.label)+'</text><path d="'+dx+'" fill="'+col+'"/>';
    g+='<text class="svg-t" x="'+(up?cx+w+6:cx-w-6).toFixed(1)+'" y="'+(y+15)+'" text-anchor="'+(up?"start":"end")+'">'+(up?"▲ ":"▼ ")+Math.abs(b.value).toFixed(1)+'%</text>';
    g+='<rect data-i="'+i+'" x="0" y="'+y+'" width="'+W+'" height="'+rh+'" fill="transparent"/>';
  });
  host.innerHTML='<svg viewBox="0 0 '+W+' '+H+'" height="'+H+'" role="img" aria-label="'+esc(cfg.title)+'">'+g+'</svg><div class="tip"></div>';
  cfg.keepNote=true;hoverBars(host,bars,W,cfg);
}
function mountChart(host,cfg){var run=function(){if(cfg.kind==="bars")drawColumns(host,cfg);else if(cfg.kind==="diverging")drawDiverging(host,cfg);else drawLines(host,cfg)};run();charts.push({host:host,run:run})}
var rz;window.addEventListener("resize",function(){clearTimeout(rz);rz=setTimeout(function(){charts=charts.filter(function(c){return document.body.contains(c.host)});charts.forEach(function(c){c.run()})},160)});

/* Answer blocks */
function cellHTML(c){
  if(c&&typeof c==="object"){var u=safe(c.href),t=c.t?'<span class="'+esc(c.t)+'">'+esc(c.v)+'</span>':esc(c.v);return u?'<a href="'+esc(u)+'" target="_blank" rel="noopener noreferrer">'+t+'</a>':t}
  return esc(c);
}
function isNum(c){var s=c&&typeof c==="object"?c.v:c;return /^[▲▼$£€¥+\-]?\s?[\d.,]+(%|bn|m|tn|k)?$/.test(String(s||"").trim())||/^[▲▼] /.test(String(s||""))}
function tableHTML(b){
  var numeric=b.columns.map(function(_,i){return b.rows.length>0&&b.rows.every(function(r){return r[i]===""||isNum(r[i])})});
  var fit=b.columns.length<=4?" fit":"";
  return (b.title?'<h4 class="block-h">'+esc(b.title)+'</h4>':"")+'<div class="tablebox'+fit+'"><table><thead><tr>'+b.columns.map(function(c,i){return '<th'+(numeric[i]?' class="num"':"")+'>'+esc(c)+'</th>'}).join("")+'</tr></thead><tbody>'+
    b.rows.map(function(r){return '<tr>'+r.map(function(c,i){return '<td'+(numeric[i]?' class="num nw"':"")+'>'+cellHTML(c)+'</td>'}).join("")+'</tr>'}).join("")+'</tbody></table></div>';
}
function itemsHTML(b){
  return (b.title?'<h4 class="block-h">'+esc(b.title)+'</h4>':"")+'<div class="feed">'+b.items.map(function(i){var u=safe(i.url);var meta=[i.date,i.source,i.tag].filter(Boolean).map(function(x){return '<span>'+esc(x)+'</span>'}).join("");
    return '<div><div class="fm">'+meta+'</div>'+(u?'<a class="ftl" href="'+esc(u)+'" target="_blank" rel="noopener noreferrer">'+esc(i.title)+'</a>':'<span class="ftl">'+esc(i.title)+'</span>')+(i.body?'<p class="fb">'+esc(i.body)+'</p>':"")+'</div>'}).join("")+'</div>';
}
function licenceHTML(items){
  return '<div class="feed" style="gap:0">'+items.map(function(i){var ds=/^(lic_|blocked_)/.test(i.id);var name=ds?'<span class="ln">'+esc(i.name)+'</span>':'<a class="ln" href="#/dataset/'+esc(i.id)+'">'+esc(i.name)+'</a>';
    var d=findSet(i.id)||{id:i.id,tier:i.tier,licence_fee:i.fee};
    return '<div class="licrow">'+name+'<span class="ls">'+(i.rows?'<span class="state">'+compact(i.rows)+' rows</span>':"")+labels(d)+'</span>'+
    '<span class="lm">'+esc(i.source)+(i.note?". "+esc(i.note):"")+'</span>'+(i.route?'<span class="lm"><b>Next step:</b> '+esc(i.route)+'</span>':"")+(i.price?'<span class="lp">'+esc(i.price)+'</span>':"")+termsHTML(findSet(i.id))+'</div>'}).join("")+'</div>';
}
function findSet(id){if(!data)return null;for(var i=0;i<data.categories.length;i++){var c=data.categories[i];for(var j=0;j<c.datasets.length;j++)if(c.datasets[j].id===id)return c.datasets[j]}return null}
function renderAnswer(a,into){
  var el=document.createElement("article");el.className="note";
  a.blocks.forEach(function(b){
    var d=document.createElement("div");
    if(b.type==="lede"){d.innerHTML='<p class="lede-a">'+esc(b.text)+'</p>'}
    else if(b.type==="stats"){d.innerHTML='<div class="statgrid">'+b.items.map(function(s){return '<div><span class="sl">'+esc(s.label)+'</span><span class="sv '+esc(s.tone||"")+'">'+esc(s.value)+'</span>'+(s.sub?'<span class="ss2">'+esc(s.sub)+'</span>':"")+'</div>'}).join("")+'</div>'}
    else if(b.type==="table"){d.innerHTML=tableHTML(b)}
    else if(b.type==="items"){d.innerHTML=itemsHTML(b)}
    else if(b.type==="license"){d.innerHTML=licenceHTML(b.items)}
    else if(b.type==="disc"){d.innerHTML='<p class="disc">'+esc(b.text)+'</p>'}
    else if(b.type==="chart"){
      d.className="chartbox";
      var multi=b.kind==="compare",cols=["var(--c1)","var(--c2)","var(--c3)","var(--c4)"];
      var cfg={kind:b.kind,title:b.title,unit:b.unit,bars:b.bars,multi:multi,mode:"line"};
      if(b.series)cfg.series=b.series.map(function(s,i){return {name:s.name,points:s.points,color:multi?cols[i%4]:b.kind==="price"?(b.up?"var(--up)":"var(--down)"):"var(--ink)"}});
      d.innerHTML='<div class="chart-h"><h4>'+esc(b.title)+'</h4>'+(b.candles?'<div class="seg small" role="group" aria-label="Chart type"><button type="button" data-mode="line" aria-pressed="true">Line</button><button type="button" data-mode="candles" aria-pressed="false">Candles</button></div>':"")+'</div>'+
        (multi?'<div class="keys">'+cfg.series.map(function(s){return '<span><i style="background:'+s.color+'"></i>'+esc(s.name)+'</span>'}).join("")+'</div>':"")+'<div class="chartwrap"></div>';
      d._chart=cfg;
    }
    el.appendChild(d);
  });
  if(a.note){var n=document.createElement("p");n.className="disc";n.textContent=a.note;el.appendChild(n)}
  var p=document.createElement("div");p.className="prov";
  // Credit lines travel with the data: some sources make them a condition of use.
  var credits=a.sources.map(function(s){var d=findSet(s.id);return d&&d.attribution?d.attribution:""}).filter(function(x,i,l){return x&&l.indexOf(x)===i});
  p.innerHTML=(a.sources.length?'<span class="eyebrow">Sources and licences</span><div class="src">'+a.sources.map(function(s){return '<a class="srow" href="#/dataset/'+esc(s.id)+'">'+lic(s.tier)+esc(s.name)+'</a>'}).join("")+'</div>':"")+
    (credits.length?'<p class="disc credit">'+credits.map(esc).join(" ")+'</p>':"")+
    (a.sql.length?'<details class="more"><summary>How this was answered</summary><pre class="sql">'+esc(a.sql.slice(0,6).join(";\n\n"))+'</pre></details>':"")+
    '<div class="actions"><button type="button" class="act" data-copysql="1">Copy SQL</button><button type="button" class="act" data-csv="1">Download CSV</button></div>';
  el.appendChild(p);el._a=a;into.appendChild(el);
  el.querySelectorAll(".chartbox").forEach(function(box){if(box._chart)mountChart(box.querySelector(".chartwrap"),box._chart)});
  el.addEventListener("click",function(e){
    var b=e.target.closest("[data-mode]");
    if(b){var box=b.closest(".chartbox"),seg=b.parentNode;seg.querySelectorAll("button").forEach(function(x){x.setAttribute("aria-pressed",x===b?"true":"false")});box._chart.mode=b.getAttribute("data-mode");drawLines(box.querySelector(".chartwrap"),box._chart)}
  });
}

/* Asking */
var busy=false,asked="";
function ask(q){
  q=(q||"").trim();if(!q||busy)return;
  busy=true;asked=q;remember(q);showThread();
  $("thread").innerHTML="";$("homeInput").value="";$("dockInput").value="";closeSug();
  var block=document.createElement("div");block.style.cssText="display:flex;flex-direction:column;gap:18px";
  var head=document.createElement("div");head.className="ask";head.innerHTML='<div class="qm"><i></i>Question</div><div class="q"></div>';head.querySelector(".q").textContent=q;block.appendChild(head);
  var proc=document.createElement("div");proc.className="process";proc.innerHTML='<div class="step run-now"><span class="b"></span>Reading your question</div>';block.appendChild(proc);
  $("thread").appendChild(block);$("scroll").scrollTop=0;
  api("/api/ask",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({q:q})}).then(function(a){
    proc.innerHTML=a.steps.map(function(s){return '<div class="step"><span class="b"></span>'+esc(s)+'</div>'}).join("");
    var els=proc.querySelectorAll(".step"),i=0,dt=reduce?0:130;
    (function next(){
      if(i>0)els[i-1].className="step done";
      proc.style.setProperty("--p",(i/els.length*100)+"%");
      if(i<els.length){els[i].className="step run-now";i++;setTimeout(next,dt);return}
      setTimeout(function(){proc.remove();renderAnswer(a,block);busy=false},dt);
    })();
  }).catch(function(){proc.remove();var p=document.createElement("p");p.className="disc";p.textContent="The database did not answer. Check the local server is running, then try again.";block.appendChild(p);busy=false});
}

/* Views */
function showHome(){$("home").style.display="";$("thread").classList.remove("on");$("dock").classList.remove("on");$("page").hidden=true;$("crumb").textContent="Data library · Home";$("scroll").scrollTop=0;nav("mAsk")}
function showThread(){$("home").style.display="none";$("thread").classList.add("on");$("dock").classList.add("on");$("page").hidden=true;$("crumb").textContent="Data library · Answer";nav("mAsk")}
function showPage(label,which){$("home").style.display="none";$("thread").classList.remove("on");$("dock").classList.remove("on");$("page").hidden=false;$("crumb").textContent="Data library · "+label;$("scroll").scrollTop=0;nav(which)}
function nav(id){["mAsk","mLib","mLic"].forEach(function(x){$(x).classList.toggle("on",x===id)})}
function dsCard(d){
  var span=d.first_date?fmtDay(d.first_date)+" to "+fmtDay(d.last_date):"";
  var state=d.rows?'<b>'+compact(d.rows)+'</b>':"";
  return '<div class="ds" data-href="#/dataset/'+esc(d.id)+'"><a class="dsn" href="#/dataset/'+esc(d.id)+'"><b>'+esc(d.name)+'</b></a><p>'+esc(d.blurb)+'</p><span class="dr">'+labels(d)+state+'<span>'+esc(span)+'</span></span>'+termsHTML(d)+'</div>';
}
function viewCategories(){
  if(!data)return;
  showPage("Categories","mLib");
  $("page").innerHTML='<a class="back" href="#/">‹ Search</a><div><h1 class="page-t">Browse by category</h1></div><p class="page-l">Explore the available data by subject.</p><div class="fear"><div class="fear-h"><b>Categories</b><span class="eyebrow">Rows</span></div>'+catsHTML()+'</div>';
  renderNav();
}
function viewLibrary(id){
  if(!data)return;
  var cats=id?data.categories.filter(function(c){return c.id===id}):data.categories;
  showPage(id&&cats[0]?cats[0].name:"Library","mLib");
  var h=id?'<a class="back" href="#/library">‹ All categories</a>':"";
  if(!id)h+='<div><div class="eyebrow">Data library</div><h1 class="page-t">Dataset catalogue</h1></div>';
  h+=cats.map(function(c){
    var list=c.datasets.slice().sort(function(a,b){return (b.rows||0)-(a.rows||0)});
    if(c.id==="licensed")return (id?'<div><h1 class="page-t">'+esc(c.name)+'</h1></div><p class="page-l">'+esc(c.blurb)+'</p>':'<h2 class="block-h" style="font-size:20px;margin-top:10px">'+esc(c.name)+'</h2>')+licenceHTML(list.map(toLicItem));
    return (id?'<div><h1 class="page-t">'+esc(c.name)+'</h1></div><p class="page-l">'+esc(c.blurb)+'</p>':'<h2 class="block-h" style="font-size:20px;margin-top:10px">'+esc(c.name)+'</h2>')+'<div class="dsl">'+list.map(dsCard).join("")+'</div>';
  }).join("");
  $("page").innerHTML=h;renderNav();
}
function toLicItem(d){return {id:d.id,name:d.name,tier:d.tier,status:d.status,source:d.source_name,note:d.licence_note||d.gap_note||d.blurb,price:d.price_note,rows:d.rows,fee:d.licence_fee,route:d.licence_route}}
/* The public register counts datasets, because data that is not hosted shows no rows here. */
function viewPublicLicences(all){
  var on=function(d){return d.rows>0},by=function(test){return all.filter(test).sort(function(a,b){return (b.rows||0)-(a.rows||0)||String(a.name).localeCompare(b.name)}).map(toLicItem)};
  var sec=function(title,blurb,items){return items.length?'<h2 class="block-h" style="font-size:20px;margin:12px 0 0">'+esc(title)+'</h2><p class="page-l" style="font-size:16px">'+esc(blurb)+'</p>'+licenceHTML(items):""};
  var free=by(function(d){return on(d)&&d.tier==="OPEN"}),cond=by(function(d){return on(d)&&d.tier!=="OPEN"});
  var feeHeld=by(function(d){return !on(d)&&d.licence_fee==="Required"&&d.status==="held"}),askHeld=by(function(d){return !on(d)&&d.licence_fee!=="Required"&&d.status==="held"});
  var gaps=by(function(d){return !on(d)&&d.status!=="held"});
  var n=function(x){return x.length===1?"dataset":"datasets"};
  $("page").innerHTML='<div><div class="eyebrow">Licence register</div><h1 class="page-t">What we can show paying users</h1></div>'+
    '<p class="page-l">Each label comes from reading the source’s own terms, for use on a paid product. This is a working reading, not legal advice.</p>'+
    '<div class="statgrid"><div><span class="sl">Free to use</span><span class="sv">'+free.length+'</span><span class="ss2">'+n(free)+' on this site</span></div><div><span class="sl">Free with conditions</span><span class="sv">'+cond.length+'</span><span class="ss2">'+n(cond)+' on this site</span></div><div><span class="sl">Fee or permission</span><span class="sv">'+(feeHeld.length+askHeld.length)+'</span><span class="ss2">held back</span></div><div><span class="sl">Not collected</span><span class="sv">'+gaps.length+'</span><span class="ss2">paid or refused</span></div></div>'+
    '<div class="panel warn"><p><b>Only data with no licence fee is on this site.</b> Everything else is listed below with its conditions and any published price, so the gaps stay visible. <a href="#/sources">See every source and when it was last collected</a>.</p></div>'+
    sec("Free to use","On this site. Open to use, with any credit line the source asks for.",free)+
    sec("Free with conditions","On this site. Each source sets a condition, such as a credit line, a licence notice or a statement that the data is free from the source. The condition is shown with its data.",cond)+
    sec("Licence fee","Held back from this site until a paid licence is in place, or a free source replaces it.",feeHeld)+
    sec("Permission needed","Held back from this site. The owner’s written agreement comes first, and the owner may or may not charge.",askHeld)+
    sec("Not collected","Paid data we do not hold, and sources that refused access, with published prices where they exist.",gaps);
}
function viewLicences(){
  if(!data)return;showPage("Licences","mLic");
  var all=[];data.categories.forEach(function(c){all=all.concat(c.datasets)});
  if(data.public){viewPublicLicences(all);renderNav();return}
  var group=function(t,held){return all.filter(function(d){return d.tier===t&&(held?d.rows>0:!d.rows)}).sort(function(a,b){return (b.rows||0)-(a.rows||0)}).map(toLicItem)};
  var t=data.tiers,sum=t.OPEN+t.TERMS+t.PERMISSION+t.FEE,share=function(k){if(!sum||!t[k])return "0%";var p=t[k]/sum*100;return p<1?"Under 1%":Math.round(p)+"%"};
  var sec=function(title,blurb,items){return items.length?'<h2 class="block-h" style="font-size:20px;margin:12px 0 0">'+esc(title)+'</h2><p class="page-l" style="font-size:16px">'+esc(blurb)+'</p>'+licenceHTML(items):""};
  var q=(data.quality||[]).map(function(x){return [x.check_name,x.detail||"",{v:x.passed?"Pass":"Needs review",t:x.passed?"u":"d"}]});
  $("page").innerHTML='<div><div class="eyebrow">Licence register</div><h1 class="page-t">What we can show paying users</h1></div>'+
    '<p class="page-l">Each label comes from reading the source’s own terms on 5 November 2026, for use on a paid product. This is a working reading, not legal advice.</p>'+
    '<div class="statgrid"><div><span class="sl">Free to use</span><span class="sv">'+share("OPEN")+'</span><span class="ss2">'+compact(t.OPEN)+' rows</span></div><div><span class="sl">Check terms</span><span class="sv">'+share("TERMS")+'</span><span class="ss2">'+compact(t.TERMS)+' rows</span></div><div><span class="sl">Permission needed</span><span class="sv">'+share("PERMISSION")+'</span><span class="ss2">'+compact(t.PERMISSION)+' rows</span></div><div><span class="sl">Licence fee</span><span class="sv">'+share("FEE")+'</span><span class="ss2">'+compact(t.FEE)+' rows</span></div></div>'+
    (data.public?'<div class="panel warn"><p><b>This public library holds free to use data only.</b> Daily market prices are left out until a licensed source replaces them.</p></div>':'<div class="panel warn"><p><b>Prices are the main gap.</b> Daily prices came from Yahoo, whose terms bar commercial use and automated collection, and Yahoo sells no licence. They are fine for building and testing here. They need replacing with a licensed source before any paying user sees them.</p></div>')+
    sec("Licence fee, held","Collected, but a paid licence is needed before these can be shown.",group("FEE",true))+
    sec("Permission needed, held","The source’s terms bar this use unless the owner agrees in writing. Collection from these sources is on hold.",group("PERMISSION",true))+
    sec("Check terms","Free to read, with conditions to meet or confirm.",group("TERMS",true))+
    sec("Not collected","Paid data and refused sources, with published prices where they exist.",group("FEE",false).concat(group("PERMISSION",false),group("TERMS",false)))+
    (q.length?'<h2 class="block-h" style="font-size:20px;margin:12px 0 0">Data quality checks</h2>'+tableHTML({columns:["Check","Result","Status"],rows:q}):"");
  renderNav();
}
function viewDataset(id){
  showPage("Dataset","mLib");$("page").innerHTML='<div class="panel"><p>Loading</p></div>';
  api("/api/dataset/"+encodeURIComponent(id)).then(function(d){
    showPage(d.name,"mLib");
    var kv=function(k,v){return v?'<dt>'+esc(k)+'</dt><dd>'+v+'</dd>':""},link=function(u,t){u=safe(u);return u?'<a href="'+esc(u)+'" target="_blank" rel="noopener noreferrer">'+esc(t||u)+'</a>':""};
    var h='<a class="back" href="#/library/'+esc(d.category_id)+'">‹ '+esc(d.category)+'</a><div><h1 class="page-t">'+esc(d.name)+'</h1></div><p class="page-l">'+esc(d.blurb)+'</p>';
    h+='<div class="statgrid"><div><span class="sl">Rows</span><span class="sv"'+(d.rows?'>'+Number(d.rows).toLocaleString("en-GB"):' style="font-size:15px">'+"None")+'</span></div><div><span class="sl">From</span><span class="sv" style="font-size:15px">'+esc(fmtDay(d.first_date)||"n/a")+'</span></div><div><span class="sl">To</span><span class="sv" style="font-size:15px">'+esc(fmtDay(d.last_date)||"n/a")+'</span></div><div><span class="sl">Updates</span><span class="sv" style="font-size:15px">'+esc(d.cadence||"n/a")+'</span></div></div>';
    h+='<div class="panel"><div>'+labels(d)+'</div><dl class="kv">'+kv("Source",link(d.source_url,d.source_name)||esc(d.source_name))+kv("Licence",esc(d.licence))+kv("What it means",esc(d.licence_note))+kv("Next step",esc(d.licence_route))+kv("Cost",esc(d.price_note))+kv("Credit line",esc(d.attribution))+kv("Terms read",link(d.terms_url))+kv("Gap",esc(d.gap_note))+kv("Table",d.table_name?'<code style="font-family:var(--mono);font-size:12.5px">'+esc(d.table_name)+'</code>':"")+'</dl></div>';
    if(d.series.length){h+=tableHTML({title:d.series.length+" series",columns:["Series","Name","Frequency","From","To"],rows:d.series.slice(0,200).map(function(s){return [s.series_id,s.title,s.frequency||"",fmtDay(s.first_date),fmtDay(s.last_date)]})})}
    if(d.sample.length){var cols=Object.keys(d.sample[0]);h+=tableHTML({title:"Latest rows",columns:cols,rows:d.sample.map(function(r){return cols.map(function(c){var v=r[c];return v==null?"":typeof v==="number"?(Number.isInteger(v)?String(v):v.toPrecision(6)):String(v)})})})}
    if(d.columns.length)h+=tableHTML({title:"Fields",columns:["Field","Type"],rows:d.columns.map(function(c){return [c.name,c.type]})});
    $("page").innerHTML=h;
  }).catch(function(){$("page").innerHTML='<div class="panel"><p>That dataset could not be loaded.</p></div>'});
}
/* The systematic source list that the daily collector works through, with when each source last ran. */
var SRC_STATE={active:"Collected",candidate:"Under review",held:"On hold",blocked:"Access refused"};
var EVERY={daily:"Daily",weekly:"Weekly",monthly:"Monthly",quarterly:"Quarterly",annual:"Yearly"};
function viewSources(){
  if(!data)return;showPage("Sources","mLic");
  var all=data.sources||[];
  var when=function(s){return s.last_run?"Last run "+fmtDay(s.last_run)+(s.last_status==="failed"?", failed":"")+(s.last_rows?", "+compact(s.last_rows)+" rows":""):"Not run yet"};
  var row=function(s){var u=safe(s.url);return '<div class="licrow">'+(u?'<a class="ln" href="'+esc(u)+'" target="_blank" rel="noopener noreferrer">'+esc(s.name)+'</a>':'<span class="ln">'+esc(s.name)+'</span>')+
    '<span class="ls"><span class="state">'+esc(EVERY[s.cadence]||s.cadence||"")+'</span>'+(s.tier?lic(s.tier):"")+'</span>'+
    '<span class="lm">'+esc(s.publisher)+'. '+esc(s.status==="active"?when(s):SRC_STATE[s.status]||s.status)+(s.note?". "+esc(s.note):"")+'</span></div>'};
  var sec=function(k,blurb){var items=all.filter(function(s){return s.status===k});return items.length?'<h2 class="block-h" style="font-size:20px;margin:12px 0 0">'+esc(SRC_STATE[k])+'</h2><p class="page-l" style="font-size:16px">'+esc(blurb)+'</p><div class="feed" style="gap:0">'+items.map(row).join("")+'</div>':""};
  var n=function(k){return all.filter(function(s){return s.status===k}).length};
  $("page").innerHTML='<div><div class="eyebrow">Collection</div><h1 class="page-t">Where the data comes from</h1></div>'+
    '<p class="page-l">The collector works through this list every day and fetches each source on its own schedule. New sources are checked for their terms before they join the list.</p>'+
    '<div class="statgrid"><div><span class="sl">Collected</span><span class="sv">'+n("active")+'</span><span class="ss2">sources</span></div><div><span class="sl">Under review</span><span class="sv">'+n("candidate")+'</span><span class="ss2">terms or collector pending</span></div><div><span class="sl">On hold</span><span class="sv">'+n("held")+'</span><span class="ss2">terms bar our use</span></div><div><span class="sl">Access refused</span><span class="sv">'+n("blocked")+'</span><span class="ss2">not bypassed</span></div></div>'+
    sec("active","Fetched automatically, each on its own schedule.")+
    sec("candidate","Found and assessed, but not collected yet. Each one joins the collection once its terms are confirmed.")+
    sec("held","Collection is paused because the source’s terms bar this use, or need a licence or the owner’s permission.")+
    sec("blocked","These sources refused automated requests. They were not bypassed.");
  renderNav();
}
function route(){
  var h=location.hash||"#/",m;
  if(!h||h==="#/"||h==="#")return showHome();
  if((m=h.match(/^#\/ask\/(.+)$/))){var q=decodeURIComponent(m[1]);if(q!==asked||!$("thread").classList.contains("on"))ask(q);else showThread();return}
  if(h==="#/categories")return viewCategories();
  if(h==="#/library")return viewLibrary();
  if((m=h.match(/^#\/library\/([a-z]+)$/)))return viewLibrary(m[1]);
  if(h==="#/licences")return viewLicences();
  if(h==="#/sources")return viewSources();
  if((m=h.match(/^#\/dataset\/([a-z0-9_]+)$/)))return viewDataset(m[1]);
  showHome();
}
function go(q){q=(q||"").trim();if(!q)return;var next="#/ask/"+encodeURIComponent(q);if(location.hash===next){asked="";route()}else location.hash=next}

/* Search box behaviour */
function wire(id,sugId,formId){
  var input=$(id),box=$(sugId),timer,opts=[],sel=-1;
  function draw(){box.innerHTML=opts.map(function(o,i){return '<button type="button" data-i="'+i+'" class="'+(i===sel?"on":"")+'"><b>'+esc(o.label)+'</b><span>'+esc(o.detail||"")+'</span><i>'+esc(o.kind)+'</i></button>'}).join("");box.classList.toggle("on",opts.length>0)}
  input.addEventListener("input",function(){
    this.style.height="auto";this.style.height=Math.min(this.scrollHeight,180)+"px";
    clearTimeout(timer);var v=this.value.trim(),last=v.split(/\s+/).pop();
    if(v.length<2||v.split(/\s+/).length>3||/^select\b/i.test(v)){opts=[];draw();return}
    timer=setTimeout(function(){api("/api/suggest?q="+encodeURIComponent(last)).then(function(r){if(input.value.trim()!==v)return;opts=r;sel=-1;draw()}).catch(function(){})},140);
  });
  input.addEventListener("keydown",function(e){
    if(e.key==="ArrowDown"&&opts.length){e.preventDefault();sel=(sel+1)%opts.length;draw();return}
    if(e.key==="ArrowUp"&&opts.length){e.preventDefault();sel=(sel-1+opts.length)%opts.length;draw();return}
    if(e.key==="Escape"){opts=[];draw();return}
    if(e.key==="Enter"&&!e.shiftKey){e.preventDefault();go(sel>=0?opts[sel].label:input.value)}
  });
  box.addEventListener("mousedown",function(e){var b=e.target.closest("[data-i]");if(b){e.preventDefault();go(opts[+b.getAttribute("data-i")].label)}});
  input.addEventListener("blur",function(){setTimeout(function(){opts=[];draw()},120)});
  $(formId).addEventListener("submit",function(e){e.preventDefault();go(input.value)});
}
function closeSug(){$("homeSug").classList.remove("on");$("dockSug").classList.remove("on")}
wire("homeInput","homeSug","homeForm");wire("dockInput","dockSug","dockForm");
function newSearch(){location.hash="#/";asked="";setTimeout(function(){$("homeInput").focus()},40)}
$("newBtn").addEventListener("click",newSearch);
document.addEventListener("keydown",function(e){var tag=document.activeElement&&document.activeElement.tagName;if((e.key==="n"||e.key==="N")&&!/TEXTAREA|INPUT/.test(tag)&&!e.metaKey&&!e.ctrlKey){e.preventDefault();newSearch()}});
document.addEventListener("click",function(e){
  var lb=e.target.closest(".licbtn");
  if(lb){e.preventDefault();e.stopPropagation();var box=lb.closest(".ds,.licrow"),panel=box&&box.querySelector(".terms");if(panel){panel.hidden=!panel.hidden;lb.setAttribute("aria-expanded",panel.hidden?"false":"true")}return}
  var card=e.target.closest(".ds[data-href]");
  if(card&&!e.target.closest("a,.terms")){location.hash=card.getAttribute("data-href");return}
  var c=e.target.closest("[data-q]");if(c){go(c.getAttribute("data-q"));return}
  var s=e.target.closest("[data-copysql]");
  if(s){var a=s.closest(".note")._a;try{navigator.clipboard.writeText(a.sql.join(";\n\n")).then(function(){toast("SQL copied")},function(){toast("Copy is blocked here. Open How this was answered.")})}catch(err){toast("Copy is blocked here. Open How this was answered.")}return}
  var v=e.target.closest("[data-csv]");
  if(v){var note=v.closest(".note"),t=note._a.blocks.filter(function(b){return b.type==="table"})[0];
    if(!t){toast("This answer has no table to download");return}
    var val=function(c){return c&&typeof c==="object"?c.v:c},q=function(x){return '"'+String(x==null?"":x).replace(/"/g,'""')+'"'};
    var csv=[t.columns.map(q).join(",")].concat(t.rows.map(function(r){return r.map(function(c){return q(val(c))}).join(",")})).join("\r\n");
    var el=document.createElement("a");el.href=URL.createObjectURL(new Blob(["﻿"+csv],{type:"text/csv"}));el.download="rehyn-markets.csv";el.click();URL.revokeObjectURL(el.href);toast("Check the licence labels before sharing");}
});

/* Colour mode, same switch as the prototype */
var root=document.documentElement;
function isDark(){var m=root.getAttribute("data-mode");if(m)return m==="dark";var h=root.getAttribute("data-theme");if(h)return h==="dark";return !!(window.matchMedia&&window.matchMedia("(prefers-color-scheme: dark)").matches)}
function syncSwitch(){var d=isDark();$("tLight").setAttribute("aria-pressed",d?"false":"true");$("tDark").setAttribute("aria-pressed",d?"true":"false")}
function setMode(mode){root.setAttribute("data-mode",mode);try{localStorage.setItem("rm-mode",mode)}catch(e){}syncSwitch()}
$("tLight").addEventListener("click",function(){setMode("light")});
$("tDark").addEventListener("click",function(){setMode("dark")});
try{var saved=localStorage.getItem("rm-mode");if(saved==="light"||saved==="dark")root.setAttribute("data-mode",saved)}catch(e){}
syncSwitch();

window.addEventListener("message",function(e){
  if(!EMBED||!HOST||e.origin!==HOST||e.source!==window.parent)return;
  var m=e.data||{};if(m.type!=="rm-db")return;
  if(m.mode==="dark"||m.mode==="light"){root.setAttribute("data-mode",m.mode);syncSwitch()}
  if(m.tour){tourTo(m.tour);return}
  tourSeq++;
  if(typeof m.route==="string"&&/^#\//.test(m.route)&&m.route!==(location.hash||"#/"))location.replace(m.route);
  if(m.focus)setTimeout(function(){$("homeInput").focus()},40);
});
/* The host's guide points at parts of this page. It names a route and a selector, and gets that area's position back. */
var tourSeq=0;
function tourTo(t){
  var seq=++tourSeq,tries=0;
  if(/^#\//.test(t.route||"")&&t.route!==(location.hash||"#/"))location.replace(t.route);
  (function look(){
    if(seq!==tourSeq)return;
    var el=document.querySelector(t.sel);
    if(!el||!el.getBoundingClientRect().width){if(++tries<100)setTimeout(look,100);return}
    el.scrollIntoView({block:"center",behavior:"auto"});
    setTimeout(function(){
      if(seq!==tourSeq)return;
      var r=el.getBoundingClientRect();
      window.parent.postMessage({type:"rm-db",tour:t.id,rect:{x:r.left,y:r.top,w:r.width,h:r.height}},HOST);
    },140);
  })();
}
api("/api/overview").then(function(o){data=o;renderShell();route();tell()}).catch(function(){$("heroBadge").textContent="The database is not reachable";route();tell()});
window.addEventListener("hashchange",route);
window.addEventListener("hashchange",tell);
})();
