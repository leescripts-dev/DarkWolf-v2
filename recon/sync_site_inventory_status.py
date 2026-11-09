import csv,json,sys
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path
sys.path.insert(0,r'D:\DarkWolf\darkwolf-backend')
from app.db.mongodb import db
from app.entities.mapper import build_entity_id
ROOT=Path(r'D:\DarkWolf\recon')
scan=json.loads((ROOT/'full_site_scan_2026-10-17.json').read_text(encoding='utf-8'))
scrape=[json.loads(line) for line in (ROOT/'full_scrape_2026-10-17.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()]
browser=json.loads((ROOT/'browser_gate_recheck_2026-10-17.json').read_text(encoding='utf-8'))
scrape_by_host={row['host']:row for row in scrape}
gate_by_group={row['group']:row for row in browser}
now=datetime.now(timezone.utc)
def as_dt(value):
 if not value:return now
 return datetime.fromisoformat(value.replace('Z','+00:00'))
rows=[]
for old in scan['sites']:
 host=old['host']; group=old['group']; scrape_row=scrape_by_host.get(host)
 state=old['state']; availability='accessible' if state=='Accessible without CAPTCHA' else 'down'
 active=state=='Accessible without CAPTCHA'
 reason='Landing page responded without a detected CAPTCHA.' if active else (old.get('error') or state)
 captcha=state=='CAPTCHA / verification'; anti_bot=False
 if captcha: availability='captcha';active=False;reason='CAPTCHA/verification detected by landing-page probe.'
 elif state=='Blocked / access denied':
  title=(old.get('title') or '').casefold()
  if 'cloudflare' in title or old.get('http_status') in (401,403,407,429):
   availability='anti_bot';anti_bot=True;reason=f"Access denied (HTTP {old.get('http_status')}); protection suspected."
  else: availability='access_denied';reason=f"Access denied (HTTP {old.get('http_status')})."
  active=False
 elif state.startswith('Down'):
  availability='down';active=False;reason=old.get('error') or state
 checked=as_dt(old.get('scan_time_utc'))
 method=old.get('method','Unknown'); scrape_health=None; pages=None;records=None;first=None;scrape_errors=[];scraped_at=None;slug=None
 if scrape_row:
  slug=scrape_row['slug'];method=scrape_row['method'];pages=scrape_row['pages'];records=scrape_row['records_observed'];first=scrape_row['first_observations'];scrape_errors=scrape_row['errors'];scraped_at=as_dt(scrape_row['time']);checked=scraped_at
  err=' '.join(scrape_errors)
  if scrape_row['status']=='active': active=True;availability='accessible';reason='Registered scraper loaded the site.';scrape_health='scraped' if records else 'loaded_no_records'
  elif scrape_row['status']=='captcha': active=False;captcha=True;availability='captcha';reason=err or 'CAPTCHA/verification detected by registered browser collector.';scrape_health='blocked_by_captcha'
  elif scrape_row['status']=='anti_bot': active=False;anti_bot=True;availability='anti_bot';reason=err or 'Anti-bot challenge detected.';scrape_health='blocked_by_anti_bot'
  else:
   parsed_miss='no victim records matched' in err.casefold()
   local_browser_error='localhost' in err.casefold() or 'chromedriver' in err.casefold()
   prior_active=state=='Accessible without CAPTCHA'
   if prior_active and (parsed_miss or local_browser_error or 'page load exceeded' in err.casefold()):
    active=True;availability='accessible';scrape_health='extractor_or_browser_issue';reason='Landing page responded in the same-day probe; this scraper run did not complete extraction.'
   else:
    active=False;availability='down';scrape_health='scrape_failed';reason=err or 'Scraper did not load a listing page.'
 if group in gate_by_group:
  gate=gate_by_group[group]
  gate_text=' '.join(str(gate.get(k) or '') for k in ('gate','current_url','title','error')).casefold()
  if 'challenge' in str(gate.get('current_url','')).casefold() or 'cloudflare' in gate_text or 'blocked' in gate_text:
   active=False;anti_bot=True;captcha=False;availability='anti_bot';scrape_health='browser_gate';reason='Browser redirected to an anti-bot challenge.';checked=now
  elif any(token in gate_text for token in ('captcha',"i\'m not a robot",'human verification','recaptcha','hcaptcha')):
   active=False;captcha=True;anti_bot=False;availability='captcha';scrape_health='browser_gate';reason=gate.get('gate') or 'Browser CAPTCHA/verification detected.';checked=now
  elif gate.get('status')=='inaccessible':
   active=False;availability='down';scrape_health='browser_probe_failed';reason=gate.get('error') or 'Browser probe failed.';checked=now
 doc={'host':host,'group':group,'url':old['url'],'network':old.get('network'),'method':method,'classification_basis':old.get('classification_basis'),'status':'active' if active else 'inactive','active':active,'availability':availability,'captcha':captcha,'anti_bot':anti_bot,'http_status':old.get('http_status'),'title':old.get('title'),'last_checked_at':checked,'checked_by':'registered_scraper' if scrape_row else ('browser_gate_probe' if group in gate_by_group else 'full_inventory_probe'),'status_reason':reason,'scraper_slug':slug,'scrape_health':scrape_health,'last_scraped_at':scraped_at,'last_scrape_pages':pages,'last_scrape_records':records,'new_observations_saved':first,'last_scrape_errors':scrape_errors,'new_vs_original':old['new_vs_original'],'source_scan_date':'2026-10-17'}
 db.leak_site_inventory.update_one({'host':host},{'$set':doc},upsert=True)
 if slug:
  db.sources.update_one({'id':build_entity_id('source',slug)},{'$set':{'status':doc['status'],'active':active,'availability':availability,'captcha':captcha,'anti_bot':anti_bot,'last_checked_at':checked,'last_check_error':reason if not active else None}},upsert=False)
 rows.append(doc)
# INC is served by its configured API; the four stale workbook onion/mirror URLs stay independently inactive.
inc_id=build_entity_id('source','inc_ransom')
db.sources.update_one({'id':inc_id},{'$set':{'status':'active','active':True,'availability':'accessible','captcha':False,'anti_bot':False,'last_checked_at':now,'last_check_error':None}},upsert=False)
counts=Counter(row['availability'] for row in rows)
summary={'inventory_sites':len(rows),'active':sum(row['active'] for row in rows),'inactive':sum(not row['active'] for row in rows),'availability':dict(counts),'registered_scrapers_processed':len(scrape),'scraper_active':sum(row['status']=='active' for row in scrape),'scraper_inactive':sum(row['status']!='active' for row in scrape),'records_observed_by_registered_scrapers':sum(row['records_observed'] for row in scrape),'first_observations_saved':sum(row['first_observations'] for row in scrape),'explicit_captcha_sites':[{'group':row['group'],'host':row['host'],'reason':row['status_reason']} for row in rows if row['captcha']],'explicit_antibot_sites':[{'group':row['group'],'host':row['host'],'reason':row['status_reason']} for row in rows if row['anti_bot']],'http403_access_denied_sites':[{'group':row['group'],'host':row['host'],'http_status':row['http_status'],'title':row['title']} for row in rows if row['availability']=='anti_bot' and row['http_status'] in (401,403,407,429)],'updated_at':now.isoformat()}
(ROOT/'site_inventory_status_2026-10-17.json').write_text(json.dumps({'summary':summary,'sites':rows},ensure_ascii=False,indent=2,default=str),encoding='utf-8')
fields=['group','host','url','network','method','status','availability','captcha','anti_bot','http_status','status_reason','scraper_slug','scrape_health','last_scraped_at','last_scrape_pages','last_scrape_records','new_observations_saved','new_vs_original']
with (ROOT/'site_inventory_status_2026-10-17.csv').open('w',encoding='utf-8-sig',newline='') as f:
 w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows([{k:r.get(k) for k in fields} for r in rows])
print(json.dumps(summary,ensure_ascii=False,indent=2))
print('MongoDB leak_site_inventory count:',db.leak_site_inventory.count_documents({}))

