/** Fixed Payment/Receipt adapter. No XML, amounts or endpoints come from UI. */
import {createHash} from 'node:crypto';
import {tallyExchange} from './tally.js';
import {readTallyReferences} from './tally-references.js';
import {requireOpenCompany,TallyUnavailable} from './tally-session.js';

const scalar=v=>String(v&&typeof v==='object'?v['#text']??'':v??'').trim();
const list=v=>v==null?[]:Array.isArray(v)?v:[v];
const xml=v=>String(v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&apos;'}[c]));
const hash=v=>createHash('sha256').update(JSON.stringify(v)).digest('hex');
const name=v=>scalar(v['@_NAME']??v.NAME);
const cents=v=>{const n=Number(scalar(v))*100;if(!Number.isSafeInteger(Math.round(n))||Math.abs(n-Math.round(n))>0.00001)throw Error('Invalid native money.');return Math.round(n);};
const entries=plan=>[{ledger:plan.data.bank_ledger,amount:-plan.data.amount_cents},{ledger:plan.data.counter_ledger,amount:plan.data.amount_cents}].sort((a,b)=>a.ledger.localeCompare(b.ledger));

function family(records, value, depth=0){
 if(depth>10)return null;
 const master=records.find(r=>name(r).toLowerCase()===value.toLowerCase());
 if(!master)return value.toLowerCase();
 const reserved=scalar(master['@_RESERVEDNAME']); if(reserved)return reserved.toLowerCase();
 const parent=scalar(master.PARENT);
 return !parent||parent.toLowerCase()===value.toLowerCase()?value.toLowerCase():family(records,parent,depth+1);
}

export async function readStatementVouchers(plan,{request=fetch}={}){
 const date=plan.data.date.replaceAll('-','');
 if(!/^\d{8}$/.test(date))throw Error('Invalid statement date.');
 const body=`<ENVELOPE><HEADER><VERSION>1</VERSION><TALLYREQUEST>Export</TALLYREQUEST><TYPE>Collection</TYPE><ID>MinkopsStatementVouchers</ID></HEADER><BODY><DESC><STATICVARIABLES><SVCURRENTCOMPANY>${xml(plan.company)}</SVCURRENTCOMPANY><SVFROMDATE TYPE="Date">${date}</SVFROMDATE><SVTODATE TYPE="Date">${date}</SVTODATE><SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT></STATICVARIABLES><TDL><TDLMESSAGE><COLLECTION NAME="MinkopsStatementVouchers"><TYPE>Voucher</TYPE><FETCH>MasterID,GUID,AlterID,Date,Reference,Narration,VoucherTypeName,AllLedgerEntries.*,LedgerEntries.*</FETCH><FILTER>MinkopsStatementDate</FILTER></COLLECTION><SYSTEM TYPE="Formulae" NAME="MinkopsStatementDate">($$YearOfDate:$Date * 10000 + $$MonthOfDate:$Date * 100 + $$DayOfDate:$Date) = ${date}</SYSTEM></TDLMESSAGE></TDL></DESC></BODY></ENVELOPE>`;
 const envelope=(await tallyExchange(plan.company,plan.port,body,request)).ENVELOPE;
 if(scalar(envelope?.HEADER?.STATUS)!=='1'||!Object.hasOwn(envelope?.BODY?.DATA??{},'COLLECTION'))throw Error('Statement vouchers could not be read.');
 const vouchers=list(envelope.BODY.DATA.COLLECTION?.VOUCHER);
 if(vouchers.length>10000)throw Error('Statement date exceeds 10,000 vouchers.');
 return vouchers.map(v=>{
  if(scalar(v.DATE)!==date)throw Error('Tally returned a voucher outside the approved statement date.');
  const nativeEntries=list(v['ALLLEDGERENTRIES.LIST']||v['LEDGERENTRIES.LIST']);
  const allocations=[];
  for(const entry of nativeEntries)for(const category of list(entry['CATEGORYALLOCATIONS.LIST']))for(const centre of list(category['COSTCENTREALLOCATIONS.LIST']))
   if(scalar(centre.NAME))allocations.push({category:scalar(category.CATEGORY),centre:scalar(centre.NAME),amount:cents(centre.AMOUNT),ledger:scalar(entry.LEDGERNAME)});
  const tag=scalar(v.NARRATION).match(/\[Minkops statement:([a-f0-9-]{36})\]/)?.[1]??null;
  return {guid:scalar(v.GUID),master_id:scalar(v.MASTERID),fingerprint:hash(v),date:scalar(v.DATE),voucher_type:scalar(v.VOUCHERTYPENAME),tag,
   entries:nativeEntries.map(e=>({ledger:scalar(e.LEDGERNAME),amount:cents(e.AMOUNT)})).sort((a,b)=>a.ledger.localeCompare(b.ledger)),
   allocation:allocations.length===0?null:allocations};
 });
}

function equal(current,plan){
 if(current.date!==plan.data.date.replaceAll('-','')||current.voucher_type!==plan.voucher_type.NAME||hash(current.entries)!==hash(entries(plan)))return false;
 if(!plan.allocation)return current.allocation==null;
 const expected=[{category:plan.allocation.category,centre:plan.allocation.centre,amount:plan.data.amount_cents,ledger:plan.data.counter_ledger}];
 return hash(current.allocation)===hash(expected);
}

export async function saveTallyStatement(plan,{request=fetch,beforeImport,
 requireCompany=requireOpenCompany,readReferences=readTallyReferences,readVouchers=readStatementVouchers}={}){
 const hold=(code)=>({outcome:'attention',hold:code});
 if(plan.format_version!==4||plan.operation!=='append'||!/^\d{4}-\d{2}-\d{2}$/.test(plan.data?.date)
  ||!/^[a-f0-9-]{36}$/.test(plan.remote_id)||!Number.isSafeInteger(plan.data.amount_cents)||!plan.data.amount_cents
  ||plan.references?.company_guid!==plan.company_guid||plan.data.bank_ledger===plan.data.counter_ledger)
  throw Error('Unsupported statement plan.');
 try{
  await requireCompany({company:plan.company,company_guid:plan.company_guid},{port:plan.port,request});
  const snapshot=await readReferences({company:plan.company,port:plan.port,
   categories:['company','ledgers','voucher_types',...(plan.allocation?['cost_centres','cost_categories']:[])]},{request});
  if(snapshot.collections.some(c=>c.status!=='ready'))return hold('destination_changed');
  const records=category=>snapshot.collections.find(c=>c.category===category)?.records??[];
  if(records('company').length!==1||scalar(records('company')[0].GUID)!==plan.company_guid)return hold('destination_changed');
  for(const ledger of [plan.data.bank_ledger,plan.data.counter_ledger]){
   const found=records('ledgers').filter(m=>name(m)===ledger),pinned=plan.references.ledgers[ledger];
   if(found.length!==1||!pinned||['GUID','PARENT','ALTERID'].some(k=>pinned[k]!=null&&scalar(found[0][k])!==scalar(pinned[k])))return hold('destination_changed');
  }
  const types=records('voucher_types'),type=types.filter(t=>name(t)===plan.voucher_type.NAME);
  if(type.length!==1||scalar(type[0].GUID)!==plan.voucher_type.GUID||scalar(type[0].ISACTIVE).toLowerCase()==='no'
    ||family(types,plan.voucher_type.NAME)!==(plan.data.amount_cents<0?'payment':'receipt'))return hold('destination_changed');
  if(plan.allocation)for(const [category,field,guid]of[['cost_centres','centre','centre_guid'],['cost_categories','category','category_guid']]){
   const found=records(category).filter(m=>name(m)===plan.allocation[field]);
   if(found.length!==1||scalar(found[0].GUID)!==plan.allocation[guid])return hold('destination_changed');
  }
  const before=await readVouchers(plan,{request}),tagged=before.filter(v=>v.tag===plan.remote_id);
  const receipt=current=>({company_guid:plan.company_guid,current:{...current,allocation:plan.allocation??null}});
  if(tagged.length)return tagged.length===1&&equal(tagged[0],plan)?{outcome:'duplicate',...receipt(tagged[0])}:hold('destination_changed');
  if(before.some(v=>!v.tag&&v.date===plan.data.date.replaceAll('-','')&&v.entries.some(e=>e.ledger===plan.data.bank_ledger&&e.amount===-plan.data.amount_cents)))return hold('possible_existing');
  if(typeof beforeImport!=='function')throw Error('A durable statement manifest is required.');
  await requireCompany({company:plan.company,company_guid:plan.company_guid},{port:plan.port,request});
  if(await beforeImport(plan)!==true)return hold('uncertain_import');
  const entry=(ledger,amount,allocation='')=>`<ALLLEDGERENTRIES.LIST><LEDGERNAME>${xml(ledger)}</LEDGERNAME><ISDEEMEDPOSITIVE>${amount<0?'Yes':'No'}</ISDEEMEDPOSITIVE><AMOUNT>${(amount/100).toFixed(2)}</AMOUNT>${allocation}</ALLLEDGERENTRIES.LIST>`;
  const allocation=plan.allocation?`<CATEGORYALLOCATIONS.LIST><CATEGORY>${xml(plan.allocation.category)}</CATEGORY><ISDEEMEDPOSITIVE>${plan.data.amount_cents<0?'Yes':'No'}</ISDEEMEDPOSITIVE><COSTCENTREALLOCATIONS.LIST><NAME>${xml(plan.allocation.centre)}</NAME><AMOUNT>${(plan.data.amount_cents/100).toFixed(2)}</AMOUNT></COSTCENTREALLOCATIONS.LIST></CATEGORYALLOCATIONS.LIST>`:'';
  const body=`<ENVELOPE><HEADER><TALLYREQUEST>Import Data</TALLYREQUEST></HEADER><BODY><IMPORTDATA><REQUESTDESC><REPORTNAME>Vouchers</REPORTNAME><STATICVARIABLES><SVCURRENTCOMPANY>${xml(plan.company)}</SVCURRENTCOMPANY></STATICVARIABLES></REQUESTDESC><REQUESTDATA><TALLYMESSAGE><VOUCHER REMOTEID="${plan.remote_id}" ACTION="Create" VCHTYPE="${xml(plan.voucher_type.NAME)}" OBJVIEW="Accounting Voucher View"><GUID>${plan.remote_id}</GUID><DATE>${plan.data.date.replaceAll('-','')}</DATE><VOUCHERTYPENAME>${xml(plan.voucher_type.NAME)}</VOUCHERTYPENAME><REFERENCE>${xml(plan.data.reference||plan.remote_id)}</REFERENCE><PERSISTEDVIEW>Accounting Voucher View</PERSISTEDVIEW><ISINVOICE>No</ISINVOICE><NARRATION>[Minkops statement:${plan.remote_id}] ${xml(String(plan.data.narration||'').slice(0,500))}</NARRATION>${entry(plan.data.bank_ledger,-plan.data.amount_cents)}${entry(plan.data.counter_ledger,plan.data.amount_cents,allocation)}</VOUCHER></TALLYMESSAGE></REQUESTDATA></IMPORTDATA></BODY></ENVELOPE>`;
  // Even a timeout is followed only by reads. The durable local fence prevents
  // a later explicit retry from importing the same uncertain intent again.
  try{
   const response=await tallyExchange(plan.company,plan.port,body,request),result=response.RESPONSE||response.ENVELOPE?.BODY?.DATA;
   if(!result||scalar(result.ERRORS)!=='0'||scalar(result.CREATED)!=='1'||Number(scalar(result.ALTERED)||0)!==0)return hold('uncertain_import');
  }catch{/* Reconcile once below; never resend. */}
  const after=(await readVouchers(plan,{request})).filter(v=>v.tag===plan.remote_id);
  return after.length===1&&equal(after[0],plan)?{outcome:'saved',...receipt(after[0])}:hold('uncertain_import');
 }catch(error){
  if(error instanceof TallyUnavailable)return hold(error.tallyState);
  throw error;
 }
}
