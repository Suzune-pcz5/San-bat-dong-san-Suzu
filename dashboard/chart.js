"use strict";

const el = id => document.getElementById(id);
const data = JSON.parse(el("market-data").textContent);
const {counties, periods, historyLength, minTransactions, models, meta} = data;
const lastActual = historyLength - 1;
const lastPeriod = periods.length - 1;
const names = Object.keys(counties);
const number = new Intl.NumberFormat("vi-VN", {maximumFractionDigits: 2});
const format = n => n == null ? "—" : number.format(n);
const euro = n => n == null ? "—" : format(n) + " EUR";
const percent = n => n == null ? "—" : (n > 0 ? "+" : "") + format(n) + "%";
const shortQuarter = q => q.slice(5) + " " + q.slice(0, 4);
const set = (id, value) => { el(id).textContent = value; };
const colors = {observed:"#68b8ff", compare:"#69dfbf", forecast:"#ffcc75", compareForecast:"#cbb4ff", grid:"#263952", labels:"#a8bad2"};
const plot = el("plot");
const ctx = plot.getContext("2d");
const forecastOn = () => el("show-forecast").checked;
const bandOn = () => forecastOn() && el("show-band").checked;
const rangeEnd = () => forecastOn() ? lastPeriod : lastActual;
const primary = () => counties[el("county").value];
const comparison = () => counties[el("comparison").value];
let left = Math.max(0, lastActual - 19);
let right = lastPeriod;
let hovered = null;
let drag = null;
let geometry;

for (const name of names) {
  el("county").add(new Option(name, name));
  el("comparison").add(new Option(name, name));
}
for (let i = lastActual; i >= 0; i--) el("quarter").add(new Option(shortQuarter(periods[i]), i));
el("county").value = names.includes("Dublin") ? "Dublin" : names[0];

function growth(rows, q) {
  const current = rows[q], before = rows[q - 4];
  return current?.[1] >= minTransactions && before?.[1] >= minTransactions
    ? (current[0] / before[0] - 1) * 100 : null;
}

function addRow(body, values, selected = false) {
  const row = body.insertRow();
  if (selected) row.className = "selected";
  for (const value of values) {
    const cell = row.insertCell();
    if (value instanceof Node) cell.append(value);
    else cell.textContent = value;
  }
}

function renderSummary() {
  const name = el("county").value;
  const {observed, forecast} = primary();
  const q = Number(el("quarter").value);
  const current = observed[q], final = forecast?.points.at(-1), latest = observed[lastActual];
  set("price", euro(current?.[0]));
  set("price-note", name + " · " + shortQuarter(periods[q]));
  set("count", format(current?.[1]));
  const change = growth(observed, q);
  set("yoy", percent(change));
  set("yoy-note", change === null ? "Thiếu kỳ đủ ngưỡng" : "So với cùng quý năm trước");
  set("endpoint", euro(final?.[0]));
  set("end-note", final ? shortQuarter(periods[lastPeriod]) + " · " + models[forecast.model] : "Thiếu chuỗi đủ điều kiện");

  const search = el("search").value.trim().toLowerCase();
  const sort = el("sort").value;
  const ranking = names.flatMap(county => {
    const rows = counties[county].observed, point = rows[q];
    return point?.[1] >= minTransactions
      ? [{county, price:point[0], count:point[1], yoy:growth(rows,q)}] : [];
  });
  const sorted = ranking.filter(row => row.county.toLowerCase().includes(search))
    .sort((a,b) => (b[sort] ?? -Infinity) - (a[sort] ?? -Infinity) || a.county.localeCompare(b.county));
  set("rank-note", shortQuarter(periods[q]) + " · " + sorted.length + "/" + ranking.length + " County đủ ngưỡng");
  const body = el("rank");
  body.replaceChildren();
  for (const row of sorted) {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = row.county;
    button.onclick = () => { el("county").value = row.county; refresh(); };
    addRow(body,[button,format(row.price),format(row.count),percent(row.yoy)],row.county === name);
  }

  const scores = el("scores"), future = el("future");
  scores.replaceChildren();
  future.replaceChildren();
  renderBacktest(name, forecast);
  if (!forecast) {
    set("forecast-summary", name + " thiếu chuỗi liên tục đạt ngưỡng cho kiểm định và dự báo.");
    set("validation", "");
    return;
  }
  const delta = (final[0] / latest[0] - 1) * 100;
  set("forecast-summary", name + " · " + models[forecast.model] + " · " + euro(final[0]) +
    " vào " + shortQuarter(periods[lastPeriod]) + " (" + percent(delta) +
    " so với quý quan sát cuối). Dải sai số cuối kỳ " + euro(final[1]) + " – " + euro(final[2]) + ".");
  set("validation", forecast.origins + " mốc chọn mô hình · Kiểm tra riêng " +
    shortQuarter(periods[historyLength - data.horizon]) + " – " + shortQuarter(periods[lastActual]));
  for (const [id,label] of Object.entries(models)) {
    const [mae,rmse] = forecast.holdout[id];
    addRow(scores,[label + (id === forecast.model ? " ✓" : ""),format(forecast.development[id]),format(mae),format(rmse)],id === forecast.model);
  }
  forecast.points.forEach(([price,low,high],i) =>
    addRow(future,[shortQuarter(periods[historyLength+i]),format(price),format(low),format(high)]));
}

