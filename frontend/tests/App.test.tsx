import{fireEvent,render,screen,waitFor,within}from'@testing-library/react';import{expect,test,vi}from'vitest';import App from'../src/App';
function mockApi(){const state={batches:[{id:1,code:'INK-T1',color:'品红',supplier:'测试供应商',received_date:'2026-01-01',expiry_date:'2027-01-01',viscosity:20,quality_status:'passed',notes:'',active:true,received_weight:50,available_weight:50}],jobs:[] as any[],issues:[] as any[],stats:{batches:1,passed:1,expiring_soon:0,jobs:0,pending_issues:0}};
const ok=(d:any)=>({ok:true,json:()=>Promise.resolve(d)}),bad=(detail:string)=>({ok:false,status:409,json:()=>Promise.resolve({detail})});
return vi.fn((u:string,opt?:RequestInit)=>{const m=opt?.method??'GET';
if(u.startsWith('/api/batches'))return Promise.resolve(ok(state.batches));
if(u.startsWith('/api/issues'))return Promise.resolve(ok(state.issues));
if(u.startsWith('/api/stats'))return Promise.resolve(ok(state.stats));
if(u==='/api/jobs'&&m==='GET')return Promise.resolve(ok(state.jobs));
if(u==='/api/jobs'&&m==='POST'){const d=JSON.parse(String(opt?.body));const b=state.batches.find(x=>x.id===d.batch_id)!;
if(d.planned_usage>b.available_weight)return Promise.resolve(bad(`可用重量不足：批次剩余 ${b.available_weight} kg，计划用量 ${d.planned_usage} kg`));
b.available_weight-=d.planned_usage;const j={id:state.jobs.length+1,...d,batch_code:b.code,batch_color:b.color,status:'planned',cancelled_at:null,actual_usage:null,settled_weight:null,completed_at:null,created_at:'2026-09-10T08:00:00'};state.jobs.push(j);return Promise.resolve(ok({...j,issues_created:0}))}
const done=u.match(/^\/api\/jobs\/(\d+)\/complete$/);if(done&&m==='PATCH'){const j=state.jobs.find(x=>x.id===Number(done[1]))!;
if(j.status==='completed')return Promise.resolve(bad('工单已完成，不能重复完成'));
if(j.status==='cancelled')return Promise.resolve(bad('工单已取消，不能完成'));
const d=JSON.parse(String(opt?.body));const b=state.batches.find(x=>x.id===j.batch_id)!;const over=Math.round((d.actual_usage-j.planned_usage)*1000)/1000;
if(over>b.available_weight)return Promise.resolve(bad(`批次可用重量不足：超用 ${over} kg，批次剩余 ${b.available_weight} kg，工单与库存均未改动`));
b.available_weight=Math.round((b.available_weight-over)*1000)/1000;j.status='completed';j.actual_usage=d.actual_usage;j.settled_weight=Math.round((j.planned_usage-d.actual_usage)*1000)/1000;j.completed_at='2026-09-10T10:00:00';return Promise.resolve(ok({id:j.id,status:'completed',actual_usage:j.actual_usage,settled_weight:j.settled_weight,available_weight:b.available_weight,completed_at:j.completed_at}))}
const cancel=u.match(/^\/api\/jobs\/(\d+)\/cancel$/);if(cancel&&m==='PATCH'){const j=state.jobs.find(x=>x.id===Number(cancel[1]))!;
if(j.status==='cancelled')return Promise.resolve(bad('工单已取消，不能重复取消'));
if(j.status==='completed')return Promise.resolve(bad('工单已完成，不能取消'));
j.status='cancelled';j.cancelled_at='2026-09-10T09:00:00';state.batches.find(x=>x.id===j.batch_id)!.available_weight+=j.planned_usage;return Promise.resolve(ok({id:j.id,status:'cancelled',returned_weight:j.planned_usage}))}
return Promise.resolve(ok([]))})}
const dd=(label:string)=>screen.getByText(label).parentElement!.querySelector('dd')!.textContent;
function openJobForm(){fireEvent.click(screen.getByText('＋ 创建上机工单'));return{code:screen.getByLabelText(/唯一工单号/),press:screen.getByLabelText(/印刷机/),substrate:screen.getByLabelText(/承印材料/),operator:screen.getByLabelText(/操作人/),usage:screen.getByLabelText(/计划用量/),batch:screen.getByLabelText(/油墨批次/)}}
function fillForm(f:any,code:string,usage:string){fireEvent.change(f.code,{target:{value:code}});fireEvent.change(f.press,{target:{value:'海德堡'}});fireEvent.change(f.substrate,{target:{value:'白卡纸'}});fireEvent.change(f.operator,{target:{value:'王工'}});fireEvent.change(f.batch,{target:{value:'1'}});fireEvent.change(f.usage,{target:{value:usage}})}
test('shows dashboard metrics',async()=>{vi.stubGlobal('fetch',vi.fn((u:string)=>Promise.resolve({ok:true,json:()=>Promise.resolve(u.includes('stats')?{batches:4,passed:2,expiring_soon:1,jobs:1,pending_issues:2}:[])})));render(<App/>);expect(screen.getByText('正在加载生产数据…')).toBeInTheDocument();await waitFor(()=>expect(screen.getByText('批次总数')).toBeInTheDocument());expect(screen.getByText(/创建上机工单/)).toBeInTheDocument()})
test('reserve create cancel main flow with persisted result',async()=>{vi.stubGlobal('fetch',mockApi());vi.spyOn(window,'confirm').mockReturnValue(true);
const app=render(<App/>);await waitFor(()=>expect(screen.getByText('批次总数')).toBeInTheDocument());
const f=openJobForm();fillForm(f,'JOB-T1','20');fireEvent.click(screen.getByText('保存'));
await waitFor(()=>expect(screen.getByText(/工单已创建/)).toBeInTheDocument());
fireEvent.click(screen.getByRole('button',{name:'上机工单'}));await waitFor(()=>expect(screen.getByText('JOB-T1')).toBeInTheDocument());
expect(dd('预占用量')).toBe('20 kg');expect(screen.getByText('计划中')).toBeInTheDocument();
fireEvent.click(screen.getByRole('button',{name:'油墨批次'}));await waitFor(()=>expect(dd('可用重量')).toBe('30 kg'));
fireEvent.click(screen.getByRole('button',{name:'上机工单'}));await waitFor(()=>expect(screen.getByText('取消')).toBeInTheDocument());
fireEvent.click(screen.getByText('取消'));
await waitFor(()=>expect(screen.getByText('已取消')).toBeInTheDocument());expect(screen.queryByText('取消')).not.toBeInTheDocument();
fireEvent.click(screen.getByRole('button',{name:'油墨批次'}));await waitFor(()=>expect(dd('可用重量')).toBe('50 kg'));
app.unmount();render(<App/>);await waitFor(()=>expect(screen.getByText('批次总数')).toBeInTheDocument());
fireEvent.click(screen.getByRole('button',{name:'上机工单'}));await waitFor(()=>expect(screen.getByText('已取消')).toBeInTheDocument());
fireEvent.click(screen.getByRole('button',{name:'油墨批次'}));await waitFor(()=>expect(dd('可用重量')).toBe('50 kg'))})
test('insufficient balance keeps form and shows server reason',async()=>{vi.stubGlobal('fetch',mockApi());render(<App/>);
await waitFor(()=>expect(screen.getByText('批次总数')).toBeInTheDocument());
const f=openJobForm();fillForm(f,'JOB-T2','999');fireEvent.click(screen.getByText('保存'));
await waitFor(()=>expect(screen.getByText(/可用重量不足：批次剩余 50 kg/)).toBeInTheDocument());
expect(screen.getByLabelText(/唯一工单号/)).toHaveValue('JOB-T2');expect(screen.getByLabelText(/计划用量/)).toHaveValue(999);
fireEvent.change(screen.getByLabelText(/计划用量/),{target:{value:'10'}});fireEvent.click(screen.getByText('保存'));
await waitFor(()=>expect(screen.getByText(/工单已创建/)).toBeInTheDocument())})
test('register actual usage completes job and refreshes settled result',async()=>{vi.stubGlobal('fetch',mockApi());
const app=render(<App/>);await waitFor(()=>expect(screen.getByText('批次总数')).toBeInTheDocument());
const f=openJobForm();fillForm(f,'JOB-C1','20');fireEvent.click(screen.getByText('保存'));
await waitFor(()=>expect(screen.getByText(/工单已创建/)).toBeInTheDocument());
fireEvent.click(screen.getByRole('button',{name:'上机工单'}));
await waitFor(()=>expect(screen.getByText('JOB-C1')).toBeInTheDocument());
expect(screen.getByText('计划中')).toBeInTheDocument();
fireEvent.change(screen.getByLabelText(/实际用量/),{target:{value:'15'}});
fireEvent.click(screen.getByRole('button',{name:'完成工单'}));
await waitFor(()=>expect(screen.getByText('已完成')).toBeInTheDocument());
expect(screen.queryByText('完成工单')).not.toBeInTheDocument();
expect(dd('预占用量')).toBe('20 kg');expect(dd('实际用量')).toBe('15 kg');expect(dd('结算差额')).toBe('少用返还 5 kg');expect(dd('完成时间')).not.toBe('');
fireEvent.click(screen.getByRole('button',{name:'油墨批次'}));await waitFor(()=>expect(dd('可用重量')).toBe('35 kg'));
app.unmount();render(<App/>);await waitFor(()=>expect(screen.getByText('批次总数')).toBeInTheDocument());
fireEvent.click(screen.getByRole('button',{name:'上机工单'}));
await waitFor(()=>expect(screen.getByText('已完成')).toBeInTheDocument());
expect(dd('结算差额')).toBe('少用返还 5 kg');
fireEvent.click(screen.getByRole('button',{name:'油墨批次'}));await waitFor(()=>expect(dd('可用重量')).toBe('35 kg'))})
test('overuse conflict keeps input for correction and cancel entry still works',async()=>{vi.stubGlobal('fetch',mockApi());vi.spyOn(window,'confirm').mockReturnValue(true);
render(<App/>);await waitFor(()=>expect(screen.getByText('批次总数')).toBeInTheDocument());
const f=openJobForm();fillForm(f,'JOB-C2','20');fireEvent.click(screen.getByText('保存'));
await waitFor(()=>expect(screen.getByText(/工单已创建/)).toBeInTheDocument());
fireEvent.click(screen.getByRole('button',{name:'上机工单'}));await waitFor(()=>expect(screen.getByText('JOB-C2')).toBeInTheDocument());
fireEvent.change(screen.getByLabelText(/实际用量/),{target:{value:'999'}});
fireEvent.click(screen.getByRole('button',{name:'完成工单'}));
await waitFor(()=>expect(screen.getByText(/批次可用重量不足：超用 979 kg/)).toBeInTheDocument());
expect(screen.getByLabelText(/实际用量/)).toHaveValue(999);
expect(screen.getByText('计划中')).toBeInTheDocument();expect(dd('预占用量')).toBe('20 kg');
fireEvent.change(screen.getByLabelText(/实际用量/),{target:{value:'15'}});
fireEvent.click(screen.getByRole('button',{name:'完成工单'}));
await waitFor(()=>expect(screen.getByText('已完成')).toBeInTheDocument());
expect(dd('结算差额')).toBe('少用返还 5 kg');
const g=openJobForm();fillForm(g,'JOB-C3','10');fireEvent.click(screen.getByText('保存'));
await waitFor(()=>expect(screen.getAllByText(/工单已创建/).length).toBeGreaterThan(0));
fireEvent.click(screen.getByRole('button',{name:'上机工单'}));
await waitFor(()=>expect(screen.getByText('JOB-C3')).toBeInTheDocument());
fireEvent.click(screen.getByRole('button',{name:'取消'}));
await waitFor(()=>expect(screen.getByText('已取消')).toBeInTheDocument());
fireEvent.click(screen.getByRole('button',{name:'油墨批次'}));await waitFor(()=>expect(dd('可用重量')).toBe('35 kg'))})
test('switch batch on planned job, record survives refresh, conflict keeps selection',async()=>{
const state={batches:[
{id:1,code:'INK-S1',color:'品红',supplier:'供应商A',received_date:'2026-01-01',expiry_date:'2027-01-01',viscosity:20,quality_status:'passed',notes:'',active:true,received_weight:50,available_weight:30},
{id:2,code:'INK-S2',color:'青',supplier:'供应商B',received_date:'2026-01-01',expiry_date:'2027-01-01',viscosity:21,quality_status:'passed',notes:'',active:true,received_weight:40,available_weight:40},
{id:3,code:'INK-S3',color:'黄',supplier:'供应商C',received_date:'2026-01-01',expiry_date:'2027-01-01',viscosity:22,quality_status:'passed',notes:'',active:true,received_weight:10,available_weight:5}],
jobs:[{id:1,job_code:'JOB-S1',batch_id:1,batch_code:'INK-S1',batch_color:'品红',press:'海德堡',substrate:'白卡纸',planned_date:'2026-09-10',operator:'王工',description:'',planned_usage:20,actual_usage:null,settled_weight:null,status:'planned',cancelled_at:null,completed_at:null,created_at:'2026-09-10T08:00:00',previous_batch_code:null,switched_at:null}] as any[],
issues:[] as any[],stats:{batches:3,passed:3,expiring_soon:0,jobs:1,pending_issues:0}};
const ok=(d:any)=>({ok:true,json:()=>Promise.resolve(d)}),bad=(detail:string)=>({ok:false,status:409,json:()=>Promise.resolve({detail})});
vi.stubGlobal('fetch',vi.fn((u:string,opt?:RequestInit)=>{const m=opt?.method??'GET';
if(u.startsWith('/api/batches'))return Promise.resolve(ok(state.batches));
if(u.startsWith('/api/issues'))return Promise.resolve(ok(state.issues));
if(u.startsWith('/api/stats'))return Promise.resolve(ok(state.stats));
if(u==='/api/jobs'&&m==='GET')return Promise.resolve(ok(state.jobs));
const sw=u.match(/^\/api\/jobs\/(\d+)\/switch$/);if(sw&&m==='PATCH'){const j=state.jobs.find(x=>x.id===Number(sw[1]))!;
if(j.status!=='planned')return Promise.resolve(bad(j.status==='completed'?'工单已完成，不能换料':'工单已取消，不能换料'));
const d=JSON.parse(String(opt?.body));const t=state.batches.find(x=>x.id===d.batch_id)!;
if(t.id===j.batch_id)return Promise.resolve(bad('目标批次与当前批次相同，无需换料'));
if(!t.active)return Promise.resolve(bad('目标批次已停用，不能换料'));
if(t.available_weight<j.planned_usage)return Promise.resolve(bad(`目标批次可用重量不足：批次剩余 ${t.available_weight} kg，计划用量 ${j.planned_usage} kg，工单与库存均未改动`));
const prev=state.batches.find(x=>x.id===j.batch_id)!;prev.available_weight+=j.planned_usage;t.available_weight-=j.planned_usage;
j.previous_batch_code=prev.code;j.batch_id=t.id;j.batch_code=t.code;j.batch_color=t.color;j.switched_at='2026-09-10T11:00:00';
return Promise.resolve(ok({id:j.id,batch_code:t.code,previous_batch_code:prev.code,switched_at:j.switched_at,issues_created:0,available_weight:t.available_weight}))}
return Promise.resolve(ok([]))}));
const app=render(<App/>);await waitFor(()=>expect(screen.getByText('批次总数')).toBeInTheDocument());
fireEvent.click(screen.getByRole('button',{name:'上机工单'}));await waitFor(()=>expect(screen.getByText('JOB-S1')).toBeInTheDocument());
expect(screen.getByText('INK-S1')).toBeInTheDocument();expect(screen.queryByText('换料前批次')).not.toBeInTheDocument();
// 先选余额不足的目标批次：冲突提示后已选目标保留，便于重新选择
fireEvent.change(screen.getByLabelText(/换料批次/),{target:{value:'3'}});
fireEvent.click(screen.getByRole('button',{name:'确认换料'}));
await waitFor(()=>expect(screen.getByText(/目标批次可用重量不足：批次剩余 5 kg/)).toBeInTheDocument());
expect(screen.getByLabelText(/换料批次/)).toHaveValue('3');expect(screen.getByText('INK-S1')).toBeInTheDocument();
// 改选余额充足的批次换料成功
fireEvent.change(screen.getByLabelText(/换料批次/),{target:{value:'2'}});
fireEvent.click(screen.getByRole('button',{name:'确认换料'}));
await waitFor(()=>expect(screen.getByText(/已换料至 INK-S2/)).toBeInTheDocument());
await waitFor(()=>expect(screen.getByText('INK-S2')).toBeInTheDocument());
expect(dd('换料前批次')).toBe('INK-S1');expect(dd('换料时间')).not.toBe('');
// 双边余额同步：原批次返还、目标批次扣减
fireEvent.click(screen.getByRole('button',{name:'油墨批次'}));
await waitFor(()=>expect(screen.getByText('INK-S3')).toBeInTheDocument());
const avail=(code:string)=>within(screen.getByText(code).closest('article')!).getByText('可用重量').parentElement!.querySelector('dd')!.textContent;
expect(avail('INK-S1')).toBe('50 kg');expect(avail('INK-S2')).toBe('20 kg');
// 刷新后换料记录仍可查看
app.unmount();render(<App/>);await waitFor(()=>expect(screen.getByText('批次总数')).toBeInTheDocument());
fireEvent.click(screen.getByRole('button',{name:'上机工单'}));
await waitFor(()=>expect(screen.getByText('INK-S2')).toBeInTheDocument());
expect(dd('换料前批次')).toBe('INK-S1');expect(dd('换料时间')).not.toBe('')})
test('successful switch clears stale conflict notice even before refresh settles',async()=>{
const state={batches:[
{id:1,code:'INK-S1',color:'品红',supplier:'供应商A',received_date:'2026-01-01',expiry_date:'2027-01-01',viscosity:20,quality_status:'passed',notes:'',active:true,received_weight:50,available_weight:30},
{id:2,code:'INK-S2',color:'青',supplier:'供应商B',received_date:'2026-01-01',expiry_date:'2027-01-01',viscosity:21,quality_status:'passed',notes:'',active:true,received_weight:40,available_weight:40},
{id:3,code:'INK-S3',color:'黄',supplier:'供应商C',received_date:'2026-01-01',expiry_date:'2027-01-01',viscosity:22,quality_status:'passed',notes:'',active:true,received_weight:10,available_weight:5}],
jobs:[{id:1,job_code:'JOB-S1',batch_id:1,batch_code:'INK-S1',batch_color:'品红',press:'海德堡',substrate:'白卡纸',planned_date:'2026-09-10',operator:'王工',description:'',planned_usage:20,actual_usage:null,settled_weight:null,status:'planned',cancelled_at:null,completed_at:null,created_at:'2026-09-10T08:00:00',previous_batch_code:null,switched_at:null}] as any[],
issues:[] as any[],stats:{batches:3,passed:3,expiring_soon:0,jobs:1,pending_issues:0}};
const ok=(d:any)=>({ok:true,json:()=>Promise.resolve(d)}),bad=(detail:string)=>({ok:false,status:409,json:()=>Promise.resolve({detail})});
let slow=false;const pending:Array<()=>void>=[];
vi.stubGlobal('fetch',vi.fn((u:string,opt?:RequestInit)=>{const m=opt?.method??'GET';
if(slow&&m==='GET')return new Promise(res=>pending.push(()=>res(ok(u.startsWith('/api/stats')?state.stats:u.startsWith('/api/batches')?state.batches:u.startsWith('/api/issues')?state.issues:state.jobs))));
if(u.startsWith('/api/batches'))return Promise.resolve(ok(state.batches));
if(u.startsWith('/api/issues'))return Promise.resolve(ok(state.issues));
if(u.startsWith('/api/stats'))return Promise.resolve(ok(state.stats));
if(u==='/api/jobs'&&m==='GET')return Promise.resolve(ok(state.jobs));
const sw=u.match(/^\/api\/jobs\/(\d+)\/switch$/);if(sw&&m==='PATCH'){const j=state.jobs.find(x=>x.id===Number(sw[1]))!;
const d=JSON.parse(String(opt?.body));const t=state.batches.find(x=>x.id===d.batch_id)!;
if(t.available_weight<j.planned_usage)return Promise.resolve(bad(`目标批次可用重量不足：批次剩余 ${t.available_weight} kg，计划用量 ${j.planned_usage} kg，工单与库存均未改动`));
const prev=state.batches.find(x=>x.id===j.batch_id)!;prev.available_weight+=j.planned_usage;t.available_weight-=j.planned_usage;
j.previous_batch_code=prev.code;j.batch_id=t.id;j.batch_code=t.code;j.batch_color=t.color;j.switched_at='2026-09-10T11:00:00';
return Promise.resolve(ok({id:j.id,batch_code:t.code,previous_batch_code:prev.code,switched_at:j.switched_at,issues_created:0,available_weight:t.available_weight}))}
return Promise.resolve(ok([]))}));
render(<App/>);await waitFor(()=>expect(screen.getByText('批次总数')).toBeInTheDocument());
fireEvent.click(screen.getByRole('button',{name:'上机工单'}));await waitFor(()=>expect(screen.getByText('JOB-S1')).toBeInTheDocument());
// 换料余额冲突：出现冲突提示
fireEvent.change(screen.getByLabelText(/换料批次/),{target:{value:'3'}});
fireEvent.click(screen.getByRole('button',{name:'确认换料'}));
await waitFor(()=>expect(screen.getByText(/目标批次可用重量不足/)).toBeInTheDocument());
// 改选充足批次换料成功：成功提示出现时旧冲突提示已被清除（刷新尚未完成也不并存）
slow=true;
fireEvent.change(screen.getByLabelText(/换料批次/),{target:{value:'2'}});
fireEvent.click(screen.getByRole('button',{name:'确认换料'}));
await waitFor(()=>expect(screen.getByText(/已换料至 INK-S2/)).toBeInTheDocument());
expect(screen.queryByText(/目标批次可用重量不足/)).not.toBeInTheDocument();
pending.splice(0).forEach(r=>r());
await waitFor(()=>expect(screen.queryByText('正在加载生产数据…')).not.toBeInTheDocument());
expect(screen.queryByText(/目标批次可用重量不足/)).not.toBeInTheDocument()})
test('switch time renders as local time of the offset-aware server instant',async()=>{
const iso='2026-09-10T02:00:00+00:00';
vi.stubGlobal('fetch',vi.fn((u:string)=>Promise.resolve({ok:true,json:()=>Promise.resolve(
u.includes('stats')?{batches:1,passed:1,expiring_soon:0,jobs:1,pending_issues:0}:
u.includes('batches')?[{id:1,code:'INK-TZ1',color:'品红',supplier:'测试供应商',received_date:'2026-01-01',expiry_date:'2027-01-01',viscosity:20,quality_status:'passed',notes:'',active:true,received_weight:50,available_weight:45}]:
u.includes('jobs')?[{id:1,job_code:'JOB-TZ1',batch_id:1,batch_code:'INK-TZ1',batch_color:'品红',press:'海德堡',substrate:'白卡纸',planned_date:'2026-09-10',operator:'王工',description:'',planned_usage:5,actual_usage:null,settled_weight:null,status:'planned',cancelled_at:null,completed_at:null,created_at:'2026-09-10T08:00:00',previous_batch_code:'INK-TZ0',switched_at:iso}]:[])})));
render(<App/>);await waitFor(()=>expect(screen.getByText('批次总数')).toBeInTheDocument());
fireEvent.click(screen.getByRole('button',{name:'上机工单'}));
await waitFor(()=>expect(screen.getByText('JOB-TZ1')).toBeInTheDocument());
// 服务端标准时区时刻按本地时间显示，不直接展示原始偏移前钟点
expect(dd('换料时间')).toBe(new Date(iso).toLocaleString('zh-CN'));
expect(dd('换料前批次')).toBe('INK-TZ0')})
test('decimal weights render at business precision without float tails',async()=>{vi.stubGlobal('fetch',vi.fn((u:string)=>Promise.resolve({ok:true,json:()=>Promise.resolve(
u.includes('stats')?{batches:1,passed:1,expiring_soon:0,jobs:1,pending_issues:0}:
u.includes('batches')?[{id:1,code:'INK-F1',color:'品红',supplier:'测试供应商',received_date:'2026-01-01',expiry_date:'2027-01-01',viscosity:20,quality_status:'passed',notes:'',active:true,received_weight:50.3,available_weight:50.199999999999996}]:
u.includes('jobs')?[{id:1,job_code:'JOB-F1',batch_id:1,batch_code:'INK-F1',batch_color:'品红',press:'海德堡',substrate:'白卡纸',planned_date:'2026-09-10',operator:'王工',description:'',planned_usage:0.1,status:'planned',cancelled_at:null,created_at:'2026-09-10T08:00:00'}]:[])})));
render(<App/>);await waitFor(()=>expect(screen.getByText('批次总数')).toBeInTheDocument());
fireEvent.click(screen.getByRole('button',{name:'油墨批次'}));
await waitFor(()=>expect(dd('可用重量')).toBe('50.2 kg'));expect(dd('入库重量')).toBe('50.3 kg');
fireEvent.click(screen.getByRole('button',{name:'上机工单'}));
await waitFor(()=>expect(dd('预占用量')).toBe('0.1 kg'))})
