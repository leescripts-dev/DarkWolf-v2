import json, re, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent/'darkwolf-backend'))
from datetime import datetime, timezone
from urllib.parse import urlsplit
from app.collection.ransomware_sites import RansomwareSitesCollectionService
from app.db.mongodb import db
from app.entities.mapper import build_entity_id
from app.sites.html_leak_sites.collector import collect_site_pages
from app.sites.html_leak_sites.registry import HTML_LEAK_SITES
from app.sites.api_leak_sites.collector import collect_api_site_pages
from app.sites.api_leak_sites.registry import API_LEAK_SITES
from app.sites.javascript_leak_sites.collector import collect_javascript_site_pages
from app.sites.javascript_leak_sites.registry import JAVASCRIPT_LEAK_SITES

OUT=str(ROOT/'full_scrape_2026-10-17.jsonl')
GATES=re.compile(r'captcha|hcaptcha|recaptcha|turnstile|human verification',re.I)
ANTIBOT=re.compile(r'challenge|verification|access denied|blocked|cloudflare|proof of work|ddos.guard|rate limit',re.I)
def host(url): return (urlsplit(url).hostname or '').lower().rstrip('.')

jobs=[('HTML',HTML_LEAK_SITES,collect_site_pages,'html_leak_sites'),('API',API_LEAK_SITES,collect_api_site_pages,'api_leak_sites'),('JavaScript',JAVASCRIPT_LEAK_SITES,collect_javascript_site_pages,'javascript_leak_sites')]
summary={'started_at':datetime.now(timezone.utc).isoformat(),'registered_sites':sum(len(x[1]) for x in jobs),'processed':0,'active':0,'inactive':0,'captcha':0,'anti_bot':0,'pages':0,'records_observed':0,'first_observations':0,'events_generated':0,'errors':[]}
with open(OUT,'w',encoding='utf-8') as f:
 for method,sites,collector,source_name in jobs:
  for site in sites:
   try:
    result=RansomwareSitesCollectionService(sites=(site,),collector=collector,collection_source=source_name).collect(baseline=False)
    errors=[str(x.get('error','')) for x in result.get('errors',[])]
    all_errors=' '.join(errors)
    gate=bool(GATES.search(all_errors))
    antibot=bool(ANTIBOT.search(all_errors)) and not gate
    pages=result.get('pages_processed',0)
    active=pages>0 and not gate and not antibot
    state='active' if active else ('captcha' if gate else 'anti_bot' if antibot else 'inaccessible')
    records=result.get('organizations_found',0)
    doc={'time':datetime.now(timezone.utc).isoformat(),'method':method,'slug':site.slug,'group':site.name,'url':site.url,'host':host(site.url),'status':state,'pages':pages,'records_observed':records,'first_observations':result.get('first_observations',0),'content_changed':result.get('content_changed',0),'events_generated':result.get('events_generated',0),'errors':errors,'collection_run_id':result.get('collection_run_id')}
    db.leak_site_inventory.update_one({'host':doc['host']},{'$set':{'slug':site.slug,'group':site.name,'url':site.url,'method':method,'status':state,'active':active,'last_scrape_at':datetime.now(timezone.utc),'last_scrape_pages':pages,'last_scrape_records':records,'anti_bot':antibot,'captcha':gate,'last_scrape_errors':errors}},upsert=True)
    sid=build_entity_id('source',site.slug)
    db.sources.update_one({'id':sid},{'$set':{'status':state,'active':active,'last_checked_at':datetime.now(timezone.utc),'last_check_error':all_errors[:500] if all_errors else None}},upsert=False)
    summary['processed']+=1;summary['active']+=int(active);summary['inactive']+=int(not active);summary['captcha']+=int(gate);summary['anti_bot']+=int(antibot);summary['pages']+=pages;summary['records_observed']+=records;summary['first_observations']+=result.get('first_observations',0);summary['events_generated']+=result.get('events_generated',0)
   except Exception as exc:
    state='inaccessible';msg=f'{type(exc).__name__}: {str(exc)[:400]}'
    doc={'time':datetime.now(timezone.utc).isoformat(),'method':method,'slug':site.slug,'group':site.name,'url':site.url,'host':host(site.url),'status':state,'pages':0,'records_observed':0,'first_observations':0,'content_changed':0,'events_generated':0,'errors':[msg]}
    db.leak_site_inventory.update_one({'host':doc['host']},{'$set':{'slug':site.slug,'group':site.name,'url':site.url,'method':method,'status':state,'active':False,'last_scrape_at':datetime.now(timezone.utc),'last_scrape_pages':0,'last_scrape_records':0,'anti_bot':False,'captcha':False,'last_scrape_errors':[msg]}},upsert=True)
    sid=build_entity_id('source',site.slug);db.sources.update_one({'id':sid},{'$set':{'status':state,'active':False,'last_checked_at':datetime.now(timezone.utc),'last_check_error':msg}},upsert=False)
    summary['processed']+=1;summary['inactive']+=1;summary['errors'].append({'group':site.name,'error':msg})
   f.write(json.dumps(doc,ensure_ascii=False)+'\n');f.flush()
   print(json.dumps({'progress':f"{summary['processed']}/{summary['registered_sites']}",'group':site.name,'method':method,'status':doc['status'],'pages':doc['pages'],'records':doc['records_observed'],'new':doc['first_observations'],'error_count':len(doc['errors'])}),flush=True)
summary['finished_at']=datetime.now(timezone.utc).isoformat()
with open(OUT+'.summary.json','w',encoding='utf-8') as f:json.dump(summary,f,ensure_ascii=False,indent=2)
print('SUMMARY '+json.dumps(summary,ensure_ascii=False),flush=True)