function renderBacktest(name, forecast) {
  const body = el("backtest-rows"), svg = el("backtest-plot");
  body.replaceChildren();
  svg.replaceChildren();
  el("backtest-results").hidden = !forecast;
  if (!forecast) {
    set("backtest-description", name + " thiếu chuỗi đủ điều kiện để kiểm định.");
    set("backtest-diagnostics", "");
    return;
  }

  const start = historyLength-data.horizon;
  const rolling = el("backtest-mode").value === "rolling";
  const points = rolling
    ? forecast.holdoutPoints.map(([actual],i)=>[actual,forecast.rollingPoints[i]])
    : forecast.holdoutPoints;
  const band = rolling ? forecast.rollingBand : forecast.holdoutBand;
  const covered = points.filter(([actual],i)=>actual>=band[i][0] && actual<=band[i][1]).length;
  const average = values => values.reduce((sum,value)=>sum+value,0)/values.length;
  const errors = points.map(([actual,predicted])=>predicted-actual);
  const [mae,rmse] = rolling
    ? [average(errors.map(Math.abs)),Math.sqrt(average(errors.map(e=>e**2)))]
    : forecast.holdout[forecast.model];
  const mape = 100*average(errors.map((e,i)=>Math.abs(e)/points[i][0]));
  const bias = average(errors);
  const method = rolling
    ? "Ở mỗi quý, giữ nguyên mô hình đã chọn và dùng dữ liệu đến quý trước để dự báo một bước."
    : "Giả lập đứng tại " + shortQuarter(periods[start-1]) + " và dự báo cả 12 quý từ mốc đó.";
  set("backtest-description", name + " · " + models[forecast.model] + ". " + method +
    " Đối chiếu với giá thật từ " + shortQuarter(periods[start]) + " đến " + shortQuarter(periods[lastActual]) + ".");
  set("backtest-diagnostics", "MAE " + euro(mae) + " · RMSE " + euro(rmse) +
    " · Sai số tương đối tuyệt đối trung bình " + format(mape) + "% · Lệch trung bình " +
    (bias>0?"+":"") + euro(bias) + " · Giá thật trong dải " + covered + "/" + points.length + " quý");
  const values = [...points,...band].flat();
  const pad = Math.max(1,(Math.max(...values)-Math.min(...values))*.12,Math.max(...values)*.01);
  const low = Math.max(0,Math.min(...values)-pad), high = Math.max(...values)+pad;
  const x = i => 58+i*520/(points.length-1);
  const y = value => 200-(value-low)*172/(high-low);
  function append(tag, attributes, content) {
    const node = document.createElementNS("http://www.w3.org/2000/svg",tag);
    for (const [key,value] of Object.entries(attributes)) node.setAttribute(key,value);
    if (content !== undefined) node.textContent=content;
    svg.append(node);
  }
  for (let i=0;i<=4;i++) {
    const level=low+(high-low)*i/4, py=y(level);
    append("line",{x1:58,x2:578,y1:py,y2:py,stroke:colors.grid});
    append("text",{x:52,y:py+4,"text-anchor":"end"},format(Math.round(level/1000))+"k");
  }
  const upper = band.map(([,value],i)=>x(i)+","+y(value));
  const lower = band.map(([value],i)=>x(i)+","+y(value)).reverse();
  append("polygon",{points:[...upper,...lower].join(" "),fill:"#ffcc7540"});
  points.forEach(([actual,predicted],i)=>{
    const quarter=shortQuarter(periods[start+i]);
    const error=Math.round((predicted-actual)*100)/100;
    addRow(body,[quarter,format(actual),format(predicted),(error>0?"+":"")+format(error)]);
    if (i%3===0 || i===points.length-1) {
      append("text",{x:x(i),y:225,"text-anchor":"middle"},quarter);
    }
  });
  for (const [index,color] of [[0,colors.observed],[1,colors.forecast]]) {
    append("polyline",{
      points:points.map((row,i)=>x(i)+","+y(row[index])).join(" "),
      fill:"none",stroke:color,"stroke-width":2,"stroke-dasharray":index ? "6 4" : "",
    });
  }
}

function renderDataset() {
  const items = [
    ["Thời gian giao dịch đủ điều kiện", meta.firstDate + " đến " + meta.lastDate],
    ["Phạm vi quan sát", shortQuarter(periods[0]) + " – " + shortQuarter(periods[lastActual])],
    ["Chân trời dự báo", shortQuarter(periods[historyLength]) + " – " + shortQuarter(periods[lastPeriod])],
    ["Số County", format(names.length)],
    ["Giao dịch sạch", format(meta.cleanRows) + " · " + format(meta.types.second_hand) +
      " nhà cũ · " + format(meta.types.new ?? 0) + " nhà mới"],
    ["Giao dịch trên biểu đồ", format(meta.observedRows) + " giao dịch nhà cũ đến mốc quan sát"],
    ["Giá có cờ rà soát", format(meta.reviewRows) + " trong tập đủ điều kiện"],
  ];
  if (meta.quality) {
    const q = meta.quality;
    items.splice(4,0,["Giao dịch ban đầu", format(q.raw_rows)],
      ["Ngoài phạm vi so sánh", format(q.excluded_rows) + " theo cờ giá thị trường hoặc VAT"]);
    items.push(["Thiếu trong nguồn", format(q.missing_eircode_rows) + " Eircode · " +
      format(q.missing_property_size_rows) + " kích thước nhà"]);
  }
  for (const [key,value] of items) {
    const term = document.createElement("dt"), desc = document.createElement("dd");
    term.textContent = key;
    desc.textContent = value;
    el("dataset").append(term,desc);
  }
  set("coverage", names.length + " County · Nhà đã qua sử dụng · " +
    shortQuarter(periods[lastActual]) + " là quý quan sát cuối");
}

function drawPath(points, x, y, color, dashed = false) {
  ctx.beginPath();
  let started = false;
  for (const [i,value] of points) {
    if (value == null) { started = false; continue; }
    if (started) ctx.lineTo(x(i),y(value));
    else ctx.moveTo(x(i),y(value));
    started = true;
  }
  ctx.strokeStyle = color;
  ctx.lineWidth = 2;
  ctx.setLineDash(dashed ? [6,4] : []);
  ctx.stroke();
  ctx.setLineDash([]);
  if (points.length === 1 && points[0][1] != null) {
    ctx.beginPath();ctx.arc(x(points[0][0]),y(points[0][1]),3,0,Math.PI*2);
    ctx.fillStyle=color;ctx.fill();
  }
}

function visibleForecast(series, range) {
  if (!forecastOn() || !series?.forecast) return [];
  return range.flatMap(i=>{
    const point=series.forecast.points[i-historyLength];
    return point ? [[i,...point]] : [];
  });
}

function drawBand(points,x,y,fill) {
  if (points.length < 2) return;
  ctx.beginPath();
  points.forEach(([i,,lower],index)=>index ? ctx.lineTo(x(i),y(lower)) : ctx.moveTo(x(i),y(lower)));
  [...points].reverse().forEach(([i,,,upper])=>ctx.lineTo(x(i),y(upper)));
  ctx.closePath();
  ctx.fillStyle=fill;
  ctx.fill();
}

function drawForecast(points,series,x,y,color) {
  const anchor=series?.observed[lastActual]?.[0];
  const joins=left<=lastActual && points[0]?.[0]===historyLength && anchor!=null;
  drawPath(joins ? [[lastActual,anchor],...points] : points,x,y,color,true);
}

function draw() {
  const width = plot.clientWidth, height = plot.clientHeight;
  if (!width || !height) return;
  const dpr = window.devicePixelRatio || 1;
  if (plot.width !== Math.round(width*dpr) || plot.height !== Math.round(height*dpr)) {
    plot.width = Math.round(width*dpr);
    plot.height = Math.round(height*dpr);
  }
  ctx.setTransform(dpr,0,0,dpr,0,0);
  ctx.clearRect(0,0,width,height);
  ctx.font = "11px system-ui";
  const startX = 60, endX = width-16, top = 28, bottom = height-96, volumeBase = height-33;
  const step = (endX-startX)/(right-left+1);
  const x = i => startX+(i-left+.5)*step;
  const series = primary(), compare = comparison();
  const range = Array.from({length:right-left+1},(_,i)=>left+i);
  const actuals = range.map(i=>[i,series.observed[i]?.[0]]);
  const others = compare ? range.map(i=>[i,compare.observed[i]?.[0]]) : [];
  const projected = visibleForecast(series,range);
  const projectedOther = visibleForecast(compare,range);
  const prices = [...actuals,...others,...projected,...projectedOther].flatMap(row=>
    (bandOn() ? row.slice(1) : row.slice(1,2)).filter(value=>value!=null));
  const lo = prices.length ? Math.min(...prices) : 0;
  const hi = prices.length ? Math.max(...prices) : 1;
  const pad = Math.max((hi-lo)*.12,hi*.02,1);
  const low = Math.max(0,lo-pad), high = hi+pad;
  const y = value => bottom-(value-low)*(bottom-top)/(high-low);
  geometry = {startX,endX,step};

  if (forecastOn() && right >= historyLength) {
    const split = Math.max(startX,x(historyLength)-step/2);
    ctx.fillStyle="#ffcc7510";ctx.fillRect(split,top,endX-split,bottom-top);
    ctx.strokeStyle="#ffcc7590";ctx.beginPath();ctx.moveTo(split,top);ctx.lineTo(split,bottom);ctx.stroke();
    if (endX-split > 90) {
      ctx.fillStyle=colors.forecast;ctx.textAlign="left";ctx.fillText("DỰ BÁO",split+7,19);
    }
  }
  ctx.textAlign="right";
  for (let k=0;k<=4;k++) {
    const value=low+(high-low)*k/4, py=y(value);
    ctx.strokeStyle=colors.grid;ctx.beginPath();ctx.moveTo(startX,py);ctx.lineTo(endX,py);ctx.stroke();
    ctx.fillStyle=colors.labels;ctx.fillText(format(Math.round(value/1000))+"k",startX-7,py+4);
  }
  if (bandOn()) {
    drawBand(projected,x,y,"#ffcc7530");
    drawBand(projectedOther,x,y,"#cbb4ff25");
  }
  drawPath(actuals,x,y,colors.observed);
  drawPath(others,x,y,colors.compare);
  drawForecast(projected,series,x,y,colors.forecast);
  drawForecast(projectedOther,compare,x,y,colors.compareForecast);
  const maxCount=Math.max(1,...range.map(i=>series.observed[i]?.[1] ?? 0));
  const tickEvery=Math.max(1,Math.ceil(range.length/Math.max(2,Math.floor((endX-startX)/76))));
  ctx.textAlign="center";
  for (const i of range) {
    const n=series.observed[i]?.[1] ?? 0, barHeight=n*40/maxCount;
    if (n) { ctx.fillStyle="#68b8ff72";ctx.fillRect(x(i)-step*.30,volumeBase-barHeight,step*.60,barHeight); }
    if ((i-left)%tickEvery===0) {
      ctx.fillStyle=colors.labels;ctx.fillText(shortQuarter(periods[i]),x(i),height-12);
    }
  }
  ctx.fillStyle=colors.labels;ctx.textAlign="right";
  ctx.fillText(format(maxCount),startX-7,volumeBase-32);
  ctx.fillText("0",startX-7,volumeBase+4);
  if (hovered !== null && hovered >= left && hovered <= right) {
    ctx.strokeStyle="#a8bad2a0";ctx.beginPath();ctx.moveTo(x(hovered),top);ctx.lineTo(x(hovered),volumeBase);ctx.stroke();
  }
}

function setRange(start,end) {
  const max = rangeEnd();
  const size = Math.min(max+1,Math.max(2,end-start+1));
  left = Math.max(0,Math.min(max+1-size,start));
  right = left+size-1;
  for (const [id,value] of [["from",left],["to",right]]) {
    el(id).max = max;
    el(id).value = value;
    el(id).setAttribute("aria-valuetext",shortQuarter(periods[value]));
  }
  set("chart-range",shortQuarter(periods[left])+" – "+shortQuarter(periods[right])+" · Giá EUR · Khối lượng bên dưới");
  hovered=null;
  el("tooltip").hidden=true;
  draw();
}

function zoom(factor,anchor) {
  const size=right-left+1;
  const next=Math.max(4,Math.min(rangeEnd()+1,Math.round(size*factor)));
  const start=Math.round(anchor-(anchor-left)*next/size);
  setRange(start,start+next-1);
}

function refresh() {
  if (el("comparison").value === el("county").value) el("comparison").value="";
  for (const option of el("comparison").options) option.disabled = option.value === el("county").value;
  el("compare-legend").hidden=!comparison();
  set("compare-legend",el("comparison").value+" · Quan sát");
  const name=el("county").value, other=el("comparison").value;
  set("observed-legend",name+" · Quan sát");
  set("forecast-legend",name+" · Dự báo");
  set("compare-forecast-legend",other+" · Dự báo");
  el("show-band").disabled=!forecastOn();
  el("forecast-legend").hidden=!forecastOn() || !primary().forecast;
  el("compare-forecast-legend").hidden=!forecastOn() || !comparison()?.forecast;
  el("band-legend").hidden=!bandOn() || !(primary().forecast || comparison()?.forecast);
  renderSummary();
  setRange(left,Math.min(right,rangeEnd()));
}

function plotPosition(event) {
  return event.clientX-plot.getBoundingClientRect().left;
}
function indexAt(position) {
  return Math.max(left,Math.min(right,left+Math.floor((position-geometry.startX)/geometry.step)));
}

plot.addEventListener("wheel",event=>{
  if (!geometry || event.deltaY === 0) return;
  event.preventDefault();
  zoom(event.deltaY<0?.8:1.25,indexAt(plotPosition(event)));
},{passive:false});
plot.addEventListener("pointerdown",event=>{
  if (!geometry || event.button!==0) return;
  drag={x:plotPosition(event),left,right,step:geometry.step,id:event.pointerId};
  plot.setPointerCapture(event.pointerId);
});
plot.addEventListener("pointermove",event=>{
  if (!geometry) return;
  const position=plotPosition(event), tip=el("tooltip");
  if (drag) {
    const shift=Math.round((drag.x-position)/drag.step);
    if (Math.abs(drag.x-position)>5) drag.moved=true;
    if (drag.moved) setRange(drag.left+shift,drag.right+shift);
    return;
  }
  if (position<geometry.startX || position>geometry.endX) { hideTip();return; }
  hovered=indexAt(position);
  const values=[shortQuarter(periods[hovered])];
  for (const name of [el("county").value,el("comparison").value].filter(Boolean)) {
    const series=counties[name];
    const observed=series.observed[hovered], future=series.forecast?.points[hovered-historyLength];
    if (observed) values.push(name+" · "+euro(observed[0])+" · "+format(observed[1])+" giao dịch");
    if (forecastOn() && future) {
      values.push(name+" · Dự báo · "+euro(future[0]));
      if (bandOn()) values.push("Dải sai số · "+euro(future[1])+" – "+euro(future[2]));
    }
  }
  if (values.length===1) values.push("Thiếu dữ liệu");
  tip.textContent=values.join("\n");
  tip.hidden=false;
  tip.style.left=Math.max(6,Math.min(plot.clientWidth-tip.offsetWidth-6,position+12))+"px";
  tip.style.top="10px";
  draw();
});
plot.addEventListener("pointerup",event=>{
  if (!drag || event.pointerId!==drag.id) return;
  const index=indexAt(plotPosition(event));
  if (!drag.moved && index<=lastActual) {
    el("quarter").value=index;
    renderSummary();
  }
  drag=null;
});
plot.addEventListener("pointercancel",()=>{drag=null;hideTip();});
function hideTip() {
  el("tooltip").hidden=true;
  if (hovered!==null) {hovered=null;draw();}
}
plot.addEventListener("pointerleave",hideTip);

for (const button of document.querySelectorAll("[data-view]")) button.onclick=()=>{
  const view=button.dataset.view;
  if (view==="future") {
    el("show-forecast").checked=true;
    refresh();
    setRange(Math.max(0,lastActual-3),lastPeriod);
  } else if (view==="all") setRange(0,rangeEnd());
  else {
    const end=Number(el("quarter").value);
    setRange(Math.max(0,end-Number(view)+1),end);
  }
};
el("zoom-in").onclick=()=>zoom(.7,(left+right)/2);
el("zoom-out").onclick=()=>zoom(1.4,(left+right)/2);
el("pan-back").onclick=()=>setRange(left-4,right-4);
el("pan-next").onclick=()=>setRange(left+4,right+4);
el("from").oninput=()=>setRange(Math.min(Number(el("from").value),right-1),right);
el("to").oninput=()=>setRange(left,Math.max(left+1,Number(el("to").value)));
for (const id of ["county","comparison","quarter","show-band"]) el(id).onchange=refresh;
el("show-forecast").onchange=()=>{
  if (forecastOn() && right===lastActual) right=lastPeriod;
  if (!forecastOn() && left>=lastActual) left=Math.max(0,lastActual-19);
  refresh();
};
el("search").oninput=renderSummary;
el("sort").onchange=renderSummary;
el("backtest-mode").onchange=()=>renderBacktest(el("county").value,primary().forecast);

el("export").onclick=()=>{
  const columns=["county,quarter,series,median_eur,transactions,lower_eur,upper_eur,model"];
  const name=el("county").value, compare=el("comparison").value;
  for (let i=left;i<=right;i++) {
    for (const county of [name,compare].filter(Boolean)) {
      const {observed,forecast}=counties[county];
      const point=observed[i], prediction=forecast?.points[i-historyLength];
      if (point) columns.push([county,periods[i],"observed",...point,"","",""].join(","));
      if (forecastOn() && prediction) columns.push([county,periods[i],"forecast",prediction[0],"",prediction[1],prediction[2],forecast.model].join(","));
    }
  }
  const url=URL.createObjectURL(new Blob(["\ufeff",columns.join("\r\n")],{type:"text/csv;charset=utf-8"}));
  const link=document.createElement("a");
  link.href=url;link.download="ireland-"+name+"-"+periods[left]+"-"+periods[right]+".csv";link.click();
  setTimeout(()=>URL.revokeObjectURL(url),1000);
};
new ResizeObserver(draw).observe(plot);
renderDataset();
refresh();
